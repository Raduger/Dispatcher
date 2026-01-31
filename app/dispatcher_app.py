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

def handle_upload(job_id, file, user_id):
    try:
        path = f"proofs/{user_id}/{job_id}_{file.name}"
        sb.storage.from_('proofs').upload(path=path, file=file.getvalue(), file_options={"content-type": file.type})
        url = sb.storage.from_('proofs').get_public_url(path)
        sb.table("jobs").update({"status": "completed", "proof_url": url, "completed_at": "now()"}).eq("id", job_id).execute()
        st.success("Job Finalized!")
        st.rerun()
    except Exception as e: st.error(f"Upload failed: {e}")

def render_app():
    user, lang = st.session_state.user, st.session_state.lang
    
    if st.query_params.get("success") == "true":
        sb.table("profiles").update({"is_premium": True}).eq("id", user.id).execute()
        st.query_params.clear(); st.toast("Premium Active! 👑")

    # --- FIXED: SAFE PROFILE FETCH ---
    try:
        # Using .maybe_single() or limit(1) prevents the APIError if row is missing
        prof_res = sb.table("profiles").select("*").eq("id", user.id).execute()
        prof = prof_res.data[0] if prof_res.data else {}
        role = prof.get('role', 'driver')
        is_p = prof.get('is_premium', False)
    except Exception as e:
        role, is_p = 'driver', False
        st.sidebar.warning("Profile not initialized. Defaulting to Driver.")

    st.sidebar.write(f"Logged in as: **{role.upper()}** {'👑' if is_p else ''}")
    menu = st.sidebar.radio("Navigation", ["Dashboard", "Earnings", "Premium", "Admin"])

    if menu == "Dashboard":
        st.header(translate('job_title', lang))
        
        if role in ['dispatch', 'admin']:
            with st.expander("➕ Post New Load"):
                t = st.text_input("Job Description")
                r = st.number_input("Revenue ($)", min_value=0.0)
                if st.button("Post Job"):
                    sb.table("jobs").insert({"title": t, "revenue": r, "user_id": user.id, "status": "pending"}).execute()
                    st.success("Posted!"); st.rerun()

        if role == 'driver':
            st.subheader("🛠️ My Active Jobs")
            ajs = sb.table("jobs").select("*").eq("driver_id", user.id).eq("status", "in_progress").execute().data
            if not ajs: st.info("No active jobs.")
            for aj in ajs:
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    c1.write(f"**{aj['title']}** — `${aj['revenue']}`")
                    up_file = c2.file_uploader("Proof", key=f"up_{aj['id']}")
                    if up_file and c2.button("Complete", key=f"fin_{aj['id']}"):
                        handle_upload(aj['id'], up_file, user.id)

        st.subheader("🌍 Available Loads")
        jobs_res = sb.table("jobs").select("*").eq("status", "pending").order("is_boosted", desc=True).execute()
        jobs = jobs_res.data if jobs_res.data else []
        for j in jobs:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                col1.write(f"{'🚀 ' if j.get('is_boosted') else ''}**{j['title']}**")
                col2.write(f"${j['revenue']}")
                if role == 'driver' and col3.button("Claim", key=f"cl_{j['id']}"):
                    sb.table("jobs").update({"driver_id": user.id, "status": "in_progress"}).eq("id", j['id']).execute()
                    st.rerun()

    elif menu == "Earnings":
        st.header(translate('earnings', lang))
        all_j = sb.table("jobs").select("*").eq("driver_id", user.id).execute().data
        if all_j:
            comp = [j for j in all_j if j['status'] == 'completed']
            pend = [j for j in all_j if j['status'] == 'in_progress']
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Paid", f"${sum(j.get('revenue', 0) for j in comp):,.2f}")
            c2.metric("Pending", f"${sum(j.get('revenue', 0) for j in pend):,.2f}")
            c3.metric("Total Jobs", len(all_j))
            st.table(pd.DataFrame(all_j)[['title', 'revenue', 'status']])
        else:
            st.info("No earnings records yet.")

    elif menu == "Premium":
        if is_p: st.success("Premium Active 👑")
        else:
            if st.button("Subscribe - $29/mo"):
                try:
                    sess = stripe.checkout.Session.create(
                        payment_method_types=['card'],
                        line_items=[{'price': PRICE_ID, 'quantity': 1}],
                        mode='subscription',
                        success_url="https://pro-dispatcher.streamlit.app/?success=true",
                        cancel_url="https://pro-dispatcher.streamlit.app/",
                    )
                    st.link_button("Go to Payment", sess.url)
                except Exception as e: st.error(f"Error: {e}")

    elif menu == "Admin" and role == 'admin':
        t1, t2, t3 = st.tabs(["Jobs", "Languages", "Diagnostic"])
        with t2:
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
        with t3:
            for k in ["STRIPE_SECRET_KEY", "STRIPE_PRICE_ID", "SUPABASE_URL"]:
                v = os.getenv(k)
                st.write(f"{k}: {'✅' if v else '❌'}")

def main():
    st.set_page_config(page_title="ProDispatcher", layout="wide")
    load_translations(sb)
    if 'lang' not in st.session_state: st.session_state.lang = 'en'
    l_name = st.sidebar.selectbox("Language", list(LANGUAGES.values()))
    st.session_state.lang = [k for k, v in LANGUAGES.items() if v == l_name][0]

    if 'user' not in st.session_state:
        t1, t2 = st.tabs(["Login", "Sign Up"])
        with t1:
            em, pw = st.text_input("Email"), st.text_input("Password", type="password")
            if st.button("Login"):
                try:
                    res = sb.auth.sign_in_with_password({"email": em, "password": pw})
                    st.session_state.user = res.user
                    st.rerun()
                except Exception as e: st.error(f"Login failed: {e}")
        with t2:
            nem, npw = st.text_input("New Email"), st.text_input("New Password", type="password")
            if st.button("Register"):
                try:
                    sb.auth.sign_up({"email": nem, "password": npw})
                    st.success("Check your email!")
                except Exception as e: st.error(f"Signup failed: {e}")
    else: render_app()

if __name__ == "__main__": main()
