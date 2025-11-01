from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
import os
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, Http404, JsonResponse, FileResponse, StreamingHttpResponse
from django.urls import reverse
from .models import UserFile, DownloadToken, YouTubeVideo
import json
import zipfile
from io import BytesIO
from django.utils import timezone
import shutil
import uuid
from django.core.signals import request_finished
from django.dispatch import receiver
import re
from django.core.cache import cache
import threading
import time
import yt_dlp
import urllib.request
import urllib.parse
import queue
from urllib.parse import quote
import logging

# Создаем глобальную очередь для прогресса
progress_queue = queue.Queue()

@login_required
def dashboard(request):
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        
        # Проверяем размер файла
        if uploaded_file.size > settings.MAX_FILE_SIZE:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': f'Файл слишком большой. Максимальный размер: {settings.MAX_FILE_SIZE / (1024*1024):.0f}MB'}, status=400)
            messages.error(request, f'Файл слишком большой. Максимальный размер: {settings.MAX_FILE_SIZE / (1024*1024):.0f}MB')
            return redirect('dashboard')
        
        # Получаем или создаем профиль пользователя
        from eventshock_auth.models import UserProfile
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        # Проверяем квоту
        if profile.get_used_storage() + uploaded_file.size > profile.storage_quota:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Недостаточно места в хранилище'}, status=400)
            messages.error(request, 'Недостаточно места в хранилище')
            return redirect('dashboard')
            
        user_folder = os.path.join(settings.MEDIA_ROOT, str(request.user.id))
        
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
            
        # Обрабатываем имя файла для избежания конфликтов
        filename = uploaded_file.name
        file_path = os.path.join(user_folder, filename)
        
        # Если файл существует, добавляем суффикс
        counter = 1
        while os.path.exists(file_path):
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{counter}{ext}"
            file_path = os.path.join(user_folder, filename)
            counter += 1
        
        with open(file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
                
        UserFile.objects.create(
            user=request.user,
            file=f'{request.user.id}/{filename}',
            filename=filename
        )
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Файл успешно загружен'})
        
        messages.success(request, 'Файл успешно загружен')
        return redirect('dashboard')
        
    user_files = UserFile.objects.filter(user=request.user)
    return render(request, 'storage/dashboard.html', {'files': user_files})

@login_required
def delete_file(request, file_id):
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        file_path = os.path.join(settings.MEDIA_ROOT, str(file.file))
        if os.path.exists(file_path):
            os.remove(file_path)
        file.delete()
        messages.success(request, 'Файл успешно удален')
    except UserFile.DoesNotExist:
        messages.error(request, 'Файл не найден')
    return redirect('dashboard')

@login_required
def download_file(request, token):
    try:
        download_token = DownloadToken.objects.get(token=token)
        if not download_token.is_valid():
            raise Http404("Ссылка устарела или уже была использована")
            
        file = download_token.file
        
        # Получаем путь к оригинальному файлу
        file_path = file.file.path
        
        # Формируем безопасное имя файла для заголовка Content-Disposition
        filename = file.filename
        encoded_filename = quote(filename)  # Кодируем имя файла для URL
        
        # Открываем файл и создаем response
        response = FileResponse(open(file_path, 'rb'))
        
        # Устанавливаем правильные заголовки для скачивания
        response['Content-Type'] = 'application/octet-stream'
        response['Content-Disposition'] = f'attachment; filename="{encoded_filename}"; filename*=UTF-8\'\'{encoded_filename}'
        
        # Помечаем токен как использованный
        download_token.is_used = True
        download_token.save()
        
        return response
            
    except DownloadToken.DoesNotExist:
        raise Http404("Ссылка недействительна")
    except Exception as e:
        raise Http404(f"Ошибка при скачивании файла: {str(e)}")

def generate_download_token(file):
    token = DownloadToken.objects.create(file=file)
    return token.token

@login_required
def generate_download_link(request, file_id):
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        token = generate_download_token(file)
        
        # Возвращаем JSON с URL для скачивания
        return JsonResponse({
            'success': True,
            'download_url': f'/storage/download/{token}/'
        })
        
    except UserFile.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Файл не найден'
        }, status=404)

@login_required
def get_archive_contents(request, file_id):
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        if not file.is_archive:
            return JsonResponse({'error': 'Файл не является архивом'}, status=400)
            
        contents = file.get_archive_contents()
        return JsonResponse({'contents': contents})
    except UserFile.DoesNotExist:
        return JsonResponse({'error': 'Файл не найден'}, status=404)

