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

from ..models import UserFile
from ..helpers import ensure_user_folder_exists, generate_unique_filename

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
        
        # Декодируем имя файла если оно было закодировано
        try:
            filename = urllib.parse.unquote(filename)
        except Exception:
            pass
        
        # Путь для временного файла
        os.makedirs(settings.FILE_UPLOAD_TEMP_DIR, exist_ok=True)
        temp_path = os.path.join(
            settings.FILE_UPLOAD_TEMP_DIR,
            f"{request.user.id}_{filename}.part"
        )
        
        # Записываем чанк
        with open(temp_path, 'ab') as f:
            for chunk_data in chunk.chunks():
                f.write(chunk_data)
        
        # Если это последний чанк
        if chunk_number == total_chunks - 1:
            # Перемещаем файл в постоянное хранилище
            user_folder = ensure_user_folder_exists(request.user.id)
            
            # Генерируем уникальное имя файла
            unique_filename = generate_unique_filename(user_folder, filename)
            final_path = os.path.join(user_folder, unique_filename)
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
            
            os.rename(temp_path, final_path)
            
            # Получаем размер файла
            file_size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
            
            # Создаем запись в БД
            UserFile.objects.create(
                user=request.user,
                file=db_file_path,
                filename=unique_filename,
                file_size=file_size
            )
            
            return JsonResponse({'status': 'complete', 'filename': unique_filename})
        
        return JsonResponse({'status': 'chunk_uploaded', 'chunk': chunk_number + 1})
        
    except Exception as e:
        logger.error(f"Upload chunk error: {e}\n{traceback.format_exc()}")
        return JsonResponse({'error': str(e)}, status=400)


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

