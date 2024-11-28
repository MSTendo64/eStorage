import json
import os
from django.conf import settings

def load_language(lang_code):
    """Загружает языковой файл"""
    lang_file = os.path.join(settings.BASE_DIR, 'lang', f'{lang_code}.json')
    try:
        with open(lang_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # Если файл не найден, возвращаем английский как язык по умолчанию
        with open(os.path.join(settings.BASE_DIR, 'lang', 'en.json'), 'r', encoding='utf-8') as f:
            return json.load(f)

def get_available_languages():
    """Возвращает список доступных языков"""
    lang_dir = os.path.join(settings.BASE_DIR, 'lang')
    languages = []
    for file in os.listdir(lang_dir):
        if file.endswith('.json'):
            with open(os.path.join(lang_dir, file), 'r', encoding='utf-8') as f:
                lang_data = json.load(f)
                languages.append({
                    'id': lang_data['id'],
                    'name': lang_data['name']
                })
    return languages

def get_translation(key, lang_code):
    """Получает перевод по ключу"""
    lang_data = load_language(lang_code)
    keys = key.split('.')
    value = lang_data['translations']
    for k in keys:
        if k in value:
            value = value[k]
        else:
            return key
    return value 