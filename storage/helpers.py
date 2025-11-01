"""
Вспомогательные функции для работы с файлами
"""
import os
import uuid
from typing import Tuple, Optional, Union
from django.conf import settings
from django.http import JsonResponse, HttpRequest, HttpResponseRedirect
from django.contrib import messages
from django.shortcuts import redirect
from eventshock_auth.models import UserProfile


def get_user_folder_path(user_id: int) -> str:
    """Возвращает путь к папке пользователя"""
    return os.path.join(settings.MEDIA_ROOT, str(user_id))


def ensure_user_folder_exists(user_id: int) -> str:
    """Создает папку пользователя, если её нет, и возвращает путь"""
    user_folder = get_user_folder_path(user_id)
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)
    return user_folder


def generate_unique_filename(user_folder: str, original_filename: str) -> str:
    """
    Генерирует уникальное имя файла, избегая конфликтов.
    Возвращает имя файла без полного пути.
    """
    filename = original_filename
    file_path = os.path.join(user_folder, filename)
    
    counter = 1
    while os.path.exists(file_path):
        name, ext = os.path.splitext(original_filename)
        filename = f"{name}_{counter}{ext}"
        file_path = os.path.join(user_folder, filename)
        counter += 1
    
    return filename


def validate_file_size(uploaded_file, request: HttpRequest) -> Optional[Union[JsonResponse, HttpResponseRedirect]]:
    """
    Проверяет размер файла. Возвращает JsonResponse или HttpResponseRedirect с ошибкой, 
    если файл слишком большой. Иначе возвращает None.
    """
    if uploaded_file.size > settings.MAX_FILE_SIZE:
        max_size_mb = settings.MAX_FILE_SIZE / (1024 * 1024)
        error_msg = f'Файл слишком большой. Максимальный размер: {max_size_mb:.0f}MB'
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': error_msg}, status=400)
        
        messages.error(request, error_msg)
        return redirect('dashboard')
    
    return None


def validate_storage_quota(user, file_size: int, request: HttpRequest) -> Optional[Union[JsonResponse, HttpResponseRedirect]]:
    """
    Проверяет доступность места в хранилище. Возвращает JsonResponse или HttpResponseRedirect 
    с ошибкой, если места недостаточно. Иначе возвращает None.
    """
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    if profile.get_used_storage() + file_size > profile.storage_quota:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'Недостаточно места в хранилище'}, status=400)
        
        messages.error(request, 'Недостаточно места в хранилище')
        return redirect('dashboard')
    
    return None


def create_json_response(success: bool, message: str = None, data: dict = None, 
                         status: int = 200) -> JsonResponse:
    """Создает стандартизированный JSON ответ"""
    response_data = {'success': success}
    
    if message:
        response_data['message' if success else 'error'] = message
    
    if data:
        response_data.update(data)
    
    return JsonResponse(response_data, status=status)


def get_file_path(user_file) -> str:
    """Возвращает полный путь к файлу на диске"""
    return os.path.join(settings.MEDIA_ROOT, str(user_file.file))

