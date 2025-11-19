import os
from typing import Optional
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib import messages
from django.http import Http404, JsonResponse, FileResponse, HttpResponse, StreamingHttpResponse
from django.urls import reverse
from urllib.parse import quote, urlparse
import requests

from ..models import UserFile, DownloadToken, Folder, MountedFolder, SharedFolderAccess
from ..helpers import (
    ensure_user_folder_exists,
    generate_unique_filename,
    validate_file_size,
    validate_storage_quota,
    create_json_response,
    get_file_path
)
from ..constants import SUCCESS_FILE_UPLOADED, SUCCESS_FILE_DELETED, ERROR_FILE_NOT_FOUND
from eventshock_auth.models import UserProfile

logger = __import__('logging').getLogger(__name__)


@login_required
def dashboard(request):
    """Главная страница с загрузкой и списком файлов"""
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        
        # Валидация размера файла
        size_error = validate_file_size(uploaded_file, request)
        if size_error:
            return size_error
        
        # Валидация квоты хранилища
        quota_error = validate_storage_quota(request.user, uploaded_file.size, request)
        if quota_error:
            return quota_error
            
        # Подготовка папки пользователя
        user_folder = ensure_user_folder_exists(request.user.id)
        
        # Генерация уникального имени файла
        filename = generate_unique_filename(user_folder, uploaded_file.name)
        file_path = os.path.join(user_folder, filename)
        
        # Сохранение файла
        try:
            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            # Получаем текущую папку для загрузки
            folder_id = request.POST.get('folder_id', None)
            folder = None
            if folder_id:
                try:
                    folder = Folder.objects.get(id=folder_id, user=request.user)
                except Folder.DoesNotExist:
                    pass
            
            # Создание записи в БД
            file = UserFile.objects.create(
                user=request.user,
                file=f'{request.user.id}/{filename}',
                filename=filename,
                file_size=uploaded_file.size,
                folder=folder
            )
            
            # Создаем токен для скачивания при загрузке файла
            generate_download_token(file)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return create_json_response(True, SUCCESS_FILE_UPLOADED)
            
            messages.success(request, SUCCESS_FILE_UPLOADED)
            return redirect('dashboard')
            
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            error_msg = f'Ошибка при загрузке файла: {str(e)}'
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return create_json_response(False, error_msg, status=500)
            
            messages.error(request, error_msg)
            return redirect('dashboard')
        
    # Получение текущей папки (из GET параметра)
    folder_id = request.GET.get('folder', None)
    current_folder = None
    if folder_id:
        try:
            current_folder = Folder.objects.get(id=folder_id, user=request.user)
        except Folder.DoesNotExist:
            pass
    
    # Получение списка файлов пользователя в текущей папке
    user_files = UserFile.objects.filter(user=request.user, folder=current_folder)
    
    # Получение списка папок в текущей папке
    folders = Folder.objects.filter(user=request.user, parent=current_folder).order_by('name')
    
    # Получение примонтированных папок (только в корне)
    mounted_folders = []
    if not current_folder:
        from .share_helpers import AccessPermissionManager
        mounted = MountedFolder.objects.filter(user=request.user).select_related(
            'shared_access', 'shared_access__folder', 'shared_access__owner'
        )
        for mount in mounted:
            # Проверяем доступ через менеджер прав
            access = mount.shared_access
            if AccessPermissionManager.can_user_view(request.user, access):
                mounted_folders.append({
                    'folder': access.folder,
                    'owner': access.owner,
                    'mounted': mount,
                    'access': access
                })
    
    # Получение пути навигации
    breadcrumbs = []
    if current_folder:
        parent = current_folder.parent
        breadcrumb_items = [current_folder]
        while parent:
            breadcrumb_items.insert(0, parent)
            parent = parent.parent
        breadcrumbs = breadcrumb_items
    
    # Получаем папки, к которым пользователь предоставил доступ
    shared_by_me = SharedFolderAccess.objects.filter(
        owner=request.user
    ).select_related('folder')
    
    return render(request, 'storage/dashboard.html', {
        'files': user_files,
        'folders': folders,
        'mounted_folders': mounted_folders,
        'current_folder': current_folder,
        'breadcrumbs': breadcrumbs,
        'shared_by_me': shared_by_me
    })


