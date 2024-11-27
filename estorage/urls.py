"""
URL configuration for estorage project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect, render, HttpResponse
from django.contrib.auth.decorators import user_passes_test
from django.conf.urls import handler400, handler403, handler404, handler500
from django.views.static import serve
import os

def home(request):
    return redirect('dashboard')

def error_400(request, exception):
    return render(request, 'errors/400.html', status=400)

def error_403(request, exception):
    return render(request, 'errors/403.html', status=403)

def error_404(request, exception):
    # Проверяем, является ли запрос запросом к медиафайлу
    if request.path.startswith(settings.MEDIA_URL):
        # Возвращаем стандартную 404 страницу для медиафайлов
        return render(request, 'errors/404.html', {
            'error_message': 'Запрашиваемый файл не найден или был удален.',
            'is_media': True
        }, status=404)
    return render(request, 'errors/404.html', status=404)

def error_500(request):
    return render(request, 'errors/500.html', status=500)

def protected_serve(request, path, document_root=None, show_indexes=False):
    try:
        return serve(request, path, document_root, show_indexes)
    except:
        return error_404(request, None)

handler400 = 'estorage.urls.error_400'
handler403 = 'estorage.urls.error_403'
handler404 = 'estorage.urls.error_404'
handler500 = 'estorage.urls.error_500'

def is_superuser(user):
    return user.is_superuser

# Блокируем стандартную админку
def admin_blocked(request):
    return HttpResponse('Доступ запрещен', status=403)

urlpatterns = [
    path('admin/', admin_blocked),  # Блокируем стандартную админку
    path('esadmin/', include(('eventshock_auth.admin.urls', 'esadmin'), namespace='esadmin')),  # Наша админка
    path('', home, name='home'),
    path('storage/', include('storage.urls')),
    path('auth/', include('eventshock_auth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # В продакшене используем protected_serve для обработки медиафайлов
    urlpatterns += [
        path(f'{settings.MEDIA_URL[1:]}<path:path>', protected_serve, {
            'document_root': settings.MEDIA_ROOT
        }),
    ]
