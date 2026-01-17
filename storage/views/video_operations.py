"""
Операции с видео: метаданные, качество, публичный доступ
"""
import os
import logging
from urllib.parse import quote
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
            from ..helpers import get_file_path, download_file_from_s3
            import tempfile
            
            # Если файл в S3 хранилище, нужно скачать его для получения метаданных
            if file.storage and file.storage.storage_type == 's3':
                # Скачиваем файл из S3 во временный файл
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                temp_file_path = temp_file.name
                temp_file.close()
                
                s3_key = f"{file.user.id}/{file.filename}"
                if not download_file_from_s3(file.storage, s3_key, temp_file_path):
                    return create_json_response(False, 'Ошибка при скачивании файла из S3', status=500)
                
                file_path = temp_file_path
            else:
                file_path = get_file_path(file)
                if not file_path or not os.path.exists(file_path):
                    raise Http404("Файл не найден")
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
        
        try:
            metadata = _get_video_metadata_with_qualities(file_path)
        finally:
            # Удаляем временный файл S3 после получения метаданных
            if file.storage and file.storage.storage_type == 's3' and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
        
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
        # Используем универсальную функцию поиска для обратной совместимости
        from ..models import find_token_in_model, UserFile
        file = find_token_in_model(UserFile, 'public_token', token)
        if not file:
            raise UserFile.DoesNotExist
        if not file.is_public:
            raise UserFile.DoesNotExist
        
        if not file.is_video:
            return create_json_response(
                False,
                'Файл не является видео',
                status=400
            )
        
        try:
            from ..helpers import get_file_path, download_file_from_s3
            import tempfile
            
            # Если файл в S3 хранилище, нужно скачать его для получения метаданных
            if file.storage and file.storage.storage_type == 's3':
                # Скачиваем файл из S3 во временный файл
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                temp_file_path = temp_file.name
                temp_file.close()
                
                s3_key = f"{file.user.id}/{file.filename}"
                if not download_file_from_s3(file.storage, s3_key, temp_file_path):
                    return create_json_response(False, 'Ошибка при скачивании файла из S3', status=500)
                
                file_path = temp_file_path
            else:
                file_path = get_file_path(file)
                if not file_path or not os.path.exists(file_path):
                    raise Http404("Файл не найден")
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
        
        try:
            metadata = _get_video_metadata_with_qualities(file_path)
        finally:
            # Удаляем временный файл S3 после получения метаданных
            if file.storage and file.storage.storage_type == 's3' and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
        
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
            from ..helpers import get_file_path
            file_path = get_file_path(file)
            if not file_path or not os.path.exists(file_path):
                raise Http404("Файл не найден")
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
        
        # Если файл в S3 хранилище, нужно скачать его для просмотра
        if file.storage and file.storage.storage_type == 's3':
            from ..helpers import download_file_from_s3
            import tempfile
            
            # Скачиваем файл из S3 во временный файл
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            temp_file_path = temp_file.name
            temp_file.close()
            
            s3_key = f"{file.user.id}/{file.filename}"
            if not download_file_from_s3(file.storage, s3_key, temp_file_path):
                return create_json_response(False, 'Ошибка при скачивании файла из S3', status=500)
            
            # Используем временный файл для получения метаданных
            file_path = temp_file_path
        
        # Если запрошенное качество равно или выше исходного, возвращаем оригинал
        if target_height >= original_height:
            # Для S3 файлов используем временный файл
            if file.storage and file.storage.storage_type == 's3':
                file_handle = open(file_path, 'rb')
            else:
                file_handle = open(file_path, 'rb')
            response = FileResponse(file_handle, content_type='video/mp4')
            response['Content-Disposition'] = f'inline; filename="{file.filename}"'
            response['Accept-Ranges'] = 'bytes'
            # Для S3 файлов удаляем временный файл после отправки
            if file.storage and file.storage.storage_type == 's3':
                import atexit
                atexit.register(lambda: os.remove(file_path) if os.path.exists(file_path) else None)
            return response
        
        # Получаем или создаем видео в нужном качестве
        quality_path = get_video_quality_path(file_path, target_height)
        
        if not quality_path:
            # Удаляем временный файл S3 если он был создан
            if file.storage and file.storage.storage_type == 's3' and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return create_json_response(
                False,
                'Не удалось перекодировать видео. Убедитесь, что ffmpeg установлен.',
                status=500
            )
        
        file_handle = open(quality_path, 'rb')
        response = FileResponse(file_handle, content_type='video/mp4')
        response['Content-Disposition'] = f'inline; filename="{file.filename}"'
        response['Accept-Ranges'] = 'bytes'
        # Удаляем временный файл S3 после отправки
        if file.storage and file.storage.storage_type == 's3' and os.path.exists(file_path):
            import atexit
            atexit.register(lambda: os.remove(file_path) if os.path.exists(file_path) else None)
        return response
        
    except UserFile.DoesNotExist:
        return create_json_response(False, 'Файл не найден', status=404)
    except Exception as e:
        logger.error(f"Error in get_video_quality: {e}", exc_info=True)
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


