import streamlit as st
import os
import sys

# --- 1. CRITICAL: MUST BE FIRST STREAMLIT COMMAND ---
st.set_page_config(page_title="ProDispatcher", layout="wide")

# --- 2. SAFE IMPORTS & DISCOVERY ---
try:
    import stripe
    import pandas as pd
    from supabase import create_client
    from dotenv import load_dotenv
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_path = os.path.abspath(os.path.join(current_dir, ".."))
    if root_path not in sys.path: sys.path.insert(0, root_path)
    
    try:
        from utils.translations import LANGUAGES, translate, load_translations
    except:
        from translations import LANGUAGES, translate, load_translations
except Exception as e:
    st.error(f"Failed to load libraries: {e}")
    st.stop()

# --- 3. SAFE INITIALIZATION ---
load_dotenv()
S_URL = os.getenv("SUPABASE_URL")
S_KEY = os.getenv("SUPABASE_KEY")

if not S_URL or not S_KEY:
    st.error("Missing SUPABASE_URL or SUPABASE_KEY in Secrets/Environment.")
    st.stop()

sb = create_client(S_URL, S_KEY)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PRICE_ID = os.getenv("STRIPE_PRICE_ID")

def sync_profile(user_id):
    """Ensures a profile row exists or creates one (First user = Admin)."""
    try:
        res = sb.table("profiles").select("*").eq("id", user_id).execute()
        if not res.data:
            count = sb.table("profiles").select("id", count="exact").limit(1).execute().count
            role = "admin" if count == 0 else "driver"
            sb.table("profiles").insert({"id": user_id, "role": role}).execute()
            st.rerun()
        return res.data[0]
    except Exception as e:
        st.error(f"Database Sync Error: {e}")
        return {"role": "driver", "is_premium": False}

def render_app():
    user = st.session_state.user
    lang = st.session_state.get('lang', 'en')
    prof = sync_profile(user.id)
    
    role = prof.get('role', 'driver')
    is_p = prof.get('is_premium', False)

    # Sidebar
    st.sidebar.title("🚚 ProDispatcher")
    st.sidebar.write(f"Logged in: **{role.upper()}**")
    
    menu = st.sidebar.radio("Navigation", ["Dashboard", "Earnings", "Premium", "Admin"])
    
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    # Content
    if menu == "Dashboard":
        st.header("Job Board")
        st.write("Welcome to the control center.")
        # [Dashboard Logic...]
        
    elif menu == "Admin":
        if role == 'admin':
            st.header("🛡️ System Admin")
            # [Admin Health Logic...]
        else:
            st.warning("Admin Access Required.")

def main():
    try:
        load_translations(sb)
    except: pass

    if 'user' not in st.session_state:
        st.title("ProDispatcher Login")
        em = st.text_input("Email")
        pw = st.text_input("Password", type="password")
        if st.button("Login"):
            try:
                res = sb.auth.sign_in_with_password({"email": em, "password": pw})
                st.session_state.user = res.user
                st.rerun()
            except Exception as e: st.error(f"Auth Error: {e}")
    else:
        render_app()

if __name__ == "__main__":
    main()
