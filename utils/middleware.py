from django.utils import translation
from django.urls import resolve, reverse
from django.contrib.auth import logout
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.conf import settings
from django.shortcuts import redirect

class LanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Пытаемся получить язык из профиля пользователя
        if request.user.is_authenticated:
            try:
                from eventshock_auth.models import UserProfile
                profile, created = UserProfile.objects.get_or_create(user=request.user)
                user_language = profile.language
            except Exception:
                # Если не удалось получить профиль, используем язык по умолчанию
                user_language = request.COOKIES.get('django_language', 'ru')
        else:
            # Если пользователь не авторизован, пробуем получить язык из cookie
            user_language = request.COOKIES.get('django_language', 'ru')
        
        # Устанавливаем язык
        translation.activate(user_language)
        request.LANGUAGE_CODE = user_language
        
        response = self.get_response(request)
        return response


class SessionValidationMiddleware:
    """
    Middleware для проверки валидности сессии.
    Если сессия недействительна, автоматически разлогинивает пользователя
    и перенаправляет на страницу логина.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        # URL-адреса, которые не требуют проверки сессии
        self.exempt_paths = [
            '/auth/login/',
            '/auth/register/',
            '/static/',
            '/media/',
            '/favicon.ico',
        ]

    def is_exempt_path(self, path):
        """Проверяет, является ли путь исключением из проверки сессии"""
        for exempt_path in self.exempt_paths:
            if path.startswith(exempt_path):
                return True
        return False

    def __call__(self, request):
        # Пропускаем проверку для исключенных путей
        if self.is_exempt_path(request.path):
            return self.get_response(request)

        # Проверяем только для аутентифицированных пользователей
        if request.user.is_authenticated:
            session_key = request.session.session_key
            
            # Если нет ключа сессии, разлогиниваем
            if not session_key:
                logout(request)
                login_url = reverse(settings.LOGIN_URL)
                return redirect(f'{login_url}?session_expired=1')
            
            try:
                # Проверяем существование сессии в базе данных
                session = Session.objects.get(session_key=session_key)
                
                # Проверяем, не истекла ли сессия
                expiry_date = session.expire_date
                if expiry_date and expiry_date < timezone.now():
                    # Сессия истекла
                    logout(request)
                    session.delete()  # Удаляем истекшую сессию
                    login_url = reverse(settings.LOGIN_URL)
                    return redirect(f'{login_url}?session_expired=1')
                
                # Проверяем, не была ли сессия удалена вручную
                # (проверка наличия данных пользователя в сессии)
                if not request.session.get('_auth_user_id'):
                    # Сессия существует, но данные пользователя отсутствуют
                    logout(request)
                    session.delete()
                    login_url = reverse(settings.LOGIN_URL)
                    return redirect(f'{login_url}?session_expired=1')
                    
            except Session.DoesNotExist:
                # Сессия не найдена в базе данных
                logout(request)
                login_url = reverse(settings.LOGIN_URL)
                return redirect(f'{login_url}?session_expired=1')
            except Exception as e:
                # Ошибка при проверке сессии - логируем и разлогиниваем для безопасности
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Session validation error: {str(e)}")
                logout(request)
                login_url = reverse(settings.LOGIN_URL)
                return redirect(f'{login_url}?session_expired=1')

        response = self.get_response(request)
        return response
