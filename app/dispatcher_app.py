import streamlit as st
import stripe
import os
import sys
import pandas as pd
import plotly.express as px
from supabase import create_client
from dotenv import load_dotenv

# --- INITIALIZATION ---
st.set_page_config(page_title="ProDispatcher", layout="wide")
load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.abspath(os.path.join(current_dir, ".."))
if root_path not in sys.path: sys.path.insert(0, root_path)

try:
    from utils.translations import LANGUAGES, translate, load_translations
except ImportError:
    from translations import LANGUAGES, translate, load_translations

# Clients
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PRICE_ID = os.getenv("STRIPE_PRICE_ID")

# --- CORE LOGIC ---
def sync_profile(user_id):
    try:
        res = sb.table("profiles").select("*").eq("id", user_id).execute()
        if not res.data:
            try:
                c = sb.table("profiles").select("id", count="exact").limit(1).execute().count
                role = "admin" if c == 0 else "driver"
                sb.table("profiles").insert({"id": user_id, "role": role}).execute()
                st.rerun()
            except Exception as e:
                if "42501" in str(e): st.error("🔑 RLS Error: Run the SQL Policy for 'profiles'.")
                return {"role": "driver", "is_premium": False}
        return res.data[0]
    except: return {"role": "driver", "is_premium": False}

def handle_upload(job_id, file, user_id):
    try:
        path = f"proofs/{user_id}/{job_id}_{file.name}"
        sb.storage.from_('proofs').upload(path=path, file=file.getvalue(), file_options={"content-type": file.type})
        url = sb.storage.from_('proofs').get_public_url(path)
        sb.table("jobs").update({"status": "completed", "proof_url": url}).eq("id", job_id).execute()
        st.success("Delivery Confirmed!"); st.rerun()
    except Exception as e: st.error(f"Upload failed: {e}")

def render_app():
    user, lang = st.session_state.user, st.session_state.get('lang', 'en')
    prof = sync_profile(user.id)
    role, is_p = prof.get('role', 'driver'), prof.get('is_premium', False)

    # Sidebar
    st.sidebar.title("🚚 ProDispatcher")
    st.sidebar.write(f"**{role.upper()}** {'👑' if is_p else ''}")
    menu = st.sidebar.radio("Nav", ["Dashboard", "Earnings", "Premium", "Admin"])
    st.sidebar.divider()
    if st.sidebar.button("Logout"):
        st.session_state.clear(); st.rerun()

    if menu == "Dashboard":
        t_title = translate('job_title', lang)
        st.header(t_title if t_title != 'job_title' else "Available Loads")

        if role in ['dispatch', 'admin']:
            with st.expander("➕ Post New Job"):
                t = st.text_input("Description")
                r = st.number_input("Revenue $", min_value=0.0)
                if st.button("Post Job"):
                    sb.table("jobs").insert({"title": t, "revenue": r, "user_id": user.id, "status": "pending"}).execute()
                    st.rerun()

        # ACTIVE JOBS
        st.subheader("🛠️ My Active Trips")
        try:
            ajs = sb.table("jobs").select("*").eq("driver_id", user.id).eq("status", "in_progress").execute().data
            if not ajs: st.info("No active trips. Claim a load below!")
            for aj in (ajs or []):
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    c1.write(f"**{aj['title']}** (${aj['revenue']})")
                    f = c2.file_uploader("Upload BOL", key=f"f{aj['id']}")
                    if f and c2.button("Finish Job", key=f"b{aj['id']}"): handle_upload(aj['id'], f, user.id)
        except: st.error("Cannot load active trips. Check 'jobs' table RLS.")

        # JOB BOARD
        st.subheader("🌍 Public Job Board")
        try:
            jobs = sb.table("jobs").select("*").eq("status", "pending").execute().data
            for j in (jobs or []):
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.write(f"**{j['title']}**")
                    c2.write(f"${j['revenue']}")
                    if role == 'driver' and c3.button("Claim", key=f"cl{j['id']}"):
                        sb.table("jobs").update({"driver_id": user.id, "status": "in_progress"}).eq("id", j['id']).execute()
                        st.rerun()
        except: st.warning("Job board temporarily unavailable.")

    elif menu == "Admin" and role == 'admin':
        t1, t2, t3, t4 = st.tabs(["Stats", "Languages", "👥 Users", "🛡️ Health"])

        with t1: # REVENUE CHART
            st.subheader("Financial Overview")
            try:
                data = sb.table("jobs").select("revenue, status, created_at").execute().data
                if data:
                    df = pd.DataFrame(data)
                    fig = px.bar(df, x="status", y="revenue", color="status", title="Revenue by Status")
                    st.plotly_chart(fig, use_container_width=True)
            except: st.write("No data for charts yet.")

        with t3: # USER MANAGEMENT
            st.subheader("User Directory")
            try:
                users_res = sb.table("profiles").select("*").execute().data
                if users_res:
                    df_u = pd.DataFrame(users_res)
                    st.dataframe(df_u[['id', 'role', 'is_premium']], use_container_width=True)
            except: st.error("Could not load user list.")

        with t4: # HEALTH
            st.subheader("System Diagnostic")
            if st.button("Run Schema Check"):
                try:
                    test = sb.table("jobs").select("*").limit(1).execute()
                    st.success("Database Connection: OK")
                    st.write("Columns found:", list(test.data[0].keys()) if test.data else "Table empty but accessible")
                except Exception as e: st.error(f"Error: {e}")

def main():
    if 'user' not in st.session_state:
        st.title("ProDispatcher")
        e, p = st.text_input("Email"), st.text_input("Password", type="password")
        if st.button("Login"):
            try:
                res = sb.auth.sign_in_with_password({"email": e, "password": p})
                st.session_state.user = res.user; st.rerun()
            except: st.error("Login failed")
    else: render_app()

if __name__ == "__main__": main()
