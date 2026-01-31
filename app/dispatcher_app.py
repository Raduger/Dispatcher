import streamlit as st
import stripe
import os
import sys
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

# --- TRIPLE-LAYER MODULE DISCOVERY ---
# Layer 1: Get absolute path to the 'Prodispatcher' root folder
current_dir = os.path.dirname(os.path.abspath(__file__)) # /mount/src/dispatcher/app
root_path = os.path.abspath(os.path.join(current_dir, "..")) # /mount/src/dispatcher

# Layer 2: Insert root into sys.path at the top priority
if root_path not in sys.path:
    sys.path.insert(0, root_path)

# Layer 3: Direct import with fallback
try:
    from utils.translations import LANGUAGES, translate, load_translations
except (ImportError, ModuleNotFoundError):
    try:
        # Fallback for flattened directory structures
        from translations import LANGUAGES, translate, load_translations
    except ImportError:
        st.error("CRITICAL: Could not find 'utils/translations.py'. Check GitHub folder structure.")
        st.stop()

load_dotenv()

# --- INITIALIZATION ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing API Credentials. Please check Streamlit Secrets.")
    st.stop()

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
stripe.api_key = STRIPE_KEY

def main():
    st.set_page_config(page_title="ProDispatcher", layout="wide", page_icon="🚚")
    
    # Initialize translation cache
    load_translations(sb)
    
    if 'lang' not in st.session_state:
        st.session_state.lang = 'en'
    
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

def auth_page():
    st.title("Welcome to ProDispatcher")
    lang = st.session_state.lang
    tab1, tab2 = st.tabs([translate('login', lang), "Sign Up"])
    
    with tab1:
        email = st.text_input("Email", key="l_email")
        pw = st.text_input("Password", type="password", key="l_pw")
        if st.button("Enter"):
            try:
                res = sb.auth.sign_in_with_password({"email": email, "password": pw})
                st.session_state.user = res.user
                st.rerun()
            except Exception as e:
                st.error(f"Auth Error: {e}")

    with tab2:
        new_email = st.text_input("Email", key="s_email")
        new_pw = st.text_input("Password", type="password", key="s_pw")
        if st.button("Register"):
            try:
                sb.auth.sign_up({"email": new_email, "password": new_pw})
                st.success("Verification email sent!")
            except Exception as e:
                st.error(f"Signup Error: {e}")

def render_app():
    user = st.session_state.user
    lang = st.session_state.lang

    try:
        profile_res = sb.table("profiles").select("*").eq("id", user.id).single().execute()
        profile = profile_res.data
        role = profile.get('role', 'driver') if profile else 'driver'
    except Exception:
        role = 'driver'
    
    st.sidebar.divider()
    st.sidebar.write(f"Logged in as: **{role.upper()}**")
    menu = st.sidebar.radio("Navigation", ["Dashboard", "Earnings", "Premium", "Admin"])

    if menu == "Dashboard":
        st.header(translate('job_title', lang))
        
        if role in ['dispatch', 'admin']:
            with st.expander(translate('post', lang)):
                title_in = st.text_input("Job Description")
                rev_in = st.number_input("Revenue ($)", min_value=0.0)
                if st.button("Post Job"):
                    sb.table("jobs").insert({
                        "title": title_in, 
                        "revenue": rev_in, 
                        "user_id": user.id,
                        "status": "pending"
                    }).execute()
                    st.success("Job live!")
                    st.rerun()

        st.divider()
        try:
            jobs_res = sb.table("jobs").select("*").order("is_boosted", desc=True).execute().data
            for j in jobs_res:
                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    boost_tag = "🚀 " if j.get('is_boosted') else ""
                    col1.write(f"**{boost_tag}{j['title']}**")
                    col2.write(f"Status: `{j['status']}`")
                    
                    if role == 'driver':
                        if j['status'] == 'pending':
                            if col3.button(translate('claim', lang), key=f"c_{j['id']}"):
                                sb.table("jobs").update({"driver_id": user.id, "status": "in_progress"}).eq("id", j['id']).execute()
                                st.rerun()
                        elif j['status'] == 'in_progress' and j['driver_id'] == user.id:
                            up_file = st.file_uploader("Upload Proof", type=['png', 'jpg', 'pdf'], key=f"f_{j['id']}")
                            if up_file:
                                handle_upload(j, up_file, user.id)
        except Exception as e:
            st.error(f"Error loading jobs: {e}")

    elif menu == "Earnings":
        st.header(translate('earnings', lang))
        earnings_data = sb.table("jobs").select("revenue").eq("driver_id", user.id).eq("status", "completed").execute().data
        total = sum(d['revenue'] for d in earnings_data) if earnings_data else 0
        st.metric("Total Payout", f"${total:,.2f}")

    elif menu == "Premium":
        st.subheader("Account Upgrades")
        if st.button("Subscribe via Stripe"):
            try:
                session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=[{'price': os.getenv("STRIPE_PRICE_ID"), 'quantity': 1}],
                    mode='subscription',
                    success_url="https://pro-dispatcher.streamlit.app/",
                    cancel_url="https://pro-dispatcher.streamlit.app/",
                )
                st.link_button("Go to Payment Gateway", session.url)
            except Exception as e:
                st.error(f"Stripe Error: {e}")

    elif menu == "Admin" and role == 'admin':
        admin_panel()

    if st.sidebar.button("Sign Out"):
        st.session_state.clear()
        st.rerun()

def handle_upload(job, file, user_id):
    try:
        path = f"proofs/{user_id}/{job['id']}_{file.name}"
        sb.storage.from_('proofs').upload(path=path, file=file.getvalue(), file_options={"content-type": file.type})
        url = sb.storage.from_('proofs').get_public_url(path)
        sb.table("jobs").update({
            "status": "completed", 
            "proof_url": url, 
            "completed_at": "now()"
        }).eq("id", job['id']).execute()
        st.success("Delivery Confirmed!")
        st.rerun()
    except Exception as e:
        st.error(f"Upload error: {e}")

def admin_panel():
    st.subheader("System Administration")
    all_data = sb.table("jobs").select("*").execute().data
    if all_data:
        df = pd.DataFrame(all_data)
        st.dataframe(df)
        if st.button("Purge Database"):
            sb.table("jobs").delete().neq("status", "archived").execute()
            st.success("Database Reset.")
            st.rerun()

if __name__ == "__main__":
    main()