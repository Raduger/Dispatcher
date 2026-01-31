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

# --- HELPER FUNCTIONS ---
def handle_upload(job_id, file, user_id):
    try:
        path = f"proofs/{user_id}/{job_id}_{file.name}"
        sb.storage.from_('proofs').upload(path=path, file=file.getvalue(), file_options={"content-type": file.type})
        url = sb.storage.from_('proofs').get_public_url(path)
        sb.table("jobs").update({"status": "completed", "proof_url": url, "completed_at": "now()"}).eq("id", job_id).execute()
        st.success("Job Finalized!")
        st.rerun()
    except Exception as e: st.error(f"Upload failed: {e}")

def get_profile(user_id):
    try:
        res = sb.table("profiles").select("*").eq("id", user_id).execute()
        return res.data[0] if res.data else None
    except: return None

# --- UI COMPONENTS ---
def render_app():
    user, lang = st.session_state.user, st.session_state.lang
    
    if st.query_params.get("success") == "true":
        sb.table("profiles").update({"is_premium": True}).eq("id", user.id).execute()
        st.query_params.clear(); st.toast("Premium Active! 👑")

    prof = get_profile(user.id)
    # Default to driver if profile missing, unless it's the very first user
    role = prof.get('role', 'driver') if prof else 'driver'
    is_p = prof.get('is_premium', False) if prof else False

    st.sidebar.write(f"Logged in as: **{role.upper()}**")
    menu = st.sidebar.radio("Navigation", ["Dashboard", "Earnings", "Premium", "Admin"])

    if menu == "Dashboard":
        st.header(translate('job_title', lang))
        # [Job Posting & Claiming Logic remains same]
        
    elif menu == "Admin":
        if role == 'admin':
            t1, t2, t3, t4 = st.tabs(["Jobs", "Users", "Languages", "System"])
            
            with t1: # Jobs Management
                all_j = sb.table("jobs").select("*").execute().data
                if all_j: st.dataframe(pd.DataFrame(all_j))
            
            with t2: # USER MANAGEMENT (New Feature)
                st.subheader("Manage Drivers & Admins")
                users_res = sb.table("profiles").select("*").execute().data
                if users_res:
                    u_df = pd.DataFrame(users_res)
                    st.dataframe(u_df[['id', 'role', 'is_premium']])
                    
                    st.divider()
                    st.write("### Change User Role")
                    target_id = st.selectbox("Select User ID", u_df['id'].tolist())
                    new_role = st.selectbox("Assign New Role", ["driver", "dispatch", "admin"])
                    if st.button("Update Role"):
                        sb.table("profiles").update({"role": new_role}).eq("id", target_id).execute()
                        st.success(f"User {target_id} is now {new_role}!"); st.rerun()

            with t3: # Languages
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
            
            with t4: # Diagnostic
                for k in ["STRIPE_PRICE_ID", "SUPABASE_URL"]:
                    st.write(f"{k}: {'✅' if os.getenv(k) else '❌'}")
        else:
            st.error("🚫 Admin Access Required.")

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
                except Exception as e: st.error(f"Login Error: {e}")
        with t2:
            nem, npw = st.text_input("New Email"), st.text_input("New Password", type="password")
            if st.button("Register"):
                try:
                    auth_res = sb.auth.sign_up({"email": nem, "password": npw})
                    # Create profile row immediately to prevent "Blank Admin" issue
                    if auth_res.user:
                        # Check if this is the first user ever
                        existing = sb.table("profiles").select("id", count="exact").execute()
                        initial_role = "admin" if existing.count == 0 else "driver"
                        sb.table("profiles").insert({"id": auth_res.user.id, "role": initial_role}).execute()
                    st.success("Account created! Check your email for verification.")
                except Exception as e: st.error(f"Signup Error: {e}")
    else: render_app()

if __name__ == "__main__": main()
