import os
import sys
import streamlit as st
from dotenv import load_dotenv
import stripe

# ────────────────────────────────────────────────
# PATH FIX
# ────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.utils import (
    get_supabase,
    check_profile_exists,
    create_profile,
    get_user_role,
    calculate_earnings,
    create_job
)
from utils.translations import load_translations

# ────────────────────────────────────────────────
# ENV
# ────────────────────────────────────────────────
load_dotenv()
supabase = get_supabase()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# ────────────────────────────────────────────────
# SESSION DEFAULTS
# ────────────────────────────────────────────────
st.session_state.setdefault("user", None)
st.session_state.setdefault("role", None)
st.session_state.setdefault("language", "en")
st.session_state.setdefault("translations", load_translations("en"))

t = st.session_state.translations

# ────────────────────────────────────────────────
# QUERY PARAM HELPERS
# ────────────────────────────────────────────────
def get_query_params():
    return st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()

def clear_query_params():
    if hasattr(st, "query_params"):
        st.query_params.clear()
    else:
        st.experimental_set_query_params({})

# ────────────────────────────────────────────────
# SIDEBAR (SINGLE, SAFE)
# ────────────────────────────────────────────────
with st.sidebar:
    st.title(t.get("select_language", "Language"))

    languages = ["en", "sw", "de", "it", "fr", "pt", "es", "nl", "ru", "uk", "tr"]
    lang = st.selectbox(
        t.get("select_language", "Choose language"),
        languages,
        index=languages.index(st.session_state.language)
    )

    if lang != st.session_state.language:
        st.session_state.language = lang
        st.session_state.translations = load_translations(lang)
        st.rerun()

    if st.session_state.user and st.session_state.role:
        st.divider()
        st.caption(f"{t.get('user_label','User')}: {st.session_state.user.email}")
        st.caption(
            f"{t.get('role_label','Role')}: "
            f"**{t.get(f'role_{st.session_state.role}', st.session_state.role.upper())}**"
        )

        st.divider()
        if st.button(t.get("logout", "Logout")):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()

# ────────────────────────────────────────────────
# AUTH (LOGIN / SIGNUP)
# ────────────────────────────────────────────────
if not st.session_state.user:
    tab1, tab2 = st.tabs([t.get("sign_in","Sign In"), t.get("sign_up","Sign Up")])

    with tab1:
        email = st.text_input(t.get("email","Email"))
        password = st.text_input(t.get("password","Password"), type="password")

        if st.button(t.get("sign_in","Sign In"), type="primary"):
            try:
                res = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
                if res.user:
                    st.session_state.user = res.user
                    role = get_user_role(supabase, res.user.id)
                    st.session_state.role = role
                    st.rerun()
            except Exception as e:
                st.error(str(e))

    with tab2:
        email = st.text_input(t.get("email","Email"), key="su_email")
        password = st.text_input(t.get("password","Password"), type="password", key="su_pw")

        role_display = st.selectbox(
            t.get("select_role","Select role"),
            [t.get("role_driver","Driver"),
             t.get("role_dispatch","Dispatch"),
             t.get("role_admin","Admin")]
        )

        role_map = {
            t.get("role_driver","Driver"): "driver",
            t.get("role_dispatch","Dispatch"): "dispatch",
            t.get("role_admin","Admin"): "admin"
        }

        if st.button(t.get("sign_up","Sign Up"), type="primary"):
            try:
                res = supabase.auth.sign_up({
                    "email": email,
                    "password": password
                })
                if res.user:
                    role = role_map[role_display]
                    create_profile(supabase, res.user.id, email, role)
                    st.session_state.user = res.user
                    st.session_state.role = role
                    st.rerun()
            except Exception as e:
                st.error(str(e))

# ────────────────────────────────────────────────
# DASHBOARD (LOGGED IN)
# ────────────────────────────────────────────────
if st.session_state.user and st.session_state.role:
    role = st.session_state.role
    user_id = st.session_state.user.id

    nav = {t.get("dashboard","Dashboard"): "dashboard"}
    if role in ["driver","dispatch"]:
        nav[t.get("earnings","Earnings")] = "earnings"
    if role == "admin":
        nav[t.get("admin_panel","Admin Panel")] = "admin"

    page = st.selectbox(t.get("navigation_menu","Go to"), list(nav.keys()))
    page = nav[page]

    if page == "dashboard":
        st.title(t.get("dashboard","Dashboard"))

        if role in ["dispatch","admin"]:
            with st.expander(t.get("create_job","Create Job")):
                title = st.text_input(t.get("title","Title"))
                expense = st.number_input(t.get("expense","Expense"), min_value=0.0)
                revenue = st.number_input(t.get("revenue","Revenue"), min_value=0.0)

                drivers = supabase.table("profiles").select("*").eq("role","driver").execute().data or []
                options = ["None"] + [f"{d['email']}|{d['id']}" for d in drivers]
                selected = st.selectbox(t.get("assign_to_driver","Assign Driver"), options)

                assigned_to = None if selected == "None" else selected.split("|")[1]

                if st.button(t.get("create_job","Create Job")):
                    create_job(
                        supabase,
                        title=title,
                        created_by=user_id,
                        expense=expense,
                        revenue=revenue,
                        assigned_to=assigned_to
                    )
                    st.success(t.get("job_created","Job created"))
                    st.rerun()

        st.subheader(t.get("your_jobs","Your Jobs"))
        if role == "driver":
            jobs = supabase.table("jobs").select("*").eq("assigned_to", user_id).execute().data
        else:
            jobs = supabase.table("jobs").select("*").execute().data

        if jobs:
            for job in jobs:
                st.markdown(f"- **{job['title']}** | {job.get('revenue',0)}")
        else:
            st.info(t.get("no_jobs","No jobs"))

    if page == "earnings":
        st.title(t.get("earnings","Earnings"))
        total = calculate_earnings(supabase, user_id)
        st.metric(t.get("total_earnings","Total"), f"${total:.2f}")

    if page == "admin":
        st.title(t.get("admin_panel","Admin Panel"))

# ────────────────────────────────────────────────
# STRIPE CALLBACK
# ────────────────────────────────────────────────
params = get_query_params()

if "session_id" in params:
    try:
        session_id = params["session_id"]
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            st.success(t.get("payment_success","Payment successful"))
    except Exception as e:
        st.error(str(e))
    clear_query_params()
    st.rerun()

elif "canceled" in params:
    st.warning(t.get("payment_cancelled","Payment cancelled"))
    clear_query_params()
