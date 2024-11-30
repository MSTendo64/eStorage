from rest_framework.decorators import api_view, permission_classes, renderer_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from ..models import DownloadTask
from ..tasks import VideoDownloader
import threading

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@renderer_classes([JSONRenderer])
def youtube_download(request):
    try:
        url = request.data.get('url')
        format_id = request.data.get('format_id')
        
        if not url:
            return Response({
                'success': False,
                'error': 'URL не указан'
            }, status=400)
            
        # Создаем задачу
        task = DownloadTask.objects.create(
            user=request.user,
            url=url,
            format_id=format_id
        )
        
        # Запускаем загрузку в отдельном потоке
        downloader = VideoDownloader(task.id)
        thread = threading.Thread(target=downloader.download)
        thread.daemon = True
        thread.start()
        
        return Response({
            'success': True,
            'task_id': task.id
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@renderer_classes([JSONRenderer])
def task_status(request, task_id):
    try:
        task = DownloadTask.objects.get(id=task_id, user=request.user)
        return Response({
            'status': task.status,
            'progress': task.progress,
            'speed': task.speed,
            'error': task.error
        })
    except DownloadTask.DoesNotExist:
        return Response({
            'error': 'Задача не найдена'
        }, status=404) 