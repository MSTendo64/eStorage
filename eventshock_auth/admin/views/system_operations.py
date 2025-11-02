"""
Операции с системными настройками и логами в админ-панели
"""
from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from ...models import SystemSettings
from .dashboard_views import is_superuser


@user_passes_test(is_superuser)
def system_logs(request):
    """
    Просмотр системных логов.
    """
    # Здесь будет логика получения системных логов
    return render(request, 'eventshock_auth/admin/system_logs.html', {
        'active_tab': 'logs'
    })


@staff_member_required
def system_settings(request):
    """
    Настройки системы (название сайта, логотип и т.д.).
    """
    settings = SystemSettings.get_settings()
    
    if request.method == 'POST':
        # Обновление названия сайта
        settings.site_name = request.POST.get('site_name', 'eStorage')
        settings.site_name_color = request.POST.get('site_name_color', '#ffffff')
        
        # Обработка логотипа
        if 'remove_logo' in request.POST and settings.site_logo:
            settings.site_logo.delete()
            settings.site_logo = None
        elif request.FILES.get('site_logo'):
            # Удаляем старый логотип, если он есть
            if settings.site_logo:
                settings.site_logo.delete()
            settings.site_logo = request.FILES['site_logo']
        
        settings.save()
        messages.success(request, 'Настройки системы успешно обновлены')
        return redirect('esadmin:system_settings')
    
    return render(request, 'eventshock_auth/admin/system_settings.html', {
        'active_tab': 'settings',
        'settings': settings
    })

