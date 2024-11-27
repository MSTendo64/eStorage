from django.urls import path, include
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('applications/', views.manage_applications, name='manage_applications'),
    path('accounts/', views.manage_accounts, name='manage_accounts'),
    path('accounts/unlink/<int:account_id>/', views.unlink_account, name='unlink_account'),
    path('accounts/link/google/', views.link_google, name='link_google'),
    path('accounts/link/github/', views.link_github, name='link_github'),
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    path('api/userinfo/', views.UserInfoView.as_view(), name='user-info'),
    path('settings/profile/', views.settings_profile, name='settings_profile'),
    path('settings/appearance/', views.settings_appearance, name='settings_appearance'),
    path('settings/api/', views.settings_api, name='settings_api'),
    path('settings/api/create-key/', views.create_api_key, name='create_api_key'),
    path('settings/api/create-token/', views.create_esid_token, name='create_esid_token'),
    path('settings/api/revoke-key/<int:key_id>/', views.revoke_api_key, name='revoke_api_key'),
    path('settings/api/revoke-token/<int:token_id>/', views.revoke_esid_token, name='revoke_esid_token'),
    path('settings/general/', views.settings_general, name='settings_general'),
    path('api/docs/', views.api_docs, name='api_docs'),
]