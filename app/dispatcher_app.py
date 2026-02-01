import os
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client
import stripe
from utils.utils import get_supabase, check_profile_exists, create_profile, get_user_role, calculate_earnings
from utils.translations import load_translations

load_dotenv()

supabase = get_supabase()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
app_domain = os.getenv("APP_DOMAIN")

# Session state initialization
if "user" not in st.session_state:
    st.session_state.user = None
if "role" not in st.session_state:
    st.session_state.role = None
if "language" not in st.session_state:
    st.session_state.language = "en"
if "translations" not in st.session_state:
    st.session_state.translations = load_translations(st.session_state.language)

# Language selector (auto-detect attempt via locale, but fallback to selector)
import locale
try:
    default_lang, _ = locale.getdefaultlocale()
    default_lang = default_lang.split("_")[0]
except:
    default_lang = "en"
if default_lang in ["en", "sw", "de", "it", "fr", "pt", "es", "nl", "ru", "uk", "tr"]:
    st.session_state.language = default_lang

st.sidebar.title("Language")
lang = st.sidebar.selectbox(st.session_state.translations.get("select_language", "Select Language"), 
                            ["en", "sw", "de", "it", "fr", "pt", "es", "nl", "ru", "uk", "tr"],
                            index=["en", "sw", "de", "it", "fr", "pt", "es", "nl", "ru", "uk", "tr"].index(st.session_state.language))
if lang != st.session_state.language:
    st.session_state.language = lang
    st.session_state.translations = load_translations(lang)
    st.experimental_rerun()

t = st.session_state.translations

# Auth logic
if not st.session_state.user:
    tab1, tab2 = st.tabs([t["sign_in"], t["sign_up"]])
    
    with tab1:
        email = st.text_input(t["email"])
        password = st.text_input(t["password"], type="password")
        if st.button(t["sign_in"]):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = res.user
                if check_profile_exists(supabase, res.user.id):
                    st.session_state.role = get_user_role(supabase, res.user.id)
                    st.success(t["success"])
                    st.experimental_rerun()
                else:
                    st.error("Profile not found. Please sign up.")
            except Exception as e:
                st.error(t["failure"])
    
    with tab2:
        email = st.text_input(t["email"])
        password = st.text_input(t["password"], type="password")
        role = st.selectbox("Role", [t["role_driver"], t["role_dispatch"], t["role_admin"]])
        role_map = {t["role_driver"]: "driver", t["role_dispatch"]: "dispatch", t["role_admin"]: "admin"}
        if st.button(t["sign_up"]):
            try:
                res = supabase.auth.sign_up({"email": email, "password": password})
                user_id = res.user.id
                create_profile(supabase, user_id, email, role_map[role])
                st.session_state.user = res.user
                st.session_state.role = role_map[role]
                st.success(t["success"])
                st.experimental_rerun()
            except Exception as e:
                st.error(t["failure"])
