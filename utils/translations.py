import streamlit as st

# 11 Languages mapping
LANGUAGES = {
    'en': 'English', 'sw': 'Swahili', 'de': 'Deutsch', 'it': 'Italiano', 
    'fr': 'French', 'pt': 'Portuguese', 'es': 'Spanish', 'nl': 'Dutch', 
    'ru': 'Russian', 'uk': 'Ukrainian', 'tr': 'Turkish'
}

def load_translations(supabase_client):
    """
    Fetches all translations from the Supabase 'translations' table 
    and caches them in Streamlit session state.
    """
    if 'translation_cache' not in st.session_state:
        try:
            response = supabase_client.table("translations").select("language, key, value").execute()
            
            # Reorganize data into: { 'en': {'login': 'Login'}, 'es': {...} }
            cache = {}
            for item in response.data:
                lang = item['language']
                if lang not in cache:
                    cache[lang] = {}
                cache[lang][item['key']] = item['value']
            
            st.session_state.translation_cache = cache
        except Exception as e:
            st.error(f"Translation Error: {e}")
            # Fallback empty cache
            st.session_state.translation_cache = {}

def translate(key, lang_code='en'):
    """
    Retrieves the translated string for a given key and language.
    Falls back to English, then to the key itself if not found.
    """
    cache = st.session_state.get('translation_cache', {})
    
    # Try requested language
    lang_dict = cache.get(lang_code, {})
    if key in lang_dict:
        return lang_dict[key]
    
    # Try English fallback
    en_dict = cache.get('en', {})
    return en_dict.get(key, key)