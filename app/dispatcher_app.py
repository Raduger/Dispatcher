import streamlit as st
import stripe
import os
import sys
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

# --- CONFIG & IMPORTS ---
try:
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

st.set_page_config(page_title="ProDispatcher", layout="wide")
load_dotenv()

# Pathing for translations
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from utils.translations import LANGUAGES, translate, load_translations
except:
    from translations import LANGUAGES, translate, load_translations

# Clients
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PRICE_ID = os.getenv("STRIPE_PRICE_ID")

# --- DATABASE CORE ---
def sync_profile(user_id):
    """Safe profile fetch that ignores recursion errors."""
    try:
        res = sb.table("profiles").select("*").eq("id", user_id).execute()
        if res.data: return res.data[0]
        # Auto-create if missing
        role = "admin" if sb.table("profiles").select("id", count="exact").limit(1).execute().count == 0 else "driver"
        p = {"id": user_id, "role": role, "is_premium": False}
        sb.table("profiles").insert(p).execute()
        return p
    except Exception as e:
        if "42P17" in str(e): st.sidebar.warning("⚠️ RLS Recursion Active")
        return {"role": "driver", "is_premium": False}

def handle_upload(job_id, file, user_id):
    try:
        path = f"proofs/{user_id}/{job_id}_{file.name}"
        sb.storage.from_('proofs').upload(path, file.getvalue(), {"content-type": file.type})
        url = sb.storage.from_('proofs').get_public_url(path)
        sb.table("jobs").update({"status": "completed", "proof_url": url}).eq("id", job_id).execute()
        st.success("Verified!"); st.rerun()
    except Exception as e: st.error(f"Upload Error: {e}")

# --- UI COMPONENTS ---
def render_app():
    user, lang = st.session_state.user, st.session_state.get('lang', 'en')
    prof = sync_profile(user.id)
    role, is_p = prof.get('role', 'driver'), prof.get('is_premium', False)

    # Sidebar
    st.sidebar.title("🚚 ProDispatcher")
    st.sidebar.write(f"**{role.upper()}** {'👑' if is_p else ''}")
    menu = st.sidebar.radio("Nav", ["Dashboard", "Earnings", "Premium", "Admin"])
    
    sel_lang = st.sidebar.selectbox("Lang", list(LANGUAGES.values()), index=list(LANGUAGES.keys()).index(lang))
    st.session_state.lang = [k for k, v in LANGUAGES.items() if v == sel_lang][0]
    
    if st.sidebar.button("Logout"):
        st.session_state.clear(); st.rerun()

    if menu == "Dashboard":
        st.header(translate('job_title', lang) if translate('job_title', lang) != 'job_title' else "Load Board")
        
        if role in ['dispatch', 'admin']:
            with st.expander("➕ Post Load"):
                t = st.text_input("Title")
                r = st.number_input("Rev", min_value=0.0)
                if st.button("Post"):
                    sb.table("jobs").insert({"title": t, "revenue": r, "user_id": user.id, "status": "pending"}).execute()
                    st.rerun()

        # Jobs Logic
        try:
            # Active
            aj = sb.table("jobs").select("*").eq("driver_id", user.id).eq("status", "in_progress").execute().data
            if aj: st.subheader("🛠️ Active")
            for a in (aj or []):
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    c1.write(f"**{a['title']}** (${a['revenue']})")
                    f = c2.file_uploader("BOL", key=f"f{a['id']}")
                    if f and c2.button("Finish", key=f"b{a['id']}"): handle_upload(a['id'], f, user.id)
            
            # Board
            st.subheader("🌍 Open Loads")
            bj = sb.table("jobs").select("*").eq("status", "pending").execute().data
            for b in (bj or []):
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.write(f"{'🚀 ' if b.get('is_boosted') else ''}{b['title']}")
                    c2.write(f"${b['revenue']}")
                    if role == 'driver' and c3.button("Claim", key=f"c{b['id']}"):
                        sb.table("jobs").update({"driver_id": user.id, "status": "in_progress"}).eq("id", b['id']).execute()
                        st.rerun()
        except Exception as e: st.error(f"Data Error: {e}")

    elif menu == "Admin" and role == 'admin':
        t1, t2, t3 = st.tabs(["Stats", "Users", "Tools"])
        with t1:
            if HAS_PLOTLY:
                data = sb.table("jobs").select("revenue, status").execute().data
                if data: st.plotly_chart(px.bar(pd.DataFrame(data), x='status', y='revenue', color='status'))
        with t2:
            usrs = sb.table("profiles").select("*").execute().data
            if usrs:
                df = pd.DataFrame(usrs)
                st.dataframe(df[['id', 'role', 'is_premium']], use_container_width=True)
                uid = st.text_input("User ID")
                new_r = st.selectbox("Role", ["driver", "dispatch", "admin"])
                if st.button("Update"):
                    sb.table("profiles").update({"role": new_r}).eq("id", uid).execute(); st.rerun()
      
with t3: # Diagnostic Tab
    if st.button("🔍 Check RLS Health"):
        try:
            # Querying the internal Postgres schema to see active policies
            policies = sb.rpc("get_policies").execute() # If you have a custom RPC
            # Or just a simple test:
            test_prof = sb.table("profiles").select("id").limit(1).execute()
            test_jobs = sb.table("jobs").select("id").limit(1).execute()
            st.success("Policies are flat and readable! ✅")
        except Exception as e:
            st.error(f"Recursion still active: {e}")
def main():
    load_translations(sb)
    if 'user' not in st.session_state:
        st.title("ProDispatcher Login")
        e, p = st.text_input("Email"), st.text_input("Pass", type="password")
        if st.button("Login"):
            try:
                res = sb.auth.sign_in_with_password({"email": e, "password": p})
                st.session_state.user = res.user; st.rerun()
            except: st.error("Login Failed")
    else: render_app()

if __name__ == "__main__": main()
