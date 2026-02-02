try:
    from supabase import create_client, Client
except ImportError as e:
    raise ImportError(
        "Supabase client not installed. "
        "Make sure 'supabase' is in requirements.txt"
    ) from e

import os

# ────────────────────────────────────────────────
# SUPABASE CLIENT
# ────────────────────────────────────────────────
def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)

# ────────────────────────────────────────────────
# PROFILE HELPERS
# ────────────────────────────────────────────────
def check_profile_exists(supabase, user_id):
    resp = supabase.table("profiles").select("*").eq("id", user_id).execute()
    return bool(resp.data)

def create_profile(supabase, user_id, email, role):
    supabase.table("profiles").insert({
        "id": user_id,
        "email": email,
        "role": role
    }).execute()

def get_user_role(supabase, user_id):
    resp = supabase.table("profiles").select("role").eq("id", user_id).execute()
    if resp.data:
        return resp.data[0]["role"]
    return None

# ────────────────────────────────────────────────
# JOB HELPERS
# ────────────────────────────────────────────────
def create_job(supabase, title, creator_id, expense=0.0, revenue=0.0,
               lat=None, lon=None, assigned_to=None):
    data = {
        "title": title,
        "user_id": creator_id,
        "expense": expense,
        "revenue": revenue,
        "latitude": lat if lat not in [None, 0.0] else None,
        "longitude": lon if lon not in [None, 0.0] else None,
        "assigned_to": assigned_to,
        "created_at": None  # Supabase can auto-fill if you have a default
    }
    supabase.table("jobs").insert(data).execute()

# ────────────────────────────────────────────────
# EARNINGS CALCULATION
# ────────────────────────────────────────────────
def calculate_earnings(supabase, user_id):
    resp = supabase.table("jobs").select("*").eq("assigned_to", user_id).execute()
    jobs = resp.data or []
    return sum(j.get("revenue", 0.0) - j.get("expense", 0.0) for j in jobs)
