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
        st.header(translate('job_title', lang))
        if role in ['dispatch', 'admin']:
            with st.expander("➕ Post Job"):
                t = st.text_input("Desc")
                r = st.number_input("Rev $", min_value=0.0)
                if st.button("Post"):
                    sb.table("jobs").insert({"title": t, "revenue": r, "user_id": user.id, "status": "pending"}).execute()
                    st.rerun()

        st.subheader("🛠️ Active")
        try:
            ajs = sb.table("jobs").select("*").eq("driver_id", user.id).eq("status", "in_progress").execute().data
            for aj in (ajs or []):
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    c1.write(f"**{aj['title']}** (${aj['revenue']})")
                    f = c2.file_uploader("BOL", key=f"f{aj['id']}")
                    if f and c2.button("Finish", key=f"b{aj['id']}"): 
                        # handle_upload logic here
                        pass
        except: st.error("Database connection issue.")

    elif menu == "Admin" and role == 'admin':
        t1, t2, t3, t4 = st.tabs(["Jobs", "Languages", "👥 Users", "🛡️ Health"])

        with t3: # USER MANAGEMENT
            st.subheader("User Directory")
            users_res = sb.table("profiles").select("*").execute().data
            if users_res:
                df_u = pd.DataFrame(users_res)
                st.dataframe(df_u[['id', 'role', 'is_premium']], use_container_width=True)
                
                with st.expander("Change User Role"):
                    uid = st.text_input("Target User ID")
                    new_role = st.selectbox("New Role", ["driver", "dispatch", "admin"])
                    if st.button("Update Role"):
                        sb.table("profiles").update({"role": new_role}).eq("id", uid).execute()
                        st.success("Role Updated!"); st.rerun()

        with t4: # HEALTH & SCHEMA DOCTOR
            st.subheader("System Diagnostic")
            c1, c2 = st.columns(2)
            try:
                sb.table("profiles").select("id").limit(1).execute()
                c1.success("Supabase: OK")
            except: c1.error("Supabase: FAIL")
            
            if st.button("Check Table Integrity"):
                try:
                    test = sb.table("jobs").select("*").limit(1).execute()
                    cols = test.data[0].keys() if test.data else []
                    req = ["driver_id", "status", "revenue", "user_id"]
                    miss = [c for c in req if c not in cols]
                    if not miss: st.success("Schema Valid!")
                    else: st.error(f"Missing: {miss}")
                except Exception as e: st.error(f"Error: {e}")

            with st.expander("Show SQL Repair Script"):
                st.code("ALTER TABLE public.jobs ADD COLUMN IF NOT EXISTS driver_id uuid;")

def main():
    if 'user' not in st.session_state:
        # Simple Login UI
        st.title("ProDispatcher")
        e = st.text_input("Email")
        p = st.text_input("Pass", type="password")
        if st.button("Login"):
            res = sb.auth.sign_in_with_password({"email": e, "password": p})
            st.session_state.user = res.user; st.rerun()
    else: render_app()

if __name__ == "__main__": main()
