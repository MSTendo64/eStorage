"""
Views для приложения storage.
Функции импортируются из модулей в подпапке views/ для лучшей организации кода.
Этот файл поддерживает обратную совместимость, экспортируя все функции.
"""
# Импортируем все функции из модулей
from .views import (
    # File operations
    dashboard,
    delete_file,
    download_file,
    generate_download_link,
    generate_download_token,
    # Archive operations
    get_archive_contents,
    extract_archive,
    delayed_folder_cleanup,
    # Video operations
    get_file_metadata,
    get_public_file_metadata,
    get_video_quality,
    get_public_video_quality,
    public_file,
    # Bulk operations
    bulk_delete,
    bulk_download,
    bulk_archive,
    # Public operations
    toggle_file_publicity,
    # Chunk upload
    upload_chunk,
    check_file,
    # Other operations
    storage_stats,
    # Cleanup functions
    cleanup_temp_folders,
    cleanup_downloads,
    cleanup_on_request,
)

# Экспортируем все функции для обратной совместимости
__all__ = [
    'dashboard',
    'delete_file',
    'download_file',
    'generate_download_link',
    'generate_download_token',
    'get_archive_contents',
    'extract_archive',
    'delayed_folder_cleanup',
    'get_file_metadata',
    'get_public_file_metadata',
    'get_video_quality',
    'get_public_video_quality',
    'public_file',
    'bulk_delete',
    'bulk_download',
    'bulk_archive',
    'toggle_file_publicity',
    'upload_chunk',
    'check_file',
    'storage_stats',
    'cleanup_temp_folders',
    'cleanup_downloads',
    'cleanup_on_request',
]
