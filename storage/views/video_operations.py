"""
Операции с видео: метаданные, качество, публичный доступ
"""
import os
import logging
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse, FileResponse
from django.shortcuts import render

from ..models import UserFile
from ..utils import get_video_metadata, get_available_qualities, get_video_quality_path
from ..helpers import create_json_response, get_file_path

logger = logging.getLogger(__name__)


def _get_video_metadata_with_qualities(file_path: str) -> dict:
    """Вспомогательная функция для получения метаданных с доступными качествами"""
    metadata = get_video_metadata(file_path)
    
    if metadata:
        height = metadata.get('height')
        if height and height > 144:
            metadata['available_qualities'] = get_available_qualities(height)
        else:
            metadata['available_qualities'] = [height] if height else []
    
    return metadata


@login_required
def get_file_metadata(request, file_id):
    """API endpoint для получения метаданных видео файла"""
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        
        if not file.is_video:
            return create_json_response(
                False,
                'Файл не является видео',
                status=400
            )
        
        try:
            file_path = file.file.path
        except Exception as e:
            logger.error(f"Error getting file path: {e}")
            return create_json_response(
                False,
                f'Ошибка при получении пути к файлу: {str(e)}',
                status=500
            )
        
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return create_json_response(
                False,
                'Файл не найден на диске',
                status=404
            )
        
        metadata = _get_video_metadata_with_qualities(file_path)
        
        if metadata:
            return JsonResponse({'success': True, 'metadata': metadata})
        else:
            return create_json_response(
                False,
                'Не удалось получить метаданные видео. Возможно, ffprobe не установлен или файл поврежден.',
                status=500
            )
            
    except UserFile.DoesNotExist:
        return create_json_response(False, 'Файл не найден', status=404)
    except Exception as e:
        logger.error(f"Error in get_file_metadata: {e}", exc_info=True)
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


def get_public_file_metadata(request, token):
    """API endpoint для получения метаданных публичного видео файла"""
    try:
        file = UserFile.objects.get(public_token=token, is_public=True)
        
        if not file.is_video:
            return create_json_response(
                False,
                'Файл не является видео',
                status=400
            )
        
        try:
            file_path = file.file.path
        except Exception as e:
            logger.error(f"Error getting file path: {e}")
            return create_json_response(
                False,
                f'Ошибка при получении пути к файлу: {str(e)}',
                status=500
            )
        
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return create_json_response(
                False,
                'Файл не найден на диске',
                status=404
            )
        
        metadata = _get_video_metadata_with_qualities(file_path)
        
        if metadata:
            return JsonResponse({'success': True, 'metadata': metadata})
        else:
            return create_json_response(
                False,
                'Не удалось получить метаданные видео. Возможно, ffprobe не установлен или файл поврежден.',
                status=500
            )
            
    except UserFile.DoesNotExist:
        return create_json_response(False, 'Файл не найден', status=404)
    except Exception as e:
        logger.error(f"Error in get_public_file_metadata: {e}", exc_info=True)
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


@login_required
def get_video_quality(request, file_id, quality):
    """API endpoint для получения видео в указанном качестве"""
    try:
        try:
            target_height = int(quality)
        except ValueError:
            return create_json_response(False, 'Некорректное качество видео', status=400)
        
        file = UserFile.objects.get(id=file_id, user=request.user)
        
        if not file.is_video:
            return create_json_response(False, 'Файл не является видео', status=400)
        
        try:
            file_path = file.file.path
        except Exception as e:
            logger.error(f"Error getting file path: {e}")
            return create_json_response(
                False,
                f'Ошибка при получении пути к файлу: {str(e)}',
                status=500
            )
        
        if not os.path.exists(file_path):
            return create_json_response(False, 'Файл не найден на диске', status=404)
        
        metadata = get_video_metadata(file_path)
        if not metadata:
            return create_json_response(False, 'Не удалось получить метаданные видео', status=500)
        
        original_height = metadata.get('height')
        if not original_height:
            return create_json_response(
                False,
                'Не удалось определить исходное разрешение видео',
                status=500
            )
        
        # Если запрошенное качество равно или выше исходного, возвращаем оригинал
        if target_height >= original_height:
            file_handle = open(file_path, 'rb')
            response = FileResponse(file_handle, content_type='video/mp4')
            response['Content-Disposition'] = f'inline; filename="{file.filename}"'
            response['Accept-Ranges'] = 'bytes'
            return response
        
        # Получаем или создаем видео в нужном качестве
        quality_path = get_video_quality_path(file_path, target_height)
        
        if not quality_path:
            return create_json_response(
                False,
                'Не удалось перекодировать видео. Убедитесь, что ffmpeg установлен.',
                status=500
            )
        
        file_handle = open(quality_path, 'rb')
        response = FileResponse(file_handle, content_type='video/mp4')
        response['Content-Disposition'] = f'inline; filename="{file.filename}"'
        response['Accept-Ranges'] = 'bytes'
        return response
        
    except UserFile.DoesNotExist:
        return create_json_response(False, 'Файл не найден', status=404)
    except Exception as e:
        logger.error(f"Error in get_video_quality: {e}", exc_info=True)
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


