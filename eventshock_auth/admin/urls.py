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
    path('logs/', views.system_logs, name='system_logs'),
    path('settings/', views.system_settings, name='system_settings'),
    path('system/stats/', views.system_stats_ajax, name='system_stats_ajax'),
] 