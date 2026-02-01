from utils.utils import get_supabase

def load_translations(language="en"):
    supabase = get_supabase()
    response = supabase.table("translations").select("key, value").eq("language", language).execute()
    return {item["key"]: item["value"] for item in response.data}
