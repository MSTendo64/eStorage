"""
Представления для дашборда админ-панели
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import psutil
from ..helpers import get_global_storage_stats
from ..constants import CHART_DAYS


def is_superuser(user):
    """Проверка, что пользователь является суперпользователем"""
    return user.is_superuser


@user_passes_test(is_superuser)
def dashboard(request):
    """
    Главная страница дашборда админ-панели.
    """
    if not request.user.is_superuser:
        return redirect('home')
    
    # Получаем статистику
    total_users = User.objects.count()
    stats = get_global_storage_stats()
    
    # Получаем данные для графика
    dates = []
    new_users = []
    
    for i in range(CHART_DAYS):
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
        'total_storage': stats['total_storage_formatted'],
        'total_files': stats['total_files'],
        'chart_labels': dates,
        'chart_data': new_users,
        'recent_actions': recent_actions
    }
    
    return render(request, 'eventshock_auth/admin/dashboard.html', context)


@user_passes_test(is_superuser)
def system_stats_ajax(request):
    """
    AJAX эндпоинт для получения статистики системы (CPU, RAM, Disk).
    """
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return JsonResponse({
            'cpu_percent': cpu_percent,
            'ram_percent': ram.percent,
            'disk_percent': disk.percent,
            'ram_total': ram.total,
            'ram_used': ram.used,
            'disk_total': disk.total,
            'disk_used': disk.used,
            'disk_free': disk.free
        })
    except Exception as e:
        return JsonResponse({
            'error': 'Ошибка при получении статистики системы',
            'details': str(e)
        }, status=500)

