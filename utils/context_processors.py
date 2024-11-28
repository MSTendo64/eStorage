from django.utils.translation import get_language
from .localization import get_available_languages, load_language
from eventshock_auth.models import SystemSettings

def language_processor(request):
    """Добавляет языковые данные в контекст шаблона"""
    current_lang = get_language() or 'ru'
    languages = get_available_languages()
    translations = load_language(current_lang)
    
    return {
        'available_languages': languages,
        'current_language': current_lang,
        't': translations['translations']
    }

def system_settings(request):
    return {
        'system_settings': SystemSettings.get_settings()
    } 