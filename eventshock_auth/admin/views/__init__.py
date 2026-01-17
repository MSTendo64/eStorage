"""
Модуль views для админ-панели.
Экспортирует все представления для обратной совместимости.
"""

# Dashboard views
from .dashboard_views import dashboard, system_stats_ajax

# User operations
from .user_operations import users_list, user_detail, user_edit, user_create

# Storage operations
from .storage_operations import storage_stats, storage_management, storage_create, storage_edit, storage_delete, storage_test_connection

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
    'storage_management',
    'storage_create',
    'storage_edit',
    'storage_delete',
    'storage_test_connection',
    # System
    'system_logs',
    'system_settings',
]