@login_required
def get_optimal_quality(request, file_id):
    """API endpoint для получения оптимального качества видео на основе состояния сервера и сети"""
    try:
        try:
            file = UserFile.objects.get(id=file_id, user=request.user)
        except UserFile.DoesNotExist:
            logger.error(f"File not found: {file_id}")
            return create_json_response(False, 'Файл не найден', status=404)
        
        if not file.is_video:
            return create_json_response(False, 'Файл не является видео', status=400)
        
        try:
            file_path = file.file.path
        except Exception as e:
            logger.error(f"Error getting file path for file_id {file_id}: {e}", exc_info=True)
            return create_json_response(False, f'Ошибка при получении пути к файлу: {str(e)}', status=500)
        
        if not os.path.exists(file_path):
            logger.error(f"File path does not exist: {file_path}")
            return create_json_response(False, 'Файл не найден на диске', status=404)
        
        try:
            metadata = get_video_metadata(file_path)
        except Exception as e:
            logger.error(f"Error getting video metadata: {e}", exc_info=True)
            return create_json_response(False, f'Ошибка получения метаданных: {str(e)}', status=500)
        
        if not metadata:
            return create_json_response(False, 'Не удалось получить метаданные видео', status=500)
        
        original_height = metadata.get('height')
        if not original_height:
            logger.error(f"Could not determine original height for file_id {file_id}")
            return create_json_response(False, 'Не удалось определить исходное разрешение видео', status=500)
        
        try:
            available_qualities = get_available_qualities(original_height)
        except Exception as e:
            logger.error(f"Error getting available qualities: {e}", exc_info=True)
            return create_json_response(False, f'Ошибка получения доступных качеств: {str(e)}', status=500)
        
        # Проверяем, что есть доступные качества
        if not available_qualities or len(available_qualities) == 0:
            logger.warning(f"No available qualities for file_id {file_id}, using original height")
            available_qualities = [original_height]
        
        # Получаем метрики от клиента
        try:
            network_speed = float(request.GET.get('network_speed', 0))  # байт/сек
        except (ValueError, TypeError):
            network_speed = None
        
        try:
            buffer_health = float(request.GET.get('buffer_health', 100))  # процент
        except (ValueError, TypeError):
            buffer_health = None
        
        is_waiting = request.GET.get('is_waiting', 'false').lower() == 'true'  # видео остановилось
        
        # Получаем метрики сервера (упрощенная версия)
        server_load = 0
        cpu_percent = 0
        memory_percent = 0
        try:
            import psutil
            # Используем interval=None для неблокирующего вызова
            cpu_percent = psutil.cpu_percent(interval=None)
            memory_percent = psutil.virtual_memory().percent
            server_load = (cpu_percent + memory_percent) / 2
        except ImportError:
            # psutil не установлен - используем значения по умолчанию
            server_load = 0
        except Exception as e:
            # Любая другая ошибка при получении метрик
            logger.warning(f"Could not get server metrics: {e}")
            server_load = 0
        
        # Определяем оптимальное качество
        optimal_quality = original_height
        
        # Если видео остановилось из-за нехватки данных - понижаем качество
        if is_waiting:
            # Находим следующее более низкое качество
            for q in reversed(available_qualities):
                if q < optimal_quality:
                    optimal_quality = q
                    break
        else:
            # Анализируем метрики
            
            # Если сервер перегружен (>80%), понижаем качество
            if server_load > 80:
                for q in reversed(available_qualities):
                    if q < optimal_quality:
                        optimal_quality = q
                        break
            
            # Если низкая скорость сети (< 100 KB/s), понижаем качество
            if network_speed and network_speed < 100000:  # 100 KB/s
                for q in reversed(available_qualities):
                    if q < optimal_quality:
                        optimal_quality = q
                        break
            
            # Если буфер пуст (< 20%), понижаем качество
            if buffer_health and buffer_health < 20:
                for q in reversed(available_qualities):
                    if q < optimal_quality:
                        optimal_quality = q
                        break
            
            # Если все хорошо и буфер > 80%, можно попробовать повысить
            if buffer_health and buffer_health > 80 and network_speed and network_speed > 500000 and server_load < 50:
                # Находим следующее более высокое качество
                for q in available_qualities:
                    if q > optimal_quality and q <= original_height:
                        optimal_quality = q
                        break
        
        # Определяем рекомендацию
        try:
            if is_waiting or (buffer_health is not None and buffer_health < 20) or (network_speed is not None and network_speed < 100000):
                recommendation = 'decrease'
            elif buffer_health is not None and buffer_health > 80 and network_speed is not None and network_speed > 500000:
                recommendation = 'increase'
            else:
                recommendation = 'maintain'
        except Exception as e:
            logger.warning(f"Error determining recommendation: {e}")
            recommendation = 'maintain'
        
        return JsonResponse({
            'success': True,
            'optimal_quality': optimal_quality,
            'available_qualities': available_qualities,
            'server_load': server_load,
            'recommendation': recommendation
        })
        
    except UserFile.DoesNotExist:
        return create_json_response(False, 'Файл не найден', status=404)
    except Exception as e:
        logger.error(f"Error in get_optimal_quality: {e}", exc_info=True)
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


