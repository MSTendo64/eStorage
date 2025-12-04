"""
Операции с пользователями в админ-панели
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import transaction
from ...models import UserProfile
from ..helpers import get_user_storage_stats, validate_storage_quota
from .dashboard_views import is_superuser
from storage.models import UserFile


@user_passes_test(is_superuser)
def users_list(request):
    """
    Список всех пользователей.
    """
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'eventshock_auth/admin/users.html', {
        'active_tab': 'users',
        'users': users
    })


@user_passes_test(is_superuser)
def user_detail(request, user_id):
    """
    Детальная информация о пользователе.
    """
    user = get_object_or_404(User, id=user_id)
    stats = get_user_storage_stats(user)
    
    # Получаем или создаем профиль пользователя
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    context = {
        'active_tab': 'users',
        'user_data': user,
        'storage_used': stats['storage_used_formatted'],
        'files_count': stats['files_count'],
        'joined_at': user.date_joined,
        'last_login': user.last_login,
        'profile': profile
    }
    return render(request, 'eventshock_auth/admin/user_detail.html', context)


@user_passes_test(is_superuser)
def user_edit(request, user_id):
    """
    Редактирование пользователя.
    """
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        # Обновление базовых полей
        user.username = request.POST.get('username', user.username)
        user.email = request.POST.get('email', user.email)
        user.is_active = request.POST.get('is_active') == 'on'
        user.is_staff = request.POST.get('is_staff') == 'on'
        
        # Защита от снятия админки с себя
        if user.id != request.user.id:
            user.is_superuser = request.POST.get('is_superuser') == 'on'
        
        # Обработка квоты хранилища
        quota_str = request.POST.get('storage_quota')
        success, quota_bytes = validate_storage_quota(quota_str)
        
        if not success and quota_str:  # Если указана квота, но она невалидна
            messages.error(request, 'Некорректное значение квоты хранилища')
            return redirect('esadmin:user_edit', user_id=user.id)
        
        # Обновляем профиль пользователя
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if quota_bytes is not None:
            profile.storage_quota = quota_bytes
            profile.save()
        
        # Обработка смены пароля
        new_password = request.POST.get('new_password')
        if new_password:
            user.set_password(new_password)
        
        user.save()
        messages.success(request, 'Пользователь успешно обновлен')
        return redirect('esadmin:user_detail', user_id=user.id)
    
    # Получаем или создаем профиль пользователя
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    return render(request, 'eventshock_auth/admin/user_edit.html', {
        'active_tab': 'users',
        'user_data': user,
        'profile': profile
    })


@user_passes_test(is_superuser)
def user_create(request):
    """
    Создание нового пользователя.
    """
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        # Валидация
        if not username or not email or not password:
            messages.error(request, 'Все поля обязательны для заполнения')
            return redirect('esadmin:user_create')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Пользователь с таким именем уже существует')
            return redirect('esadmin:user_create')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Пользователь с таким email уже существует')
            return redirect('esadmin:user_create')
        
        # Создание пользователя
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )
        
        messages.success(request, 'Пользователь успешно создан')
        return redirect('esadmin:user_detail', user_id=user.id)
    
    return render(request, 'eventshock_auth/admin/user_create.html', {
        'active_tab': 'users'
    })


@user_passes_test(is_superuser)
@require_POST
def user_delete(request, user_id):
    """
    Удаление пользователя вместе с его файлами и профилем.
    """
    user = get_object_or_404(User, id=user_id)

    if user.id == request.user.id:
        messages.error(request, 'Нельзя удалить собственную учетную запись.')
        return redirect('esadmin:users')

    with transaction.atomic():
        # Удаляем пользовательские файлы с диска
        user_files = UserFile.objects.filter(user=user)
        for user_file in user_files:
            if user_file.file:
                user_file.file.delete(save=False)
        user_files.delete()

        # Удаляем аватар, если он есть
        profile = UserProfile.objects.filter(user=user).first()
        if profile:
            if profile.avatar:
                profile.avatar.delete(save=False)
            profile.delete()

        user.delete()

    messages.success(request, 'Пользователь и все его файлы успешно удалены.')
    return redirect('esadmin:users')

