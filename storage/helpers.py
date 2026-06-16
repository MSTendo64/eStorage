"""
Вспомогательные функции для работы с файлами
"""
import os
import uuid
import asyncio
from typing import Tuple, Optional, Union
from django.conf import settings
from django.http import JsonResponse, HttpRequest, HttpResponseRedirect
from django.contrib import messages
from django.shortcuts import redirect
from eventshock_auth.models import UserProfile
from storage.models import Storage
import logging

logger = logging.getLogger(__name__)


def get_user_folder_path(user_id: int) -> str:
    """Возвращает путь к папке пользователя"""
    return os.path.join(settings.MEDIA_ROOT, str(user_id))


def ensure_user_folder_exists(user_id: int) -> str:
    """Создает папку пользователя, если её нет, и возвращает путь"""
    user_folder = get_user_folder_path(user_id)
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)
    return user_folder


def sanitize_filename(filename: str) -> str:
    """
    Очищает имя файла от недопустимых символов для файловой системы.
    """
    import re
    # Удаляем недопустимые символы для Windows и Unix
    # Windows: < > : " / \ | ? *
    # Также удаляем управляющие символы (0x00-0x1F)
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    filename = re.sub(invalid_chars, '_', filename)
    
    # Удаляем пробелы в начале и конце
    filename = filename.strip()
    
    # Удаляем точки в конце (кроме расширения)
    while filename.endswith('.') and '.' in filename[:-1]:
        filename = filename[:-1]
    
    # Если имя файла пустое после очистки, используем дефолтное
    if not filename or filename == '.' or filename == '..':
        filename = 'file'
    
    # Ограничиваем длину имени файла (255 символов - стандартный лимит)
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        max_name_length = 255 - len(ext)
        filename = name[:max_name_length] + ext
    
    return filename


def generate_unique_filename(user_folder: str, original_filename: str) -> str:
    """
    Генерирует уникальное имя файла, избегая конфликтов.
    Возвращает имя файла без полного пути.
    """
    # Очищаем имя файла от недопустимых символов
    filename = sanitize_filename(original_filename)
    file_path = os.path.join(user_folder, filename)
    
    counter = 1
    while os.path.exists(file_path):
        name, ext = os.path.splitext(filename)
        # Если имя файла уже содержит суффикс _N, заменяем его
        if name.endswith(f'_{counter - 1}'):
            name = name[:-len(f'_{counter - 1}')]
        filename = f"{name}_{counter}{ext}"
        file_path = os.path.join(user_folder, filename)
        counter += 1
        # Защита от бесконечного цикла
        if counter > 10000:
            # Используем UUID если не удалось найти уникальное имя
            import uuid
            name, ext = os.path.splitext(sanitize_filename(original_filename))
            filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
            break
    
    return filename


def validate_file_size(uploaded_file, request: HttpRequest) -> Optional[Union[JsonResponse, HttpResponseRedirect]]:
    """
    Проверяет размер файла. Возвращает JsonResponse или HttpResponseRedirect с ошибкой, 
    если файл слишком большой. Иначе возвращает None.
    """
    if uploaded_file.size > settings.MAX_FILE_SIZE:
        max_size_mb = settings.MAX_FILE_SIZE / (1024 * 1024)
        error_msg = f'Файл слишком большой. Максимальный размер: {max_size_mb:.0f}MB'
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': error_msg}, status=400)
        
        messages.error(request, error_msg)
        return redirect('dashboard')
    
    return None


def validate_storage_quota(user, file_size: int, request: HttpRequest) -> Optional[Union[JsonResponse, HttpResponseRedirect]]:
    """
    Проверяет доступность места в хранилище. Возвращает JsonResponse или HttpResponseRedirect 
    с ошибкой, если места недостаточно. Иначе возвращает None.
    """
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    if profile.get_used_storage() + file_size > profile.storage_quota:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'Недостаточно места в хранилище'}, status=400)
        
        messages.error(request, 'Недостаточно места в хранилище')
        return redirect('dashboard')
    
    return None


