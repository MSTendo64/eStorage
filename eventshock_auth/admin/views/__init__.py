"""
Модуль views для админ-панели.
Экспортирует все представления для обратной совместимости.
"""

# Dashboard views
from .dashboard_views import dashboard, system_stats_ajax

# User operations
from .user_operations import users_list, user_detail, user_edit, user_create

# Storage operations
from .storage_operations import storage_stats

# System operations
from .system_operations import system_logs, system_settings

__all__ = [
    # Dashboard
    'dashboard',
    'system_stats_ajax',
    # Users
    'users_list',
    'user_detail',
    'user_edit',
    'user_create',
    # Storage
    'storage_stats',
    # System
    'system_logs',
    'system_settings',
]

