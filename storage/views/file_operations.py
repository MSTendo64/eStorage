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

from ..models import UserFile, DownloadToken
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
            
            # Создание записи в БД
            UserFile.objects.create(
                user=request.user,
                file=f'{request.user.id}/{filename}',
                filename=filename,
                file_size=uploaded_file.size
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
        
    # Получение списка файлов пользователя
    user_files = UserFile.objects.filter(user=request.user)
    return render(request, 'storage/dashboard.html', {'files': user_files})


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

