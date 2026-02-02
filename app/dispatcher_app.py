import os
import sys
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
import stripe
from supabase import create_client, Client

# Fix imports when running from any folder
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.utils import (
    get_supabase,
    check_profile_exists,
    create_profile,
    get_user_role,
    calculate_earnings,
)
from utils.translations import load_translations

# ────────────────────────────────────────────────
load_dotenv()

supabase: Client = get_supabase()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
app_domain = os.getenv("APP_DOMAIN", "http://localhost:8501")

# ────────────────────────────────────────────────
# Session state defaults
defaults = {
    "user": None,
    "role": None,
    "language": "en",
    "translations": load_translations("en"),
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

t = st.session_state.translations


# Add this near the top (after session init)
if "logout_triggered" not in st.session_state:
    st.session_state.logout_triggered = False

# The logout button
st.sidebar.button(
    t.get("logout", "Logout"),
    on_click=lambda: [
        supabase.auth.sign_out(),
        st.session_state.clear(),
        st.session_state.__setitem__("logout_triggered", True),  # flag
    ],
    key="logout_btn"
)

# Right after the button (still in the logged-in branch)
if st.session_state.logout_triggered:
    st.session_state.logout_triggered = False  # reset flag
    st.rerun()  # safe here — outside callback
# ────────────────────────────────────────────────
# Language auto-detection (fixed deprecation)
import locale

default_lang = "en"
try:
    loc = locale.getlocale()
    if loc and loc[0]:
        default_lang = loc[0].split("_")[0].lower()
except Exception:
    pass

if default_lang in ["en", "sw", "de", "it", "fr", "pt", "es", "nl", "ru", "uk", "tr"]:
    if st.session_state.language == "en":  # only on first load
        st.session_state.language = default_lang
        st.session_state.translations = load_translations(default_lang)
        t = st.session_state.translations

# Language selector – proper label
st.sidebar.title(t.get("select_language", "Language"))
languages = ["en", "sw", "de", "it", "fr", "pt", "es", "nl", "ru", "uk", "tr"]
lang = st.sidebar.selectbox(
    t.get("select_language", "Choose language"),
    languages,
    index=languages.index(st.session_state.language),
    label_visibility="visible",
)
if lang != st.session_state.language:
    st.session_state.language = lang
    st.session_state.translations = load_translations(lang)
    st.rerun()

t = st.session_state.translations

# ────────────────────────────────────────────────
# AUTHENTICATION
# ────────────────────────────────────────────────
if not st.session_state.user:
    tab1, tab2 = st.tabs([t.get("sign_in", "Sign In"), t.get("sign_up", "Sign Up")])

    with tab1:
        email = st.text_input(t.get("email", "Email"), key="si_email")
        pw = st.text_input(t.get("password", "Password"), type="password", key="si_pw")
        if st.button(t.get("sign_in", "Sign In"), type="primary"):
            with st.spinner("Signing in..."):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pw})
                    if res.user:
                        st.session_state.user = res.user
                        uid = res.user.id
                        if check_profile_exists(supabase, uid):
                            role = get_user_role(supabase, uid)
                            if role:
                                st.session_state.role = role
                                st.success(f"Welcome back, {role.title()}!")
                                st.rerun()
                            else:
                                st.error("Profile found but no role assigned.")
                        else:
                            st.error("No profile found – please sign up first.")
                except Exception as e:
                    st.error(f"Login failed: {str(e)}")

    with tab2:
        email = st.text_input(t.get("email", "Email"), key="su_email")
        pw = st.text_input(t.get("password", "Password"), type="password", key="su_pw")
        role_display = st.selectbox(
            t.get("select_role", "Select your role"),
            [t.get("role_driver", "Driver"), t.get("role_dispatch", "Dispatch"), t.get("role_admin", "Admin")],
            label_visibility="visible",
        )
        role_map = {
            t.get("role_driver", "Driver"): "driver",
            t.get("role_dispatch", "Dispatch"): "dispatch",
            t.get("role_admin", "Admin"): "admin",
        }
        if st.button(t.get("sign_up", "Sign Up"), type="primary"):
            with st.spinner("Creating account..."):
                try:
                    res = supabase.auth.sign_up({"email": email, "password": pw})
                    if res.user:
                        create_profile(supabase, res.user.id, email, role_map[role_display])
                        st.session_state.user = res.user
                        st.session_state.role = role_map[role_display]
                        st.success("Account created! Check your email to confirm.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Sign-up failed: {str(e)}")

