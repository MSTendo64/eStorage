from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from storage.models import UserFile
from ..models import UserProfile, SystemSettings
import psutil
from django.http import JsonResponse

def is_superuser(user):
    return user.is_superuser

@user_passes_test(is_superuser)
def dashboard(request):
    if not request.user.is_superuser:
        return redirect('home')
        
    # Получаем статистику
    total_users = User.objects.count()
    total_storage = UserFile.objects.aggregate(total=Sum('file_size'))['total'] or 0
    total_files = UserFile.objects.count()
    
    # Получаем данные для графика
    days = 30
    dates = []
    new_users = []
    
    for i in range(days):
        date = timezone.now() - timedelta(days=i)
        dates.insert(0, date.strftime('%d.%m'))
        count = User.objects.filter(
            date_joined__date=date.date()
        ).count()
        new_users.insert(0, count)
    
    # Получаем последние действия
    recent_actions = []  # Здесь будет логика получения последних действий
    
    context = {
        'active_tab': 'dashboard',
        'total_users': total_users,
        'total_storage': f"{total_storage / (1024*1024*1024):.1f} GB",
        'total_files': total_files,
        'chart_labels': dates,
        'chart_data': new_users,
        'recent_actions': recent_actions
    }
    
    return render(request, 'eventshock_auth/admin/dashboard.html', context)

@user_passes_test(is_superuser)
def users_list(request):
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'eventshock_auth/admin/users.html', {
        'active_tab': 'users',
        'users': users
    })

@user_passes_test(is_superuser)
def user_detail(request, user_id):
    user = get_object_or_404(User, id=user_id)
    storage_used = UserFile.objects.filter(user=user).aggregate(
        total=Sum('file_size'))['total'] or 0
    files_count = UserFile.objects.filter(user=user).count()
    
    context = {
        'active_tab': 'users',
        'user_data': user,
        'storage_used': f"{storage_used / (1024*1024*1024):.1f} GB",
        'files_count': files_count,
        'joined_at': user.date_joined,
        'last_login': user.last_login
    }
    return render(request, 'eventshock_auth/admin/user_detail.html', context)

@user_passes_test(is_superuser)
def user_edit(request, user_id):
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        user.username = request.POST.get('username')
        user.email = request.POST.get('email')
        user.is_active = request.POST.get('is_active') == 'on'
        user.is_staff = request.POST.get('is_staff') == 'on'
        
        # Защита от снятия админки с себя
        if user.id != request.user.id:
            user.is_superuser = request.POST.get('is_superuser') == 'on'
        
        # Обработка квоты
        try:
            storage_quota = int(request.POST.get('storage_quota', 10))  # По умолчанию 10 ГБ
            user.userprofile.storage_quota = storage_quota * 1024 * 1024 * 1024  # Конвертируем в байты
            user.userprofile.save()
        except (ValueError, TypeError):
            messages.error(request, 'Некорректное значение квоты')
            return redirect('esadmin:user_edit', user_id=user.id)
        
        if request.POST.get('new_password'):
            user.set_password(request.POST.get('new_password'))
            
        user.save()
        messages.success(request, 'Пользователь успешно обновлен')
        return redirect('esadmin:user_detail', user_id=user.id)
        
    return render(request, 'eventshock_auth/admin/user_edit.html', {
        'active_tab': 'users',
        'user_data': user
    })

@user_passes_test(is_superuser)
def user_create(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Пользователь с таким именем уже существует')
            return redirect('esadmin:user_create')
            
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
def storage_stats(request):
    total_storage = UserFile.objects.aggregate(total=Sum('file_size'))['total'] or 0
    total_files = UserFile.objects.count()
    users_storage = User.objects.annotate(
        storage_used=Sum('userfile__file_size'),
        files_count=Count('userfile')
    ).order_by('-storage_used')
    
    context = {
        'active_tab': 'storage',
        'total_storage': f"{total_storage / (1024*1024*1024):.1f} GB",
        'total_files': total_files,
        'users_storage': users_storage
    }
    return render(request, 'eventshock_auth/admin/storage_stats.html', context)

@user_passes_test(is_superuser)
def system_logs(request):
    # Здесь будет логика получения системных логов
    return render(request, 'eventshock_auth/admin/system_logs.html', {
        'active_tab': 'logs'
    })

@staff_member_required
def system_settings(request):
    settings = SystemSettings.get_settings()
    
    if request.method == 'POST':
        settings.site_name = request.POST.get('site_name', 'eStorage')
        settings.site_name_color = request.POST.get('site_name_color', '#ffffff')
        
        if 'remove_logo' in request.POST and settings.site_logo:
            settings.site_logo.delete()
            settings.site_logo = None
        elif request.FILES.get('site_logo'):
            if settings.site_logo:
                settings.site_logo.delete()
            settings.site_logo = request.FILES['site_logo']
            
        settings.save()
        messages.success(request, 'Настройки системы обновлены')
        return redirect('esadmin:system_settings')
        
    return render(request, 'eventshock_auth/admin/system_settings.html', {
        'settings': settings
    })

@user_passes_test(is_superuser)
def system_stats_ajax(request):
    cpu_percent = psutil.cpu_percent()
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return JsonResponse({
        'cpu_percent': cpu_percent,
        'ram_percent': ram.percent,
        'disk_percent': disk.percent
    })

# ... остальные views для админки ... 