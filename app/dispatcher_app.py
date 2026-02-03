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

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PREMIUM_PRICE_ID = os.getenv("STRIPE_PREMIUM_PRICE_ID")
STRIPE_BOOST_PRICE_ID = os.getenv("STRIPE_BOOST_PRICE_ID")
APP_DOMAIN = os.getenv("APP_DOMAIN", "https://dispatchers.streamlit.app")
stripe.api_key = STRIPE_SECRET_KEY

# ────────────────────────────────────────────────
# SESSION DEFAULTS
# ────────────────────────────────────────────────
st.session_state.setdefault("user", None)
st.session_state.setdefault("role", None)
st.session_state.setdefault("language", "en")
st.session_state.setdefault("translations", load_translations("en"))

translations = st.session_state.translations

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
# SUBSCRIPTION CHECKS (SAFE)
# ────────────────────────────────────────────────
def check_subscription(user_id):
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    if not res.data or len(res.data) == 0:
        return False
    user = res.data[0]
    return user.get("subscription_active", False)

def check_boost(user_id):
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    if not res.data or len(res.data) == 0:
        return False
    user = res.data[0]
    return user.get("boost_active", False)

def create_checkout_session(email, price_id):
    customer = stripe.Customer.create(email=email)
    session = stripe.checkout.Session.create(
        customer=customer.id,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{APP_DOMAIN}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{APP_DOMAIN}?canceled=true",
    )
    supabase.table("profiles").update({"stripe_customer_id": customer.id}).eq("email", email).execute()
    return session

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

        # ⚡ Boost Drivers Sidebar (Dispatch/Admin only)
        if st.session_state.role in ["dispatch", "admin"]:
            st.subheader("⚡ Boost Drivers")
            boost_drivers = supabase.table("profiles").select("*").eq("role","driver").eq("boost_active", True).execute().data or []
            if boost_drivers:
                for d in boost_drivers:
                    st.markdown(f"⚡ {d['email']}")
            else:
                st.info("No active Boost drivers")

# ────────────────────────────────────────────────
# AUTH
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
# STRIPE CALLBACK
# ────────────────────────────────────────────────
params = get_query_params()
if "session_id" in params:
    session_id = params["session_id"]
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        sub_id = session.subscription
        customer_id = session.customer
        price_id = session["display_items"][0]["price"]["id"]

        if price_id == STRIPE_PREMIUM_PRICE_ID:
            supabase.table("profiles").update({
                "stripe_subscription_id": sub_id,
                "subscription_active": True
            }).eq("stripe_customer_id", customer_id).execute()
        elif price_id == STRIPE_BOOST_PRICE_ID:
            supabase.table("profiles").update({
                "boost_subscription_id": sub_id,
                "boost_active": True
            }).eq("stripe_customer_id", customer_id).execute()

        st.success(t("payment_success"))
    except Exception as e:
        st.error(str(e))
    clear_query_params()
    st.rerun()
elif "canceled" in params:
    st.warning(t("payment_cancelled"))
    clear_query_params()

# ────────────────────────────────────────────────
# DASHBOARD
# ────────────────────────────────────────────────
if st.session_state.user and st.session_state.role:
    user_id = st.session_state.user.id
    role = st.session_state.role

    # Subscription enforcement
    if role in ["driver", "dispatch"] and not check_subscription(user_id):
        st.warning(t("subscription_required"))
        col1, col2 = st.columns(2)
        with col1:
            if st.button(t("subscribe_premium")):
                session = create_checkout_session(st.session_state.user.email, STRIPE_PREMIUM_PRICE_ID)
                st.markdown(f"[{t('pay_now')}]({session.url})")
        with col2:
            if st.button(t("subscribe_boost")):
                session = create_checkout_session(st.session_state.user.email, STRIPE_BOOST_PRICE_ID)
                st.markdown(f"[{t('pay_now')}]({session.url})")
        st.stop()

    # Navigation
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

                # Prioritize Boost drivers & add ⚡ icon
                drivers.sort(key=lambda d: d.get("boost_active", False), reverse=True)
                options = ["None"] + [f"{'⚡ ' if d.get('boost_active') else ''}{d['email']}|{d['id']}" for d in drivers]
                selected = st.selectbox(t("assign_to_driver","Assign Driver"), options)
                assigned_to = None if selected == "None" else selected.split("|")[1]

                if st.button(t("create_job")):
                    create_job(supabase, title=title, created_by=user_id, expense=expense, revenue=revenue, assigned_to=assigned_to)
                    st.success(t("job_created"))
                    st.rerun()

        # Jobs Overview with Boost Highlights
        st.subheader("Jobs Overview")
        jobs = supabase.table("jobs").select("*").execute().data or []

        if jobs:
            for job in jobs:
                boost = False
                assigned_email = "-"
                if job.get("assigned_to"):
                    driver = supabase.table("profiles").select("*").eq("id", job["assigned_to"]).execute().data
                    driver = driver[0] if driver else None
                    if driver:
                        boost = driver.get("boost_active", False)
                        assigned_email = driver.get("email","-")
                # Highlight Boost jobs
                if boost:
                    st.markdown(f"<span style='color:orange;'>⚡ {job['title']} | {job.get('revenue',0)} | Assigned to {assigned_email}</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"- {job['title']} | {job.get('revenue',0)} | Assigned to {assigned_email}")
        else:
            st.info("No jobs available")

    # Earnings Page
    if page == "earnings" and role in ["driver", "dispatch"]:
        st.title(t("earnings"))
        total = calculate_earnings(supabase, user_id)
        st.metric(t("total_earnings"), f"${total:.2f}")

    # Admin Page
    if page == "admin" and role=="admin":
        st.title(t("admin_panel"))
        st.info(t("admin_info"))
