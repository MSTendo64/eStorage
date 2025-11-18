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
    save_text_file,
    raw_file,
    get_raw_link
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
from .share_operations import (
    share_folder_wizard,
    share_folder_email,
    share_folder_link,
    revoke_folder_access,
    update_access_permissions,
    shared_folders_list,
    mount_folder,
    unmount_folder,
    get_link_access_users,
    shared_folder_view,
    shared_file_download
)

__all__ = [
    # File operations
    'dashboard',
    'delete_file',
    'download_file',
    'generate_download_link',
    'generate_download_token',
    'save_text_file',
    'raw_file',
    'get_raw_link',
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
    # Share operations
    'share_folder_wizard',
    'share_folder_email',
    'share_folder_link',
    'revoke_folder_access',
    'update_access_permissions',
    'shared_folders_list',
    'mount_folder',
    'unmount_folder',
    'get_link_access_users',
    'shared_folder_view',
    'shared_file_download',
]

