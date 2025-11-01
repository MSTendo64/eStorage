"""
Модуль views для админ-панели.

Этот файл сохраняется для обратной совместимости.
Все представления теперь находятся в подмодуле views/.
"""

# Импортируем все представления из новых модулей
from .views import (
    # Dashboard
    dashboard,
    system_stats_ajax,
    # Users
    users_list,
    user_detail,
    user_edit,
    user_create,
    # Storage
    storage_stats,
    # System
    system_logs,
    system_settings,
)

# Экспортируем для обратной совместимости
__all__ = [
    'dashboard',
    'system_stats_ajax',
    'users_list',
    'user_detail',
    'user_edit',
    'user_create',
    'storage_stats',
    'system_logs',
    'system_settings',
]
