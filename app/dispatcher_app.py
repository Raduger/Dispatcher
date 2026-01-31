import streamlit as st
import stripe
import os
import sys
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

# --- SAFE IMPORTS ---
try:
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# --- CONFIG ---
st.set_page_config(page_title="ProDispatcher", layout="wide")
load_dotenv()

# Module Discovery
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

# --- DATABASE LOGIC ---
def sync_profile(user_id):
    try:
        res = sb.table("profiles").select("*").eq("id", user_id).execute()
        if not res.data:
            c = sb.table("profiles").select("id", count="exact").limit(1).execute().count
            role = "admin" if c == 0 else "driver"
            sb.table("profiles").insert({"id": user_id, "role": role}).execute()
            st.rerun()
        return res.data[0]
    except: return {"role": "driver", "is_premium": False}

def handle_upload(job_id, file, user_id):
    try:
        path = f"proofs/{user_id}/{job_id}_{file.name}"
        sb.storage.from_('proofs').upload(path=path, file=file.getvalue(), file_options={"content-type": file.type})
        url = sb.storage.from_('proofs').get_public_url(path)
        sb.table("jobs").update({"status": "completed", "proof_url": url, "completed_at": "now()"}).eq("id", job_id).execute()
        st.success("✅ Delivery Verified!"); st.rerun()
    except Exception as e: st.error(f"Upload failed: {e}")

# --- UI LOGIC ---
def render_app():
    user, lang = st.session_state.user, st.session_state.get('lang', 'en')
    prof = sync_profile(user.id)
    role, is_p = prof.get('role', 'driver'), prof.get('is_premium', False)

    # Sync Premium Status after payment
    if st.query_params.get("success") == "true":
        sb.table("profiles").update({"is_premium": True}).eq("id", user.id).execute()
        st.query_params.clear(); st.rerun()

    # Sidebar
    st.sidebar.title("🚚 ProDispatcher")
    st.sidebar.write(f"Role: **{role.upper()}** {'👑' if is_p else ''}")
    menu = st.sidebar.radio("Nav", ["Dashboard", "Earnings", "Premium", "Admin"])
    
    # Language Selector
    l_name = st.sidebar.selectbox("Language", list(LANGUAGES.values()), index=list(LANGUAGES.keys()).index(lang))
    st.session_state.lang = [k for k, v in LANGUAGES.items() if v == l_name][0]
    
    st.sidebar.divider()
    if st.sidebar.button("Logout"):
        st.session_state.clear(); st.rerun()

    if menu == "Dashboard":
        st.header(translate('job_title', lang) if translate('job_title', lang) != 'job_title' else "Load Board")
        
        if role in ['dispatch', 'admin']:
            with st.expander("➕ Post New Job"):
                t = st.text_input("Desc")
                r = st.number_input("Revenue", min_value=0.0)
                if st.button("Post"):
                    sb.table("jobs").insert({"title": t, "revenue": r, "user_id": user.id, "status": "pending"}).execute()
                    st.rerun()

        # ACTIVE TRIPS
        st.subheader("🛠️ Active Trips")
        try:
            ajs = sb.table("jobs").select("*").eq("driver_id", user.id).eq("status", "in_progress").execute().data
            for aj in (ajs or []):
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    c1.write(f"**{aj['title']}** (${aj['revenue']})")
                    f = c2.file_uploader("Upload BOL", key=f"f{aj['id']}")
                    if f and c2.button("Confirm Delivery", key=f"b{aj['id']}"): handle_upload(aj['id'], f, user.id)
        except: st.error("Table Access Error")

        # PUBLIC BOARD
        st.subheader("🌍 Open Loads")
        try:
            jobs = sb.table("jobs").select("*").eq("status", "pending").execute().data
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
            ej = sb.table("jobs").select("*").eq("driver_id", user.id).execute().data
            if ej:
                df = pd.DataFrame(ej)
                st.metric("Total Paid", f"${df[df['status']=='completed']['revenue'].sum():,.2f}")
                st.dataframe(df[['title', 'revenue', 'status']], use_container_width=True)
        except: st.info("No earnings yet.")

    elif menu == "Premium":
        if is_p: st.success("Premium Active 👑")
        else:
            if st.button("Subscribe - $29/mo"):
                try:
                    s = stripe.checkout.Session.create(
                        payment_method_types=['card'], line_items=[{'price': PRICE_ID, 'quantity': 1}],
                        mode='subscription', success_url="https://pro-dispatcher.streamlit.app/?success=true",
                        cancel_url="https://pro-dispatcher.streamlit.app/",
                    )
                    st.link_button("Pay Now", s.url)
                except Exception as e: st.error(f"Stripe: {e}")

    elif menu == "Admin" and role == 'admin':
        t1, t2, t3, t4 = st.tabs(["Analytics", "Translations", "Users", "Health"])
        
        with t1: # PLOTLY CHARTS
            if HAS_PLOTLY:
                data = sb.table("jobs").select("revenue, status").execute().data
                if data: st.plotly_chart(px.pie(pd.DataFrame(data), values='revenue', names='status', title="Revenue Split"))
        
        with t2: # 11-LANGUAGE EDITOR
            tr = sb.table("translations").select("*").execute().data
            if tr:
                sk = st.selectbox("Select Key", [i['key'] for i in tr])
                curr = next(i for i in tr if i['key'] == sk)
                with st.form("tr_edit"):
                    updates, cols = {}, st.columns(2)
                    for i, (code, name) in enumerate(LANGUAGES.items()):
                        updates[code] = cols[i%2].text_input(name, value=curr.get(code, ""))
                    if st.form_submit_button("Save Changes"):
                        sb.table("translations").update(updates).eq("key", sk).execute(); st.rerun()

        with t3: # USER MANAGEMENT
            users = sb.table("profiles").select("*").execute().data
            if users:
                df_u = pd.DataFrame(users)
                st.dataframe(df_u[['id', 'role', 'is_premium']], use_container_width=True)
                uid = st.text_input("Target User ID")
                new_r = st.selectbox("Role", ["driver", "dispatch", "admin"])
                if st.button("Update User"):
                    sb.table("profiles").update({"role": new_r}).eq("id", uid).execute(); st.rerun()

        with t4: # DIAGNOSTICS
            if st.button("Check Database Integrity"):
                try:
                    sb.table("jobs").select("*").limit(1).execute()
                    st.success("Jobs Table: Accessible ✅")
                except Exception as e: st.error(f"Error: {e}")

def main():
    load_translations(sb)
    if 'lang' not in st.session_state: st.session_state.lang = 'en'
    if 'user' not in st.session_state:
        st.title("ProDispatcher Login")
        e, p = st.text_input("Email"), st.text_input("Password", type="password")
        if st.button("Enter"):
            try:
                res = sb.auth.sign_in_with_password({"email": e, "password": p})
                st.session_state.user = res.user; st.rerun()
            except: st.error("Auth Failed")
    else: render_app()

if __name__ == "__main__": main()
