"""
Операции с файлами: загрузка, удаление, скачивание
"""
import os
from typing import Optional
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib import messages
from django.http import Http404, JsonResponse, FileResponse, HttpResponse
from django.urls import reverse
from urllib.parse import quote

from ..models import UserFile, DownloadToken, Folder, MountedFolder, SharedFolderAccess
from ..helpers import (
    ensure_user_folder_exists,
    generate_unique_filename,
    validate_file_size,
    validate_storage_quota,
    create_json_response,
    get_file_path
)
from ..constants import SUCCESS_FILE_UPLOADED, SUCCESS_FILE_DELETED, ERROR_FILE_NOT_FOUND
from eventshock_auth.models import UserProfile

logger = __import__('logging').getLogger(__name__)


@login_required
def dashboard(request):
    """Главная страница с загрузкой и списком файлов"""
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        
        # Валидация размера файла
        size_error = validate_file_size(uploaded_file, request)
        if size_error:
            return size_error
        
        # Валидация квоты хранилища
        quota_error = validate_storage_quota(request.user, uploaded_file.size, request)
        if quota_error:
            return quota_error
            
        # Подготовка папки пользователя
        user_folder = ensure_user_folder_exists(request.user.id)
        
        # Генерация уникального имени файла
        filename = generate_unique_filename(user_folder, uploaded_file.name)
        file_path = os.path.join(user_folder, filename)
        
        # Сохранение файла
        try:
            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            # Получаем текущую папку для загрузки
            folder_id = request.POST.get('folder_id', None)
            folder = None
            if folder_id:
                try:
                    folder = Folder.objects.get(id=folder_id, user=request.user)
                except Folder.DoesNotExist:
                    pass
            
            # Создание записи в БД
            UserFile.objects.create(
                user=request.user,
                file=f'{request.user.id}/{filename}',
                filename=filename,
                file_size=uploaded_file.size,
                folder=folder
            )
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return create_json_response(True, SUCCESS_FILE_UPLOADED)
            
            messages.success(request, SUCCESS_FILE_UPLOADED)
            return redirect('dashboard')
            
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            error_msg = f'Ошибка при загрузке файла: {str(e)}'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return create_json_response(False, error_msg, status=500)
            
            messages.error(request, error_msg)
            return redirect('dashboard')
        
    # Получение текущей папки (из GET параметра)
    folder_id = request.GET.get('folder', None)
    current_folder = None
    if folder_id:
        try:
            current_folder = Folder.objects.get(id=folder_id, user=request.user)
        except Folder.DoesNotExist:
            pass
    
    # Получение списка файлов пользователя в текущей папке
    user_files = UserFile.objects.filter(user=request.user, folder=current_folder)
    
    # Получение списка папок в текущей папке
    folders = Folder.objects.filter(user=request.user, parent=current_folder).order_by('name')
    
    # Получение примонтированных папок (только в корне)
    mounted_folders = []
    if not current_folder:
        from .share_helpers import AccessPermissionManager
        mounted = MountedFolder.objects.filter(user=request.user).select_related(
            'shared_access', 'shared_access__folder', 'shared_access__owner'
        )
        for mount in mounted:
            # Проверяем доступ через менеджер прав
            access = mount.shared_access
            if AccessPermissionManager.can_user_view(request.user, access):
                mounted_folders.append({
                    'folder': access.folder,
                    'owner': access.owner,
                    'mounted': mount,
                    'access': access
                })
    
    # Получение пути навигации
    breadcrumbs = []
    if current_folder:
        parent = current_folder.parent
        breadcrumb_items = [current_folder]
        while parent:
            breadcrumb_items.insert(0, parent)
            parent = parent.parent
        breadcrumbs = breadcrumb_items
    
    # Получаем папки, к которым пользователь предоставил доступ
    shared_by_me = SharedFolderAccess.objects.filter(
        owner=request.user
    ).select_related('folder')
    
    return render(request, 'storage/dashboard.html', {
        'files': user_files,
        'folders': folders,
        'mounted_folders': mounted_folders,
        'current_folder': current_folder,
        'breadcrumbs': breadcrumbs,
        'shared_by_me': shared_by_me
    })


