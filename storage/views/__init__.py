"""
Инициализация views модуля.
Экспортирует все view функции для обратной совместимости.
"""
from .file_operations import (
    dashboard,
    delete_file,
    download_file,
    generate_download_link,
    generate_download_token,
    save_text_file
)
from .archive_operations import (
    get_archive_contents,
    extract_archive,
    delayed_folder_cleanup
)
from .video_operations import (
    get_file_metadata,
    get_public_file_metadata,
    get_video_quality,
    get_public_video_quality,
    public_file
)
from .bulk_operations import (
    bulk_delete,
    bulk_download,
    bulk_archive
)
from .public_operations import (
    toggle_file_publicity
)
from .youtube_operations import (
    get_video_info,
    download_progress,
    download_youtube_video,
    video_list
)
from .chunk_upload import (
    upload_chunk,
    check_file
)
from .other_operations import (
    storage_stats
)
from .cleanup import (
    cleanup_temp_folders,
    cleanup_downloads,
    cleanup_on_request
)
from .folder_operations import (
    create_folder,
    rename_folder,
    delete_folder,
    move_files,
    rename_file,
    get_folders_tree
)

__all__ = [
    # File operations
    'dashboard',
    'delete_file',
    'download_file',
    'generate_download_link',
    'generate_download_token',
    'save_text_file',
    # Archive operations
    'get_archive_contents',
    'extract_archive',
    'delayed_folder_cleanup',
    # Video operations
    'get_file_metadata',
    'get_public_file_metadata',
    'get_video_quality',
    'get_public_video_quality',
    'public_file',
    # Bulk operations
    'bulk_delete',
    'bulk_download',
    'bulk_archive',
    # Public operations
    'toggle_file_publicity',
    # YouTube operations
    'get_video_info',
    'download_progress',
    'download_youtube_video',
    'video_list',
    # Chunk upload
    'upload_chunk',
    'check_file',
    # Other operations
    'storage_stats',
    # Cleanup functions
    'cleanup_temp_folders',
    'cleanup_downloads',
    'cleanup_on_request',
    # Folder operations
    'create_folder',
    'rename_folder',
    'delete_folder',
    'move_files',
    'rename_file',
    'get_folders_tree',
]

