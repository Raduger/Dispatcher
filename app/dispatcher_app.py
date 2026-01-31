import streamlit as st
import stripe
import os
import sys
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

# Path fix to ensure utils is found
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.translations import LANGUAGES, translate, load_translations

load_dotenv()

# Initialize Clients
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def main():
    st.set_page_config(page_title="ProDispatcher", layout="wide")
    
    # Initialize translation cache
    load_translations(sb)
    
    if 'lang' not in st.session_state:
        st.session_state.lang = 'en'
    
    # Sidebar Language Selector
    st.sidebar.title("ProDispatcher")
    lang_choice = st.sidebar.selectbox("Language", list(LANGUAGES.values()), index=0)
    st.session_state.lang = [k for k, v in LANGUAGES.items() if v == lang_choice][0]

    if 'user' not in st.session_state:
        auth_page()
    else:
        render_app()

def auth_page():
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    with tab1:
        email = st.text_input("Email", key="l_email")
        pw = st.text_input("Password", type="password", key="l_pw")
        if st.button("Enter"):
            try:
                res = sb.auth.sign_in_with_password({"email": email, "password": pw})
                st.session_state.user = res.user
                st.rerun()
            except Exception as e:
                st.error(f"Login Failed: {e}")
    with tab2:
        new_email = st.text_input("Email", key="s_email")
        new_pw = st.text_input("Password", type="password", key="s_pw")
        if st.button("Register"):
            sb.auth.sign_up({"email": new_email, "password": new_pw})
            st.success("Check your email for confirmation!")

def render_app():
    user = st.session_state.user
    # Fetch profile for role check
    profile = sb.table("profiles").select("*").eq("id", user.id).single().execute().data
    role = profile.get('role', 'driver')
    
    st.sidebar.write(f"Logged in as: **{role.upper()}**")
    menu = st.sidebar.radio("Menu", ["Dashboard", "Earnings", "Premium", "Admin"])

    if menu == "Dashboard":
        st.header(translate('job_title', st.session_state.lang))
        
        # Dispatcher: Create Job
        if role == 'dispatch':
            with st.expander("Post New Job"):
                t_input = st.text_input("Title")
                rev = st.number_input("Revenue", min_value=0.0)
                if st.button("Post"):
                    sb.table("jobs").insert({"title": t_input, "revenue": rev, "user_id": user.id}).execute()
                    st.success("Job Posted!")
                    st.rerun()

        # Job Feed logic
        jobs = sb.table("jobs").select("*").execute().data
        for j in jobs:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{j['title']}** (${j['revenue']})")
                c2.write(f"Status: `{j['status']}`")
                
                # Driver Actions: Claim or Upload Proof
                if role == 'driver':
                    if j['status'] == 'pending':
                        if c3.button("Claim", key=f"claim_{j['id']}"):
                            sb.table("jobs").update({"driver_id": user.id, "status": "in_progress"}).eq("id", j['id']).execute()
                            st.rerun()
                    
                    elif j['status'] == 'in_progress' and j['driver_id'] == user.id:
                        uploaded_file = st.file_uploader("Upload Proof", type=['png', 'jpg', 'pdf'], key=f"proof_{j['id']}")
                        if uploaded_file:
                            handle_upload(j, uploaded_file, user.id)

    elif menu == "Earnings":
        done = sb.table("jobs").select("revenue").eq("driver_id", user.id).eq("status", "completed").execute().data
        total = sum(d['revenue'] for d in done) if done else 0
        st.metric(translate('earnings', st.session_state.lang), f"${total:,.2f}")

    elif menu == "Admin":
        if role != 'admin':
            st.error("Access Denied")
        else:
            admin_panel()

    elif menu == "Premium":
        st.subheader("Upgrade to Boost Jobs")
        if st.button("Get Premium Subscription"):
            # Ensure price_id is set in Stripe Dashboard
            checkout = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{'price': os.getenv("STRIPE_PRICE_ID"), 'quantity': 1}],
                mode='subscription',
                success_url="https://your-app.streamlit.app/",
                cancel_url="https://your-app.streamlit.app/",
            )
            st.link_button("Pay via Stripe", checkout.url)

    if st.sidebar.button("Logout"):
        sb.auth.sign_out()
        del st.session_state.user
        st.rerun()

def handle_upload(job, file, user_id):
    try:
        file_path = f"{user_id}/{job['id']}_{file.name}"
        sb.storage.from_('proofs').upload(path=file_path, file=file.getvalue(), file_options={"content-type": file.type})
        public_url = sb.storage.from_('proofs').get_public_url(file_path)
        sb.table("jobs").update({"status": "completed", "proof_url": public_url, "completed_at": "now()"}).eq("id", job['id']).execute()
        st.success("Job Completed!")
        st.rerun()
    except Exception as e:
        st.error(f"Upload Error: {e}")

def admin_panel():
    st.subheader("System Overview")
    all_jobs = sb.table("jobs").select("*").execute().data
    if all_jobs:
        df = pd.DataFrame(all_jobs)
        st.dataframe(df)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Export to CSV", data=csv, file_name="jobs.csv")
        
        if st.button("Clear All Jobs"):
            sb.table("jobs").delete().neq("status", "archived").execute()
            st.success("Cleared!")
            st.rerun()

if __name__ == "__main__":
    main()