# Добавим функцию для отложенного удаления папки
def delayed_folder_cleanup(folder_path, delay=300):  # 5 минут по умолчанию
    def cleanup():
        time.sleep(delay)
        try:
            if os.path.exists(folder_path):
                shutil.rmtree(folder_path)
        except Exception as e:
            print(f"Error cleaning up folder {folder_path}: {e}")
    
    thread = threading.Thread(target=cleanup)
    thread.daemon = True
    thread.start()

@login_required
def extract_archive(request, file_id):
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        if not file.is_archive:
            return JsonResponse({'error': 'Файл не является архивом'}, status=400)
            
        # Создаем временную папку для распаковки с уникальным именем
        user_folder = os.path.join(settings.MEDIA_ROOT, str(request.user.id))
        temp_extract_folder = os.path.join(user_folder, f'temp_extracted_{file_id}_{uuid.uuid4().hex}')
        
        if not os.path.exists(temp_extract_folder):
            os.makedirs(temp_extract_folder)
            
        # Распаковываем архив
        success = file.extract_archive(temp_extract_folder)
        
        if success:
            # Перемещаем файлы в основную папку пользователя
            for root, dirs, files in os.walk(temp_extract_folder):
                for filename in files:
                    src_path = os.path.join(root, filename)
                    # Генерируем уникальное имя файла
                    base, ext = os.path.splitext(filename)
                    unique_filename = f"{base}_{uuid.uuid4().hex[:8]}{ext}"
                    dst_path = os.path.join(user_folder, unique_filename)
                    
                    # Перемещаем файл
                    shutil.move(src_path, dst_path)
                    
                    # Создаем запис в БД
                    UserFile.objects.create(
                        user=request.user,
                        file=f'{request.user.id}/{unique_filename}',
                        filename=filename
                    )
            
            # Запускаем отложенное удаление временной папки
            delayed_folder_cleanup(temp_extract_folder)
            
            messages.success(request, 'Архив успешно распакован')
            return JsonResponse({'success': True})
        else:
            # Удаляем временную папку в случае ошибки
            if os.path.exists(temp_extract_folder):
                shutil.rmtree(temp_extract_folder)
            messages.error(request, 'Ошибка при распаковке архива')
            return JsonResponse({'error': 'Ошибка при распаковке'}, status=400)
            
    except UserFile.DoesNotExist:
        return JsonResponse({'error': 'Файл не найден'}, status=404)
    except Exception as e:
        if os.path.exists(temp_extract_folder):
            shutil.rmtree(temp_extract_folder)
        return JsonResponse({'error': str(e)}, status=500)

# Добавим функцию для очистки всех временных папок
def cleanup_temp_folders():
    media_root = settings.MEDIA_ROOT
    for user_folder in os.listdir(media_root):
        user_path = os.path.join(media_root, user_folder)
        if os.path.isdir(user_path):
            for item in os.listdir(user_path):
                if item.startswith('temp_extracted_'):
                    try:
                        full_path = os.path.join(user_path, item)
                        if os.path.exists(full_path):
                            shutil.rmtree(full_path)
                    except Exception as e:
                        print(f"Error cleaning up temp folder {item}: {e}")

# Запускаем очистку при каждом запросе к extract_archive
@receiver(request_finished)
def cleanup_on_request(sender, **kwargs):
    cleanup_temp_folders()

@login_required
def toggle_file_publicity(request, file_id):
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        file.is_public = not file.is_public
        file.save()
        
        if file.is_public:
            messages.success(request, 'Публичный доступ включен')
            return JsonResponse({
                'status': 'success',
                'is_public': True,
                'public_url': request.build_absolute_uri(file.get_public_url())
            })
        else:
            messages.success(request, 'Публичный доступ отключен')
            return JsonResponse({
                'status': 'success',
                'is_public': False
            })
            
    except UserFile.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Файл не найден'
        }, status=404)

