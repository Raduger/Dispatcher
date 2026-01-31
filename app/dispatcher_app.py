import streamlit as st
import stripe
import os
import sys
import pandas as pd
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
                if "42501" in str(e): st.error("🔑 **RLS Error:** Run the SQL Policy for 'profiles'.")
                return {"role": "driver", "is_premium": False}
        return res.data[0]
    except: return {"role": "driver", "is_premium": False}

def handle_upload(job_id, file, user_id):
    try:
        path = f"proofs/{user_id}/{job_id}_{file.name}"
        sb.storage.from_('proofs').upload(path=path, file=file.getvalue(), file_options={"content-type": file.type})
        url = sb.storage.from_('proofs').get_public_url(path)
        sb.table("jobs").update({"status": "completed", "proof_url": url, "completed_at": "now()"}).eq("id", job_id).execute()
        st.success("Job Finalized!"); st.rerun()
    except Exception as e: st.error(f"Upload failed: {e}")

# --- UI COMPONENTS ---
def render_app():
    user, lang = st.session_state.user, st.session_state.get('lang', 'en')
    prof = sync_profile(user.id)
    role, is_p = prof.get('role', 'driver'), prof.get('is_premium', False)

    if st.query_params.get("success") == "true":
        sb.table("profiles").update({"is_premium": True}).eq("id", user.id).execute()
        st.query_params.clear(); st.rerun()

    st.sidebar.title("🚚 ProDispatcher")
    st.sidebar.write(f"**{role.upper()}** {'👑' if is_p else ''}")
    menu = st.sidebar.radio("Nav", ["Dashboard", "Earnings", "Premium", "Admin"])
    st.sidebar.divider()
    if st.sidebar.button("Logout"):
        st.session_state.clear(); st.rerun()

    if menu == "Dashboard":
        st.header(translate('job_title', lang))
        if role in ['dispatch', 'admin']:
            with st.expander("➕ Post Job"):
                t = st.text_input("Desc")
                r = st.number_input("Rev $", min_value=0.0)
                if st.button("Post"):
                    sb.table("jobs").insert({"title": t, "revenue": r, "user_id": user.id, "status": "pending"}).execute()
                    st.rerun()

        # --- FAIL-SAFE JOB FETCHING ---
        st.subheader("🛠️ Active")
        try:
            ajs = sb.table("jobs").select("*").eq("driver_id", user.id).eq("status", "in_progress").execute().data
            if not ajs: st.info("No active jobs.")
            for aj in ajs:
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    c1.write(f"**{aj['title']}** (${aj['revenue']})")
                    f = c2.file_uploader("BOL", key=f"f{aj['id']}")
                    if f and c2.button("Finish", key=f"b{aj['id']}"): handle_upload(aj['id'], f, user.id)
        except Exception: st.error("⚠️ Database Error: Cannot read 'jobs' table. Check RLS Policies.")

        st.subheader("🌍 Job Board")
        try:
            jobs = sb.table("jobs").select("*").eq("status", "pending").order("is_boosted", desc=True).execute().data
            for j in (jobs or []):
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.write(f"{'🚀 ' if j.get('is_boosted') else ''}**{j['title']}**")
                    c2.write(f"${j['revenue']}")
                    if role == 'driver' and c3.button("Claim", key=f"cl{j['id']}"):
                        sb.table("jobs").update({"driver_id": user.id, "status": "in_progress"}).eq("id", j['id']).execute()
                        st.rerun()
        except: pass

    elif menu == "Earnings":
        st.header(translate('earnings', lang))
        try:
            all_j = sb.table("jobs").select("*").eq("driver_id", user.id).execute().data
            if all_j:
                df = pd.DataFrame(all_j)
                st.metric("Total Paid", f"${df[df['status']=='completed']['revenue'].sum():,.2f}")
                st.table(df[['title', 'revenue', 'status']])
            else: st.info("No history.")
        except Exception: st.error("⚠️ Access Denied to 'jobs' table.")

    elif menu == "Admin" and role == 'admin':
        t1, t2, t3 = st.tabs(["Jobs", "Languages", "🛡️ Health"])
        with t2:
            try:
                data = sb.table("translations").select("*").execute().data
                if data:
                    sk = st.selectbox("Key", [i['key'] for i in data])
                    curr = next(i for i in data if i['key'] == sk)
                    with st.form("tr"):
                        ups, cols = {}, st.columns(2)
                        for i, (cd, nm) in enumerate(LANGUAGES.items()):
                            ups[cd] = cols[i%2].text_input(nm, value=curr.get(cd, ""))
                        if st.form_submit_button("Save"):
                            sb.table("translations").update(ups).eq("key", sk).execute(); st.rerun()
            except: st.error("Translations table unreachable.")
        with t3:
            c1, c2 = st.columns(2)
            try:
                sb.table("profiles").select("id").limit(1).execute()
                c1.success("Supabase: OK")
            except: c1.error("Supabase: FAIL (Check RLS)")
            try:
                stripe.Balance.retrieve()
                c2.success("Stripe: OK")
            except: c2.error("Stripe: FAIL")

def main():
    try: load_translations(sb)
    except: pass
    if 'lang' not in st.session_state: st.session_state.lang = 'en'
    l_name = st.sidebar.selectbox("Lugha", list(LANGUAGES.values()))
    st.session_state.lang = [k for k, v in LANGUAGES.items() if v == l_name][0]

    if 'user' not in st.session_state:
        t1, t2 = st.tabs(["Login", "Sign Up"])
        with t1:
            e, p = st.text_input("Email", key="le"), st.text_input("Pass", type="password", key="lp")
            if st.button("Login"):
                try:
                    res = sb.auth.sign_in_with_password({"email": e, "password": p})
                    st.session_state.user = res.user; st.rerun()
                except: st.error("Login failed")
        with t2:
            ne, np = st.text_input("Email", key="re"), st.text_input("Pass", type="password", key="rp")
            if st.button("Register"):
                try:
                    sb.auth.sign_up({"email": ne, "password": np})
                    st.success("Check Email")
                except: st.error("Signup failed")
    else: render_app()

if __name__ == "__main__": main()
