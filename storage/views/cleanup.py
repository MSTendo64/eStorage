"""
Функции очистки временных файлов и папок
"""
import os
import shutil
import logging
from django.conf import settings
from django.core.signals import request_finished
from django.dispatch import receiver
from django.core.cache import cache

from ..constants import TEMP_FOLDER_PREFIX, TEMP_DOWNLOADS_PREFIX

logger = logging.getLogger(__name__)


def cleanup_temp_folders():
    """Очистка всех временных папок для распаковки архивов"""
    media_root = settings.MEDIA_ROOT
    if not os.path.exists(media_root):
        return
    
    try:
        for user_folder in os.listdir(media_root):
            user_path = os.path.join(media_root, user_folder)
            if not os.path.isdir(user_path):
                continue
                
            for item in os.listdir(user_path):
                if item.startswith(TEMP_FOLDER_PREFIX):
                    try:
                        full_path = os.path.join(user_path, item)
                        if os.path.exists(full_path):
                            shutil.rmtree(full_path)
                            logger.debug(f"Cleaned up temp folder: {item}")
                    except Exception as e:
                        logger.error(f"Error cleaning up temp folder {item}: {e}")
    except Exception as e:
        logger.error(f"Error in cleanup_temp_folders: {e}")


def cleanup_downloads():
    """Очистка старых временных файлов загрузок"""
    downloads_dir = os.path.join(settings.MEDIA_ROOT, 'downloads')
    if not os.path.exists(downloads_dir):
        return
    
    try:
        for filename in os.listdir(downloads_dir):
            file_path = os.path.join(downloads_dir, filename)
            try:
                if os.path.isfile(file_path):
                    cache_key = f"delete_file_{filename}"
                    if cache.get(cache_key):
                        os.remove(file_path)
                        cache.delete(cache_key)
                        logger.debug(f"Cleaned up download file: {filename}")
            except Exception as e:
                logger.error(f"Error deleting {file_path}: {e}")
    except Exception as e:
        logger.error(f"Error in cleanup_downloads: {e}")


@receiver(request_finished)
def cleanup_on_request(sender, **kwargs):
    """Запускает очистку временных файлов после каждого запроса"""
    cleanup_temp_folders()
    cleanup_downloads()