def get_optimal_quality_public(request, token):
    """API endpoint для получения оптимального качества публичного видео"""
    try:
        try:
            file = UserFile.objects.get(public_token=token, is_public=True)
        except UserFile.DoesNotExist:
            logger.error(f"Public file not found with token: {token}")
            return create_json_response(False, 'Файл не найден или недоступен', status=404)
        
        if not file.is_video:
            return create_json_response(False, 'Файл не является видео', status=400)
        
        try:
            file_path = file.file.path
        except Exception as e:
            logger.error(f"Error getting file path for token {token}: {e}", exc_info=True)
            return create_json_response(False, f'Ошибка при получении пути к файлу: {str(e)}', status=500)
        
        if not os.path.exists(file_path):
            logger.error(f"File path does not exist: {file_path}")
            return create_json_response(False, 'Файл не найден на диске', status=404)
        
        try:
            metadata = get_video_metadata(file_path)
        except Exception as e:
            logger.error(f"Error getting video metadata for token {token}: {e}", exc_info=True)
            return create_json_response(False, f'Ошибка получения метаданных: {str(e)}', status=500)
        
        if not metadata:
            return create_json_response(False, 'Не удалось получить метаданные видео', status=500)
        
        original_height = metadata.get('height')
        if not original_height:
            logger.error(f"Could not determine original height for token {token}")
            return create_json_response(False, 'Не удалось определить исходное разрешение видео', status=500)
        
        try:
            available_qualities = get_available_qualities(original_height)
        except Exception as e:
            logger.error(f"Error getting available qualities for token {token}: {e}", exc_info=True)
            return create_json_response(False, f'Ошибка получения доступных качеств: {str(e)}', status=500)
        
        # Проверяем, что есть доступные качества
        if not available_qualities or len(available_qualities) == 0:
            logger.warning(f"No available qualities for token {token}, using original height")
            available_qualities = [original_height]
        
        # Получаем метрики от клиента
        try:
            network_speed = float(request.GET.get('network_speed', 0))
        except (ValueError, TypeError):
            network_speed = None
        
        try:
            buffer_health = float(request.GET.get('buffer_health', 100))
        except (ValueError, TypeError):
            buffer_health = None
        
        is_waiting = request.GET.get('is_waiting', 'false').lower() == 'true'
        
        # Получаем метрики сервера
        server_load = 0
        cpu_percent = 0
        memory_percent = 0
        try:
            import psutil
            # Используем interval=None для неблокирующего вызова
            cpu_percent = psutil.cpu_percent(interval=None)
            memory_percent = psutil.virtual_memory().percent
            server_load = (cpu_percent + memory_percent) / 2
        except ImportError:
            # psutil не установлен - используем значения по умолчанию
            server_load = 0
        except Exception as e:
            # Любая другая ошибка при получении метрик
            logger.warning(f"Could not get server metrics: {e}")
            server_load = 0
        
        # Определяем оптимальное качество (та же логика)
        optimal_quality = original_height
        
        if is_waiting:
            for q in reversed(available_qualities):
                if q < optimal_quality:
                    optimal_quality = q
                    break
        else:
            
            if server_load > 80:
                for q in reversed(available_qualities):
                    if q < optimal_quality:
                        optimal_quality = q
                        break
            
            if network_speed and network_speed < 100000:
                for q in reversed(available_qualities):
                    if q < optimal_quality:
                        optimal_quality = q
                        break
            
            if buffer_health and buffer_health < 20:
                for q in reversed(available_qualities):
                    if q < optimal_quality:
                        optimal_quality = q
                        break
            
            if buffer_health and buffer_health > 80 and network_speed and network_speed > 500000 and server_load < 50:
                for q in available_qualities:
                    if q > optimal_quality and q <= original_height:
                        optimal_quality = q
                        break
        
        # Определяем рекомендацию
        try:
            if is_waiting or (buffer_health is not None and buffer_health < 20) or (network_speed is not None and network_speed < 100000):
                recommendation = 'decrease'
            elif buffer_health is not None and buffer_health > 80 and network_speed is not None and network_speed > 500000:
                recommendation = 'increase'
            else:
                recommendation = 'maintain'
        except Exception as e:
            logger.warning(f"Error determining recommendation: {e}")
            recommendation = 'maintain'
        
        return JsonResponse({
            'success': True,
            'optimal_quality': optimal_quality,
            'available_qualities': available_qualities,
            'server_load': server_load,
            'recommendation': recommendation
        })
        
    except UserFile.DoesNotExist:
        return create_json_response(False, 'Файл не найден или недоступен', status=404)
    except Exception as e:
        logger.error(f"Error in get_optimal_quality_public: {e}", exc_info=True)
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


