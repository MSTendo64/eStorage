from .localization import get_available_languages, load_language

def language_processor(request):
    """Добавляет языковые данные в контекст шаблона"""
    current_lang = request.LANGUAGE_CODE
    languages = get_available_languages()
    translations = load_language(current_lang)
    
    return {
        'available_languages': languages,
        'current_language': current_lang,
        't': translations['translations']  # Для удобного доступа к переводам в шаблонах
    } 