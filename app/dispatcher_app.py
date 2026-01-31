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

# --- CORE FUNCTIONS ---
def handle_upload(job_id, file, user_id):
    try:
        path = f"proofs/{user_id}/{job_id}_{file.name}"
        sb.storage.from_('proofs').upload(path=path, file=file.getvalue(), file_options={"content-type": file.type})
        url = sb.storage.from_('proofs').get_public_url(path)
        sb.table("jobs").update({"status": "completed", "proof_url": url, "completed_at": "now()"}).eq("id", job_id).execute()
        st.success("Job Finalized!")
        st.rerun()
    except Exception as e: st.error(f"Upload failed: {e}")

def logout():
    st.session_state.clear()
    st.rerun()

# --- APP UI ---
def render_app():
    user, lang = st.session_state.user, st.session_state.lang
    
    if st.query_params.get("success") == "true":
        sb.table("profiles").update({"is_premium": True}).eq("id", user.id).execute()
        st.query_params.clear(); st.toast("Premium Active! 👑")

    try:
        prof_res = sb.table("profiles").select("*").eq("id", user.id).execute()
        prof = prof_res.data[0] if prof_res.data else {}
        role = prof.get('role', 'driver')
        is_p = prof.get('is_premium', False)
    except Exception:
        role, is_p = 'driver', False

    st.sidebar.title("🚚 ProDispatcher")
    st.sidebar.write(f"Role: **{role.upper()}** {'👑' if is_p else ''}")
    menu = st.sidebar.radio("Navigation", ["Dashboard", "Earnings", "Premium", "Admin"])
    
    st.sidebar.divider()
    if st.sidebar.button("Logout"): logout()

    if menu == "Dashboard":
        st.header(translate('job_title', lang))
        if role in ['dispatch', 'admin']:
            with st.expander("➕ Post New Load"):
                t = st.text_input("Job Description")
                r = st.number_input("Revenue ($)", min_value=0.0)
                if st.button("Post Job"):
                    sb.table("jobs").insert({"title": t, "revenue": r, "user_id": user.id, "status": "pending"}).execute()
                    st.rerun()

        if role == 'driver':
            st.subheader("🛠️ My Active Jobs")
            ajs = sb.table("jobs").select("*").eq("driver_id", user.id).eq("status", "in_progress").execute().data
            for aj in (ajs or []):
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    c1.write(f"**{aj['title']}** — `${aj['revenue']}`")
                    up_file = c2.file_uploader("Proof", key=f"up_{aj['id']}")
                    if up_file and c2.button("Complete", key=f"fin_{aj['id']}"):
                        handle_upload(aj['id'], up_file, user.id)

        st.subheader("🌍 Available Loads")
        jobs = sb.table("jobs").select("*").eq("status", "pending").execute().data
        for j in (jobs or []):
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                col1.write(f"**{j['title']}**")
                col2.write(f"${j['revenue']}")
                if role == 'driver' and col3.button("Claim", key=f"cl_{j['id']}"):
                    sb.table("jobs").update({"driver_id": user.id, "status": "in_progress"}).eq("id", j['id']).execute()
                    st.rerun()

    elif menu == "Earnings":
        st.header(translate('earnings', lang))
        all_j = sb.table("jobs").select("*").eq("driver_id", user.id).execute().data
        if all_j:
            df = pd.DataFrame(all_j)
            c1, c2 = st.columns(2)
            c1.metric("Total Paid", f"${df[df['status']=='completed']['revenue'].sum():,.2f}")
            c2.metric("Pending", f"${df[df['status']=='in_progress']['revenue'].sum():,.2f}")
            st.table(df[['title', 'revenue', 'status']])

    elif menu == "Admin" and role == 'admin':
        t1, t2, t3 = st.tabs(["Jobs", "Languages", "🛡️ System Health"])
        
        with t2: # Language Editor
            data = sb.table("translations").select("*").execute().data
            if data:
                sk = st.selectbox("Key", [i['key'] for i in data])
                curr = next(i for i in data if i['key'] == sk)
                with st.form("tr"):
                    ups, cols = {}, st.columns(2)
                    for i, (cd, nm) in enumerate(LANGUAGES.items()):
                        ups[cd] = cols[i%2].text_input(nm, value=curr.get(cd, ""))
                    if st.form_submit_button("Save"):
                        sb.table("translations").update(ups).eq("key", sk).execute()
                        st.rerun()
        
        with t3: # REFINED DIAGNOSTIC
            st.subheader("API Connectivity")
            c1, c2, c3 = st.columns(3)
            
            # Supabase Test
            try:
                sb.table("profiles").select("id").limit(1).execute()
                c1.success("Supabase: OK")
            except: c1.error("Supabase: FAIL")
                
            # Stripe Test
            try:
                stripe.Balance.retrieve()
                c2.success("Stripe: OK")
            except: c2.error("Stripe: FAIL")
            
            # Storage Test
            try:
                sb.storage.get_bucket("proofs")
                c3.success("Storage: OK")
            except: c3.error("Storage: FAIL")

            st.divider()
            st.subheader("System Metrics")
            m1, m2 = st.columns(2)
            u_count = sb.table("profiles").select("id", count="exact").execute().count
            j_count = sb.table("jobs").select("id", count="exact").execute().count
            m1.metric("Total Users", u_count)
            m2.metric("Total Jobs", j_count)

            with st.expander("Environment Check (Masked)"):
                for k in ["SUPABASE_URL", "STRIPE_PRICE_ID", "STRIPE_SECRET_KEY"]:
                    v = os.getenv(k, "Not Found")
                    masked = f"{v[:5]}...{v[-5:]}" if len(v) > 10 else "Invalid Key"
                    st.text(f"{k}: {masked}")

def main():
    st.set_page_config(page_title="ProDispatcher", layout="wide")
    load_translations(sb)
    if 'lang' not in st.session_state: st.session_state.lang = 'en'
    l_name = st.sidebar.selectbox("Language / Lugha", list(LANGUAGES.values()))
    st.session_state.lang = [k for k, v in LANGUAGES.items() if v == l_name][0]

    if 'user' not in st.session_state:
        t1, t2 = st.tabs(["Login", "Sign Up"])
        with t1:
            em = st.text_input("Email", key="l_em")
            pw = st.text_input("Password", type="password", key="l_pw")
            if st.button("Login"):
                try:
                    res = sb.auth.sign_in_with_password({"email": em, "password": pw})
                    st.session_state.user = res.user
                    st.rerun()
                except Exception as e: st.error("Login failed.")
        with t2:
            nem = st.text_input("New Email", key="r_em")
            npw = st.text_input("New Password", type="password", key="r_pw")
            if st.button("Register"):
                try:
                    sb.auth.sign_up({"email": nem, "password": npw})
                    st.success("Check email!")
                except Exception as e: st.error("Signup failed.")
    else: render_app()

if __name__ == "__main__": main()