def get_public_video_quality(request, token, quality):
    """API endpoint для получения публичного видео в указанном качестве"""
    try:
        try:
            target_height = int(quality)
        except ValueError:
            return create_json_response(False, 'Некорректное качество видео', status=400)
        
        file = UserFile.objects.get(public_token=token, is_public=True)
        
        if not file.is_video:
            return create_json_response(False, 'Файл не является видео', status=400)
        
        try:
            file_path = file.file.path
        except Exception as e:
            logger.error(f"Error getting file path: {e}")
            return create_json_response(
                False,
                f'Ошибка при получении пути к файлу: {str(e)}',
                status=500
            )
        
        if not os.path.exists(file_path):
            return create_json_response(False, 'Файл не найден на диске', status=404)
        
        metadata = get_video_metadata(file_path)
        if not metadata:
            return create_json_response(False, 'Не удалось получить метаданные видео', status=500)
        
        original_height = metadata.get('height')
        if not original_height:
            return create_json_response(
                False,
                'Не удалось определить исходное разрешение видео',
                status=500
            )
        
        if target_height >= original_height:
            file_handle = open(file_path, 'rb')
            response = FileResponse(file_handle, content_type='video/mp4')
            response['Content-Disposition'] = f'inline; filename="{file.filename}"'
            response['Accept-Ranges'] = 'bytes'
            return response
        
        quality_path = get_video_quality_path(file_path, target_height)
        
        if not quality_path:
            return create_json_response(
                False,
                'Не удалось перекодировать видео. Убедитесь, что ffmpeg установлен.',
                status=500
            )
        
        file_handle = open(quality_path, 'rb')
        response = FileResponse(file_handle, content_type='video/mp4')
        response['Content-Disposition'] = f'inline; filename="{file.filename}"'
        response['Accept-Ranges'] = 'bytes'
        return response
        
    except UserFile.DoesNotExist:
        return create_json_response(False, 'Файл не найден или недоступен', status=404)
    except Exception as e:
        logger.error(f"Error in get_public_video_quality: {e}", exc_info=True)
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


def public_file(request, token):
    """Публичный просмотр файла"""
    try:
        file = UserFile.objects.get(public_token=token, is_public=True)
        
        # Для медиафайлов показываем страницу просмотра
        if file.is_image or file.is_video or file.is_audio:
            if file.is_video:
                file_type = 'video'
            elif file.is_image:
                file_type = 'image'
            elif file.is_audio:
                file_type = 'audio'
            else:
                file_type = None
            
            return render(request, 'storage/public_file.html', {
                'file': file,
                'file_type': file_type
            })
            
        # Для остальных файлов - скачивание
        from django.http import HttpResponse
        response = HttpResponse(file.file, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{file.filename}"'
        return response
        
    except UserFile.DoesNotExist:
        raise Http404("Файл не найден или недоступен")

