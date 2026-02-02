# utils/utils.py
from supabase import create_client

def get_supabase():
    import os
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)

def check_profile_exists(supabase, user_id):
    resp = supabase.table("profiles").select("*").eq("id", user_id).execute()
    return bool(resp.data)

def create_profile(supabase, user_id, email, role):
    supabase.table("profiles").insert({"id": user_id, "email": email, "role": role}).execute()

def get_user_role(supabase, user_id):
    resp = supabase.table("profiles").select("role").eq("id", user_id).execute()
    if resp.data:
        return resp.data[0]["role"]
    return None

def calculate_earnings(supabase, user_id):
    resp = supabase.table("jobs").select("revenue, expense").eq("user_id", user_id).execute()
    total = 0
    for job in resp.data or []:
        total += (job.get("revenue", 0) or 0) - (job.get("expense", 0) or 0)
    return total
