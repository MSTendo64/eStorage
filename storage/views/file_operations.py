import os
import json
import re
import shutil
import tempfile
from typing import Optional, Tuple
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib import messages
from django.http import Http404, JsonResponse, FileResponse, HttpResponse, StreamingHttpResponse
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from urllib.parse import quote, urlparse, parse_qs
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


def extract_google_drive_file_id(url: str) -> Optional[str]:
    """
    Извлекает ID файла из различных форматов Google Drive ссылок
    
    Поддерживаемые форматы:
    - https://drive.google.com/file/d/FILE_ID/view
    - https://drive.google.com/file/d/FILE_ID/edit
    - https://drive.google.com/open?id=FILE_ID
    - https://drive.google.com/uc?id=FILE_ID
    - https://docs.google.com/document/d/FILE_ID/edit (для Google Docs)
    """
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]+)',
        r'/open\?id=([a-zA-Z0-9_-]+)',
        r'/uc\?id=([a-zA-Z0-9_-]+)',
        r'/document/d/([a-zA-Z0-9_-]+)',
        r'/spreadsheets/d/([a-zA-Z0-9_-]+)',
        r'/presentation/d/([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    # Попытка извлечь из query параметров
    parsed = urlparse(url)
    if parsed.netloc in ['drive.google.com', 'docs.google.com']:
        query_params = parse_qs(parsed.query)
        if 'id' in query_params:
            return query_params['id'][0]
    
    return None


def convert_google_drive_url(url: str) -> Optional[str]:
    """
    Преобразует Google Drive ссылку в прямую ссылку для скачивания
    
    Возвращает None, если это не Google Drive ссылка
    """
    parsed = urlparse(url)
    
    # Проверяем, является ли это Google Drive ссылкой
    if parsed.netloc not in ['drive.google.com', 'docs.google.com']:
        return None
    
    file_id = extract_google_drive_file_id(url)
    if not file_id:
        return None
    
    # Для обычных файлов используем прямую ссылку
    # Для Google Docs/Sheets/Slides нужно использовать другой формат
    if 'docs.google.com' in parsed.netloc:
        # Google Docs/Sheets/Slides требуют экспорта
        doc_type = 'document' if '/document/' in url else 'spreadsheets' if '/spreadsheets/' in url else 'presentation'
        # Пытаемся экспортировать как PDF или другой формат
        # Но для простоты попробуем прямую ссылку
        return f'https://drive.google.com/uc?export=download&id={file_id}'
    else:
        # Обычные файлы - прямая ссылка для скачивания
        return f'https://drive.google.com/uc?export=download&id={file_id}'


