import streamlit as st

def load_translations(supabase_client):
    """Fetch all translations once and cache them."""
    if 'translation_cache' not in st.session_state:
        response = supabase_client.table("translations").select("language, key, value").execute()
        cache = {}
        for item in response.data:
            lang = item['language']
            if lang not in cache:
                cache[lang] = {}
            cache[lang][item['key']] = item['value']
        st.session_state.translation_cache = cache

def t(key):
    """Retrieve translated string with English fallback."""
    lang = st.session_state.get('lang', 'en')
    cache = st.session_state.get('translation_cache', {})
    return cache.get(lang, {}).get(key, cache.get('en', {}).get(key, key))