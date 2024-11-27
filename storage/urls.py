from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('download/<str:token>/', views.download_file, name='download_file'),
    path('delete/<int:file_id>/', views.delete_file, name='delete_file'),
    path('generate-link/<int:file_id>/', views.generate_download_link, name='generate_download_link'),
    path('archive-contents/<int:file_id>/', views.get_archive_contents, name='archive_contents'),
    path('extract-archive/<int:file_id>/', views.extract_archive, name='extract_archive'),
    path('toggle-publicity/<int:file_id>/', views.toggle_file_publicity, name='toggle_file_publicity'),
    path('public/<str:token>/', views.public_file, name='public_file'),
    path('bulk-delete/', views.bulk_delete, name='bulk_delete'),
    path('bulk-download/', views.bulk_download, name='bulk_download'),
    path('bulk-archive/', views.bulk_archive, name='bulk_archive'),
    path('stats/', views.storage_stats, name='storage_stats'),
    path('youtube/download/', views.download_youtube_video, name='youtube_download'),
    path('youtube/preview/', views.get_video_info, name='youtube_preview'),
    path('youtube/progress/', views.download_progress, name='youtube_progress'),
    path('youtube/videos/', views.video_list, name='video_list'),
] 