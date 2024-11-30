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
    try:
        youtube_url = request.data.get('url')
        format_id = request.data.get('format_id')
        
        if not youtube_url:
            return Response({
                'success': False,
                'error': 'URL не указан'
            }, status=400)
            
        # Определяем папку для сохранения
        user_folder = os.path.join(settings.MEDIA_ROOT, str(request.user.id))
        os.makedirs(user_folder, exist_ok=True)

        # Настройки для загрузки
        ydl_opts = settings.YOUTUBE_DOWNLOAD_SETTINGS.copy()
        ydl_opts.update({
            'format': format_id if format_id else 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
            'outtmpl': os.path.join(user_folder, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'nocheckcertificate': True,
            'no_warnings': True
        })

        def progress_hook(d):
            if d['status'] == 'downloading':
                try:
                    total_bytes = d.get('total_bytes')
                    downloaded_bytes = d.get('downloaded_bytes', 0)
                    if total_bytes:
                        percentage = (downloaded_bytes / total_bytes) * 100
                        speed = d.get('speed', 0)
                        speed_mb = speed / 1024 / 1024 if speed else 0
                        from storage.views import progress_queue
                        progress_queue.put(f"{percentage:.1f}:{speed_mb:.2f}")
                except Exception as e:
                    logger.error(f"Progress hook error: {str(e)}")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
                logger.info(f"Video downloaded successfully: {youtube_url}")
                return Response({'success': True})
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=400)

    except Exception as e:
        logger.error(f"API error: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=500) 