def create_json_response(success: bool, message: str = None, data: dict = None, 
                         status: int = 200) -> JsonResponse:
    """Создает стандартизированный JSON ответ"""
    response_data = {'success': success}
    
    if message:
        response_data['message' if success else 'error'] = message
    
    if data:
        response_data.update(data)
    
    return JsonResponse(response_data, status=status)


def get_file_path(user_file) -> Optional[str]:
    """Возвращает полный путь к файлу на диске"""
    # Если файл в хранилище, используем путь хранилища
    if user_file.storage:
        if user_file.storage.storage_type == 'local':
            return user_file.storage.get_storage_path(user_file.user.id, user_file.filename)
        elif user_file.storage.storage_type == 's3':
            # Для S3 возвращаем None, так как файл нужно скачивать через aioboto3
            return None
    # Иначе используем стандартный путь
    return os.path.join(settings.MEDIA_ROOT, str(user_file.file))


def get_file_for_response(user_file):
    """
    Возвращает файл для HTTP ответа, учитывая тип хранилища.
    Для локальных файлов возвращает путь, для S3 - скачивает во временный файл.
    
    Returns:
        tuple: (file_path_or_file_object, is_temp_file, temp_file_path)
        - file_path_or_file_object: путь к файлу или файловый объект
        - is_temp_file: True если это временный файл (нужно удалить после использования)
        - temp_file_path: путь к временному файлу (если is_temp_file=True)
    """
    if user_file.storage:
        if user_file.storage.storage_type == 'local':
            file_path = user_file.storage.get_storage_path(user_file.user.id, user_file.filename)
            if os.path.exists(file_path):
                return (file_path, False, None)
            else:
                logger.error(f"File not found in local storage: {file_path}")
                return (None, False, None)
        elif user_file.storage.storage_type == 's3':
            # Для S3 скачиваем во временный файл
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file_path = temp_file.name
            temp_file.close()
            
            s3_key = f"{user_file.user.id}/{user_file.filename}"
            if download_file_from_s3(user_file.storage, s3_key, temp_file_path):
                return (temp_file_path, True, temp_file_path)
            else:
                logger.error(f"Failed to download file from S3: {s3_key}")
                return (None, False, None)
    
    # Для файлов без хранилища используем стандартный путь
    file_path = os.path.join(settings.MEDIA_ROOT, str(user_file.file))
    if os.path.exists(file_path):
        return (file_path, False, None)
    else:
        logger.error(f"File not found in media: {file_path}")
        return (None, False, None)


def has_any_storage() -> bool:
    """
    Проверяет, есть ли хотя бы одно активное хранилище в системе.
    
    Returns:
        True, если есть хотя бы одно активное хранилище, иначе False
    """
    return Storage.objects.filter(is_active=True).exists()


