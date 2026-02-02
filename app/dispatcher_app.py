# app/dispatcher_app.py
import os
import sys
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
import stripe

# Fix imports
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
# ENV & CLIENTS
# ────────────────────────────────────────────────
load_dotenv()
supabase = get_supabase()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
app_domain = os.getenv("APP_DOMAIN", "http://localhost:8501")

# ────────────────────────────────────────────────
# SESSION DEFAULTS
# ────────────────────────────────────────────────
st.session_state.setdefault("user", None)
st.session_state.setdefault("role", None)
st.session_state.setdefault("language", "en")
st.session_state.setdefault("translations", load_translations("en"))

t = st.session_state.translations

# ────────────────────────────────────────────────
# LANGUAGE SELECTOR
# ────────────────────────────────────────────────
st.sidebar.title(t.get("select_language", "Language"))
languages = ["en", "sw", "de", "it", "fr", "pt", "es", "nl", "ru", "uk", "tr"]

lang = st.sidebar.selectbox(
    t.get("select_language", "Choose language"),
    languages,
    index=languages.index(st.session_state.language),
)

if lang != st.session_state.language:
    st.session_state.language = lang
    st.session_state.translations = load_translations(lang)
    st.rerun()

t = st.session_state.translations

# ────────────────────────────────────────────────
# STREAMLIT VERSION-SAFE QUERY PARAM HELPERS
# ────────────────────────────────────────────────
def get_query_params():
    if hasattr(st, "query_params"):
        return st.query_params
    return st.experimental_get_query_params()


def clear_query_params():
    if hasattr(st, "query_params"):
        st.query_params.clear()
    else:
        st.experimental_set_query_params()

# ────────────────────────────────────────────────
# AUTH (LOGIN / SIGNUP)
# ────────────────────────────────────────────────
if not st.session_state.user:
    tab1, tab2 = st.tabs([t.get("sign_in", "Sign In"), t.get("sign_up", "Sign Up")])

    # ───── LOGIN ─────
    with tab1:
        email = st.text_input(t.get("email", "Email"), key="login_email")
        pw = st.text_input(t.get("password", "Password"), type="password", key="login_pw")

        if st.button(t.get("sign_in", "Sign In"), type="primary"):
            if not email or not pw:
                st.warning(t.get("email_password_required", "Email and password required."))
            else:
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pw})
                    if res.user:
                        st.session_state.user = res.user
                        uid = res.user.id
                        if check_profile_exists(supabase, uid):
                            role = get_user_role(supabase, uid)
                            if role:
                                st.session_state.role = role
                                st.success(t.get("login_success", "Login successful!"))
                                st.rerun()
                            else:
                                st.error(t.get("user_role_missing", "User role missing."))
                        else:
                            st.error(t.get("profile_not_found", "Profile not found. Please sign up."))
                except Exception as e:
                    st.error(f"{t.get('login_failed', 'Login failed')}: {e}")

    # ───── SIGN UP ─────
    with tab2:
        email = st.text_input(t.get("email", "Email"), key="su_email")
        pw = st.text_input(t.get("password", "Password"), type="password", key="su_pw")
        role_display = st.selectbox(
            t.get("select_role", "Select your role"),
            [t.get("role_driver", "Driver"),
             t.get("role_dispatch", "Dispatch"),
             t.get("role_admin", "Admin")],
            key="role_select"
        )

        role_map = {
            t.get("role_driver", "Driver"): "driver",
            t.get("role_dispatch", "Dispatch"): "dispatch",
            t.get("role_admin", "Admin"): "admin",
        }

        if st.button(t.get("sign_up", "Sign Up"), type="primary"):
            if not email or not pw:
                st.warning(t.get("email_password_required", "Email and password required."))
            else:
                try:
                    res = supabase.auth.sign_up({"email": email, "password": pw})
                    if res.user:
                        role = role_map.get(role_display)
                        create_profile(supabase, res.user.id, email, role)
                        st.session_state.user = res.user
                        st.session_state.role = role
                        st.success(t.get("signup_success", "Account created! Check your email to confirm."))
                        st.rerun()
                except Exception as e:
                    st.error(f"{t.get('signup_failed', 'Signup failed')}: {e}")