def get_public_video_quality(request, token, quality):
    """API endpoint для получения публичного видео в указанном качестве"""
    try:
        try:
            target_height = int(quality)
        except ValueError:
            return create_json_response(False, 'Некорректное качество видео', status=400)
        
        # Используем универсальную функцию поиска для обратной совместимости
        from ..models import find_token_in_model, UserFile
        file = find_token_in_model(UserFile, 'public_token', token)
        if not file:
            raise UserFile.DoesNotExist
        if not file.is_public:
            raise UserFile.DoesNotExist
        
        if not file.is_video:
            return create_json_response(False, 'Файл не является видео', status=400)
        
        try:
            from ..helpers import get_file_path, download_file_from_s3
            import tempfile
            
            # Если файл в S3 хранилище, нужно скачать его для просмотра
            if file.storage and file.storage.storage_type == 's3':
                # Скачиваем файл из S3 во временный файл
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                temp_file_path = temp_file.name
                temp_file.close()
                
                s3_key = f"{file.user.id}/{file.filename}"
                if not download_file_from_s3(file.storage, s3_key, temp_file_path):
                    return create_json_response(False, 'Ошибка при скачивании файла из S3', status=500)
                
                file_path = temp_file_path
            else:
                file_path = get_file_path(file)
                if not file_path or not os.path.exists(file_path):
                    raise Http404("Файл не найден")
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
            # Удаляем временный файл S3 если он был создан
            if file.storage and file.storage.storage_type == 's3' and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return create_json_response(False, 'Не удалось получить метаданные видео', status=500)
        
        original_height = metadata.get('height')
        if not original_height:
            # Удаляем временный файл S3 если он был создан
            if file.storage and file.storage.storage_type == 's3' and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
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
            # Удаляем временный файл S3 после отправки
            if file.storage and file.storage.storage_type == 's3':
                import atexit
                atexit.register(lambda: os.remove(file_path) if os.path.exists(file_path) else None)
            return response
        
        quality_path = get_video_quality_path(file_path, target_height)
        
        if not quality_path:
            # Удаляем временный файл S3 если он был создан
            if file.storage and file.storage.storage_type == 's3' and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return create_json_response(
                False,
                'Не удалось перекодировать видео. Убедитесь, что ffmpeg установлен.',
                status=500
            )
        
        file_handle = open(quality_path, 'rb')
        response = FileResponse(file_handle, content_type='video/mp4')
        response['Content-Disposition'] = f'inline; filename="{file.filename}"'
        response['Accept-Ranges'] = 'bytes'
        # Удаляем временный файл S3 после отправки
        if file.storage and file.storage.storage_type == 's3':
            import atexit
            atexit.register(lambda: os.remove(file_path) if os.path.exists(file_path) else None)
        return response
        
    except UserFile.DoesNotExist:
        return create_json_response(False, 'Файл не найден или недоступен', status=404)
    except Exception as e:
        logger.error(f"Error in get_public_video_quality: {e}", exc_info=True)
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


def public_file(request, token):
    """Публичный просмотр файла"""
    try:
        # Используем универсальную функцию поиска для обратной совместимости
        from ..models import find_token_in_model, UserFile
        file = find_token_in_model(UserFile, 'public_token', token)
        if not file:
            raise UserFile.DoesNotExist
        if not file.is_public:
            raise UserFile.DoesNotExist
        
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
        from django.http import HttpResponse, FileResponse, HttpResponseRedirect
        from ..helpers import get_file_for_response, generate_s3_presigned_url
        import os
        
        # Проверяем, если файл в S3 хранилище, используем presigned URL
        if file.storage and file.storage.storage_type == 's3':
            s3_key = f"{file.user.id}/{file.filename}"
            presigned_url = generate_s3_presigned_url(file.storage, s3_key, expiration=3600)
            if presigned_url:
                # Перенаправляем на presigned URL для прямого скачивания
                return HttpResponseRedirect(presigned_url)
        
        # Для локальных файлов используем стандартный метод
        file_path, is_temp, temp_path = get_file_for_response(file)
        if not file_path:
            raise Http404("Файл не найден")
        
        try:
            response = FileResponse(open(file_path, 'rb'), content_type='application/octet-stream')
            encoded_filename = quote(file.filename)
            response['Content-Disposition'] = f'attachment; filename="{encoded_filename}"'
            
            # Если это временный файл, удаляем его после отправки
            if is_temp and temp_path:
                import atexit
                atexit.register(lambda: os.remove(temp_path) if os.path.exists(temp_path) else None)
            
            return response
        except Exception as e:
            # Удаляем временный файл в случае ошибки
            if is_temp and temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            raise
        
    except UserFile.DoesNotExist:
        raise Http404("Файл не найден или недоступен")

