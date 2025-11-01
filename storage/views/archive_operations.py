"""
Операции с архивами: просмотр содержимого, распаковка
"""
import os
import uuid
import shutil
import threading
import time
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone

from ..models import UserFile
from ..helpers import ensure_user_folder_exists, create_json_response
from ..constants import ERROR_FILE_NOT_FOUND, TEMP_FOLDER_PREFIX, CLEANUP_DELAY

logger = __import__('logging').getLogger(__name__)


def delayed_folder_cleanup(folder_path: str, delay: int = CLEANUP_DELAY):
    """Отложенное удаление папки в отдельном потоке"""
    def cleanup():
        time.sleep(delay)
        try:
            if os.path.exists(folder_path):
                shutil.rmtree(folder_path)
        except Exception as e:
            logger.error(f"Error cleaning up folder {folder_path}: {e}")
    
    thread = threading.Thread(target=cleanup)
    thread.daemon = True
    thread.start()


@login_required
def get_archive_contents(request, file_id):
    """Получение содержимого архива"""
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        if not file.is_archive:
            return create_json_response(
                False,
                'Файл не является архивом',
                status=400
            )
            
        contents = file.get_archive_contents()
        return JsonResponse({'contents': contents})
        
    except UserFile.DoesNotExist:
        return create_json_response(False, ERROR_FILE_NOT_FOUND, status=404)


@login_required
def extract_archive(request, file_id):
    """Распаковка архива"""
    temp_extract_folder = None
    
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        if not file.is_archive:
            return create_json_response(
                False,
                'Файл не является архивом',
                status=400
            )
            
        # Создаем временную папку для распаковки
        user_folder = ensure_user_folder_exists(request.user.id)
        temp_extract_folder = os.path.join(
            user_folder,
            f'{TEMP_FOLDER_PREFIX}{file_id}_{uuid.uuid4().hex}'
        )
        os.makedirs(temp_extract_folder, exist_ok=True)
        
        # Распаковываем архив
        success = file.extract_archive(temp_extract_folder)
        
        if success:
            # Перемещаем файлы в основную папку пользователя
            for root, dirs, files in os.walk(temp_extract_folder):
                for filename in files:
                    src_path = os.path.join(root, filename)
                    base, ext = os.path.splitext(filename)
                    unique_filename = f"{base}_{uuid.uuid4().hex[:8]}{ext}"
                    dst_path = os.path.join(user_folder, unique_filename)
                    
                    shutil.move(src_path, dst_path)
                    file_size = os.path.getsize(dst_path) if os.path.exists(dst_path) else 0
                    
                    UserFile.objects.create(
                        user=request.user,
                        file=f'{request.user.id}/{unique_filename}',
                        filename=filename,
                        file_size=file_size
                    )
            
            # Запускаем отложенное удаление временной папки
            delayed_folder_cleanup(temp_extract_folder)
            
            messages.success(request, 'Архив успешно распакован')
            return create_json_response(True)
        else:
            # Удаляем временную папку в случае ошибки
            if os.path.exists(temp_extract_folder):
                shutil.rmtree(temp_extract_folder)
            messages.error(request, 'Ошибка при распаковке архива')
            return create_json_response(False, 'Ошибка при распаковке', status=400)
            
    except UserFile.DoesNotExist:
        return create_json_response(False, ERROR_FILE_NOT_FOUND, status=404)
    except Exception as e:
        logger.error(f"Error extracting archive {file_id}: {e}")
        if temp_extract_folder and os.path.exists(temp_extract_folder):
            shutil.rmtree(temp_extract_folder)
        return create_json_response(False, str(e), status=500)

