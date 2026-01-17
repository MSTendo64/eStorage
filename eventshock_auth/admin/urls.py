from django.urls import path
from . import views

app_name = 'esadmin'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('users/', views.users_list, name='users'),
    path('users/<int:user_id>/', views.user_detail, name='user_detail'),
    path('users/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('users/create/', views.user_create, name='user_create'),
    path('storage/', views.storage_stats, name='storage_stats'),
    path('storage/management/', views.storage_management, name='storage_management'),
    path('storage/create/', views.storage_create, name='storage_create'),
    path('storage/<int:storage_id>/edit/', views.storage_edit, name='storage_edit'),
    path('storage/<int:storage_id>/delete/', views.storage_delete, name='storage_delete'),
    path('storage/<int:storage_id>/test-connection/', views.storage_test_connection, name='storage_test_connection'),
    path('logs/', views.system_logs, name='system_logs'),
    path('settings/', views.system_settings, name='system_settings'),
    path('system/stats/', views.system_stats_ajax, name='system_stats_ajax'),
] 