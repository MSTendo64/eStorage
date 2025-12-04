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
    settings = SystemSettings.get_settings()

    user_theme = getattr(
        getattr(getattr(request, 'user', None), 'userprofile', None),
        'theme',
        None,
    ) or 'dark'

    normalized_theme = user_theme.lower() if isinstance(user_theme, str) else 'dark'
    if normalized_theme not in ('light', 'dark'):
        normalized_theme = 'dark'

    return {
        'system_settings': settings,
        'system_theme_logo': settings.get_logo_for_theme(normalized_theme),
        'system_theme_name': normalized_theme,
    }