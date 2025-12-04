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

        # Режим логотипа
        requested_logo_mode = request.POST.get('logo_mode', SystemSettings.LOGO_MODE_SINGLE)
        available_modes = {choice[0] for choice in SystemSettings.LOGO_MODE_CHOICES}
        settings.logo_mode = requested_logo_mode if requested_logo_mode in available_modes else SystemSettings.LOGO_MODE_SINGLE
        
        # Обновление прокси
        proxy_url = request.POST.get('proxy_url', '').strip()
        if proxy_url:
            settings.proxy_url = proxy_url
        else:
            settings.proxy_url = None
        
        # Обновление доменов для прокси
        proxy_domains = request.POST.get('proxy_domains', '').strip()
        if proxy_domains:
            settings.proxy_domains = proxy_domains
        else:
            settings.proxy_domains = None
        
        # Обработка логотипа
        if 'remove_logo' in request.POST and settings.site_logo:
            settings.site_logo.delete(save=False)
            settings.site_logo = None
        elif request.FILES.get('site_logo'):
            # Удаляем старый логотип, если он есть
            if settings.site_logo:
                settings.site_logo.delete(save=False)
            settings.site_logo = request.FILES['site_logo']

        # Логотип для светлой темы
        if 'remove_logo_light' in request.POST and settings.logo_light:
            settings.logo_light.delete(save=False)
            settings.logo_light = None
        elif request.FILES.get('logo_light'):
            if settings.logo_light:
                settings.logo_light.delete(save=False)
            settings.logo_light = request.FILES['logo_light']

        # Логотип для темной темы
        if 'remove_logo_dark' in request.POST and settings.logo_dark:
            settings.logo_dark.delete(save=False)
            settings.logo_dark = None
        elif request.FILES.get('logo_dark'):
            if settings.logo_dark:
                settings.logo_dark.delete(save=False)
            settings.logo_dark = request.FILES['logo_dark']
        
        settings.save()
        messages.success(request, 'Настройки системы успешно обновлены')
        return redirect('esadmin:system_settings')
    
    return render(request, 'eventshock_auth/admin/system_settings.html', {
        'active_tab': 'settings',
        'settings': settings
    })