def public_file(request, token):
    try:
        file = UserFile.objects.get(public_token=token, is_public=True)
        
        # Для медиафайлов показываем страницу просмотра
        if file.is_image or file.is_video or file.is_audio:
            return render(request, 'storage/public_file.html', {'file': file})
            
        # Для остальных файлов - скачивание
        response = HttpResponse(file.file, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{file.filename}"'
        return response
        
    except UserFile.DoesNotExist:
        raise Http404("Файл не найден или недоступен")

@login_required
def bulk_delete(request):
    if request.method == 'POST':
        file_ids = request.POST.getlist('file_ids[]')
        files = UserFile.objects.filter(id__in=file_ids, user=request.user)
        
        for file in files:
            file_path = os.path.join(settings.MEDIA_ROOT, str(file.file))
            if os.path.exists(file_path):
                os.remove(file_path)
            file.delete()
            
        return JsonResponse({'success': True, 'message': f'Удалено файлов: {len(file_ids)}'})
    return JsonResponse({'success': False, 'message': 'Метод не поддерживается'}, status=405)

@login_required
def bulk_download(request):
    if request.method == 'POST':
        file_ids = request.POST.getlist('file_ids[]')
        files = UserFile.objects.filter(id__in=file_ids, user=request.user)
        
        # Создаем временный ZIP-файл в памяти
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file in files:
                file_path = os.path.join(settings.MEDIA_ROOT, str(file.file))
                if os.path.exists(file_path):
                    zip_file.write(file_path, file.filename)
        
        # Возвращаем ZIP-файл
        zip_buffer.seek(0)
        response = FileResponse(zip_buffer, content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="selected_files.zip"'
        return response
        
    return JsonResponse({'success': False, 'message': 'Метод не поддерживается'}, status=405)

@login_required
def bulk_archive(request):
    if request.method == 'POST':
        file_ids = request.POST.getlist('file_ids[]')
        files = UserFile.objects.filter(id__in=file_ids, user=request.user)
        
        # Создаем ZIP-архив
        archive_name = f'archive_{timezone.now().strftime("%Y%m%d_%H%M%S")}.zip'
        user_folder = os.path.join(settings.MEDIA_ROOT, str(request.user.id))
        archive_path = os.path.join(user_folder, archive_name)
        
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file in files:
                file_path = os.path.join(settings.MEDIA_ROOT, str(file.file))
                if os.path.exists(file_path):
                    zip_file.write(file_path, file.filename)
        
        # Создаем новый файл в БД
        UserFile.objects.create(
            user=request.user,
            file=f'{request.user.id}/{archive_name}',
            filename=archive_name
        )
        
        return JsonResponse({
            'success': True, 
            'message': f'Создан архив: {archive_name}',
            'archive_name': archive_name
        })
        
    return JsonResponse({'success': False, 'message': 'Метод не поддерживаеся'}, status=405)

# Доавим функцию для очистки старых файлов
def cleanup_downloads():
    downloads_dir = os.path.join(settings.MEDIA_ROOT, 'downloads')
    if os.path.exists(downloads_dir):
        for filename in os.listdir(downloads_dir):
            file_path = os.path.join(downloads_dir, filename)
            try:
                if os.path.isfile(file_path):
                    from django.core.cache import cache
                    # Испольуем езопасный ключ кеша
                    cache_key = f"delete_file_{filename}"
                    if cache.get(cache_key):
                        os.remove(file_path)
                        cache.delete(cache_key)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

# Запускаем очистку при каждом запросе к download_file
@receiver(request_finished)
def cleanup_on_request(sender, **kwargs):
    cleanup_downloads()

@login_required
def storage_stats(request):
    profile = request.user.userprofile
    return JsonResponse({
        'percent': profile.get_storage_percent(),
        'used_formatted': profile.get_used_storage_formatted(),
        'quota_formatted': profile.get_quota_formatted()
    })

def get_video_info(request):
    url = request.GET.get('url')
    if not url:
        return JsonResponse({'success': False, 'error': 'URL не указан'})
    
    try:
        # Получаем информацию о доступных форматах
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'youtube_include_dash_manifest': True,  # Включаем DASH форматы
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Получам список орматов
            formats = []
            seen_resolutions = set()  # Для отслеживания уникальных разрешений
            
            for f in info['formats']:
                # Проверяем только MP4 форматы с видео и аудио
                if (f.get('ext') == 'mp4' and 
                    f.get('vcodec') != 'none' and 
                    f.get('acodec') != 'none' and 
                    f.get('height')):
                    
                    height = f.get('height', 0)
                    resolution = f'{height}p'
                    
                    # Пропускаем дубликаты разрешений
                    if resolution in seen_resolutions:
                        continue
                    
                    seen_resolutions.add(resolution)
                    
                    formats.append({
                        'format_id': f['format_id'],
                        'height': height,
                        'resolution': resolution,
                        'filesize': f.get('filesize', 0),
                        'vcodec': f.get('vcodec', 'unknown'),
                        'fps': f.get('fps', 0),
                        'tbr': f.get('tbr', 0),  # Общий битрейт
                        'format_note': f.get('format_note', ''),
                    })
            
            # Добавляем отдельно все доступные разрешения
            available_formats = ydl.extract_info(url, download=False)['formats']
            for f in available_formats:
                if (f.get('height') and 
                    f'{f["height"]}p' not in seen_resolutions and 
                    f.get('vcodec') != 'none'):
                    
                    resolution = f'{f["height"]}p'
                    seen_resolutions.add(resolution)
                    
                    formats.append({
                        'format_id': f['format_id'],
                        'height': f['height'],
                        'resolution': resolution,
                        'filesize': f.get('filesize', 0),
                        'vcodec': f.get('vcodec', 'unknown'),
                        'fps': f.get('fps', 0),
                        'tbr': f.get('tbr', 0),
                        'format_note': f.get('format_note', ''),
                    })

            # Сортируем форматы по качеству (от высокого к низкому)
            formats.sort(key=lambda x: (x['height'], x.get('tbr', 0)), reverse=True)
            
            # Находим формат 720p или ближайший к нему
            default_format = None
            for f in formats:
                if f['height'] <= 720:
                    default_format = f['format_id']
                    break
            if not default_format and formats:
                default_format = formats[0]['format_id']

            print(f"Available formats: {formats}")  # Для отладки

            data = {
                'success': True,
                'title': info.get('title', ''),
                'thumbnail_url': info.get('thumbnail', ''),
                'channel': info.get('uploader', 'Неизвестный канал'),
                'description': info.get('description', 'Описание отсутствует'),
                'formats': formats,
                'default_format': default_format,
                'duration': info.get('duration', 0),
                'view_count': info.get('view_count', 0)
            }
            return JsonResponse(data)
            
    except Exception as e:
        print(f"Error fetching video info: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Ошибка при получении информации о видео'
        })

def download_progress(request):
    def event_stream():
        try:
            while True:
                try:
                    data = progress_queue.get(timeout=30)
                    if data:
                        yield f"data: {data}\n\n"
                    else:
                        yield "data: ping\n\n"
                except queue.Empty:
                    yield "data: ping\n\n"
                except Exception as e:
                    logger.error(f"Stream error: {str(e)}")
                    yield f"data: error:{str(e)}\n\n"
                    break
        except GeneratorExit:
            logger.info("Client disconnected")
        except Exception as e:
            logger.error(f"Stream error: {str(e)}")

    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = '*'
    return response

def download_youtube_video(request):
    if request.method == 'POST':
        youtube_url = request.POST.get('youtube_url')
        format_id = request.POST.get('format_id')
        
        try:
            # Добавляем обработку ошибок и логирование
            logger = logging.getLogger(__name__)
            
            # Сначала получаем информацию о видео для проверки длительности
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'extract_flat': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(youtube_url, download=False)
                    logger.info(f"Video info extracted: {info.get('title')}")
                except Exception as e:
                    logger.error(f"Error extracting video info: {str(e)}")
                    raise
                
                duration = info.get('duration', 0)
                
                # Проверяем длительность только для неавторизованных пользователей
                if not request.user.is_authenticated and duration > 1200:
                    return JsonResponse({
                        'success': False,
                        'error': 'Для скачивания видео длиннее 20 минут необходимо авторизоваться.'
                    })

            # Определяем папку для сохранения
            if request.user.is_authenticated:
                user_folder = os.path.join(settings.MEDIA_ROOT, str(request.user.id))
                os.makedirs(user_folder, exist_ok=True)
            else:
                temp_folder = os.path.join(settings.MEDIA_ROOT, 'temp_downloads')
                os.makedirs(temp_folder, exist_ok=True)
                user_folder = temp_folder

            def progress_hook(d):
                if d['status'] == 'downloading':
                    try:
                        total_bytes = d.get('total_bytes')
                        downloaded_bytes = d.get('downloaded_bytes', 0)
                        if total_bytes:
                            percentage = (downloaded_bytes / total_bytes) * 100
                            speed = d.get('speed', 0)
                            if speed:
                                speed_mb = speed / 1024 / 1024
                            else:
                                speed_mb = 0
                            progress_queue.put(f"{percentage:.1f}:{speed_mb:.2f}")
                    except Exception as e:
                        logger.error(f"Error in progress_hook: {str(e)}")

            # Настройки для загрузки
            ydl_opts = settings.YOUTUBE_DOWNLOAD_SETTINGS.copy()
            ydl_opts.update({
                'format': format_id if format_id else 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
                'outtmpl': os.path.join(user_folder, '%(title)s.%(ext)s'),
                'progress_hooks': [progress_hook],
            })

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([youtube_url])
                    logger.info(f"Video downloaded successfully: {youtube_url}")
                    return JsonResponse({'success': True})
            except Exception as e:
                logger.error(f"Error downloading video: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'error': f'Ошибка при загрузке видео: {str(e)}'
                })

        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Неожиданная ошибка: {str(e)}'
            })
            
    return render(request, 'storage/youtube_download.html', {
        'max_duration': 20,
        'is_authenticated': request.user.is_authenticated
    })