else:
    st.sidebar.button(t["logout"], on_click=lambda: supabase.auth.sign_out() or st.session_state.clear() or st.experimental_rerun())

    user_id = st.session_state.user.id
    role = st.session_state.role

    # Sidebar navigation
    pages = {
        t["dashboard"]: "dashboard",
        t["earnings"]: "earnings",
    }
    if role in ["driver", "dispatch"]:
        pages[t["boosts"]] = "boosts"
        pages[t["premium"]] = "premium"
    if role == "admin":
        pages[t["admin_panel"]] = "admin_panel"
    
    page = st.sidebar.selectbox("Page", list(pages.keys()))
    selected_page = pages[page]

    if selected_page == "dashboard":
        st.title(t["dashboard"])
        
        if role == "dispatch":
            with st.expander(t["create_job"]):
                title = st.text_input(t["title"])
                expense = st.number_input(t["expense"])
                revenue = st.number_input(t["revenue"])
                lat = st.number_input(t["latitude"])
                lon = st.number_input(t["longitude"])
                if st.button(t["create_job"]):
                    supabase.table("jobs").insert({
                        "title": title, "user_id": user_id, "expense": expense, "revenue": revenue,
                        "latitude": lat, "longitude": lon
                    }).execute()
                    st.success(t["success"])
        
        # Job list based on role
        if role == "driver":
            jobs = supabase.table("jobs").select("*").or_(f"status.eq.pending,driver_id.eq.{user_id}").execute().data
            st.subheader(t["job_list"])
        elif role == "dispatch":
            jobs = supabase.table("jobs").select("*").eq("user_id", user_id).execute().data
            st.subheader(t["my_jobs"])
        elif role == "admin":
            jobs = supabase.table("jobs").select("*").execute().data
            st.subheader(t["all_jobs"])
        
        for job in jobs:
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"{t['title']}: {job['title']}")
                st.write(f"{t['status']}: {job['status']}")
                if job['is_boosted']:
                    st.write(f"{t['is_boosted']}: Yes, {t['boost_expires']}: {job['boost_expires_at']}")
            with col2:
                if role == "driver" and job["status"] == "pending":
                    if st.button(t["claim"], key=f"claim_{job['id']}"):
                        supabase.table("jobs").update({"driver_id": user_id, "status": "in_progress"}).eq("id", job["id"]).execute()
                        st.experimental_rerun()
                elif role == "driver" and job["status"] == "in_progress" and job["driver_id"] == user_id:
                    if st.button(t["mark_completed"], key=f"complete_{job['id']}"):
                        supabase.table("jobs").update({"status": "completed", "completed_at": "now()"}).eq("id", job["id"]).execute()
                        st.experimental_rerun()
                elif role == "dispatch" and job["user_id"] == user_id:
                    if st.button(t["update_job"], key=f"update_{job['id']}"):
                        # Simple update example, expand as needed
                        pass

    elif selected_page == "earnings":
        st.title(t["earnings"])
        if role == "driver":
            completed_jobs = supabase.table("jobs").select("*").eq("driver_id", user_id).eq("status", "completed").execute().data
            total = calculate_earnings(supabase, user_id)
            st.subheader(t["total_earnings"] + f": ${total}")
            st.subheader(t["completed_jobs"])
            for job in completed_jobs:
                st.write(f"{t['title']}: {job['title']}, Net: ${job['revenue'] - job['expense']}")
        else:
            st.write("Earnings available for drivers only.")

    elif selected_page == "boosts":
        st.title(t["boosts"])
        if role in ["driver", "dispatch"]:
            jobs = supabase.table("jobs").select("id, title").eq("user_id", user_id if role == "dispatch" else "driver_id", user_id).execute().data
            job_id = st.selectbox("Select Job to Boost", [j["title"] for j in jobs], format_func=lambda x: x)
            job_id = next(j["id"] for j in jobs if j["title"] == job_id)
            if st.button(t["boost_job"]):
                session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=[{'price': os.getenv("STRIPE_BOOST_PRICE_ID"), 'quantity': 1}],
                    mode='payment',
                    success_url=f"{app_domain}/?session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{app_domain}/?canceled=true",
                    metadata={'user_id': user_id, 'job_id': job_id}
                )
                st.markdown(f'<meta http-equiv="refresh" content="0;URL={session.url}">', unsafe_allow_html=True)
        else:
            st.write("Boosts for drivers/dispatch only.")

    elif selected_page == "premium":
        st.title(t["premium"])
        profile = supabase.table("profiles").select("is_premium").eq("id", user_id).single().execute().data
        if profile["is_premium"]:
            st.write("You are already Premium.")
        else:
            if st.button(t["subscribe_premium"]):
                session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=[{'price': os.getenv("STRIPE_PREMIUM_PRICE_ID"), 'quantity': 1}],
                    mode='subscription',
                    success_url=f"{app_domain}/?session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{app_domain}/?canceled=true",
                    metadata={'user_id': user_id}
                )
                st.markdown(f'<meta http-equiv="refresh" content="0;URL={session.url}">', unsafe_allow_html=True)

    elif selected_page == "admin_panel":
        st.title(t["admin_panel"])
        if role == "admin":
            jobs = supabase.table("jobs").select("status", count="exact").execute()
            counts = {"pending": 0, "in_progress": 0, "completed": 0}
            for job in jobs.data:
                counts[job["status"]] += 1
            st.subheader(t["job_status_counts"])
            st.write(counts)
            if st.button(t["clear_all_jobs"]):
                supabase.table("jobs").delete().execute()
                st.success(t["success"])
        else:
            st.error("Access denied.")

# Handle Stripe redirect
query_params = st.experimental_get_query_params()
if "session_id" in query_params:
    try:
        session = stripe.checkout.Session.retrieve(query_params["session_id"][0])
        if session.payment_status == "paid":
            # Webhook handles DB update, but show message
            st.success(t["payment_success"])
        else:
            st.error(t["payment_failure"])
    except:
        st.error(t["failure"])
elif "canceled" in query_params:
    st.error(t["payment_failure"])
