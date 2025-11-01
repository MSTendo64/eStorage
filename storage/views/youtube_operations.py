"""
Операции с YouTube: получение информации, загрузка видео
"""
import os
import logging
import queue
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
import yt_dlp

from ..models import YouTubeVideo
from ..helpers import create_json_response, ensure_user_folder_exists

logger = logging.getLogger(__name__)

# Глобальная очередь для прогресса YouTube загрузок
progress_queue = queue.Queue()


def get_video_info(request):
    """Получение информации о YouTube видео"""
    url = request.GET.get('url')
    if not url:
        return create_json_response(False, 'URL не указан', status=400)
    
    try:
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'youtube_include_dash_manifest': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            seen_resolutions = set()
            
            for f in info['formats']:
                if (f.get('ext') == 'mp4' and 
                    f.get('vcodec') != 'none' and 
                    f.get('acodec') != 'none' and 
                    f.get('height')):
                    
                    height = f.get('height', 0)
                    resolution = f'{height}p'
                    
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
                        'tbr': f.get('tbr', 0),
                        'format_note': f.get('format_note', ''),
                    })

            # Сортируем форматы по качеству
            formats.sort(key=lambda x: (x['height'], x.get('tbr', 0)), reverse=True)
            
            # Находим формат 720p или ближайший
            default_format = None
            for f in formats:
                if f['height'] <= 720:
                    default_format = f['format_id']
                    break
            if not default_format and formats:
                default_format = formats[0]['format_id']

            return JsonResponse({
                'success': True,
                'title': info.get('title', ''),
                'description': info.get('description', ''),
                'thumbnail_url': info.get('thumbnail', ''),
                'channel': info.get('uploader', ''),
                'duration': info.get('duration', 0),
                'formats': formats,
                'default_format': default_format
            })
            
    except Exception as e:
        logger.error(f"Error getting video info: {e}", exc_info=True)
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


def download_progress(request):
    """Получение прогресса загрузки YouTube видео через Server-Sent Events"""
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
                    logger.error(f"Stream error: {e}")
                    yield f"data: error:{str(e)}\n\n"
                    break
        except GeneratorExit:
            logger.info("Client disconnected")
        except Exception as e:
            logger.error(f"Stream error: {e}")

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = '*'
    return response


def download_youtube_video(request):
    """Загрузка YouTube видео"""
    if request.method == 'POST':
        youtube_url = request.POST.get('youtube_url')
        format_id = request.POST.get('format_id')
        
        try:
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
                    logger.error(f"Error extracting video info: {e}")
                    raise
                
                duration = info.get('duration', 0)
                
                # Проверяем длительность только для неавторизованных пользователей
                MAX_DURATION_UNAUTH = 1200  # 20 минут
                if not request.user.is_authenticated and duration > MAX_DURATION_UNAUTH:
                    return create_json_response(
                        False,
                        'Для скачивания видео длиннее 20 минут необходимо авторизоваться.',
                        status=403
                    )

            # Определяем папку для сохранения
            if request.user.is_authenticated:
                user_folder = ensure_user_folder_exists(request.user.id)
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
                            speed_mb = (speed / 1024 / 1024) if speed else 0
                            progress_queue.put(f"{percentage:.1f}:{speed_mb:.2f}")
                    except Exception as e:
                        logger.error(f"Error in progress_hook: {e}")

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
                    return create_json_response(True)
            except Exception as e:
                logger.error(f"Error downloading video: {e}")
                return create_json_response(False, f'Ошибка при загрузке видео: {str(e)}', status=500)

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return create_json_response(False, f'Неожиданная ошибка: {str(e)}', status=500)
            
    return render(request, 'storage/youtube_download.html', {
        'max_duration': 20,
        'is_authenticated': request.user.is_authenticated
    })


def video_list(request):
    """Список загруженных YouTube видео"""
    videos = YouTubeVideo.objects.all().order_by('-downloaded_at')
    return render(request, 'storage/video_list.html', {'videos': videos})

