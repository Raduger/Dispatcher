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
except:
    try:
        from translations import LANGUAGES, translate, load_translations
    except:
        st.error("Discovery Failed. Check folder structure.")
        st.stop()

load_dotenv()

# --- INITIALIZATION ---
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PRICE_ID = os.getenv("STRIPE_PRICE_ID")

# --- ADMIN FEATURES ---
def run_diagnostic():
    st.info("System Health Check")
    for k in ["STRIPE_SECRET_KEY", "STRIPE_PRICE_ID", "SUPABASE_URL", "SUPABASE_KEY"]:
        v = os.getenv(k)
        if v: st.success(f"✅ {k} found")
        else: st.error(f"❌ {k} missing")

def translation_editor():
    st.subheader("Language Manager")
    data = sb.table("translations").select("*").execute().data
    if data:
        sk = st.selectbox("Key", [i['key'] for i in data])
        curr = next(i for i in data if i['key'] == sk)
        with st.form("tr_editor"):
            ups = {}
            cols = st.columns(2)
            for i, (code, name) in enumerate(LANGUAGES.items()):
                ups[code] = cols[i%2].text_input(f"{name}", value=curr.get(code, ""))
            if st.form_submit_button("Update"):
                sb.table("translations").update(ups).eq("key", sk).execute()
                st.success("Saved!"); st.rerun()

# --- MAIN APP LOGIC ---
def render_app():
    user, lang = st.session_state.user, st.session_state.lang
    
    # Auto-Sync Premium Status
    if st.query_params.get("success") == "true":
        sb.table("profiles").update({"is_premium": True}).eq("id", user.id).execute()
        st.query_params.clear()
        st.toast("Premium Active! 👑")

    # Get Profile
    try:
        prof = sb.table("profiles").select("*").eq("id", user.id).single().execute().data
        role = prof.get('role', 'driver')
        is_p = prof.get('is_premium', False)
    except:
        role, is_p = 'driver', False

    st.sidebar.write(f"Logged in as: **{role.upper()}** {'👑' if is_p else ''}")
    menu = st.sidebar.radio("Menu", ["Dashboard", "Earnings", "Premium", "Admin"])

    if menu == "Dashboard":
        st.header(translate('job_title', lang))
        # ... [Your working Job Posting/Claiming logic] ...

    elif menu == "Premium":
        if is_p: st.success("Premium Active 👑")
        else:
            if st.button("Subscribe Now"):
                try:
                    # Logic identical to your working version
                    sess = stripe.checkout.Session.create(
                        payment_method_types=['card'],
                        line_items=[{'price': PRICE_ID, 'quantity': 1}],
                        mode='subscription',
                        success_url="https://dispatcher.streamlit.app/?success=true",
                        cancel_url="https://dispatcher.streamlit.app/",
                    )
                    st.link_button("Go to Payment", sess.url)
                except Exception as e: st.error(f"Stripe Error: {e}")

    elif menu == "Admin" and role == 'admin':
        t1, t2, t3 = st.tabs(["Jobs", "Languages", "Diagnostic"])
        with t2: translation_editor()
        with t3: run_diagnostic()

def main():
    st.set_page_config(page_title="ProDispatcher", layout="wide")
    load_translations(sb) # Initialize cache
    
    if 'lang' not in st.session_state: st.session_state.lang = 'en'
    
    # Language Selector
    lang_name = st.sidebar.selectbox("Language", list(LANGUAGES.values()))
    st.session_state.lang = [k for k, v in LANGUAGES.items() if v == lang_name][0]

    if 'user' not in st.session_state:
        # Standard Auth UI
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        with tab1:
            em = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            if st.button("Login"):
                res = sb.auth.sign_in_with_password({"email": em, "password": pw})
                st.session_state.user = res.user
                st.rerun()
    else:
        render_app()

if __name__ == "__main__":
    main()
