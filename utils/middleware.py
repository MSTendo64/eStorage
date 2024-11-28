from django.utils import translation
from django.urls import resolve

class LanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Пытаемся получить язык из профиля пользователя
        if request.user.is_authenticated:
            user_language = request.user.userprofile.language
        else:
            # Если пользователь не авторизован, пробуем получить язык из cookie
            user_language = request.COOKIES.get('django_language', 'ru')
        
        # Устанавливаем язык
        translation.activate(user_language)
        request.LANGUAGE_CODE = user_language
        
        response = self.get_response(request)
        return response
