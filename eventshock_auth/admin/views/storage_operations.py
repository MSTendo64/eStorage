"""
Операции со статистикой хранилища в админ-панели
"""
from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from ..helpers import get_global_storage_stats, get_users_with_storage
from .dashboard_views import is_superuser


@user_passes_test(is_superuser)
def storage_stats(request):
    """
    Статистика использования хранилища пользователями.
    """
    stats = get_global_storage_stats()
    users_storage = get_users_with_storage()
    
    context = {
        'active_tab': 'storage',
        'total_storage': stats['total_storage_formatted'],
        'total_files': stats['total_files'],
        'users_storage': users_storage
    }
    return render(request, 'eventshock_auth/admin/storage_stats.html', context)

