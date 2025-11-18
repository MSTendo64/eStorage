"""
Массовые операции с файлами: удаление, скачивание, архивирование
"""
import os
import zipfile
from io import BytesIO
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import JsonResponse, FileResponse
from django.utils import timezone

from ..models import UserFile, Folder, DownloadToken
from ..helpers import ensure_user_folder_exists, create_json_response, get_file_path

logger = __import__('logging').getLogger(__name__)


@login_required
def bulk_delete(request):
    """Массовое удаление файлов"""
    if request.method != 'POST':
        return create_json_response(False, 'Метод не поддерживается', status=405)
    
    try:
        file_ids = request.POST.getlist('file_ids[]')
        files = UserFile.objects.filter(id__in=file_ids, user=request.user)
        
        deleted_count = 0
        for file in files:
            file_path = os.path.join(settings.MEDIA_ROOT, str(file.file))
            if os.path.exists(file_path):
                os.remove(file_path)
            file.delete()
            deleted_count += 1
            
        return create_json_response(
            True,
            f'Удалено файлов: {deleted_count}'
        )
    except Exception as e:
        logger.error(f"Error in bulk_delete: {e}")
        return create_json_response(False, f'Ошибка при удалении: {str(e)}', status=500)


@login_required
def bulk_download(request):
    """Массовое скачивание файлов в ZIP-архиве с сохранением структуры папок"""
    if request.method != 'POST':
        return create_json_response(False, 'Метод не поддерживается', status=405)
    
    try:
        selected_items = request.POST.getlist('file_ids[]')
        
        # Разделяем файлы и папки
        file_ids = []
        folder_ids = []
        for item in selected_items:
            if item.startswith('folder_'):
                folder_ids.append(int(item.replace('folder_', '')))
            else:
                try:
                    file_ids.append(int(item))
                except (ValueError, TypeError):
                    continue  # Пропускаем некорректные значения
        
        # Получаем выбранные файлы
        files = UserFile.objects.filter(id__in=file_ids, user=request.user) if file_ids else []
        
        # Собираем все файлы из выбранных папок (рекурсивно)
        folders_files = []
        if folder_ids:
            folders = Folder.objects.filter(id__in=folder_ids, user=request.user)
            for folder in folders:
                folders_files.extend(get_files_from_folder_recursive(folder))
        
        # Объединяем файлы из выбранных файлов и папок
        all_files = list(files) + folders_files
        # Убираем дубликаты по ID
        seen_ids = set()
        unique_files = []
        for file in all_files:
            if file.id not in seen_ids:
                seen_ids.add(file.id)
                unique_files.append(file)
        all_files = unique_files
        
        # Создаем временный ZIP-файл в памяти
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file in all_files:
                file_path = get_file_path(file)
                if os.path.exists(file_path):
                    # Формируем путь в архиве с учетом папки
                    archive_path = get_archive_path_for_file(file)
                    zip_file.write(file_path, archive_path)
        
        # Возвращаем ZIP-файл
        zip_buffer.seek(0)
        response = FileResponse(zip_buffer, content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="selected_files.zip"'
        return response
        
    except Exception as e:
        logger.error(f"Error in bulk_download: {e}")
        return create_json_response(False, f'Ошибка при создании архива: {str(e)}', status=500)


def get_archive_path_for_file(file):
    """Формирует путь файла в архиве с учетом структуры папок"""
    if not file.folder:
        return file.filename
    
    # Получаем полный путь папки
    folder_path = file.folder.get_full_path()
    # Возвращаем путь с учетом папки
    return f"{folder_path}/{file.filename}"


def get_files_from_folder_recursive(folder):
    """Рекурсивно получает все файлы из папки и подпапок"""
    files = list(folder.files.all())
    
    # Рекурсивно получаем файлы из подпапок
    for subfolder in folder.subfolders.all():
        files.extend(get_files_from_folder_recursive(subfolder))
    
    return files


@login_required
def bulk_archive(request):
    """Создание ZIP-архива из выбранных файлов и папок с сохранением структуры"""
    if request.method != 'POST':
        return create_json_response(False, 'Метод не поддерживается', status=405)
    
    try:
        selected_items = request.POST.getlist('file_ids[]')
        
        # Разделяем файлы и папки
        file_ids = []
        folder_ids = []
        for item in selected_items:
            if item.startswith('folder_'):
                folder_ids.append(int(item.replace('folder_', '')))
            else:
                try:
                    file_ids.append(int(item))
                except (ValueError, TypeError):
                    continue  # Пропускаем некорректные значения
        
        # Получаем выбранные файлы
        files = UserFile.objects.filter(id__in=file_ids, user=request.user) if file_ids else []
        
        # Собираем все файлы из выбранных папок (рекурсивно)
        folders_files = []
        if folder_ids:
            folders = Folder.objects.filter(id__in=folder_ids, user=request.user)
            for folder in folders:
                folders_files.extend(get_files_from_folder_recursive(folder))
        
        # Объединяем файлы из выбранных файлов и папок
        all_files = list(files) + folders_files
        # Убираем дубликаты по ID
        seen_ids = set()
        unique_files = []
        for file in all_files:
            if file.id not in seen_ids:
                seen_ids.add(file.id)
                unique_files.append(file)
        
        # Создаем ZIP-архив
        archive_name = f'archive_{timezone.now().strftime("%Y%m%d_%H%M%S")}.zip'
        user_folder = ensure_user_folder_exists(request.user.id)
        archive_path = os.path.join(user_folder, archive_name)
        
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file in unique_files:
                file_path = get_file_path(file)
                if os.path.exists(file_path):
                    # Формируем путь в архиве с учетом папки
                    archive_path_in_zip = get_archive_path_for_file(file)
                    zip_file.write(file_path, archive_path_in_zip)
        
        # Получаем размер архива
        file_size = os.path.getsize(archive_path) if os.path.exists(archive_path) else 0
        
        # Создаем новый файл в БД
        file = UserFile.objects.create(
            user=request.user,
            file=f'{request.user.id}/{archive_name}',
            filename=archive_name,
            file_size=file_size
        )
        
        # Создаем токен для скачивания при загрузке файла
        DownloadToken.get_or_create_valid_token(file)
        
        return create_json_response(
            True,
            f'Создан архив: {archive_name}',
            data={'archive_name': archive_name}
        )
        
    except Exception as e:
        logger.error(f"Error in bulk_archive: {e}")
        return create_json_response(False, f'Ошибка при создании архива: {str(e)}', status=500)

