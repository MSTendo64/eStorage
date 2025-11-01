from django.urls import path
from . import views
from .api import youtube

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('download/<str:token>/', views.download_file, name='download_file'),
    path('delete/<int:file_id>/', views.delete_file, name='delete_file'),
    path('generate-link/<int:file_id>/', views.generate_download_link, name='generate_download_link'),
    path('save-text/<int:file_id>/', views.save_text_file, name='save_text_file'),
    path('archive-contents/<int:file_id>/', views.get_archive_contents, name='archive_contents'),
    path('extract-archive/<int:file_id>/', views.extract_archive, name='extract_archive'),
    path('toggle-publicity/<int:file_id>/', views.toggle_file_publicity, name='toggle_file_publicity'),
    path('public/metadata/<str:token>/', views.get_public_file_metadata, name='get_public_file_metadata'),
    path('public/<str:token>/', views.public_file, name='public_file'),
    path('bulk-delete/', views.bulk_delete, name='bulk_delete'),
    path('bulk-download/', views.bulk_download, name='bulk_download'),
    path('bulk-archive/', views.bulk_archive, name='bulk_archive'),
    path('stats/', views.storage_stats, name='storage_stats'),
    path('youtube/download/', views.download_youtube_video, name='youtube_download'),
    path('youtube/preview/', views.get_video_info, name='youtube_preview'),
    path('youtube/progress/', views.download_progress, name='youtube_progress'),
    path('youtube/videos/', views.video_list, name='video_list'),
    path('check-file/', views.check_file, name='check_file'),
    path('upload-chunk/<str:filename>/', views.upload_chunk, name='upload_chunk'),
    path('api/yt-download/', youtube.youtube_download, name='api_youtube_download'),
    path('api/yt-task/<int:task_id>/', youtube.task_status, name='api_task_status'),
    path('metadata/<int:file_id>/', views.get_file_metadata, name='get_file_metadata'),
    path('video-quality/<int:file_id>/<int:quality>/', views.get_video_quality, name='get_video_quality'),
    path('public/video-quality/<str:token>/<int:quality>/', views.get_public_video_quality, name='get_public_video_quality'),
] 