def download_via_proxy(url: str, headers: dict, timeout: int = 600) -> Optional[requests.Response]:
    """
    Пытается скачать файл через прокси-сервисы
    
    Возвращает Response объект или None если все попытки не удались
    """
    from eventshock_auth.models import SystemSettings
    
    # Получаем настройки системы
    system_settings = SystemSettings.get_settings()
    
    # Список прокси-сервисов для попыток
    proxy_services = []
    
    # Если настроен пользовательский прокси, используем его первым
    if system_settings.proxy_url:
        # Проверяем формат прокси URL
        proxy_template = system_settings.proxy_url.strip()
        if proxy_template.endswith('=') or proxy_template.endswith('?'):
            # Прокси с параметром URL
            proxy_services.append(f'{proxy_template}{quote(url)}')
        else:
            # Прокси без параметра - добавляем URL как параметр
            if '?' in proxy_template:
                proxy_services.append(f'{proxy_template}&url={quote(url)}')
            else:
                proxy_services.append(f'{proxy_template}?url={quote(url)}')
    
    # Добавляем встроенные прокси-сервисы как резервные
    proxy_services.extend([
        f'https://api.allorigins.win/raw?url={quote(url)}',
        f'https://corsproxy.io/?{quote(url)}',
    ])
    
    for proxy_url in proxy_services:
        try:
            logger.info(f"Trying to download via proxy: {proxy_url[:100]}...")
            response = requests.get(proxy_url, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
            response.raise_for_status()
            logger.info(f"Successfully downloaded via proxy, status: {response.status_code}")
            return response
        except requests.exceptions.RequestException as e:
            logger.warning(f"Proxy service failed: {e}")
            continue
    
    return None


def download_pinterest_video_with_ytdlp(pinterest_url: str) -> Optional[str]:
    """
    Пытается скачать видео с Pinterest используя yt-dlp
    
    Возвращает путь к скачанному файлу или None если не удалось
    """
    try:
        import yt_dlp
        
        # Создаем временную директорию для загрузки
        temp_dir = tempfile.mkdtemp()
        
        # Настройки yt-dlp для Pinterest
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',  # Предпочитаем MP4
            'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),  # Используем ID вместо title
            'quiet': True,  # Уменьшаем вывод
            'no_warnings': False,
            'extract_flat': False,
            'writeinfojson': False,
            'writethumbnail': False,
            'noplaylist': True,  # Только одно видео
            'ignoreerrors': False,
            'no_check_certificate': False,
        }
        
        logger.info(f"Attempting to download Pinterest video using yt-dlp: {pinterest_url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # Получаем информацию о видео
                info = ydl.extract_info(pinterest_url, download=False)
                
                if not info:
                    logger.warning("yt-dlp could not extract video info from Pinterest URL")
                    try:
                        shutil.rmtree(temp_dir)
                    except:
                        pass
                    return None
                
                # Проверяем, есть ли видео (может быть изображение)
                if info.get('_type') == 'playlist':
                    logger.warning("Pinterest URL returned playlist, not a single video")
                    try:
                        shutil.rmtree(temp_dir)
                    except:
                        pass
                    return None
                
                # Проверяем наличие видео URL или форматов
                has_video = False
                if 'url' in info:
                    has_video = True
                elif 'formats' in info and info['formats']:
                    # Проверяем, есть ли видео форматы
                    for fmt in info['formats']:
                        if fmt.get('vcodec') != 'none':  # Есть видео кодек
                            has_video = True
                            break
                
                if not has_video:
                    logger.warning("No video found in Pinterest pin (might be image only)")
                    try:
                        shutil.rmtree(temp_dir)
                    except:
                        pass
                    return None
                
                logger.info(f"yt-dlp found video, starting download...")
                
                # Скачиваем видео
                ydl.download([pinterest_url])
                
                # Ищем скачанный файл (исключаем служебные файлы)
                downloaded_files = [
                    f for f in os.listdir(temp_dir) 
                    if os.path.isfile(os.path.join(temp_dir, f)) 
                    and not f.endswith(('.json', '.description', '.info', '.jpg', '.png', '.webp'))
                ]
                
                if downloaded_files:
                    video_file = os.path.join(temp_dir, downloaded_files[0])
                    logger.info(f"Video downloaded successfully: {video_file} ({os.path.getsize(video_file)} bytes)")
                    return video_file
                else:
                    logger.warning("Video file not found after download")
                    try:
                        shutil.rmtree(temp_dir)
                    except:
                        pass
                    return None
                    
            except Exception as e:
                logger.error(f"Error downloading video with yt-dlp: {e}")
                # Удаляем временную директорию при ошибке
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
                return None
                
    except ImportError:
        logger.warning("yt-dlp is not installed, cannot download Pinterest videos")
        return None
    except Exception as e:
        logger.error(f"Error in download_pinterest_video_with_ytdlp: {e}")
        return None


def convert_pinterest_url(url: str) -> Optional[str]:
    """
    Преобразует Pinterest ссылку в прямую ссылку на медиа-файл (изображение или видео)
    
    Возвращает None, если это не Pinterest ссылка или не удалось получить медиа-файл
    """
    parsed = urlparse(url)
    
    # Проверяем, является ли это Pinterest ссылкой
    if parsed.netloc not in ['pinterest.com', 'www.pinterest.com', 'ru.pinterest.com', 'pinterest.ru']:
        return None
    
    # Проверяем, что это ссылка на пин
    if '/pin/' not in parsed.path:
        return None
    
    try:
        # Получаем HTML страницы пина
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        html = response.text
        
        # Сначала проверяем наличие видео (приоритет видео над изображением)
        # Собираем все найденные видео URL для фильтрации m3u8
        all_video_urls = []
        
        # Ищем og:video мета-тег
        og_video_match = re.search(r'<meta\s+property=["\']og:video["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if og_video_match:
            video_url = og_video_match.group(1)
            logger.info(f"Found Pinterest video via og:video: {video_url}")
            all_video_urls.append(video_url)
        
        # Ищем og:video:url
        og_video_url_match = re.search(r'<meta\s+property=["\']og:video:url["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if og_video_url_match:
            video_url = og_video_url_match.group(1)
            logger.info(f"Found Pinterest video via og:video:url: {video_url}")
            all_video_urls.append(video_url)
        
        # Ищем video:content
        video_content_match = re.search(r'<meta\s+property=["\']video:content["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if video_content_match:
            video_url = video_content_match.group(1)
            logger.info(f"Found Pinterest video via video:content: {video_url}")
            all_video_urls.append(video_url)
        
        # Ищем в JSON-LD данных для видео (добавляем в all_video_urls) (исключаем m3u8)
        json_ld_match = re.search(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
        if json_ld_match:
            try:
                json_data = json.loads(json_ld_match.group(1))
                # Проверяем наличие видео в JSON-LD
                if isinstance(json_data, dict):
                    # Ищем video в различных форматах
                    if 'video' in json_data:
                        video_data = json_data['video']
                        if isinstance(video_data, str):
                            # Пропускаем m3u8
                            if '.m3u8' not in video_data.lower() and 'hls' not in video_data.lower():
                                logger.info(f"Found Pinterest video in JSON-LD: {video_data}")
                                all_video_urls.append(video_data)
                        elif isinstance(video_data, dict):
                            # Проверяем все возможные поля
                            for field in ['contentUrl', 'url', 'embedUrl', 'streamUrl']:
                                if field in video_data:
                                    url = video_data[field]
                                    # Пропускаем m3u8
                                    if isinstance(url, str) and '.m3u8' not in url.lower() and 'hls' not in url.lower():
                                        logger.info(f"Found Pinterest video {field} in JSON-LD: {url}")
                                        all_video_urls.append(url)
                                        break
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Error parsing JSON-LD for video: {e}")
        
        # Фильтруем m3u8 из всех собранных URL и предпочитаем прямые видео файлы
        direct_video_urls = [url for url in all_video_urls if '.m3u8' not in url.lower() and 'hls' not in url.lower()]
        if direct_video_urls:
            # Предпочитаем mp4, webm, mov, avi
            for url in direct_video_urls:
                if any(ext in url.lower() for ext in ['.mp4', '.webm', '.mov', '.avi']):
                    logger.info(f"Returning direct video URL (preferred): {url}")
                    return url
            # Если нет явных расширений, но это не m3u8, возвращаем первое
            logger.info(f"Returning direct video URL: {direct_video_urls[0]}")
            return direct_video_urls[0]
        
        # Ищем data-video-url атрибуты (исключаем m3u8)
        data_video_match = re.search(r'data-video-url=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if data_video_match:
            video_url = data_video_match.group(1)
            # Пропускаем m3u8
            if '.m3u8' not in video_url.lower() and 'hls' not in video_url.lower():
                logger.info(f"Found Pinterest video via data-video-url: {video_url}")
                all_video_urls.append(video_url)
        
        # Ищем другие варианты data-атрибутов для видео (исключаем m3u8)
        data_video_patterns = [
            r'data-video-src=["\']([^"\']+)["\']',
            r'data-video-uri=["\']([^"\']+)["\']',
            r'data-video-href=["\']([^"\']+)["\']',
            r'data-pin-video-url=["\']([^"\']+)["\']',
        ]
        for pattern in data_video_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                video_url = match.group(1)
                # Пропускаем m3u8
                if '.m3u8' not in video_url.lower() and 'hls' not in video_url.lower():
                    logger.info(f"Found Pinterest video via pattern {pattern}: {video_url}")
                    all_video_urls.append(video_url)
        
        # Если видео не найдено в мета-тегах и data-атрибутах, ищем в JavaScript данных
        # (продолжение ниже в коде)
        
        # Временно сохраняем найденные изображения, но не возвращаем их пока не проверим все источники видео
        temp_image_urls = []
        # Сохраняем найденные изображения, но не возвращаем их пока не проверим все источники видео
        # Ищем og:image мета-тег
        og_image_match = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if og_image_match:
            image_url = og_image_match.group(1)
            # Pinterest часто использует промежуточные URL, преобразуем в прямой
            if 'pinimg.com' in image_url:
                # Заменяем размер на оригинальный (убираем параметры размера)
                image_url = re.sub(r'/[\d]+x[\d]+/', '/originals/', image_url)
            logger.info(f"Found Pinterest image via og:image: {image_url}")
            temp_image_urls.append(image_url)
        
        # Альтернативный способ: ищем в JSON-LD данных для изображения
        if json_ld_match:
            try:
                json_data = json.loads(json_ld_match.group(1))
                if isinstance(json_data, dict) and 'image' in json_data:
                    image_url = json_data['image']
                    if isinstance(image_url, str):
                        logger.info(f"Found Pinterest image in JSON-LD: {image_url}")
                        temp_image_urls.append(image_url)
                    elif isinstance(image_url, dict) and 'url' in image_url:
                        logger.info(f"Found Pinterest image url: {image_url['url']}")
                        temp_image_urls.append(image_url['url'])
            except (json.JSONDecodeError, KeyError):
                pass
        
        # Еще один способ: ищем в data-атрибутах для изображения
        data_image_match = re.search(r'data-image-url=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if data_image_match:
            image_url = data_image_match.group(1)
            logger.info(f"Found Pinterest image via data-image-url: {image_url}")
            temp_image_urls.append(image_url)
        
        # Ищем в Pinterest специфичных скриптах
        # Pinterest часто хранит данные в различных JavaScript переменных
        pinterest_data_patterns = [
            r'window\.__initialData__\s*=\s*({.*?});',
            r'window\.__PWS_INITIAL_DATA__\s*=\s*({.*?});',
            r'window\.__PWS_INITIAL_STATE__\s*=\s*({.*?});',
            r'__PWS_INITIAL_DATA__\s*=\s*({.*?});',
        ]
        
        video_urls = []  # Собираем все найденные видео URL
        image_urls = []  # Собираем все найденные изображения
        
        for pattern in pinterest_data_patterns:
            pinterest_data_match = re.search(pattern, html, re.DOTALL)
            if pinterest_data_match:
                try:
                    pinterest_data = json.loads(pinterest_data_match.group(1))
                    # Ищем видео или изображение в структуре данных Pinterest
                    def find_media_in_pinterest_data(data, path='', is_video_priority=True):
                        found_video = None
                        found_image = None
                        
                        if isinstance(data, dict):
                            # Проверяем ключи, связанные с медиа
                            for key, value in data.items():
                                key_lower = key.lower()
                                
                                # Приоритет видео (исключаем m3u8 и blob URLs)
                                # Расширяем поиск - ищем в любых полях, которые могут содержать видео
                                if is_video_priority:
                                    # Проверяем ключи, связанные с видео
                                    video_keywords = ['video', 'videos', 'stream', 'media', 'playback', 'content', 'source', 'url', 'src']
                                    is_video_key = any(keyword in key_lower for keyword in video_keywords)
                                    
                                    if isinstance(value, str) and (value.startswith('http') or value.startswith('//')):
                                        # Пропускаем m3u8, HLS плейлисты, blob URLs и изображения
                                        if ('.m3u8' not in value.lower() and 'hls' not in value.lower() and 
                                            not value.startswith('blob:') and
                                            'pinimg.com' not in value.lower() and
                                            not value.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'))):
                                            # Если это явно видео поле или URL выглядит как видео
                                            if (is_video_key or 
                                                'video' in value.lower() or 'stream' in value.lower() or 
                                                any(ext in value.lower() for ext in ['.mp4', '.webm', '.mov', '.avi', '.m4v', '.flv'])):
                                                logger.info(f"Found Pinterest video in data at {path}.{key}: {value}")
                                                found_video = value
                                    elif isinstance(value, (dict, list)) and is_video_key:
                                        # Если ключ связан с видео, ищем глубже
                                        nested_result = find_media_in_pinterest_data(value, f"{path}.{key}", is_video_priority)
                                        if nested_result:
                                            if isinstance(nested_result, tuple) and nested_result[0]:
                                                found_video = nested_result[0]
                                            elif isinstance(nested_result, str) and not nested_result.startswith('blob:'):
                                                found_video = nested_result
                                    elif isinstance(value, dict):
                                        # Ищем вложенные видео URL в различных полях
                                        # Расширяем список полей для поиска
                                        video_fields = ['url', 'src', 'source', 'streamUrl', 'videoUrl', 'contentUrl', 
                                                       'playbackUrl', 'downloadUrl', 'mediaUrl', 'fileUrl', 'originalUrl',
                                                       'hdUrl', 'sdUrl', 'mp4Url', 'webmUrl', 'video', 'stream', 'content']
                                        
                                        # Сначала проверяем все строковые значения в словаре
                                        for sub_key, sub_value in value.items():
                                            if isinstance(sub_value, str) and (sub_value.startswith('http') or sub_value.startswith('//')):
                                                # Пропускаем m3u8, blob URLs и изображения
                                                if ('.m3u8' not in sub_value.lower() and 'hls' not in sub_value.lower() and 
                                                    not sub_value.startswith('blob:') and
                                                    'pinimg.com' not in sub_value.lower() and
                                                    not sub_value.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'))):
                                                    sub_key_lower = sub_key.lower()
                                                    # Если это видео поле или URL выглядит как видео
                                                    if (sub_key_lower in video_fields or 
                                                        'video' in sub_value.lower() or 'stream' in sub_value.lower() or 
                                                        any(ext in sub_value.lower() for ext in ['.mp4', '.webm', '.mov', '.avi', '.m4v', '.flv'])):
                                                        logger.info(f"Found Pinterest video in nested data at {path}.{key}.{sub_key}: {sub_value}")
                                                        found_video = sub_value
                                                        break
                                        
                                        # Если не нашли в обычных полях, ищем рекурсивно во всех вложенных структурах
                                        if not found_video:
                                            for sub_key, sub_value in value.items():
                                                if isinstance(sub_value, (dict, list)):
                                                    nested_result = find_media_in_pinterest_data(sub_value, f"{path}.{key}.{sub_key}", is_video_priority)
                                                    if nested_result:
                                                        if isinstance(nested_result, tuple) and nested_result[0]:
                                                            found_video = nested_result[0]
                                                            break
                                                        elif isinstance(nested_result, str) and not nested_result.startswith('blob:'):
                                                            found_video = nested_result
                                                            break
                                
                                # Изображения (только если видео не найдено)
                                if not found_video and ('image' in key_lower or 'images' in key_lower or 'pinimg' in key_lower):
                                    if isinstance(value, str) and (value.startswith('http') or value.startswith('//')):
                                        if 'pinimg.com' in value or 'image' in value.lower():
                                            logger.info(f"Found Pinterest image in data at {path}.{key}: {value}")
                                            found_image = value
                                
                                # Рекурсивный поиск
                                if isinstance(value, (dict, list)):
                                    result = find_media_in_pinterest_data(value, f"{path}.{key}", is_video_priority)
                                    if result:
                                        if isinstance(result, tuple):
                                            if result[0]:  # video
                                                found_video = result[0]
                                            if result[1]:  # image
                                                found_image = result[1]
                                        elif isinstance(result, str):
                                            # Пропускаем m3u8
                                            if '.m3u8' not in result.lower() and 'hls' not in result.lower():
                                                if 'video' in result.lower() or any(ext in result.lower() for ext in ['.mp4', '.webm', '.mov', '.avi']):
                                                    found_video = result
                                                else:
                                                    found_image = result
                                
                                if found_video:
                                    break
                                    
                        elif isinstance(data, list):
                            for i, item in enumerate(data):
                                result = find_media_in_pinterest_data(item, f"{path}[{i}]", is_video_priority)
                                if result:
                                    if isinstance(result, tuple):
                                        if result[0]:
                                            found_video = result[0]
                                        if result[1]:
                                            found_image = result[1]
                                    elif isinstance(result, str):
                                        # Пропускаем m3u8
                                        if '.m3u8' not in result.lower() and 'hls' not in result.lower():
                                            if 'video' in result.lower() or any(ext in result.lower() for ext in ['.mp4', '.webm', '.mov', '.avi']):
                                                found_video = result
                                            else:
                                                found_image = result
                                if found_video:
                                    break
                        
                        return (found_video, found_image) if is_video_priority else (found_image, found_video)
                    
                    result = find_media_in_pinterest_data(pinterest_data, is_video_priority=True)
                    if result:
                        video_url, image_url = result
                        if video_url:
                            video_urls.append(video_url)
                        if image_url:
                            image_urls.append(image_url)
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug(f"Error parsing Pinterest data pattern {pattern}: {e}")
        
        # Ищем video теги в HTML
        # Pinterest использует blob URLs, поэтому ищем исходные данные в атрибутах и JavaScript
        video_tag_match = re.search(r'<video[^>]*>', html, re.IGNORECASE)
        has_video_tag = False
        if video_tag_match:
            has_video_tag = True
            video_tag = video_tag_match.group(0)
            
            # Ищем src атрибут (может быть blob URL)
            src_match = re.search(r'src=["\']([^"\']+)["\']', video_tag, re.IGNORECASE)
            if src_match:
                src_url = src_match.group(1)
                # Если это blob URL, это означает, что видео есть, но прямая ссылка недоступна
                if src_url.startswith('blob:'):
                    logger.warning(f"Found blob URL in video tag - Pinterest uses dynamic video loading, no direct URL available: {src_url}")
                    # Помечаем, что видео есть, но прямая ссылка недоступна
                    # Продолжаем поиск в других местах
                elif (src_url.startswith('http') or src_url.startswith('//')) and '.m3u8' not in src_url.lower():
                    logger.info(f"Found Pinterest video in <video> src: {src_url}")
                    video_urls.append(src_url)
            
            # Ищем data-атрибуты в video теге, которые могут содержать исходные URL
            data_attrs = re.findall(r'data-([^=]+)=["\']([^"\']+)["\']', video_tag, re.IGNORECASE)
            for attr_name, attr_value in data_attrs:
                if (attr_value.startswith('http') or attr_value.startswith('//')):
                    # Пропускаем m3u8
                    if '.m3u8' not in attr_value.lower() and 'hls' not in attr_value.lower():
                        logger.info(f"Found Pinterest video in video tag data-{attr_name}: {attr_value}")
                        video_urls.append(attr_value)
        
        # Ищем source теги внутри video (исключаем m3u8)
        video_source_match = re.search(r'<video[^>]*>.*?<source[^>]*src=["\']([^"\']+)["\']', html, re.DOTALL | re.IGNORECASE)
        if video_source_match:
            video_url = video_source_match.group(1)
            if (video_url.startswith('http') or video_url.startswith('//')) and '.m3u8' not in video_url.lower():
                logger.info(f"Found Pinterest video in <source> tag: {video_url}")
                video_urls.append(video_url)
        
        # Ищем в JavaScript коде, где могут быть исходные видео URL перед созданием blob
        # Pinterest часто хранит исходные URL в JavaScript переменных
        js_video_patterns = [
            r'["\']videoUrl["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']video_url["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']videoSrc["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']video_src["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']videoSource["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']video_source["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']streamUrl["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']stream_url["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']playbackUrl["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']playback_url["\']\s*:\s*["\']([^"\']+)["\']',
            r'videoUrl["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'video_url["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            # Прямой поиск .mp4, .webm, .mov ссылок в JavaScript
            r'["\']([^"\']*\.mp4[^"\']*)["\']',
            r'["\']([^"\']*\.webm[^"\']*)["\']',
            r'["\']([^"\']*\.mov[^"\']*)["\']',
            r'https?://[^"\']+\.mp4[^"\']*',
            r'https?://[^"\']+\.webm[^"\']*',
            r'https?://[^"\']+\.mov[^"\']*',
        ]
        for pattern in js_video_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0] if match else ''
                if match and (match.startswith('http') or match.startswith('//')):
                    # Пропускаем m3u8, blob URLs и изображения
                    if ('.m3u8' not in match.lower() and 'hls' not in match.lower() and 
                        not match.startswith('blob:') and 
                        'pinimg.com' not in match.lower() and
                        not match.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))):
                        logger.info(f"Found Pinterest video in JS pattern: {match}")
                        video_urls.append(match)
        
        # Ищем в JavaScript коде, где могут быть исходные видео URL перед созданием blob
        # Ищем паттерны типа: videoUrl, video_url, videoSrc, video_src и т.д.
        js_video_patterns = [
            r'["\']videoUrl["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']video_url["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']videoSrc["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']video_src["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']videoSource["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']video_source["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']streamUrl["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']stream_url["\']\s*:\s*["\']([^"\']+)["\']',
            r'videoUrl["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'video_url["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        ]
        for pattern in js_video_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0] if match else ''
                if match and (match.startswith('http') or match.startswith('//')):
                    # Пропускаем m3u8
                    if '.m3u8' not in match.lower() and 'hls' not in match.lower():
                        logger.info(f"Found Pinterest video in JS pattern {pattern}: {match}")
                        video_urls.append(match)
        
        # Объединяем все найденные изображения
        all_image_urls = temp_image_urls + image_urls
        
        # Если нашли видео, фильтруем m3u8, blob URLs и изображения, возвращаем прямые видео файлы
        if video_urls:
            # Фильтруем m3u8, HLS плейлисты, blob URLs и изображения
            direct_videos = []
            for v_url in video_urls:
                if ('.m3u8' not in v_url.lower() and 'hls' not in v_url.lower() and 
                    not v_url.startswith('blob:') and
                    'pinimg.com' not in v_url.lower() and
                    not v_url.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'))):
                    direct_videos.append(v_url)
            
            if direct_videos:
                # Предпочитаем URL с явными признаками видео (mp4, webm, mov, avi)
                for v_url in direct_videos:
                    if any(ext in v_url.lower() for ext in ['.mp4', '.webm', '.mov', '.avi', '.m4v', '.flv']):
                        logger.info(f"Returning Pinterest direct video URL (preferred): {v_url}")
                        return v_url
                # Если нет явных расширений, но это не m3u8 и не изображение, возвращаем первое
                logger.info(f"Returning first Pinterest direct video URL: {direct_videos[0]}")
                return direct_videos[0]
            else:
                # Если остались только m3u8 или blob URLs, логируем предупреждение
                logger.warning("Only m3u8/HLS playlists or blob URLs found, no direct video files available")
                # Не возвращаем m3u8 или blob, пусть вернется изображение
        
        # Если видео не найдено, но есть video тег с blob URL, это означает, что видео есть,
        # но Pinterest не предоставляет прямую ссылку (использует динамическую загрузку)
        # В этом случае возвращаем None, чтобы система могла использовать yt-dlp
        if has_video_tag and not video_urls:
            logger.warning("Pinterest pin contains video with blob URL, but no direct video URL is available. "
                          "Pinterest uses dynamic video loading. Will try yt-dlp for download.")
            # Возвращаем None, чтобы система могла использовать yt-dlp
            return None
        
        # Если видео не найдено и это не видео пин, возвращаем изображение (если есть)
        if all_image_urls:
            # Предпочитаем оригинальные размеры
            for img_url in all_image_urls:
                if 'originals' in img_url or '/originals/' in img_url:
                    logger.info(f"No video found, returning Pinterest original image URL: {img_url}")
                    return img_url
            logger.info(f"No video found, returning first Pinterest image URL: {all_image_urls[0]}")
            return all_image_urls[0]
        
        # Если ничего не найдено, возвращаем None
        logger.warning("No video or image found in Pinterest pin")
        return None
    except requests.RequestException as e:
        logger.warning(f"Error fetching Pinterest URL {url}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error parsing Pinterest URL {url}: {e}")
        return None


@login_required
@ensure_csrf_cookie
def upload_from_url(request):
    """Загрузка файла по URL"""
    if request.method != 'POST':
        return create_json_response(False, 'Неверный метод запроса', status=405)
    
    try:
        # Получаем URL из POST или JSON
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return create_json_response(False, 'Некорректный JSON в запросе', status=400)
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
        
        # Проверяем, является ли это Google Drive или Pinterest ссылкой, и преобразуем её
        original_url = file_url  # Сохраняем оригинальный URL для возможного использования
        
        # Сначала проверяем Pinterest
        is_pinterest = False
        parsed = urlparse(file_url)
        if parsed.netloc in ['pinterest.com', 'www.pinterest.com', 'ru.pinterest.com', 'pinterest.ru'] and '/pin/' in parsed.path:
            is_pinterest = True
        
        pinterest_url = convert_pinterest_url(file_url)
        if pinterest_url:
            # Проверяем, не является ли это изображением (для видео пинов нужно использовать yt-dlp)
            # Если URL содержит pinimg.com, это изображение, используем его
            if 'pinimg.com' in pinterest_url.lower():
                logger.info(f"Detected Pinterest URL: {original_url}, converting to image: {pinterest_url}")
                file_url = pinterest_url
            else:
                # Если это не изображение, возможно это видео URL, используем его
                logger.info(f"Detected Pinterest URL: {original_url}, converting to: {pinterest_url}")
                file_url = pinterest_url
        elif is_pinterest:
            # Если это Pinterest, но convert_pinterest_url вернул None (blob URL или видео)
            # Пытаемся использовать yt-dlp для загрузки видео
            logger.info(f"Pinterest URL detected but no direct link found (likely blob URL video), trying yt-dlp for video download")
            downloaded_video_path = download_pinterest_video_with_ytdlp(original_url)
            if downloaded_video_path and os.path.exists(downloaded_video_path):
                # Файл уже скачан через yt-dlp, обрабатываем его напрямую
                logger.info(f"Successfully downloaded Pinterest video using yt-dlp: {downloaded_video_path}")
                
                # Получаем текущую папку для загрузки
                folder = None
                if folder_id:
                    try:
                        folder = Folder.objects.get(id=folder_id, user=request.user)
                    except Folder.DoesNotExist:
                        pass
                
                # Подготовка папки пользователя
                user_folder = ensure_user_folder_exists(request.user.id)
                
                # Получаем имя файла из скачанного файла
                original_filename = os.path.basename(downloaded_video_path)
                filename = generate_unique_filename(user_folder, original_filename)
                file_path = os.path.join(user_folder, filename)
                
                # Перемещаем файл из временной директории в постоянную
                try:
                    import shutil
                    shutil.move(downloaded_video_path, file_path)
                    
                    # Получаем размер файла
                    actual_size = os.path.getsize(file_path)
                    logger.info(f"File moved successfully, size: {actual_size} bytes")
                    
                    # Проверяем размер файла
                    if actual_size > settings.MAX_FILE_SIZE:
                        os.remove(file_path)
                        return create_json_response(
                            False, 
                            f'Файл слишком большой. Максимальный размер: {settings.MAX_FILE_SIZE / (1024 * 1024):.0f}MB', 
                            status=400
                        )
                    
                    # Проверяем квоту хранилища
                    quota_error = validate_storage_quota(request.user, actual_size, request)
                    if quota_error:
                        os.remove(file_path)
                        return quota_error
                    
                    # Создаем запись в БД
                    try:
                        file = UserFile.objects.create(
                            user=request.user,
                            file=f'{request.user.id}/{filename}',
                            filename=filename,
                            file_size=actual_size,
                            folder=folder
                        )
                        logger.info(f"File record created in DB: {file.id}")
                    except Exception as e:
                        logger.error(f"Error creating file record in DB: {e}")
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except:
                                pass
                        return create_json_response(
                            False,
                            f'Ошибка при создании записи файла: {str(e)}',
                            status=500
                        )
                    
                    # Создаем токен для скачивания
                    generate_download_token(file)
                    
                    # Удаляем временную директорию
                    try:
                        temp_dir = os.path.dirname(downloaded_video_path)
                        if os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir)
                    except:
                        pass
                    
                    return create_json_response(True, SUCCESS_FILE_UPLOADED)
                    
                except Exception as e:
                    logger.error(f"Error moving downloaded video file: {e}")
                    # Удаляем временный файл
                    try:
                        if os.path.exists(downloaded_video_path):
                            os.remove(downloaded_video_path)
                        temp_dir = os.path.dirname(downloaded_video_path)
                        if os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir)
                    except:
                        pass
                    return create_json_response(
                        False,
                        f'Ошибка при сохранении скачанного видео: {str(e)}',
                        status=500
                    )
            else:
                # Если yt-dlp не помог, проверяем, есть ли video тег (это точно видео пин)
                # Если это видео пин, не возвращаем изображение
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    response = requests.get(original_url, headers=headers, timeout=10)
                    response.raise_for_status()
                    html = response.text
                    has_video_tag = bool(re.search(r'<video[^>]*>', html, re.IGNORECASE))
                    
                    if has_video_tag:
                        # Это видео пин, но yt-dlp не смог скачать
                        logger.error("Video pin detected but yt-dlp failed to download")
                        return create_json_response(
                            False,
                            'Ошибка загрузки. код: cloadres_000',
                            status=400
                        )
                    else:
                        # Это не видео пин, можно попробовать получить изображение
                        logger.warning("Could not download with yt-dlp, trying to get image (not a video pin)")
                        pinterest_url = convert_pinterest_url(original_url)
                        if pinterest_url:
                            file_url = pinterest_url
                        else:
                            return create_json_response(
                                False,
                                'Не удалось загрузить контент из Pinterest.',
                                status=400
                            )
                except Exception as e:
                    logger.error(f"Error checking Pinterest pin type: {e}")
                    # Если не удалось проверить, предполагаем что это видео пин
                    return create_json_response(
                        False,
                        'Ошибка загрузки. код: cloadres_000',
                        status=400
                    )
        
        # Затем проверяем Google Drive
        google_drive_url = convert_google_drive_url(file_url)
        if google_drive_url:
            logger.info(f"Detected Google Drive URL: {original_url}, converting to: {google_drive_url}")
            file_url = google_drive_url
        
        # Получаем текущую папку для загрузки
        folder = None
        if folder_id:
            try:
                folder = Folder.objects.get(id=folder_id, user=request.user)
            except Folder.DoesNotExist:
                pass
        
        # Скачиваем файл
        use_proxy = False
        proxy_attempted = False
        
        try:
            # Устанавливаем таймаут и заголовки для запроса
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            logger.info(f"Starting download from URL: {file_url}")
            
            # Делаем HEAD запрос для проверки размера файла (если поддерживается)
            content_length = None
            try:
                head_response = requests.head(file_url, headers=headers, timeout=30, allow_redirects=True)
                content_length = head_response.headers.get('Content-Length')
                logger.info(f"HEAD request successful, Content-Length: {content_length}")
            except requests.exceptions.RequestException as e:
                # Если HEAD запрос не поддерживается, пропускаем проверку размера
                # Размер будет проверен во время загрузки
                logger.warning(f"HEAD request failed, will check size during download: {e}")
                pass
            
            if content_length:
                try:
                    file_size = int(content_length)
                    logger.info(f"File size from headers: {file_size} bytes ({file_size / (1024*1024):.2f} MB)")
                    
                    # Проверяем размер файла
                    if file_size > settings.MAX_FILE_SIZE:
                        max_size_mb = settings.MAX_FILE_SIZE / (1024 * 1024)
                        logger.warning(f"File too large: {file_size / (1024*1024):.2f} MB > {max_size_mb:.0f} MB")
                        return create_json_response(
                            False, 
                            f'Файл слишком большой. Максимальный размер: {max_size_mb:.0f}MB', 
                            status=400
                        )
                    
                    # Проверяем квоту хранилища
                    quota_error = validate_storage_quota(request.user, file_size, request)
                    if quota_error:
                        logger.warning(f"Storage quota exceeded for user {request.user.id}")
                        return quota_error
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse Content-Length: {content_length}, error: {e}")
            
            # Скачиваем файл с увеличенным таймаутом для больших файлов
            logger.info(f"Starting GET request to download file...")
            response = None
            try:
                response = requests.get(file_url, headers=headers, timeout=600, stream=True, allow_redirects=True)
                response.raise_for_status()
            except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
                # Если первая попытка не удалась, пробуем через прокси
                logger.warning(f"Direct download failed: {e}, attempting via proxy...")
                if response:
                    try:
                        response.close()
                    except:
                        pass
                
                proxy_response = download_via_proxy(file_url, headers, timeout=600)
                if proxy_response:
                    response = proxy_response
                    use_proxy = True
                    proxy_attempted = True
                    logger.info("Successfully retrying download via proxy")
                else:
                    # Если прокси тоже не помог, возвращаем ошибку
                    error_msg = f'Не удалось скачать файл: {str(e)}. Попытка через прокси также не удалась.'
                    return create_json_response(False, error_msg, status=500)
            
            # Проверяем, не вернул ли Google Drive HTML страницу (например, для больших файлов требуется подтверждение)
            content_type = response.headers.get('Content-Type', '')
            is_google_drive = 'drive.google.com' in original_url or 'docs.google.com' in original_url
            
            if 'text/html' in content_type and is_google_drive:
                # Пытаемся найти прямую ссылку в HTML или используем альтернативный метод
                logger.warning("Google Drive returned HTML page, file may require confirmation or be too large")
                
                # Для больших файлов Google Drive может требовать подтверждение
                # Пытаемся использовать альтернативный формат ссылки
                file_id = extract_google_drive_file_id(original_url)
                if file_id:
                    # Для больших файлов Google Drive требует подтверждение
                    # Используем формат с confirm параметром
                    alt_url = f'https://drive.google.com/uc?export=download&confirm=t&id={file_id}'
                    logger.info(f"Trying alternative Google Drive URL: {alt_url}")
                    response.close()  # Закрываем предыдущий ответ
                    response = requests.get(alt_url, headers=headers, timeout=600, stream=True, allow_redirects=True)
                    response.raise_for_status()
                    content_type = response.headers.get('Content-Type', '')
                    
                    if 'text/html' in content_type:
                        return create_json_response(
                            False,
                            'Не удалось скачать файл из Google Drive. Файл может быть слишком большим или требовать подтверждения доступа. Убедитесь, что файл доступен для скачивания (настройки доступа: "Все, у кого есть ссылка").',
                            status=400
                        )
                else:
                    return create_json_response(
                        False,
                        'Не удалось определить ID файла из Google Drive ссылки. Убедитесь, что ссылка корректна.',
                        status=400
                    )
            
            logger.info(f"GET request successful, status: {response.status_code}, Content-Type: {content_type}")
            
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
            
            # Определяем расширение на основе Content-Type, если его нет
            content_type = response.headers.get('Content-Type', '').lower()
            if '.' not in filename or not os.path.splitext(filename)[1]:
                # Определяем расширение по Content-Type
                if 'video' in content_type:
                    if 'mp4' in content_type:
                        filename += '.mp4'
                    elif 'webm' in content_type:
                        filename += '.webm'
                    elif 'quicktime' in content_type or 'mov' in content_type:
                        filename += '.mov'
                    elif 'x-msvideo' in content_type or 'avi' in content_type:
                        filename += '.avi'
                    else:
                        filename += '.mp4'  # По умолчанию для видео
                elif 'image' in content_type:
                    if 'jpeg' in content_type or 'jpg' in content_type:
                        filename += '.jpg'
                    elif 'png' in content_type:
                        filename += '.png'
                    elif 'gif' in content_type:
                        filename += '.gif'
                    elif 'webp' in content_type:
                        filename += '.webp'
                    else:
                        filename += '.jpg'  # По умолчанию для изображений
                elif 'pdf' in content_type:
                    filename += '.pdf'
                elif 'text' in content_type:
                    filename += '.txt'
                else:
                    # Если это Pinterest URL, пытаемся определить тип по URL
                    if 'pinterest' in original_url.lower():
                        # Проверяем, был ли это видео или изображение
                        if 'video' in file_url.lower() or 'mp4' in file_url.lower() or 'webm' in file_url.lower():
                            filename += '.mp4'
                        else:
                            filename += '.jpg'
                    else:
                        filename += '.bin'  # По умолчанию для неизвестных типов
            
            # Подготовка папки пользователя
            user_folder = ensure_user_folder_exists(request.user.id)
            
            # Генерация уникального имени файла
            filename = generate_unique_filename(user_folder, filename)
            file_path = os.path.join(user_folder, filename)
            
            # Сохранение файла
            downloaded_size = 0
            chunk_size = 1024 * 1024  # 1MB chunks для больших файлов
            last_log_size = 0
            log_interval = 10 * 1024 * 1024  # Логируем каждые 10MB
            
            try:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            
                            # Логируем прогресс для больших файлов
                            if downloaded_size - last_log_size >= log_interval:
                                logger.info(f"Downloaded {downloaded_size / (1024*1024):.2f} MB of {file_url}")
                                last_log_size = downloaded_size
                            
                            # Проверяем размер во время загрузки
                            if downloaded_size > settings.MAX_FILE_SIZE:
                                os.remove(file_path)
                                logger.warning(f"File exceeded max size during download: {downloaded_size / (1024*1024):.2f} MB")
                                return create_json_response(
                                    False, 
                                    f'Файл слишком большой. Максимальный размер: {settings.MAX_FILE_SIZE / (1024 * 1024):.0f}MB', 
                                    status=400
                                )
                
                logger.info(f"File downloaded successfully, size: {downloaded_size} bytes")
            except IOError as e:
                logger.error(f"IOError while saving file: {e}")
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                
                # Если еще не пробовали через прокси, пробуем сейчас
                if not proxy_attempted:
                    logger.info("Retrying download via proxy after IOError...")
                    try:
                        if response:
                            response.close()
                    except:
                        pass
                    
                    proxy_response = download_via_proxy(file_url, headers, timeout=600)
                    if proxy_response:
                        # Пробуем сохранить файл снова через прокси
                        downloaded_size = 0
                        try:
                            with open(file_path, 'wb') as f:
                                for chunk in proxy_response.iter_content(chunk_size=chunk_size):
                                    if chunk:
                                        f.write(chunk)
                                        downloaded_size += len(chunk)
                                        
                                        if downloaded_size > settings.MAX_FILE_SIZE:
                                            os.remove(file_path)
                                            return create_json_response(
                                                False, 
                                                f'Файл слишком большой. Максимальный размер: {settings.MAX_FILE_SIZE / (1024 * 1024):.0f}MB', 
                                                status=400
                                            )
                            logger.info(f"File downloaded successfully via proxy, size: {downloaded_size} bytes")
                            # Продолжаем выполнение - файл успешно сохранен через прокси
                        except Exception as proxy_error:
                            logger.error(f"Error saving file via proxy: {proxy_error}")
                            if os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                except:
                                    pass
                            return create_json_response(
                                False,
                                f'Ошибка при сохранении файла: {str(e)}. Попытка через прокси также не удалась: {str(proxy_error)}',
                                status=500
                            )
                    else:
                        return create_json_response(
                            False,
                            f'Ошибка при сохранении файла: {str(e)}. Попытка через прокси также не удалась.',
                            status=500
                        )
                else:
                    return create_json_response(
                        False,
                        f'Ошибка при сохранении файла: {str(e)}',
                        status=500
                    )
            
            # Получаем реальный размер файла
            try:
                actual_size = os.path.getsize(file_path)
                logger.info(f"File saved, actual size: {actual_size} bytes")
            except OSError as e:
                logger.error(f"Error getting file size: {e}")
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                return create_json_response(
                    False,
                    f'Ошибка при проверке размера файла: {str(e)}',
                    status=500
                )
            
            # Создание записи в БД
            try:
                file = UserFile.objects.create(
                    user=request.user,
                    file=f'{request.user.id}/{filename}',
                    filename=filename,
                    file_size=actual_size,
                    folder=folder
                )
                logger.info(f"File record created in DB: {file.id}")
            except Exception as e:
                logger.error(f"Error creating file record in DB: {e}")
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                return create_json_response(
                    False,
                    f'Ошибка при создании записи в базе данных: {str(e)}',
                    status=500
                )
            
            # Создаем токен для скачивания при загрузке файла
            try:
                generate_download_token(file)
                logger.info(f"Download token created for file {file.id}")
            except Exception as e:
                logger.warning(f"Error creating download token: {e}, but file is saved")
            
            logger.info(f"File upload from URL completed successfully: {filename}")
            return create_json_response(
                True, 
                'Файл успешно загружен по URL',
                data={'filename': filename, 'file_id': file.id}
            )
            
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout while downloading file from URL {file_url}: {e}", exc_info=True)
            return create_json_response(
                False, 
                'Превышено время ожидания при скачивании файла. Файл может быть слишком большим или сервер недоступен.', 
                status=500
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error downloading file from URL {file_url}: {e}", exc_info=True)
            return create_json_response(
                False,
                'Ошибка подключения к серверу. Проверьте URL и доступность файла.',
                status=500
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error downloading file from URL {file_url}: {e}", exc_info=True)
            error_msg = f'Ошибка при скачивании файла: {str(e)}'
            return create_json_response(
                False, 
                error_msg, 
                status=500
            )
        except OSError as e:
            logger.error(f"OS error while uploading file from URL {file_url}: {e}", exc_info=True)
            return create_json_response(
                False,
                f'Ошибка файловой системы: {str(e)}. Возможно, недостаточно места на диске.',
                status=500
            )
        except Exception as e:
            logger.error(f"Unexpected error uploading file from URL {file_url}: {e}", exc_info=True)
            return create_json_response(
                False, 
                f'Ошибка при загрузке файла: {str(e)}', 
                status=500
            )
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in upload_from_url: {e}")
        return create_json_response(False, 'Ошибка при обработке запроса: некорректный JSON', status=400)
    except Exception as e:
        logger.error(f"Error in upload_from_url: {e}", exc_info=True)
        # Всегда возвращаем JSON, даже при ошибках
        error_message = str(e) if str(e) else 'Неизвестная ошибка'
        return create_json_response(False, f'Ошибка: {error_message}', status=500)