else:
    # ────────────────────────────────────────────────
    # Role guard – prevents KeyError: None
    # ────────────────────────────────────────────────
    if not st.session_state.role:
        st.error("**Session issue:** Role is missing in your profile.")
        st.warning("Please log out and log in again. If it persists, delete your profile row and re-register.")
        if st.button("Force Logout & Clear Session"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
        st.stop()

    user_id = st.session_state.user.id
    role = st.session_state.role

    # Sidebar debug info
    with st.sidebar:
        st.caption(f"User: {st.session_state.user.email or '—'}")
        st.caption(f"Role: {role}")
        st.divider()

    st.sidebar.button(
        t.get("logout", "Logout"),
        on_click=lambda: [supabase.auth.sign_out(), st.session_state.clear(), st.rerun()],
    )

    # ────────────────────────────────────────────────
    # Navigation – safe
    # ────────────────────────────────────────────────
    nav = {
        t.get("dashboard", "Dashboard"): "dashboard",
        t.get("earnings", "Earnings"): "earnings",
    }
    if role in ["driver", "dispatch"]:
        nav[t.get("boosts", "Boosts")] = "boosts"
        nav[t.get("premium", "Premium")] = "premium"
    if role == "admin":
        nav[t.get("admin_panel", "Admin Panel")] = "admin_panel"

    choice = st.sidebar.selectbox(
        t.get("navigation_menu", "Go to"),
        list(nav.keys()),
        label_visibility="visible",
    )
    page = nav[choice]

    # ────────────────────────────────────────────────
    # Dashboard page
    # ────────────────────────────────────────────────
    if page == "dashboard":
        st.title(t.get("dashboard", "Dashboard"))

        if role == "dispatch":
            with st.expander(t.get("create_job", "Create New Job")):
                title = st.text_input(t.get("title", "Title"))
                col1, col2 = st.columns(2)
                with col1:
                    expense = st.number_input(t.get("expense", "Expense"), min_value=0.0, step=0.01)
                    revenue = st.number_input(t.get("revenue", "Revenue"), min_value=0.0, step=0.01)
                with col2:
                    lat = st.number_input(t.get("latitude", "Latitude"), format="%.6f")
                    lon = st.number_input(t.get("longitude", "Longitude"), format="%.6f")

                if st.button(t.get("create_job", "Create Job"), type="primary"):
                    if title.strip():
                        try:
                            supabase.table("jobs").insert({
                                "title": title.strip(),
                                "user_id": user_id,
                                "expense": expense,
                                "revenue": revenue,
                                "latitude": lat or None,
                                "longitude": lon or None,
                            }).execute()
                            st.success(t.get("job_created", "Job created successfully!"))
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to create job: {e}")
                    else:
                        st.warning("Title is required.")

        # Job list
        header_map = {
            "driver": t.get("job_list", "Available / My Jobs"),
            "dispatch": t.get("my_jobs", "My Jobs"),
            "admin": t.get("all_jobs", "All Jobs"),
        }
        st.subheader(header_map.get(role, "Jobs"))

        with st.spinner(t.get("loading_jobs", "Loading jobs...")):
            try:
                q = supabase.table("jobs").select("*")
                if role == "driver":
                    q = q.or_(f"status.eq.pending,driver_id.eq.{user_id}")
                elif role == "dispatch":
                    q = q.eq("user_id", user_id)
                jobs = q.order("created_at", desc=True).execute().data

                if not jobs:
                    st.info(t.get("no_jobs", "No jobs found yet."))
                else:
                    for job in jobs:
                        with st.container(border=True):
                            c1, c2 = st.columns([4, 1])
                            with c1:
                                st.markdown(f"**{job.get('title', 'No title')}**")
                                st.caption(f"Status: **{job.get('status', 'unknown').capitalize()}**")
                                if job.get("is_boosted", False):
                                    st.caption(f"Boosted until: {job.get('boost_expires_at', '—')}")
                            with c2:
                                if role == "driver" and job["status"] == "pending":
                                    if st.button(
                                        t.get("claim", "Claim"),
                                        key=f"claim_{job['id']}",
                                        use_container_width=True,
                                        type="primary"
                                    ):
                                        supabase.table("jobs").update({
                                            "driver_id": user_id,
                                            "status": "in_progress"
                                        }).eq("id", job["id"]).execute()
                                        st.success(t.get("claimed", "Job claimed!"))
                                        st.rerun()

                                if role == "driver" and job["status"] == "in_progress" and job["driver_id"] == user_id:
                                    if st.button(
                                        t.get("mark_completed", "Complete"),
                                        key=f"comp_{job['id']}",
                                        use_container_width=True,
                                        type="primary"
                                    ):
                                        supabase.table("jobs").update({
                                            "status": "completed",
                                            "completed_at": "now()"
                                        }).eq("id", job["id"]).execute()
                                        st.success(t.get("completed", "Job completed!"))
                                        st.rerun()

            except Exception as e:
                st.error(f"{t.get('error_loading', 'Error loading jobs')}: {str(e)}")

    # ────────────────────────────────────────────────
    # Stripe redirect handler – compatible with 1.29.0
    # ────────────────────────────────────────────────
    query_params = st.experimental_get_query_params()

    if "session_id" in query_params:
        try:
            session_id = query_params["session_id"][0]
            session = stripe.checkout.Session.retrieve(session_id)
            if session.payment_status == "paid":
                st.success(t.get("payment_success", "Payment successful! (Webhook should update DB shortly)"))
            else:
                st.warning(t.get("payment_not_completed", "Payment not completed."))
        except Exception as e:
            st.error(f"Payment verification failed: {str(e)}")

        # Clean URL
        st.experimental_set_query_params()
        st.rerun()

    elif "canceled" in query_params:
        st.warning(t.get("payment_cancelled", "Payment was cancelled."))
        st.experimental_set_query_params()
        st.rerun()