# ────────────────────────────────────────────────
# LOGGED-IN DASHBOARD
# ────────────────────────────────────────────────
if st.session_state.user and st.session_state.role:
    user_id = st.session_state.user.id
    role = st.session_state.role

    # Sidebar info
    with st.sidebar:
        st.caption(f"{t.get('user_label', 'User')}: {st.session_state.user.email}")
        st.caption(f"{t.get('role_label', 'Role')}: **{t.get(f'role_{role}', role.upper())}**")
        st.divider()
        if st.button(t.get("logout", "Logout")):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()

    # Role-based navigation
    nav = {t.get("dashboard", "Dashboard"): "dashboard"}
    if role in ["driver", "dispatch"]:
        nav[t.get("earnings", "Earnings")] = "earnings"
        nav[t.get("boosts", "Boosts")] = "boosts"
        nav[t.get("premium", "Premium")] = "premium"
    if role == "admin":
        nav[t.get("admin_panel", "Admin Panel")] = "admin_panel"

    choice = st.sidebar.selectbox(
        t.get("navigation_menu", "Go to"),
        list(nav.keys()),
        label_visibility="visible",
        key="nav_selector"
    )
    page = nav[choice]

    # ───────── DASHBOARD ─────────
    if page == "dashboard":
        st.title(t.get("dashboard", "Dashboard"))
        st.markdown(f"**{t.get(f'welcome_{role}', f'Welcome, {role.title()}!')}**")

        # Job creation only for Dispatcher & Admin
        if role in ["dispatch", "admin"]:
            with st.expander(t.get("create_job", "Create Job")):
                title = st.text_input(t.get("title", "Title"), key="create_title")
                col1, col2 = st.columns(2)

                with col1:
                    expense = st.number_input(t.get("expense", "Expense"), min_value=0.0, step=0.01, key="expense")
                    revenue = st.number_input(t.get("revenue", "Revenue"), min_value=0.0, step=0.01, key="revenue")
                with col2:
                    lat = st.number_input(t.get("latitude", "Latitude"), format="%.6f", key="lat")
                    lon = st.number_input(t.get("longitude", "Longitude"), format="%.6f", key="lon")

                if st.button(t.get("create_job", "Create Job"), type="primary", key="create_btn"):
                    if title.strip():
                        try:
                            supabase.table("jobs").insert({
                                "title": title.strip(),
                                "user_id": user_id,
                                "expense": expense,
                                "revenue": revenue,
                                "latitude": lat if lat != 0.0 else None,
                                "longitude": lon if lon != 0.0 else None,
                                "created_at": datetime.utcnow().isoformat()
                            }).execute()
                            st.success(t.get("job_created", "Job created!"))
                            st.experimental_rerun()
                        except Exception as e:
                            st.error(f"{t.get('job_creation_failed', 'Failed to create job')}: {e}")
                    else:
                        st.warning(t.get("title_required", "Title is required."))

        # List user jobs
        st.subheader(t.get("your_jobs", "Your Jobs"))
        try:
            if role == "driver":
                jobs_resp = supabase.table("jobs").select("*").eq("user_id", user_id).execute()
            else:
                jobs_resp = supabase.table("jobs").select("*").execute()

            jobs = jobs_resp.data or []
            if jobs:
                for job in jobs:
                    st.markdown(
                        f"- **{job.get('title')}** | {t.get('expense', 'Expense')}: {job.get('expense')} | "
                        f"{t.get('revenue', 'Revenue')}: {job.get('revenue')}"
                    )
            else:
                st.info(t.get("no_jobs", "No jobs yet."))
        except Exception as e:
            st.error(f"{t.get('job_fetch_failed', 'Failed to fetch jobs')}: {e}")

    # ───────── EARNINGS ─────────
    if page == "earnings" and role in ["driver", "dispatch"]:
        st.title(t.get("earnings", "Earnings"))
        try:
            earnings = calculate_earnings(supabase, user_id)
            st.metric(t.get("total_earnings", "Total Earnings"), f"${earnings:.2f}")
        except Exception as e:
            st.error(f"{t.get('earnings_failed', 'Failed to calculate earnings')}: {e}")

    # ───────── PREMIUM / BOOSTS ─────────
    if page == "premium":
        st.title(t.get("premium", "Premium"))
        st.info(t.get("premium_info", "Premium features coming soon."))

    if page == "boosts":
        st.title(t.get("boosts", "Boosts"))
        st.info(t.get("boosts_info", "Boost boosts coming soon."))

    # ───────── ADMIN PANEL ─────────
    if page == "admin_panel" and role == "admin":
        st.title(t.get("admin_panel", "Admin Panel"))
        st.info(t.get("admin_info", "Admin controls will be added here."))

# ────────────────────────────────────────────────
# STRIPE CALLBACK HANDLER
# ────────────────────────────────────────────────
params = get_query_params()

if "session_id" in params:
    try:
        session_id = params["session_id"][0] if isinstance(params["session_id"], list) else params["session_id"]
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            st.success(t.get("payment_success", "Payment successful!"))
        else:
            st.error(t.get("payment_failure", "Payment failed."))
    except Exception as e:
        st.error(f"{t.get('stripe_error', 'Stripe error')}: {e}")
    clear_query_params()
    st.rerun()
elif "canceled" in params:
    st.warning(t.get("payment_cancelled", "Payment cancelled."))
    clear_query_params()
