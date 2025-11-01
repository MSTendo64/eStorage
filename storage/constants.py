"""
Константы для приложения storage
"""
from django.conf import settings

# Задержки и таймауты
CLEANUP_DELAY = 300  # 5 минут
TEMP_FOLDER_PREFIX = 'temp_extracted_'
TEMP_DOWNLOADS_PREFIX = 'temp_download_'

# Размеры файлов
BYTES_PER_MB = 1024 * 1024
BYTES_PER_GB = 1024 * 1024 * 1024

# Типы файлов
FILE_TYPE_IMAGE = 'image'
FILE_TYPE_VIDEO = 'video'
FILE_TYPE_AUDIO = 'audio'
FILE_TYPE_ARCHIVE = 'archive'
FILE_TYPE_OTHER = 'other'

# HTTP заголовки
AJAX_HEADER = 'X-Requested-With'
AJAX_VALUE = 'XMLHttpRequest'

# Сообщения об ошибках
ERROR_FILE_TOO_LARGE = 'Файл слишком большой. Максимальный размер: {max_size}MB'
ERROR_INSUFFICIENT_STORAGE = 'Недостаточно места в хранилище'
ERROR_FILE_NOT_FOUND = 'Файл не найден'
ERROR_INVALID_FILE = 'Файл не является {file_type}'

# Сообщения об успехе
SUCCESS_FILE_UPLOADED = 'Файл успешно загружен'
SUCCESS_FILE_DELETED = 'Файл успешно удален'
SUCCESS_PUBLIC_ENABLED = 'Публичный доступ включен'
SUCCESS_PUBLIC_DISABLED = 'Публичный доступ отключен'

# Настройки для перекодирования видео
VIDEO_QUALITY_OPTIONS = [2160, 1440, 1080, 720, 480, 360, 240, 144]
FFMPEG_TIMEOUT = 3600  # 1 час

