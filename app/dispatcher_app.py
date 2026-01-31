import streamlit as st
import stripe
import os
import sys
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

# --- TRIPLE-LAYER MODULE DISCOVERY ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.abspath(os.path.join(current_dir, ".."))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

try:
    from utils.translations import LANGUAGES, translate, load_translations
except (ImportError, ModuleNotFoundError):
    try:
        from translations import LANGUAGES, translate, load_translations
    except ImportError:
        st.error("CRITICAL: Could not find 'utils/translations.py'. Check GitHub folder structure.")
        st.stop()

load_dotenv()

# --- INITIALIZATION ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY")
# Using the exact variable name from your working version
PRICE_ID = os.getenv("STRIPE_PRICE_ID") 

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing API Credentials. Please check Streamlit Secrets.")
    st.stop()

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
stripe.api_key = STRIPE_KEY

# --- NEW: SYSTEM DIAGNOSTIC (Hidden in Admin) ---
def run_diagnostic():
    st.write("### 🔍 System Health Check")
    for v in ["STRIPE_SECRET_KEY", "STRIPE_PRICE_ID", "SUPABASE_URL", "SUPABASE_KEY"]:
        val = os.getenv(v)
        if val: st.success(f"✅ {v}: Detected ({val[:5]}...)")
        else: st.error(f"❌ {v}: Missing from Secrets")
    
    if PRICE_ID:
        try:
            p = stripe.Price.retrieve(PRICE_ID)
            st.success(f"✅ Stripe Price: Found ({p.unit_amount/100} {p.currency.upper()})")
        except Exception as e: st.error(f"❌ Stripe Price API: {e}")

# --- NEW: TRANSLATION EDITOR ---
def translation_editor():
    st.subheader("Global Language Manager")
    data = sb.table("translations").select("*").execute().data
    if data:
        keys = [i['key'] for i in data]
        sk = st.selectbox("Select Text Key to Edit", keys)
        curr = next(i for i in data if i['key'] == sk)
        with st.form("tr_editor"):
            ups, cols = {}, st.columns(2)
            for i, (code, name) in enumerate(LANGUAGES.items()):
                ups[code] = cols[i%2].text_input(f"{name} ({code})", value=curr.get(code, ""))
            if st.form_submit_button("Save Changes"):
                sb.table("translations").update(ups).eq("key", sk).execute()
                st.success("Updated!"); st.rerun()

def main():
    st.set_page_config(page_title="ProDispatcher", layout="wide", page_icon="🚚")
    load_translations(sb)
    
    if 'lang' not in st.session_state:
        st.session_state.lang = 'en'
    
    # Handle Stripe Success Redirect
    if st.query_params.get("success") == "true" and 'user' in st.session_state:
        sb.table("profiles").update({"is_premium": True}).eq("id", st.session_state.user.id).execute()
        st.success("🎉 Payment Successful! Premium features unlocked.")
        st.query_params.clear()

    st.sidebar.title("ProDispatcher")
    available_langs = list(LANGUAGES.values())
    current_lang_name = LANGUAGES.get(st.session_state.lang, "English")
    lang_idx = available_langs.index(current_lang_name) if current_lang_name in available_langs else 0
    lang_name = st.sidebar.selectbox("Language / Lugha", available_langs, index=lang_idx)
    st.session_state.lang = [k for k, v in LANGUAGES.items() if v == lang_name][0]

    if 'user' not in st.session_state:
        auth_page()
    else:
        render_app()

def render_app():
    user = st.session_state.user
    lang = st.session_state.lang

    try:
        profile_res = sb.table("profiles").select("*").eq("id", user.id).single().execute()
        profile = profile_res.data
        role = profile.get('role', 'driver') if profile else 'driver'
        is_premium = profile.get('is_premium', False)
    except Exception:
        role, is_premium = 'driver', False
    
    st.sidebar.divider()
    st.sidebar.write(f"Logged in as: **{role.upper()}** {'👑' if is_premium else ''}")
    menu = st.sidebar.radio("Navigation", ["Dashboard", "Earnings", "Premium", "Admin"])

    if menu == "Dashboard":
        st.header(translate('job_title', lang))
        # ... [Your existing Dashboard code remains exactly the same] ...

    elif menu == "Premium":
        st.subheader("Account Upgrades")
        if is_premium:
            st.success("Premium status active! 👑")
        else:
            if st.button("Subscribe via Stripe"):
                try:
                    # Using the identical logic from your working code
                    session = stripe.checkout.Session.create(
                        payment_method_types=['card'],
                        line_items=[{'price': PRICE_ID, 'quantity': 1}],
                        mode='subscription',
                        success_url="https://pro-dispatcher.streamlit.app/?success=true",
                        cancel_url="https://pro-dispatcher.streamlit.app/",
                    )
                    st.link_button("Go to Payment Gateway", session.url)
                except Exception as e:
                    st.error(f"Stripe Error: {e}")

    elif menu == "Admin" and role == 'admin':
        tab1, tab2, tab3 = st.tabs(["Jobs Database", "Language Editor", "Diagnostic"])
        with tab1:
            admin_panel()
        with tab2:
            translation_editor()
        with tab3:
            run_diagnostic()

    if st.sidebar.button("Sign Out"):
        st.session_state.clear()
        st.rerun()

# ... [auth_page, handle_upload, and admin_panel functions remain unchanged] ...