@login_required
def delete_file(request, file_id):
    """Удаление файла"""
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        file_path = get_file_path(file)
        
        if os.path.exists(file_path):
            os.remove(file_path)
        
        file.delete()
        messages.success(request, SUCCESS_FILE_DELETED)
        
    except UserFile.DoesNotExist:
        messages.error(request, ERROR_FILE_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error deleting file {file_id}: {e}")
        messages.error(request, f'Ошибка при удалении файла: {str(e)}')
    
    return redirect('dashboard')


def _file_iterator(file_path, start=0, end=None, chunk_size=None):
    """Генератор для чтения файла по частям с поддержкой Range-запросов"""
    # Определяем оптимальный размер чанка в зависимости от размера файла
    if chunk_size is None:
        file_size = os.path.getsize(file_path)
        # Для больших файлов (>100MB) используем больший чанк (4MB)
        # Для средних (10-100MB) - 2MB, для маленьких - 512KB
        # Увеличенные чанки помогают избежать таймаутов
        if file_size > 100 * 1024 * 1024:  # > 100MB
            chunk_size = 4 * 1024 * 1024  # 4MB
        elif file_size > 10 * 1024 * 1024:  # > 10MB
            chunk_size = 2 * 1024 * 1024  # 2MB
        else:
            chunk_size = 512 * 1024  # 512KB
    
    # Открываем файл в бинарном режиме
    # Важно: файл должен оставаться открытым на время работы генератора
    f = open(file_path, 'rb')
    try:
        f.seek(start)
        remaining = end - start + 1 if end else None
        bytes_yielded = 0
        
        while True:
            if remaining is not None and remaining <= 0:
                break
            
            chunk_size_to_read = min(chunk_size, remaining) if remaining else chunk_size
            chunk = f.read(chunk_size_to_read)
            
            if not chunk:
                break
            
            bytes_yielded += len(chunk)
            if remaining is not None:
                remaining -= len(chunk)
            
            # Отправляем чанк
            yield chunk
            
            # Логируем прогресс для больших файлов (каждые 50MB)
            if bytes_yielded % (50 * 1024 * 1024) == 0:
                logger.debug(f"Downloaded {bytes_yielded / (1024 * 1024):.2f} MB from {file_path}")
                
    finally:
        # Закрываем файл только после завершения генератора
        if not f.closed:
            f.close()


def _parse_range_header(range_header, file_size):
    """Парсит HTTP Range заголовок"""
    if not range_header:
        return None, None
    
    try:
        # Формат: "bytes=start-end"
        range_match = range_header.replace('bytes=', '').split('-')
        start = int(range_match[0]) if range_match[0] else None
        end = int(range_match[1]) if range_match[1] else None
        
        if start is None:
            # Запрос последних N байт
            start = file_size - end
            end = file_size - 1
        elif end is None:
            # Запрос от start до конца
            end = file_size - 1
        else:
            # Запрос конкретного диапазона
            end = min(end, file_size - 1)
        
        if start < 0 or end < start or start >= file_size:
            return None, None
            
        return start, end
    except (ValueError, IndexError):
        return None, None


@login_required
def download_file(request, token):
    """Скачивание файла по токену - отдает файл напрямую через nginx (X-Accel-Redirect)"""
    try:
        download_token = DownloadToken.objects.get(token=token)
        if not download_token.is_valid():
            raise Http404("Ссылка устарела")
            
        file = download_token.file
        file_path = file.file.path
        
        if not os.path.exists(file_path):
            raise Http404("Файл не найден на диске")
        
        # Получаем относительный путь от MEDIA_ROOT для X-Accel-Redirect
        # file.file хранит путь вида "1/filename.ext" относительно MEDIA_ROOT
        internal_path = f"/protected_media/{file.file.name}"
        
        # Создаем ответ с X-Accel-Redirect
        # Nginx перехватит этот заголовок и отдаст файл напрямую
        response = HttpResponse()
        response['X-Accel-Redirect'] = internal_path
        response['Content-Type'] = 'application/octet-stream'
        
        # Content-Disposition: attachment - файл будет скачан
        encoded_filename = quote(file.filename)
        response['Content-Disposition'] = (
            f'attachment; filename="{encoded_filename}"; '
            f'filename*=UTF-8\'\'{encoded_filename}'
        )
        response['Accept-Ranges'] = 'bytes'
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        # НЕ помечаем токен как использованный - он может использоваться многократно в течение дня
        
        return response
            
    except DownloadToken.DoesNotExist:
        raise Http404("Ссылка недействительна")
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise Http404(f"Ошибка при скачивании файла: {str(e)}")


def generate_download_token(file: UserFile) -> DownloadToken:
    """Получает или создает валидный токен для скачивания файла"""
    return DownloadToken.get_or_create_valid_token(file)


@login_required
def generate_download_link(request, file_id):
    """Получает или создает ссылку для скачивания файла"""
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        download_token = generate_download_token(file)
        
        return create_json_response(
            True,
            data={'download_url': f'/storage/download/{download_token.token}/'}
        )
        
    except UserFile.DoesNotExist:
        return create_json_response(False, ERROR_FILE_NOT_FOUND, status=404)


def raw_file(request, filename):
    """Прямая ссылка на файл - отдает файл напрямую через nginx (X-Accel-Redirect)"""
    try:
        # Получаем токен из query параметра
        token = request.GET.get('token')
        if not token:
            raise Http404("Токен не указан")
        
        download_token = DownloadToken.objects.get(token=token)
        if not download_token.is_valid():
            raise Http404("Ссылка устарела")
            
        file = download_token.file
        
        # Токен уже обеспечивает безопасность, поэтому проверка имени файла необязательна
        # Но логируем для отладки, если имена не совпадают
        from urllib.parse import unquote, unquote_plus
        decoded_filename = unquote_plus(filename)
        if decoded_filename == filename:
            decoded_filename = unquote(filename)
        
        # Логируем несоответствие имен (но не блокируем доступ)
        if file.filename.lower() != decoded_filename.lower():
            logger.debug(
                f"Filename in URL differs from DB for token {token[:8]}...: "
                f"URL='{decoded_filename}' vs DB='{file.filename}'"
            )
        
        file_path = file.file.path
        
        if not os.path.exists(file_path):
            logger.error(f"File not found on disk: {file_path} for file_id={file.id}")
            raise Http404("Файл не найден на диске")
        
        # Получаем относительный путь от MEDIA_ROOT для X-Accel-Redirect
        # file.file хранит путь вида "1/filename.ext" относительно MEDIA_ROOT
        internal_path = f"/protected_media/{file.file.name}"
        
        # Создаем ответ с X-Accel-Redirect
        # Nginx перехватит этот заголовок и отдаст файл напрямую
        response = HttpResponse()
        response['X-Accel-Redirect'] = internal_path
        response['Content-Type'] = 'application/octet-stream'
        
        # Определяем Content-Type на основе типа файла
        if file.is_image:
            if file.filename.lower().endswith(('.jpg', '.jpeg')):
                response['Content-Type'] = 'image/jpeg'
            elif file.filename.lower().endswith('.png'):
                response['Content-Type'] = 'image/png'
            elif file.filename.lower().endswith('.gif'):
                response['Content-Type'] = 'image/gif'
            elif file.filename.lower().endswith('.webp'):
                response['Content-Type'] = 'image/webp'
            else:
                response['Content-Type'] = 'image/*'
        elif file.is_video:
            response['Content-Type'] = 'video/mp4'
        elif file.is_audio:
            response['Content-Type'] = 'audio/mpeg'
        elif file.is_text or file.is_code:
            response['Content-Type'] = 'text/plain; charset=utf-8'
        elif file.is_document:
            if file.filename.lower().endswith('.pdf'):
                response['Content-Type'] = 'application/pdf'
        
        # Content-Disposition: inline - файл откроется в браузере
        encoded_filename = quote(file.filename)
        response['Content-Disposition'] = f'inline; filename="{encoded_filename}"'
        response['Accept-Ranges'] = 'bytes'
        response['Cache-Control'] = 'public, max-age=3600'
        
        return response
            
    except DownloadToken.DoesNotExist:
        raise Http404("Ссылка недействительна")
    except Http404:
        raise
    except Exception as e:
        logger.error(f"Error serving raw file: {e}", exc_info=True)
        raise Http404(f"Ошибка при получении файла: {str(e)}")


@login_required
def get_raw_link(request, file_id):
    """Получает прямую ссылку на файл"""
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        download_token = generate_download_token(file)
        
        # Кодируем имя файла для URL
        # Используем safe='' чтобы закодировать все специальные символы
        # Но оставляем слэши, так как они могут быть частью пути
        encoded_filename = quote(file.filename, safe='')
        
        # Получаем полный URL с именем файла (токен в query параметре)
        raw_url = request.build_absolute_uri(f'/storage/raw/{encoded_filename}?token={download_token.token}')
        
        return create_json_response(
            True,
            data={'raw_url': raw_url}
        )
        
    except UserFile.DoesNotExist:
        return create_json_response(False, ERROR_FILE_NOT_FOUND, status=404)


@login_required
def save_text_file(request, file_id):
    """Сохранение изменений в текстовом файле"""
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        
        if not file.is_text and not file.is_code:
            return create_json_response(False, 'Файл не является текстовым', status=400)
        
        if request.method != 'POST':
            return create_json_response(False, 'Неверный метод запроса', status=405)
        
        # Получаем содержимое из POST или JSON
        if request.content_type == 'application/json':
            import json
            data = json.loads(request.body)
            content = data.get('content', '')
        else:
            content = request.POST.get('content', '')
        
        # Получаем путь к файлу - используем file.path для Django FileField
        try:
            # Пытаемся получить путь через Django FileField
            if file.file:
                file_path = file.file.path
            else:
                raise AttributeError("file.file is None")
        except (ValueError, AttributeError, OSError) as e:
            # Если file.path недоступен, используем get_file_path
            logger.warning(f"Could not get file.path for file {file_id}, using get_file_path: {e}")
            try:
                file_path = get_file_path(file)
            except Exception as e2:
                logger.error(f"Error in get_file_path for file {file_id}: {e2}")
                return create_json_response(False, f'Ошибка при получении пути к файлу: {str(e2)}', status=500)
        
        # Проверяем, что путь существует или создаем директорию
        try:
            dir_path = os.path.dirname(file_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"Created directory: {dir_path}")
        except OSError as e:
            logger.error(f"Error creating directory for file {file_id}: {e}")
            return create_json_response(False, f'Ошибка при создании директории: {str(e)}', status=500)
        
        # Сохраняем содержимое
        try:
            logger.info(f"Saving text file {file_id} to path: {file_path}")
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Обновляем размер файла
            new_size = os.path.getsize(file_path)
            file.file_size = new_size
            file.save(update_fields=['file_size'])
            
            logger.info(f"Text file {file_id} saved successfully, new size: {new_size} bytes")
            
            return create_json_response(True, 'Файл успешно сохранен')
            
        except Exception as e:
            logger.error(f"Error saving text file {file_id}: {e}")
            return create_json_response(False, f'Ошибка при сохранении: {str(e)}', status=500)
        
    except UserFile.DoesNotExist:
        return create_json_response(False, ERROR_FILE_NOT_FOUND, status=404)
    except Exception as e:
        logger.error(f"Error in save_text_file: {e}")
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


@login_required
def upload_from_url(request):
    """Загрузка файла по URL"""
    if request.method != 'POST':
        return create_json_response(False, 'Неверный метод запроса', status=405)
    
    try:
        # Получаем URL из POST или JSON
        if request.content_type == 'application/json':
            import json
            data = json.loads(request.body)
            file_url = data.get('url', '').strip()
            folder_id = data.get('folder_id', None)
        else:
            file_url = request.POST.get('url', '').strip()
            folder_id = request.POST.get('folder_id', None)
        
        if not file_url:
            return create_json_response(False, 'URL не указан', status=400)
        
        # Валидация URL
        try:
            parsed_url = urlparse(file_url)
            if not parsed_url.scheme or not parsed_url.netloc:
                return create_json_response(False, 'Некорректный URL', status=400)
        except Exception as e:
            return create_json_response(False, f'Ошибка при проверке URL: {str(e)}', status=400)
        
        # Получаем текущую папку для загрузки
        folder = None
        if folder_id:
            try:
                folder = Folder.objects.get(id=folder_id, user=request.user)
            except Folder.DoesNotExist:
                pass
        
        # Скачиваем файл
        try:
            # Устанавливаем таймаут и заголовки для запроса
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Делаем HEAD запрос для проверки размера файла (если поддерживается)
            content_length = None
            try:
                head_response = requests.head(file_url, headers=headers, timeout=10, allow_redirects=True)
                content_length = head_response.headers.get('Content-Length')
            except requests.exceptions.RequestException:
                # Если HEAD запрос не поддерживается, пропускаем проверку размера
                # Размер будет проверен во время загрузки
                pass
            
            if content_length:
                file_size = int(content_length)
                # Проверяем размер файла
                if file_size > settings.MAX_FILE_SIZE:
                    max_size_mb = settings.MAX_FILE_SIZE / (1024 * 1024)
                    return create_json_response(
                        False, 
                        f'Файл слишком большой. Максимальный размер: {max_size_mb:.0f}MB', 
                        status=400
                    )
                
                # Проверяем квоту хранилища
                quota_error = validate_storage_quota(request.user, file_size, request)
                if quota_error:
                    return quota_error
            
            # Скачиваем файл
            response = requests.get(file_url, headers=headers, timeout=300, stream=True, allow_redirects=True)
            response.raise_for_status()
            
            # Получаем имя файла из URL или заголовков
            filename = None
            content_disposition = response.headers.get('Content-Disposition', '')
            if 'filename=' in content_disposition:
                try:
                    filename = content_disposition.split('filename=')[1].strip('"\'')
                except:
                    pass
            
            if not filename:
                # Извлекаем имя файла из URL
                path = urlparse(file_url).path
                filename = os.path.basename(path) or 'downloaded_file'
                # Если нет расширения, пытаемся определить из Content-Type
                if '.' not in filename:
                    content_type = response.headers.get('Content-Type', '')
                    if 'image' in content_type:
                        filename += '.jpg'
                    elif 'pdf' in content_type:
                        filename += '.pdf'
                    elif 'text' in content_type:
                        filename += '.txt'
            
            # Подготовка папки пользователя
            user_folder = ensure_user_folder_exists(request.user.id)
            
            # Генерация уникального имени файла
            filename = generate_unique_filename(user_folder, filename)
            file_path = os.path.join(user_folder, filename)
            
            # Сохранение файла
            downloaded_size = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # Проверяем размер во время загрузки
                        if downloaded_size > settings.MAX_FILE_SIZE:
                            os.remove(file_path)
                            return create_json_response(
                                False, 
                                f'Файл слишком большой. Максимальный размер: {settings.MAX_FILE_SIZE / (1024 * 1024):.0f}MB', 
                                status=400
                            )
            
            # Получаем реальный размер файла
            actual_size = os.path.getsize(file_path)
            
            # Создание записи в БД
            file = UserFile.objects.create(
                user=request.user,
                file=f'{request.user.id}/{filename}',
                filename=filename,
                file_size=actual_size,
                folder=folder
            )
            
            # Создаем токен для скачивания при загрузке файла
            generate_download_token(file)
            
            return create_json_response(
                True, 
                'Файл успешно загружен по URL',
                data={'filename': filename, 'file_id': file.id}
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading file from URL {file_url}: {e}")
            return create_json_response(
                False, 
                f'Ошибка при скачивании файла: {str(e)}', 
                status=500
            )
        except Exception as e:
            logger.error(f"Error uploading file from URL {file_url}: {e}")
            return create_json_response(
                False, 
                f'Ошибка при загрузке файла: {str(e)}', 
                status=500
            )
    
    except Exception as e:
        logger.error(f"Error in upload_from_url: {e}")
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)