def video_list(request):
    videos = YouTubeVideo.objects.all().order_by('-downloaded_at')
    return render(request, 'storage/video_list.html', {'videos': videos})

@login_required
@ensure_csrf_cookie
def upload_chunk(request, filename):
    if request.method == 'POST':
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
                return JsonResponse({
                    'error': f'File too large. Maximum size: {settings.MAX_FILE_SIZE / (1024*1024):.0f}MB',
                    'max_size': settings.MAX_FILE_SIZE
                }, status=400)
            
            # Получаем или создаем профиль пользователя
            from eventshock_auth.models import UserProfile
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            
            # Проверяем квоту
            if profile.get_used_storage() + file_size > profile.storage_quota:
                return JsonResponse({
                    'error': 'Not enough storage space',
                    'available': profile.storage_quota - profile.get_used_storage()
                }, status=400)
            
            # Декодируем имя файла если оно было закодировано
            import urllib.parse
            try:
                filename = urllib.parse.unquote(filename)
            except:
                pass
            
            # Путь для временного файла
            os.makedirs(settings.FILE_UPLOAD_TEMP_DIR, exist_ok=True)
            temp_path = os.path.join(settings.FILE_UPLOAD_TEMP_DIR, f"{request.user.id}_{filename}.part")
            
            # Записываем чанк
            with open(temp_path, 'ab') as f:
                for chunk_data in chunk.chunks():
                    f.write(chunk_data)
            
            # Если это последний чанк
            if chunk_number == total_chunks - 1:
                # Перемещаем файл в постоянное хранилище
                user_folder = os.path.join(settings.MEDIA_ROOT, str(request.user.id))
                os.makedirs(user_folder, exist_ok=True)
                
                final_path = os.path.join(user_folder, filename)
                
                # Если файл существует на файловой системе, добавляем суффикс
                counter = 1
                original_path = final_path
                while os.path.exists(final_path):
                    name, ext = os.path.splitext(filename)
                    new_filename = f"{name}_{counter}{ext}"
                    final_path = os.path.join(user_folder, new_filename)
                    filename = new_filename
                    counter += 1
                
                # Вычисляем путь для записи в БД
                db_file_path = f'{request.user.id}/{filename}'
                
                # Проверяем, не существует ли уже запись в БД с таким путем к файлу
                existing_file = UserFile.objects.filter(user=request.user, file=db_file_path).first()
                if existing_file:
                    # Проверяем, существует ли файл физически по этому пути
                    if os.path.exists(final_path):
                        # Файл существует на ФС - это реальный конфликт, переименовываем
                        while os.path.exists(final_path) or UserFile.objects.filter(user=request.user, file=db_file_path).exists():
                            name, ext = os.path.splitext(filename)
                            new_filename = f"{name}_{counter}{ext}"
                            final_path = os.path.join(user_folder, new_filename)
                            filename = new_filename
                            db_file_path = f'{request.user.id}/{filename}'
                            counter += 1
                    else:
                        # Файл не существует на ФС - это сиротская запись в БД, удаляем её
                        existing_file.delete()
                
                os.rename(temp_path, final_path)
                
                # Создаем запись в БД
                UserFile.objects.create(
                    user=request.user,
                    file=db_file_path,
                    filename=filename
                )
                
                return JsonResponse({'status': 'complete', 'filename': filename})
            
            return JsonResponse({'status': 'chunk_uploaded', 'chunk': chunk_number + 1})
            
        except Exception as e:
            import traceback
            logging.error(f"Upload chunk error: {str(e)}\n{traceback.format_exc()}")
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def check_file(request):
    # @login_required гарантирует аутентификацию, поэтому request.user всегда аутентифицирован
    filename = request.GET.get('filename')
    filesize = int(request.GET.get('filesize', 0))
    
    # Проверяем размер файла
    if filesize > settings.MAX_FILE_SIZE:
        return JsonResponse({
            'error': 'File too large',
            'max_size': settings.MAX_FILE_SIZE
        }, status=400)
    
    # Получаем или создаем профиль пользователя
    from eventshock_auth.models import UserProfile
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
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
