from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from oauth2_provider.views.generic import ProtectedResourceView
from oauth2_provider.models import AccessToken
from .models import UserProfile, LinkedAccount, OAuthApplication, APIKey, ESIDToken
from django.utils import timezone
from datetime import timedelta
import uuid

def generate_client_id():
    return f"client_{uuid.uuid4().hex[:16]}"

def generate_client_secret():
    return uuid.uuid4().hex

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Проверяем, является ли ввод email'ом
        if '@' in username:
            try:
                user = User.objects.get(email=username)
                username = user.username
            except User.DoesNotExist:
                messages.error(request, 'Аккаунт не найден')
                return redirect('login')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Создаем или обновляем ESUID токен
            esid_token, created = ESIDToken.objects.get_or_create(
                user=user,
                defaults={
                    'name': 'Основной токен',
                    'expires_at': timezone.now() + timedelta(days=30)
                }
            )
            if not created:
                esid_token.expires_at = timezone.now() + timedelta(days=30)
                esid_token.save()
            
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Неверные учетные данные')
    
    return render(request, 'eventshock_auth/login.html')

def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        
        if password != password2:
            messages.error(request, 'Пароли не совпадают')
            return redirect('register')
            
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Пользователь с таким именем уже существует')
            return redirect('register')
            
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Пользователь с таким email уже существует')
            return redirect('register')
            
        # Создаем пользователя
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )
        
        # Создаем ESUID токен
        ESIDToken.objects.create(
            user=user,
            name='Основной токен',
            expires_at=timezone.now() + timedelta(days=30)
        )
        
        login(request, user)
        messages.success(request, 'Регистрация успешна! Добро пожаловать в Eventshock Storage.')
        return redirect('dashboard')
        
    return render(request, 'eventshock_auth/register.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

class UserInfoView(ProtectedResourceView):
    def get(self, request, *args, **kwargs):
        token = request.auth
        user = token.user
        profile = UserProfile.objects.get_or_create(user=user)[0]
        
        return JsonResponse({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'avatar': profile.avatar.url if profile.avatar else None
        })

@login_required
def manage_applications(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        redirect_uris = request.POST.get('redirect_uris')
        
        app = OAuthApplication.objects.create(
            name=name,
            client_id=generate_client_id(),
            client_secret=generate_client_secret(),
            redirect_uris=redirect_uris,
            user=request.user
        )
        messages.success(request, 'Приложение успешно создано')
        return redirect('manage_applications')
        
    applications = OAuthApplication.objects.filter(user=request.user)
    return render(request, 'eventshock_auth/manage_applications.html', {
        'applications': applications
    })

@login_required
def manage_accounts(request):
    linked_accounts = LinkedAccount.objects.filter(user=request.user)
    return render(request, 'eventshock_auth/manage_accounts.html', {
        'linked_accounts': linked_accounts
    })

@login_required
def unlink_account(request, account_id):
    try:
        account = LinkedAccount.objects.get(id=account_id, user=request.user)
        account.delete()
        messages.success(request, 'Аккаунт успешно отключен')
    except LinkedAccount.DoesNotExist:
        messages.error(request, 'Аккаунт не найден')
    return redirect('manage_accounts')

@login_required
def link_google(request):
    # Здесь будет логика подключения Google аккаунта
    messages.info(request, 'Подключение Google аккаунтов будет доступно позже')
    return redirect('manage_accounts')

@login_required
def link_github(request):
    # Здесь будет логика подключения GitHub аккаунта
    messages.info(request, 'Подключение GitHub аккаунтов будет доступно позже')
    return redirect('manage_accounts')

@login_required
def settings_profile(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        user = request.user
        user.username = request.POST.get('username')
        user.email = request.POST.get('email')
        user.first_name = request.POST.get('first_name')
        user.last_name = request.POST.get('last_name')
        
        if request.FILES.get('avatar'):
            profile.avatar = request.FILES['avatar']
            profile.save()
            
        user.save()
        messages.success(request, 'Профиль успешно обновлен')
        return redirect('settings_profile')
        
    return render(request, 'eventshock_auth/settings/profile.html', {'active_tab': 'profile'})

@login_required
def settings_appearance(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        profile.theme = request.POST.get('theme', 'light')
        profile.language = request.POST.get('language', 'ru')
        profile.accent_color = request.POST.get('accent_color', '#0d6efd')
        
        # Обработка цвета текста
        text_color_mode = request.POST.get('text_color_mode')
        profile.custom_text_color = (text_color_mode == 'custom')
        if profile.custom_text_color:
            profile.text_color = request.POST.get('text_color', '#000000')
        
        # Обработка фонового изображения
        if 'remove_background' in request.POST:
            if profile.background_image:
                profile.background_image.delete()
                profile.background_image = None
        elif request.FILES.get('background_image'):
            if profile.background_image:
                profile.background_image.delete()
            profile.background_image = request.FILES['background_image']
            
        profile.save()
        
<<<<<<< HEAD
        # Возвращаем JSON с обновленными настройками для AJAX запросов
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'theme': profile.theme,
                'language': profile.language,
                'accent_color': profile.accent_color,
                'custom_text_color': profile.custom_text_color,
                'text_color': profile.text_color
            })
            
        messages.success(request, 'Настройки внешнего вида обновлены')
        return redirect('settings_appearance')
        
    return render(request, 'eventshock_auth/settings/appearance.html', {'active_tab': 'appearance'})
=======
        # Обработка смены языка
        language = request.POST.get('language')
        if language:
            request.user.userprofile.language = language
            request.user.userprofile.save()
            
            # Устанавливаем язык в сессии
            request.session['django_language'] = language
            
            # Устанавливаем cookie для языка
            response = redirect('settings_appearance')
            response.set_cookie('django_language', language, max_age=365*24*60*60)
            
            messages.success(request, 'Настройки внешнего вида обновлены')
            return response
            
    return render(request, 'eventshock_auth/settings/appearance.html', {
        'active_tab': 'appearance'
    })
>>>>>>> a2370a2 (Initial commit)

@login_required
def settings_general(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        profile.developer_mode = request.POST.get('developer_mode') == 'on'
        profile.save()
        messages.success(request, 'Настройки успешно обновлены')
        return redirect('settings_general')
        
    return render(request, 'eventshock_auth/settings/general.html', {'active_tab': 'general'})

@login_required
def settings_api(request):
    if not request.user.userprofile.developer_mode:
        messages.error(request, 'Включите режим разработчика для доступа к API')
        return redirect('settings_general')
        
    context = {
        'active_tab': 'api',
        'api_keys': APIKey.objects.filter(user=request.user),
        'esid_tokens': ESIDToken.objects.filter(user=request.user)
    }
    return render(request, 'eventshock_auth/settings/api.html', context)

@login_required
def create_api_key(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        APIKey.objects.create(user=request.user, name=name)
        messages.success(request, 'API ключ успешно создан')
    return redirect('settings_api')

@login_required
def create_esid_token(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        allowed_origins = request.POST.get('allowed_origins')
        expires_in_days = int(request.POST.get('expires_in', 30))
        
        ESIDToken.objects.create(
            user=request.user,
            name=name,
            allowed_origins=allowed_origins,
            expires_at=timezone.now() + timedelta(days=expires_in_days)
        )
        messages.success(request, 'ESID токен успешно создан')
    return redirect('settings_api')

@login_required
def revoke_api_key(request, key_id):
    try:
        key = APIKey.objects.get(id=key_id, user=request.user)
        key.is_active = False
        key.save()
        messages.success(request, 'API ключ отозван')
    except APIKey.DoesNotExist:
        messages.error(request, 'API ключ не найден')
    return redirect('settings_api')

@login_required
def revoke_esid_token(request, token_id):
    try:
        token = ESIDToken.objects.get(id=token_id, user=request.user)
        token.is_active = False
        token.save()
        messages.success(request, 'ESID токен отозван')
    except ESIDToken.DoesNotExist:
        messages.error(request, 'ESID токен не найден')
    return redirect('settings_api')

@login_required
def api_docs(request):
    if not request.user.userprofile.developer_mode:
        messages.error(request, 'Включите режим разработчика для доступа к документации API')
        return redirect('settings_general')
        
    return render(request, 'eventshock_auth/api_docs.html')
