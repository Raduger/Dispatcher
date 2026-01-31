import streamlit as st
import stripe
import os
import sys
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

# --- DISCOVERY ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.abspath(os.path.join(current_dir, ".."))
if root_path not in sys.path: sys.path.insert(0, root_path)

try:
    from utils.translations import LANGUAGES, translate, load_translations
except:
    from translations import LANGUAGES, translate, load_translations

load_dotenv()
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PRICE_ID = os.getenv("STRIPE_PRICE_ID")

def sync_profile(user):
    """Detects missing profiles and repairs them instantly."""
    res = sb.table("profiles").select("*").eq("id", user.id).execute()
    if not res.data:
        # Check if first user to assign admin role
        count = sb.table("profiles").select("id", count="exact").limit(1).execute().count
        role = "admin" if count == 0 else "driver"
        new_prof = {"id": user.id, "role": role, "is_premium": False}
        sb.table("profiles").insert(new_prof).execute()
        return new_prof
    return res.data[0]

def render_app():
    user, lang = st.session_state.user, st.session_state.lang
    prof = sync_profile(user) # Auto-repair trigger
    
    role, is_p = prof.get('role', 'driver'), prof.get('is_premium', False)

    # Sync Premium after payment
    if st.query_params.get("success") == "true":
        sb.table("profiles").update({"is_premium": True}).eq("id", user.id).execute()
        st.query_params.clear(); st.rerun()

    st.sidebar.title("🚚 ProDispatcher")
    st.sidebar.write(f"Role: **{role.upper()}**")
    menu = st.sidebar.radio("Nav", ["Dashboard", "Earnings", "Premium", "Admin"])

    if menu == "Premium":
        st.header("👑 Premium Subscription")
        if is_p: 
            st.success("You are a Premium Member!")
        else:
            st.write("Upgrade to boost your loads to the top of the list.")
            if st.button("Subscribe - $29/mo"):
                try:
                    sess = stripe.checkout.Session.create(
                        payment_method_types=['card'],
                        line_items=[{'price': PRICE_ID, 'quantity': 1}],
                        mode='subscription',
                        success_url="https://pro-dispatcher.streamlit.app/?success=true",
                        cancel_url="https://pro-dispatcher.streamlit.app/",
                    )
                    st.link_button("Pay Now", sess.url)
                except Exception as e: st.error(f"Stripe Error: {e}")

    elif menu == "Admin":
        if role == 'admin':
            t1, t2 = st.tabs(["Manage System", "Diagnostic"])
            with t1:
                st.subheader("Language Editor")
                # Translation logic remains same
            with t2:
                # Refined Diagnostic logic
                st.write("Checking API Keys...")
                st.write(f"Supabase URL: {'✅' if os.getenv('SUPABASE_URL') else '❌'}")
        else:
            st.warning("🚫 Admin access required. Contact support to change your role.")

    if st.sidebar.button("Logout"):
        st.session_state.clear(); st.rerun()

def main():
    st.set_page_config(page_title="ProDispatcher", layout="wide")
    load_translations(sb)
    if 'lang' not in st.session_state: st.session_state.lang = 'en'
    if 'user' not in st.session_state:
        # Login UI...
        pass
    else: render_app()

if __name__ == "__main__": main()