@login_required
def delete_file(request, file_id):
    """Удаление файла"""
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        file_path = get_file_path(file)
        
        if os.path.exists(file_path):
            os.remove(file_path)
        
        file.delete()
        messages.success(request, SUCCESS_FILE_DELETED)
        
    except UserFile.DoesNotExist:
        messages.error(request, ERROR_FILE_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error deleting file {file_id}: {e}")
        messages.error(request, f'Ошибка при удалении файла: {str(e)}')
    
    return redirect('dashboard')


@login_required
def download_file(request, token):
    """Скачивание файла по токену"""
    try:
        download_token = DownloadToken.objects.get(token=token)
        if not download_token.is_valid():
            raise Http404("Ссылка устарела или уже была использована")
            
        file = download_token.file
        file_path = file.file.path
        encoded_filename = quote(file.filename)
        
        response = FileResponse(open(file_path, 'rb'))
        response['Content-Type'] = 'application/octet-stream'
        response['Content-Disposition'] = (
            f'attachment; filename="{encoded_filename}"; '
            f'filename*=UTF-8\'\'{encoded_filename}'
        )
        
        # Помечаем токен как использованный
        download_token.is_used = True
        download_token.save()
        
        return response
            
    except DownloadToken.DoesNotExist:
        raise Http404("Ссылка недействительна")
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise Http404(f"Ошибка при скачивании файла: {str(e)}")


def generate_download_token(file: UserFile) -> str:
    """Генерирует токен для скачивания файла"""
    token = DownloadToken.objects.create(file=file)
    return token.token


@login_required
def generate_download_link(request, file_id):
    """Генерирует ссылку для скачивания файла"""
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        token = generate_download_token(file)
        
        return create_json_response(
            True,
            data={'download_url': f'/storage/download/{token}/'}
        )
        
    except UserFile.DoesNotExist:
        return create_json_response(False, ERROR_FILE_NOT_FOUND, status=404)


@login_required
def save_text_file(request, file_id):
    """Сохранение изменений в текстовом файле"""
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        
        if not file.is_text and not file.is_code:
            return create_json_response(False, 'Файл не является текстовым', status=400)
        
        if request.method != 'POST':
            return create_json_response(False, 'Неверный метод запроса', status=405)
        
        # Получаем содержимое из POST или JSON
        if request.content_type == 'application/json':
            import json
            data = json.loads(request.body)
            content = data.get('content', '')
        else:
            content = request.POST.get('content', '')
        
        # Получаем путь к файлу - используем file.path для Django FileField
        try:
            # Пытаемся получить путь через Django FileField
            if file.file:
                file_path = file.file.path
            else:
                raise AttributeError("file.file is None")
        except (ValueError, AttributeError, OSError) as e:
            # Если file.path недоступен, используем get_file_path
            logger.warning(f"Could not get file.path for file {file_id}, using get_file_path: {e}")
            try:
                file_path = get_file_path(file)
            except Exception as e2:
                logger.error(f"Error in get_file_path for file {file_id}: {e2}")
                return create_json_response(False, f'Ошибка при получении пути к файлу: {str(e2)}', status=500)
        
        # Проверяем, что путь существует или создаем директорию
        try:
            dir_path = os.path.dirname(file_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"Created directory: {dir_path}")
        except OSError as e:
            logger.error(f"Error creating directory for file {file_id}: {e}")
            return create_json_response(False, f'Ошибка при создании директории: {str(e)}', status=500)
        
        # Сохраняем содержимое
        try:
            logger.info(f"Saving text file {file_id} to path: {file_path}")
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Обновляем размер файла
            new_size = os.path.getsize(file_path)
            file.file_size = new_size
            file.save(update_fields=['file_size'])
            
            logger.info(f"Text file {file_id} saved successfully, new size: {new_size} bytes")
            
            return create_json_response(True, 'Файл успешно сохранен')
            
        except Exception as e:
            logger.error(f"Error saving text file {file_id}: {e}")
            return create_json_response(False, f'Ошибка при сохранении: {str(e)}', status=500)
        
    except UserFile.DoesNotExist:
        return create_json_response(False, ERROR_FILE_NOT_FOUND, status=404)
    except Exception as e:
        logger.error(f"Error in save_text_file: {e}")
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)

