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

translations = st.session_state.translations

# Helper for safe translation
def t(key: str):
    lang = st.session_state.language
    return translations.get(lang, {}).get(key) or translations.get("en", {}).get(key) or key

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
# SIDEBAR
# ────────────────────────────────────────────────
with st.sidebar:
    st.title(t("select_language"))

    languages = ["en", "sw", "de", "it", "fr", "pt", "es", "nl", "ru", "uk", "tr"]
    lang = st.selectbox(
        t("select_language"),
        languages,
        index=languages.index(st.session_state.language)
    )

    if lang != st.session_state.language:
        st.session_state.language = lang
        st.session_state.translations = load_translations(lang)
        st.rerun()

    if st.session_state.user and st.session_state.role:
        st.divider()
        st.caption(f"{t('user_label')}: {st.session_state.user.email}")
        st.caption(f"{t('role_label')}: **{t(f'role_{st.session_state.role}') or st.session_state.role.upper()}**")
        st.divider()
        if st.button(t("logout")):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()

# ────────────────────────────────────────────────
# AUTH (LOGIN / SIGNUP)
# ────────────────────────────────────────────────
if not st.session_state.user:
    tab1, tab2 = st.tabs([t("sign_in"), t("sign_up")])

    with tab1:
        email = st.text_input(t("email"))
        password = st.text_input(t("password"), type="password")
        if st.button(t("sign_in"), type="primary"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                if res.user:
                    st.session_state.user = res.user
                    st.session_state.role = get_user_role(supabase, res.user.id)
                    st.rerun()
            except Exception as e:
                st.error(str(e))

    with tab2:
        email = st.text_input(t("email"), key="su_email")
        password = st.text_input(t("password"), type="password", key="su_pw")
        role_display = st.selectbox(
            t("select_role"),
            [t("role_driver"), t("role_dispatch"), t("role_admin")]
        )
        role_map = {t("role_driver"): "driver", t("role_dispatch"): "dispatch", t("role_admin"): "admin"}
        if st.button(t("sign_up"), type="primary"):
            try:
                res = supabase.auth.sign_up({"email": email, "password": password})
                if res.user:
                    role = role_map[role_display]
                    create_profile(supabase, res.user.id, email, role)
                    st.session_state.user = res.user
                    st.session_state.role = role
                    st.rerun()
            except Exception as e:
                st.error(str(e))

# ────────────────────────────────────────────────
# DASHBOARD
# ────────────────────────────────────────────────
if st.session_state.user and st.session_state.role:
    user_id = st.session_state.user.id
    role = st.session_state.role

    nav = {t("dashboard"): "dashboard"}
    if role in ["driver", "dispatch"]:
        nav[t("earnings")] = "earnings"
    if role == "admin":
        nav[t("admin_panel")] = "admin"

    page = st.selectbox(t("navigation_menu"), list(nav.keys()))
    page = nav[page]

    # Dashboard Page
    if page == "dashboard":
        st.title(t("dashboard"))

        if role in ["dispatch", "admin"]:
            with st.expander(t("create_job")):
                title = st.text_input(t("title"))
                expense = st.number_input(t("expense"), min_value=0.0)
                revenue = st.number_input(t("revenue"), min_value=0.0)

                drivers = supabase.table("profiles").select("*").eq("role","driver").execute().data or []
                options = ["None"] + [f"{d['email']}|{d['id']}" for d in drivers]
                selected = st.selectbox(t("assign_to_driver","Assign Driver"), options)
                assigned_to = None if selected == "None" else selected.split("|")[1]

                if st.button(t("create_job")):
                    create_job(supabase, title=title, created_by=user_id, expense=expense, revenue=revenue, assigned_to=assigned_to)
                    st.success(t("job_created"))
                    st.rerun()

        st.subheader(t("your_jobs"))
        jobs = supabase.table("jobs").select("*").eq("assigned_to" if role=="driver" else "id", user_id if role=="driver" else None).execute().data or []
        if jobs:
            for job in jobs:
                st.markdown(f"- **{job['title']}** | {job.get('revenue',0)}")
        else:
            st.info(t("no_jobs"))

    # Earnings Page
    if page == "earnings" and role in ["driver", "dispatch"]:
        st.title(t("earnings"))
        total = calculate_earnings(supabase, user_id)
        st.metric(t("total_earnings"), f"${total:.2f}")

    # Admin Page
    if page == "admin" and role=="admin":
        st.title(t("admin_panel"))
        st.info(t("admin_info"))

# ────────────────────────────────────────────────
# STRIPE CALLBACK
# ────────────────────────────────────────────────
params = get_query_params()
if "session_id" in params:
    try:
        session_id = params["session_id"]
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            st.success(t("payment_success"))
        else:
            st.error(t("payment_failure"))
    except Exception as e:
        st.error(str(e))
    clear_query_params()
    st.rerun()
elif "canceled" in params:
    st.warning(t("payment_cancelled"))
    clear_query_params()
