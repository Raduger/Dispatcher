import os
import sys
from supabase import create_client

# Add parent folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)

def check_profile_exists(supabase, user_id):
    response = supabase.table("profiles").select("*").eq("id", user_id).execute()
    return len(response.data) > 0

def create_profile(supabase, user_id, email, role):
    supabase.table("profiles").insert({"id": user_id, "email": email, "role": role}).execute()

def get_user_role(supabase, user_id):
    response = supabase.table("profiles").select("role").eq("id", user_id).single().execute()
    return response.data["role"] if response.data else None

def calculate_earnings(supabase, driver_id):
    response = supabase.table("jobs").select("revenue, expense").eq("driver_id", driver_id).eq("status", "completed").execute()
    total = sum((job["revenue"] - job["expense"]) for job in response.data)
    return total
