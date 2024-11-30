from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.conf import settings
import yt_dlp
import os
import logging

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def youtube_download(request):
    """
    API endpoint для загрузки видео с YouTube
    POST /api/yt-download/
    
    Параметры:
    - url: URL видео на YouTube
    - format_id: ID формата видео (опционально)
    """
    youtube_url = request.data.get('url')
    format_id = request.data.get('format_id')
    
    if not youtube_url:
        return Response({
            'success': False,
            'error': 'URL не указан'
        }, status=400)
        
    try:
        # Получаем информацию о видео
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
                return Response({
                    'success': False,
                    'error': f'Ошибка при получении информации о видео: {str(e)}'
                }, status=400)

        # Определяем папку для сохранения
        user_folder = os.path.join(settings.MEDIA_ROOT, str(request.user.id))
        os.makedirs(user_folder, exist_ok=True)

        # Настройки для загрузки
        ydl_opts = settings.YOUTUBE_DOWNLOAD_SETTINGS.copy()
        ydl_opts.update({
            'format': format_id if format_id else 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
            'outtmpl': os.path.join(user_folder, '%(title)s.%(ext)s'),
        })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
                logger.info(f"Video downloaded successfully: {youtube_url}")
                
                return Response({
                    'success': True,
                    'title': info.get('title'),
                    'duration': info.get('duration'),
                    'thumbnail': info.get('thumbnail'),
                    'message': 'Видео успешно загружено'
                })
                
        except Exception as e:
            logger.error(f"Error downloading video: {str(e)}")
            return Response({
                'success': False,
                'error': f'Ошибка при загрузке видео: {str(e)}'
            }, status=400)

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return Response({
            'success': False,
            'error': f'Неожиданная ошибка: {str(e)}'
        }, status=500) 