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

def sync_user_profile(user_id):
    """Ensures a user has a profile row. Makes first user Admin."""
    res = sb.table("profiles").select("*").eq("id", user_id).execute()
    if not res.data:
        # Check if table is empty to assign first Admin
        count_res = sb.table("profiles").select("id", count="exact").limit(1).execute()
        is_first = (count_res.count == 0)
        role = "admin" if is_first else "driver"
        sb.table("profiles").insert({"id": user_id, "role": role, "is_premium": False}).execute()
        st.rerun()
    return res.data[0] if res.data else {"role": "driver", "is_premium": False}

def render_app():
    user, lang = st.session_state.user, st.session_state.lang
    
    # 1. Force Profile Sync (Fixes the "Empty" issue)
    prof = sync_user_profile(user.id)
    role = prof.get('role', 'driver')
    is_p = prof.get('is_premium', False)

    # 2. Premium Status Sync
    if st.query_params.get("success") == "true":
        sb.table("profiles").update({"is_premium": True}).eq("id", user.id).execute()
        st.query_params.clear(); st.rerun()

    st.sidebar.title("🚚 ProDispatcher")
    st.sidebar.write(f"Role: **{role.upper()}**")
    menu = st.sidebar.radio("Navigation", ["Dashboard", "Earnings", "Premium", "Admin"])

    if menu == "Dashboard":
        st.header(translate('job_title', lang))
        
        # Dispatcher View
        if role in ['dispatch', 'admin']:
            with st.expander("➕ Post New Load"):
                with st.form("post_job"):
                    t = st.text_input("Job Description")
                    r = st.number_input("Revenue ($)", min_value=0.0)
                    if st.form_submit_button("Post"):
                        sb.table("jobs").insert({"title": t, "revenue": r, "user_id": user.id, "status": "pending"}).execute()
                        st.rerun()

        # Driver View
        st.subheader("🛠️ My Active Jobs")
        ajs = sb.table("jobs").select("*").eq("driver_id", user.id).eq("status", "in_progress").execute().data
        if ajs:
            for aj in ajs:
                with st.container(border=True):
                    st.write(f"**{aj['title']}** — `${aj['revenue']}`")
                    up_file = st.file_uploader("Upload BOL", key=f"up_{aj['id']}")
                    if up_file and st.button("Complete", key=f"fin_{aj['id']}"):
                        # Upload & Status Update logic...
                        pass
        else: st.info("No active jobs.")

        st.divider()
        st.subheader("🌍 Available Loads")
        jobs = sb.table("jobs").select("*").eq("status", "pending").execute().data
        for j in jobs:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{j['title']}**")
                c2.write(f"${j['revenue']}")
                if c3.button("Claim", key=f"cl_{j['id']}"):
                    sb.table("jobs").update({"driver_id": user.id, "status": "in_progress"}).eq("id", j['id']).execute()
                    st.rerun()

    elif menu == "Earnings":
        st.header(translate('earnings', lang))
        all_j = sb.table("jobs").select("*").eq("driver_id", user.id).execute().data
        if all_j:
            df = pd.DataFrame(all_j)
            st.metric("Total Payout", f"${df[df['status']=='completed']['revenue'].sum():,.2f}")
            st.dataframe(df[['title', 'revenue', 'status']])
        else: st.warning("No earnings yet. Claim and complete a job first.")

    elif menu == "Admin":
        if role == 'admin':
            t1, t2 = st.tabs(["User Management", "System Status"])
            with t1:
                users = sb.table("profiles").select("*").execute().data
                st.table(pd.DataFrame(users))
        else:
            st.error("🚫 Admin Access Required.")

def main():
    st.set_page_config(page_title="ProDispatcher", layout="wide")
    load_translations(sb)
    if 'user' not in st.session_state:
        # Standard Auth UI...
        pass
    else: render_app()

if __name__ == "__main__": main()
