"""
Операции с чанковой загрузкой файлов
"""
import os
import urllib.parse
import logging
import traceback
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings
from django.http import JsonResponse
from eventshock_auth.models import UserProfile

from ..models import UserFile, DownloadToken
from ..helpers import (
    ensure_user_folder_exists, 
    generate_unique_filename,
    select_optimal_storage,
    ensure_storage_user_folder_exists,
    has_any_storage,
    upload_file_to_s3,
    sanitize_filename
)

logger = logging.getLogger(__name__)


@login_required
@ensure_csrf_cookie
def upload_chunk(request, filename):
    """Загрузка файла по частям (chunked upload)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
            
        chunk = request.FILES.get('file')
        if not chunk:
            return JsonResponse({'error': 'No file chunk provided'}, status=400)
            
        chunk_number = int(request.POST.get('chunk', 0))
        total_chunks = int(request.POST.get('chunks', 1))
        file_size = int(request.POST.get('file_size', 0))
        
        # Проверяем размер файла
        if file_size > settings.MAX_FILE_SIZE:
            max_size_mb = settings.MAX_FILE_SIZE / (1024 * 1024)
            return JsonResponse({
                'error': f'File too large. Maximum size: {max_size_mb:.0f}MB',
                'max_size': settings.MAX_FILE_SIZE
            }, status=400)
        
        # Получаем или создаем профиль пользователя
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        
        # Проверяем квоту
        if profile.get_used_storage() + file_size > profile.storage_quota:
            return JsonResponse({
                'error': 'Not enough storage space',
                'available': profile.storage_quota - profile.get_used_storage()
            }, status=400)
        
        # Декодируем и обрабатываем имя файла
        try:
            # Декодируем имя файла если оно было закодировано
            try:
                filename = urllib.parse.unquote(filename)
            except Exception:
                pass
            
            # Обрабатываем возможные проблемы с кодировкой
            if isinstance(filename, bytes):
                try:
                    filename = filename.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        filename = filename.decode('cp1251')
                    except UnicodeDecodeError:
                        filename = filename.decode('latin-1', errors='replace')
            
            # Очищаем имя файла от недопустимых символов
            filename = sanitize_filename(filename)
        except Exception as e:
            logger.error(f"Ошибка при обработке имени файла '{filename}': {e}", exc_info=True)
            return JsonResponse({
                'error': f'Ошибка при обработке имени файла: {str(e)}'
            }, status=400)
        
        # Путь для временного файла (используем безопасное имя)
        os.makedirs(settings.FILE_UPLOAD_TEMP_DIR, exist_ok=True)
        # Используем только безопасные символы для временного файла
        safe_temp_name = f"{request.user.id}_{hash(filename) % 1000000}.part"
        temp_path = os.path.join(settings.FILE_UPLOAD_TEMP_DIR, safe_temp_name)
        
        # Записываем чанк
        with open(temp_path, 'ab') as f:
            for chunk_data in chunk.chunks():
                f.write(chunk_data)
        
        # Если это последний чанк
        if chunk_number == total_chunks - 1:
            # Получаем размер файла
            actual_file_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else file_size
            
            # Выбираем оптимальное хранилище
            selected_storage = select_optimal_storage(actual_file_size)
            if not selected_storage:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return JsonResponse({
                    'error': 'Нет доступного хранилища для загрузки файла'
                }, status=400)
            
            # Подготовка папки пользователя в выбранном хранилище
            if selected_storage.storage_type == 'local':
                user_folder = ensure_storage_user_folder_exists(selected_storage, request.user.id)
                if not user_folder:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    return JsonResponse({
                        'error': 'Ошибка при создании папки в хранилище'
                    }, status=500)
            else:
                # Для обратной совместимости используем стандартную папку
                user_folder = ensure_user_folder_exists(request.user.id)
            
            # Генерируем уникальное имя файла
            unique_filename = generate_unique_filename(user_folder, filename)
            final_path = os.path.join(user_folder, unique_filename)
            
            # Определяем путь для сохранения в БД
            db_file_path = f'{request.user.id}/{unique_filename}'
            
            # Проверяем на дубликаты в БД
            existing_file = UserFile.objects.filter(
                user=request.user,
                file=db_file_path
            ).first()
            
            if existing_file:
                # Если файл существует на ФС - переименовываем
                if os.path.exists(final_path):
                    counter = 1
                    while os.path.exists(final_path) or UserFile.objects.filter(
                        user=request.user,
                        file=db_file_path
                    ).exists():
                        name, ext = os.path.splitext(unique_filename)
                        new_filename = f"{name}_{counter}{ext}"
                        final_path = os.path.join(user_folder, new_filename)
                        unique_filename = new_filename
                        db_file_path = f'{request.user.id}/{unique_filename}'
                        counter += 1
                else:
                    # Сиротская запись в БД - удаляем
                    existing_file.delete()
            
            # Обрабатываем файл в зависимости от типа хранилища
            if selected_storage and selected_storage.storage_type == 's3':
                # Для S3 загружаем файл в хранилище
                s3_key = f"{request.user.id}/{unique_filename}"
                if upload_file_to_s3(selected_storage, temp_path, s3_key):
                    # Удаляем временный файл после успешной загрузки
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                    logger.info(f"Файл успешно загружен в S3 хранилище '{selected_storage.name}'")
                else:
                    # Если загрузка в S3 не удалась, удаляем временный файл и возвращаем ошибку
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                    return JsonResponse({
                        'error': f'Ошибка при загрузке файла в S3 хранилище "{selected_storage.name}". Проверьте настройки подключения.'
                    }, status=500)
                # Для S3 не нужно перемещать файл, он уже в S3
                actual_file_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else actual_file_size
            else:
                # Для локального хранилища или media перемещаем файл
                os.rename(temp_path, final_path)
                actual_file_size = os.path.getsize(final_path) if os.path.exists(final_path) else actual_file_size
            
            # Создаем запись в БД
            file = UserFile.objects.create(
                user=request.user,
                file=db_file_path,
                filename=unique_filename,
                file_size=actual_file_size,
                storage=selected_storage  # Может быть None, если хранилищ нет
            )
            
            # Создаем токен для скачивания при загрузке файла
            DownloadToken.get_or_create_valid_token(file)
            
            return JsonResponse({
                'status': 'complete', 
                'filename': unique_filename,
                'file_id': file.id  # Добавляем ID файла для отслеживания прогресса
            })
        
        return JsonResponse({'status': 'chunk_uploaded', 'chunk': chunk_number + 1})
        
    except OSError as e:
        logger.error(f"OS error in upload chunk: {e}\n{traceback.format_exc()}")
        return JsonResponse({
            'error': f'Ошибка файловой системы: {str(e)}. Возможно, недостаточно места на диске.'
        }, status=500)
    except PermissionError as e:
        logger.error(f"Permission error in upload chunk: {e}\n{traceback.format_exc()}")
        return JsonResponse({
            'error': f'Ошибка доступа: {str(e)}. Проверьте права доступа к папке.'
        }, status=500)
    except Exception as e:
        logger.error(f"Upload chunk error: {e}\n{traceback.format_exc()}")
        return JsonResponse({
            'error': f'Ошибка при загрузке файла: {str(e)}'
        }, status=400)


@login_required
def check_file(request):
    """Проверка статуса загружаемого файла"""
    filename = request.GET.get('filename')
    filesize = int(request.GET.get('filesize', 0))
    
    # Проверяем размер файла
    if filesize > settings.MAX_FILE_SIZE:
        return JsonResponse({
            'error': 'File too large',
            'max_size': settings.MAX_FILE_SIZE
        }, status=400)
    
    # Получаем или создаем профиль пользователя
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    
    # Проверяем доступное место
    user_storage = profile.get_used_storage()
    if user_storage + filesize > profile.storage_quota:
        return JsonResponse({
            'error': 'Not enough storage space',
            'available': profile.storage_quota - user_storage
        }, status=400)
    
    return JsonResponse({
        'chunked': filesize > settings.LARGE_FILE_SIZE_THRESHOLD,
        'chunk_size': settings.CHUNKED_UPLOAD_CHUNK_SIZE
    })