def select_optimal_storage(file_size: int) -> Optional[Storage]:
    """
    Выбирает оптимальное хранилище для загрузки файла.
    Выбирает хранилище с наибольшим свободным местом, которое может вместить файл.
    
    Args:
        file_size: Размер файла в байтах
    
    Returns:
        Storage объект или None, если подходящего хранилища нет
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Получаем все активные хранилища, отсортированные по приоритету
    storages = Storage.objects.filter(is_active=True).order_by('-priority', 'name')
    
    logger.info(f"Поиск хранилища для файла размером {file_size} байт. Найдено активных хранилищ: {storages.count()}")
    
    if not storages.exists():
        logger.warning("Нет активных хранилищ")
        return None
    
    # Фильтруем хранилища, которые могут вместить файл
    suitable_storages = []
    for s in storages:
        can_store = s.can_store_file(file_size)
        available = s.get_available_size()
        logger.info(f"Хранилище '{s.name}': может вместить={can_store}, доступно={available} байт, максимум={s.max_size} байт")
        if can_store:
            suitable_storages.append(s)
    
    if not suitable_storages:
        logger.warning(f"Нет подходящих хранилищ для файла размером {file_size} байт")
        return None
    
    # Выбираем хранилище с наибольшим свободным местом
    best_storage = max(suitable_storages, key=lambda s: s.get_available_size())
    logger.info(f"Выбрано хранилище '{best_storage.name}' с доступным местом {best_storage.get_available_size()} байт")
    
    return best_storage


def get_storage_user_folder_path(storage: Storage, user_id: int) -> str:
    """Возвращает путь к папке пользователя в хранилище"""
    if storage.storage_type == 'local':
        user_folder = os.path.join(storage.local_path, str(user_id))
        if not os.path.exists(user_folder):
            os.makedirs(user_folder, exist_ok=True)
        return user_folder
    # Для S3 путь не нужен, так как файлы загружаются через aioboto3
    return None


def ensure_storage_user_folder_exists(storage: Storage, user_id: int) -> Optional[str]:
    """Создает папку пользователя в хранилище, если её нет, и возвращает путь"""
    if storage.storage_type == 'local':
        return get_storage_user_folder_path(storage, user_id)
    return None


async def _upload_file_to_s3_async(storage: Storage, file_path: str, s3_key: str, progress_callback=None) -> bool:
    """
    Асинхронная функция для загрузки файла в S3-совместимое хранилище.
    
    Args:
        storage: Объект Storage с настройками S3
        file_path: Локальный путь к файлу
        s3_key: Ключ (путь) в S3 bucket
        progress_callback: Опциональная функция для отслеживания прогресса (bytes_uploaded, total_bytes)
    
    Returns:
        True если загрузка успешна, False в противном случае
    """
    try:
        import aioboto3
        from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
        
        # Получаем размер файла для отслеживания прогресса
        file_size = os.path.getsize(file_path)
        uploaded_bytes = 0
        
        # Создаем сессию aioboto3
        session = aioboto3.Session()
        
        # Конфигурация для S3 клиента
        s3_config = {
            'aws_access_key_id': storage.s3_access_key,
            'aws_secret_access_key': storage.s3_secret_key,
        }
        
        if storage.s3_endpoint_url:
            s3_config['endpoint_url'] = storage.s3_endpoint_url
        
        if storage.s3_region:
            s3_config['region_name'] = storage.s3_region
        
        # Загружаем файл в S3
        from botocore.config import Config
        from boto3.s3.transfer import TransferConfig
        
        # Конфигурация клиента: таймауты и повторные попытки
        client_config = Config(
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            },
            connect_timeout=60,
            read_timeout=600,  # 10 минут на чтение для больших файлов
        )
        
        # Конфигурация передачи: multipart upload для больших файлов
        transfer_config = TransferConfig(
            multipart_threshold=100 * 1024 * 1024,  # 100 MB
            multipart_chunksize=100 * 1024 * 1024,  # 100 MB
        )
        
        async with session.client('s3', **s3_config, config=client_config) as s3_client:
            try:
                with open(file_path, 'rb') as file_data:
                    await s3_client.upload_fileobj(
                        file_data,
                        storage.s3_bucket_name,
                        s3_key,
                        Config=transfer_config,
                    )
                logger.info(f"Файл успешно загружен в S3 хранилище '{storage.name}': {s3_key} (размер: {file_size} байт)")
                return True
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                error_message = e.response.get('Error', {}).get('Message', str(e))
                error_details = e.response.get('Error', {})
                
                # Логируем полную информацию об ошибке
                logger.error(
                    f"Ошибка ClientError при загрузке файла в S3 '{storage.name}': "
                    f"Code={error_code}, Message={error_message}, "
                    f"File={s3_key}, Size={file_size} байт, "
                    f"Details={error_details}",
                    exc_info=True
                )
                
                # Если ошибка связана с multipart upload, пробуем простую загрузку для небольших файлов
                if error_code in ['InvalidRequest', 'MalformedXML', 'InvalidArgument'] and file_size < 100 * 1024 * 1024:
                    logger.info(f"Пробуем простую загрузку без multipart для файла {s3_key}")
                    try:
                        with open(file_path, 'rb') as file_data:
                            # Используем put_object для простой загрузки
                            file_data.seek(0)
                            file_content = file_data.read()
                            await s3_client.put_object(
                                Bucket=storage.s3_bucket_name,
                                Key=s3_key,
                                Body=file_content
                            )
                        logger.info(f"Файл успешно загружен простым методом в S3 '{storage.name}': {s3_key}")
                        return True
                    except Exception as e2:
                        logger.error(f"Ошибка при простой загрузке: {str(e2)}", exc_info=True)
                
                return False
            except Exception as e:
                logger.error(
                    f"Неожиданная ошибка при загрузке в S3 '{storage.name}': "
                    f"{type(e).__name__}: {str(e)}, "
                    f"File={s3_key}, Size={file_size} байт",
                    exc_info=True
                )
                return False
                
    except ImportError:
        logger.error("Библиотека aioboto3 не установлена. Установите: pip install aioboto3")
        return False
    except Exception as e:
        logger.error(f"Ошибка при инициализации S3 клиента: {str(e)}")
        return False


def upload_file_to_s3(storage: Storage, file_path: str, s3_key: str, progress_callback=None) -> bool:
    """
    Загружает файл в S3-совместимое хранилище с отслеживанием прогресса.
    Синхронная обертка над асинхронной функцией.
    
    Args:
        storage: Объект Storage с настройками S3
        file_path: Локальный путь к файлу
        s3_key: Ключ (путь) в S3 bucket
        progress_callback: Опциональная функция для отслеживания прогресса (bytes_uploaded, total_bytes)
    
    Returns:
        True если загрузка успешна, False в противном случае
    """
    if storage.storage_type != 's3':
        logger.error(f"Попытка загрузить файл в не-S3 хранилище: {storage.name}")
        return False
    
    try:
        # Запускаем асинхронную функцию в синхронном контексте
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_upload_file_to_s3_async(storage, file_path, s3_key, progress_callback))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла в S3: {str(e)}")
        return False


async def _generate_s3_presigned_url_async(storage: Storage, s3_key: str, expiration: int = 3600, 
                                          response_content_disposition: Optional[str] = None) -> Optional[str]:
    """
    Асинхронная функция для генерации presigned URL для прямого скачивания файла из S3.
    
    Args:
        storage: Объект Storage с настройками S3
        s3_key: Ключ (путь) в S3 bucket
        expiration: Время жизни URL в секундах (по умолчанию 1 час)
        response_content_disposition: Content-Disposition заголовок (например, 'attachment; filename="file.mp4"')
    
    Returns:
        Presigned URL или None в случае ошибки
    """
    try:
        import aioboto3
        from botocore.exceptions import ClientError
        
        # Создаем сессию aioboto3
        session = aioboto3.Session()
        
        # Конфигурация для S3 клиента
        s3_config = {
            'aws_access_key_id': storage.s3_access_key,
            'aws_secret_access_key': storage.s3_secret_key,
        }
        
        if storage.s3_endpoint_url:
            s3_config['endpoint_url'] = storage.s3_endpoint_url
        
        if storage.s3_region:
            s3_config['region_name'] = storage.s3_region
        
        # Генерируем presigned URL
        async with session.client('s3', **s3_config) as s3_client:
            try:
                params = {
                    'Bucket': storage.s3_bucket_name,
                    'Key': s3_key
                }
                if response_content_disposition:
                    params['ResponseContentDisposition'] = response_content_disposition
                
                # generate_presigned_url в aioboto3 асинхронный метод
                presigned_url = await s3_client.generate_presigned_url(
                    'get_object',
                    Params=params,
                    ExpiresIn=expiration
                )
                logger.info(f"Presigned URL сгенерирован для файла '{s3_key}' в хранилище '{storage.name}'")
                return presigned_url
            except ClientError as e:
                logger.error(f"Ошибка при генерации presigned URL: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"Неожиданная ошибка при генерации presigned URL: {str(e)}")
                return None
                
    except ImportError:
        logger.error("Библиотека aioboto3 не установлена")
        return None
    except Exception as e:
        logger.error(f"Ошибка при инициализации S3 клиента: {str(e)}")
        return None


def generate_s3_presigned_url(storage: Storage, s3_key: str, expiration: int = 3600, 
                              response_content_disposition: Optional[str] = None) -> Optional[str]:
    """
    Генерирует presigned URL для прямого скачивания файла из S3.
    Синхронная обертка над асинхронной функцией.
    
    Args:
        storage: Объект Storage с настройками S3
        s3_key: Ключ (путь) в S3 bucket
        expiration: Время жизни URL в секундах (по умолчанию 1 час)
        response_content_disposition: Content-Disposition заголовок (например, 'attachment; filename="file.mp4"')
    
    Returns:
        Presigned URL или None в случае ошибки
    """
    if storage.storage_type != 's3':
        logger.error(f"Попытка сгенерировать presigned URL для не-S3 хранилища: {storage.name}")
        return None
    
    try:
        # Запускаем асинхронную функцию в синхронном контексте
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_generate_s3_presigned_url_async(storage, s3_key, expiration, response_content_disposition))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Ошибка при генерации presigned URL: {str(e)}")
        return None


async def _download_file_from_s3_async(storage: Storage, s3_key: str, local_path: str) -> bool:
    """
    Асинхронная функция для скачивания файла из S3-совместимого хранилища.
    
    Args:
        storage: Объект Storage с настройками S3
        s3_key: Ключ (путь) в S3 bucket
        local_path: Локальный путь для сохранения файла
    
    Returns:
        True если скачивание успешно, False в противном случае
    """
    try:
        import aioboto3
        from botocore.exceptions import ClientError
        
        # Создаем сессию aioboto3
        session = aioboto3.Session()
        
        # Конфигурация для S3 клиента
        s3_config = {
            'aws_access_key_id': storage.s3_access_key,
            'aws_secret_access_key': storage.s3_secret_key,
        }
        
        if storage.s3_endpoint_url:
            s3_config['endpoint_url'] = storage.s3_endpoint_url
        
        if storage.s3_region:
            s3_config['region_name'] = storage.s3_region
        
        # Скачиваем файл из S3
        async with session.client('s3', **s3_config) as s3_client:
            try:
                # Создаем директорию, если её нет
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                
                with open(local_path, 'wb') as file_data:
                    await s3_client.download_fileobj(
                        storage.s3_bucket_name,
                        s3_key,
                        file_data
                    )
                logger.info(f"Файл успешно скачан из S3 хранилища '{storage.name}': {s3_key}")
                return True
            except ClientError as e:
                logger.error(f"Ошибка при скачивании файла из S3: {str(e)}")
                return False
            except Exception as e:
                logger.error(f"Неожиданная ошибка при скачивании из S3: {str(e)}")
                return False
                
    except ImportError:
        logger.error("Библиотека aioboto3 не установлена. Установите: pip install aioboto3")
        return False
    except Exception as e:
        logger.error(f"Ошибка при инициализации S3 клиента: {str(e)}")
        return False


def download_file_from_s3(storage: Storage, s3_key: str, local_path: str) -> bool:
    """
    Скачивает файл из S3-совместимого хранилища.
    Синхронная обертка над асинхронной функцией.
    
    Args:
        storage: Объект Storage с настройками S3
        s3_key: Ключ (путь) в S3 bucket
        local_path: Локальный путь для сохранения файла
    
    Returns:
        True если скачивание успешно, False в противном случае
    """
    if storage.storage_type != 's3':
        logger.error(f"Попытка скачать файл из не-S3 хранилища: {storage.name}")
        return False
    
    try:
        # Запускаем асинхронную функцию в синхронном контексте
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_download_file_from_s3_async(storage, s3_key, local_path))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла из S3: {str(e)}")
        return False

