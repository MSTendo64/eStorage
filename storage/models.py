from django.db import models
from django.contrib.auth.models import User
import uuid
from django.utils import timezone
from datetime import timedelta
import os
import zipfile
import tarfile
from django.urls import reverse
from django.core.exceptions import ValidationError
import base64
import shutil


def generate_short_token():
    """
    Генерирует короткий токен (22 символа вместо 32).
    Использует base64url кодирование UUID для совместимости с URL.
    Обратная совместимость: старые токены (32 символа hex) также поддерживаются.
    """
    # Генерируем UUID и кодируем в base64url (без padding)
    token_bytes = uuid.uuid4().bytes
    token_b64 = base64.urlsafe_b64encode(token_bytes).decode('ascii')
    # Убираем padding '=' и получаем 22 символа
    return token_b64.rstrip('=')


def find_token_in_model(model_class, token_field, token_value):
    """
    Универсальная функция для поиска токена с обратной совместимостью.
    Поддерживает как новые короткие токены (22 символа base64url), 
    так и старые длинные токены (32 символа hex).
    Django ORM автоматически найдет токен по точному совпадению независимо от формата.
    
    Args:
        model_class: Класс модели Django
        token_field: Имя поля с токеном
        token_value: Значение токена для поиска
    
    Returns:
        Объект модели или None
    """
    # Прямой поиск (работает для новых и старых токенов)
    try:
        return model_class.objects.get(**{token_field: token_value})
    except model_class.DoesNotExist:
        return None
    except model_class.MultipleObjectsReturned:
        # Если несколько объектов (не должно быть, но на всякий случай)
        return model_class.objects.filter(**{token_field: token_value}).first()

class Folder(models.Model):
    """Модель для виртуальных папок пользователя"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='folders')
    name = models.CharField(max_length=255)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subfolders')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['user', 'name', 'parent']
        verbose_name = 'Папка'
        verbose_name_plural = 'Папки'
    
    def __str__(self):
        return self.get_full_path()
    
    def get_full_path(self):
        """Возвращает полный путь папки"""
        path = [self.name]
        parent = self.parent
        while parent:
            path.insert(0, parent.name)
            parent = parent.parent
        return '/'.join(path)
    
    def get_depth(self):
        """Возвращает глубину вложенности папки"""
        depth = 0
        parent = self.parent
        while parent:
            depth += 1
            parent = parent.parent
        return depth
    
    def clean(self):
        """Валидация папки"""
        if self.parent and self.parent.user != self.user:
            raise ValidationError('Родительская папка должна принадлежать тому же пользователю')
        if self.parent == self:
            raise ValidationError('Папка не может быть родителем самой себя')
        # Проверка на циклические ссылки
        parent = self.parent
        while parent:
            if parent == self:
                raise ValidationError('Обнаружена циклическая ссылка')
            parent = parent.parent
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def get_files_count(self):
        """Возвращает количество файлов в папке"""
        return self.files.count()
    
    def get_total_size(self):
        """Возвращает общий размер файлов в папке"""
        return sum(f.file_size for f in self.files.all())


class SharedFolderAccess(models.Model):
    """Модель для хранения доступа к папкам"""
    ACCESS_TYPES = [
        ('email', 'По email'),
        ('link', 'По ссылке'),
    ]
    
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name='shared_accesses')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_folders')
    access_type = models.CharField(max_length=10, choices=ACCESS_TYPES)
    
    # Для доступа по email
    granted_to_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, 
                                         related_name='folder_accesses', 
                                         help_text='Пользователь, которому предоставлен доступ')
    
    # Для доступа по ссылке
    share_token = models.CharField(max_length=64, unique=True, null=True, blank=True,
                                   help_text='Токен для доступа по ссылке')
    max_users = models.IntegerField(default=0, help_text='Максимум пользователей (0 = неограничено)')
    
    # Модификаторы доступа
    can_view = models.BooleanField(default=True, help_text='Может просматривать файлы')
    can_download = models.BooleanField(default=True, help_text='Может скачивать файлы')
    can_modify = models.BooleanField(default=False, help_text='Может изменять файлы')
    can_delete = models.BooleanField(default=False, help_text='Может удалять файлы')
    
    # Настройки для незарегистрированных пользователей (по ссылке)
    allow_unregistered_view = models.BooleanField(default=True, 
                                                  help_text='Незарегистрированные могут просматривать')
    allow_unregistered_download = models.BooleanField(default=False,
                                                      help_text='Незарегистрированные могут скачивать')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['folder', 'granted_to_user'], ['folder', 'share_token']]
        verbose_name = 'Доступ к папке'
        verbose_name_plural = 'Доступы к папкам'
    
    def save(self, *args, **kwargs):
        if not self.share_token and self.access_type == 'link':
            self.share_token = generate_short_token()
        if not self.owner_id and self.folder:
            self.owner = self.folder.user
        super().save(*args, **kwargs)
    
    def get_shared_users_count(self):
        """Возвращает количество пользователей, получивших доступ по ссылке"""
        if self.access_type == 'link':
            return SharedFolderLinkUser.objects.filter(share_access=self).count()
        return 0
    
    def is_access_limit_reached(self):
        """Проверяет, достигнут ли лимит доступа"""
        if self.max_users == 0:
            return False
        return self.get_shared_users_count() >= self.max_users


class SharedFolderLinkUser(models.Model):
    """Пользователи, получившие доступ по ссылке"""
    share_access = models.ForeignKey(SharedFolderAccess, on_delete=models.CASCADE, 
                                      related_name='link_users')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='link_folder_accesses')
    accessed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [['share_access', 'user']]
        verbose_name = 'Пользователь с доступом по ссылке'
        verbose_name_plural = 'Пользователи с доступом по ссылке'


class MountedFolder(models.Model):
    """Примонтированные папки других пользователей"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mounted_folders')
    shared_access = models.ForeignKey(SharedFolderAccess, on_delete=models.CASCADE, 
                                       related_name='mounted_by')
    mounted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [['user', 'shared_access']]
        verbose_name = 'Примонтированная папка'
        verbose_name_plural = 'Примонтированные папки'


class Storage(models.Model):
    """Модель для хранения информации о хранилищах"""
    STORAGE_TYPES = [
        ('local', 'Локальное хранилище'),
        ('s3', 'S3-совместимое хранилище'),
    ]
    
    name = models.CharField(max_length=255, verbose_name='Название хранилища')
    storage_type = models.CharField(max_length=10, choices=STORAGE_TYPES, default='local', verbose_name='Тип хранилища')
    is_active = models.BooleanField(default=True, verbose_name='Активно')
    max_size = models.BigIntegerField(verbose_name='Максимальный размер (в байтах)', 
                                      help_text='Максимальный размер хранилища в байтах')
    priority = models.IntegerField(default=0, verbose_name='Приоритет', 
                                    help_text='Чем выше число, тем выше приоритет при выборе хранилища')
    
    # Для локального хранилища
    local_path = models.CharField(max_length=500, null=True, blank=True, 
                                  verbose_name='Локальный путь',
                                  help_text='Абсолютный путь к директории хранилища')
    
    # Для S3-совместимого хранилища
    s3_access_key = models.CharField(max_length=255, null=True, blank=True, verbose_name='Access Key ID',
                                     help_text='Access Key для S3-совместимого сервиса')
    s3_secret_key = models.CharField(max_length=255, null=True, blank=True, verbose_name='Secret Access Key',
                                     help_text='Secret Key для S3-совместимого сервиса')
    s3_bucket_name = models.CharField(max_length=255, null=True, blank=True, verbose_name='Bucket Name',
                                       help_text='Имя bucket в S3-совместимом хранилище')
    s3_endpoint_url = models.CharField(max_length=500, null=True, blank=True, verbose_name='Endpoint URL',
                                       help_text='URL эндпоинта (обязательно для не-Amazon сервисов: MinIO, DigitalOcean Spaces и т.д.)')
    s3_region = models.CharField(max_length=100, null=True, blank=True, verbose_name='Region',
                                 help_text='Регион (опционально для некоторых сервисов)')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')
    
    class Meta:
        ordering = ['-priority', 'name']
        verbose_name = 'Хранилище'
        verbose_name_plural = 'Хранилища'
    
    def __str__(self):
        return f"{self.name} ({self.get_storage_type_display()})"
    
    def clean(self):
        """Валидация хранилища"""
        if self.storage_type == 'local':
            if not self.local_path:
                raise ValidationError('Для локального хранилища необходимо указать путь')
            # Проверяем, что путь существует или может быть создан
            if not os.path.exists(self.local_path):
                try:
                    os.makedirs(self.local_path, exist_ok=True)
                except Exception as e:
                    raise ValidationError(f'Не удалось создать директорию: {str(e)}')
        elif self.storage_type == 's3':
            if not all([self.s3_access_key, self.s3_secret_key, self.s3_bucket_name]):
                raise ValidationError('Для S3-совместимого хранилища необходимо указать Access Key, Secret Key и Bucket Name')
            # Endpoint URL рекомендуется для не-Amazon сервисов
            if not self.s3_endpoint_url:
                # Не делаем обязательным, но предупреждаем
                pass
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def get_used_size(self):
        """Возвращает используемый размер хранилища в байтах"""
        from django.db.models import Sum
        total = UserFile.objects.filter(storage=self).aggregate(
            total=Sum('file_size'))['total'] or 0
        return total
    
    def get_available_size(self):
        """Возвращает доступный размер хранилища в байтах"""
        used = self.get_used_size()
        return max(0, self.max_size - used)
    
    def _format_size(self, size_bytes):
        """Вспомогательный метод для форматирования размера"""
        size = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                # Если число целое, отображаем без десятичных знаков
                if size == int(size):
                    return f"{int(size)} {unit}"
                # Иначе отображаем с 2 знаками после запятой, убирая лишние нули
                return f"{size:.2f} {unit}".rstrip('0').rstrip('.')
            size /= 1024.0
        # Для очень больших размеров (PB)
        if size == int(size):
            return f"{int(size)} PB"
        return f"{size:.2f} PB".rstrip('0').rstrip('.')
    
    def get_used_size_formatted(self):
        """Возвращает отформатированный размер используемого хранилища"""
        return self._format_size(self.get_used_size())
    
    def get_available_size_formatted(self):
        """Возвращает отформатированный размер доступного хранилища"""
        return self._format_size(self.get_available_size())
    
    def get_max_size_formatted(self):
        """Возвращает отформатированный максимальный размер хранилища"""
        return self._format_size(self.max_size)
    
    def get_usage_percent(self):
        """Возвращает процент использования хранилища"""
        if self.max_size == 0:
            return 0
        used = self.get_used_size()
        return min(round((used / self.max_size) * 100, 1), 100)
    
    def get_files_count(self):
        """Возвращает количество файлов в хранилище"""
        return UserFile.objects.filter(storage=self).count()
    
    def can_store_file(self, file_size):
        """Проверяет, может ли хранилище вместить файл указанного размера"""
        return self.is_active and self.get_available_size() >= file_size
    
    def get_storage_path(self, user_id, filename):
        """Возвращает путь к файлу в хранилище"""
        if self.storage_type == 'local':
            user_folder = os.path.join(self.local_path, str(user_id))
            return os.path.join(user_folder, filename)
        elif self.storage_type == 's3':
            # Для S3 возвращаем путь относительно bucket
            return f"{user_id}/{filename}"
        return None
    
    def test_s3_connection(self):
        """
        Проверяет подключение к S3-совместимому хранилищу.
        Возвращает кортеж (success: bool, message: str)
        """
        if self.storage_type != 's3':
            return False, 'Это не S3 хранилище'
        
        if not all([self.s3_access_key, self.s3_secret_key, self.s3_bucket_name]):
            return False, 'Не указаны все необходимые реквизиты (Access Key, Secret Key, Bucket Name)'
        
        import asyncio
        try:
            # Запускаем асинхронную функцию в синхронном контексте
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._test_s3_connection_async())
            finally:
                loop.close()
        except Exception as e:
            return False, f'Ошибка при проверке подключения: {str(e)}'
    
    async def _test_s3_connection_async(self):
        """
        Асинхронная функция для проверки подключения к S3-совместимому хранилищу.
        Возвращает кортеж (success: bool, message: str)
        """
        if self.storage_type != 's3':
            return False, 'Это не S3 хранилище'
        
        if not all([self.s3_access_key, self.s3_secret_key, self.s3_bucket_name]):
            return False, 'Не указаны все необходимые реквизиты (Access Key, Secret Key, Bucket Name)'
        
        try:
            import aioboto3
            from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
            
            # Создаем сессию aioboto3
            session = aioboto3.Session()
            
            # Конфигурация для S3 клиента
            s3_config = {
                'aws_access_key_id': self.s3_access_key,
                'aws_secret_access_key': self.s3_secret_key,
            }
            
            if self.s3_endpoint_url:
                s3_config['endpoint_url'] = self.s3_endpoint_url
            
            if self.s3_region:
                s3_config['region_name'] = self.s3_region
            
            # Пытаемся получить информацию о bucket
            async with session.client('s3', **s3_config) as s3_client:
                try:
                    await s3_client.head_bucket(Bucket=self.s3_bucket_name)
                    # Пытаемся выполнить простую операцию (list objects)
                    await s3_client.list_objects_v2(Bucket=self.s3_bucket_name, MaxKeys=1)
                    return True, 'Подключение успешно. Хранилище доступно.'
                except ClientError as e:
                    error_code = e.response.get('Error', {}).get('Code', '')
                    if error_code == '403':
                        return False, 'Доступ запрещен. Проверьте права доступа (Access Key и Secret Key).'
                    elif error_code == '404':
                        return False, f'Bucket "{self.s3_bucket_name}" не найден. Проверьте имя bucket.'
                    else:
                        return False, f'Ошибка подключения: {str(e)}'
                except EndpointConnectionError as e:
                    return False, f'Не удалось подключиться к эндпоинту. Проверьте Endpoint URL: {str(e)}'
                except NoCredentialsError:
                    return False, 'Неверные учетные данные (Access Key или Secret Key)'
                except Exception as e:
                    return False, f'Неожиданная ошибка: {str(e)}'
                    
        except ImportError:
            return False, 'Библиотека aioboto3 не установлена. Установите: pip install aioboto3'
        except Exception as e:
            return False, f'Ошибка при инициализации S3 клиента: {str(e)}'
    
    def get_s3_connection_status(self):
        """
        Возвращает статус подключения к S3 хранилищу.
        Возвращает словарь с информацией о статусе.
        """
        if self.storage_type != 's3':
            return {
                'status': 'not_applicable',
                'message': 'Не применимо для локального хранилища',
                'is_available': None
            }
        
        success, message = self.test_s3_connection()
        return {
            'status': 'success' if success else 'error',
            'message': message,
            'is_available': success
        }

class UserFile(models.Model):
    FILE_TYPES = [
        ('image', 'Изображение'),
        ('video', 'Видео'),
        ('audio', 'Аудио'),
        ('archive', 'Архив'),
        ('text', 'Текстовый файл'),
        ('document', 'Документ'),
        ('code', 'Код'),
        ('other', 'Другое')
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='')
    filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_type = models.CharField(max_length=20, choices=FILE_TYPES, default='other')
    is_public = models.BooleanField(default=False)
    public_token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    file_size = models.BigIntegerField(default=0)
    folder = models.ForeignKey(Folder, on_delete=models.SET_NULL, null=True, blank=True, related_name='files')
    storage = models.ForeignKey('Storage', on_delete=models.SET_NULL, null=True, blank=True, 
                                related_name='files', verbose_name='Хранилище')
    
    # Добавляем поля для информации о видео
    title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)
    thumbnail_url = models.URLField(null=True, blank=True)
    
    class Meta:
        ordering = ['-uploaded_at']

    def save(self, *args, **kwargs):
        if self.is_public and not self.public_token:
            self.public_token = generate_short_token()
        elif not self.is_public:
            self.public_token = None
            
        # Определяем тип файла по расширению
        ext = os.path.splitext(self.filename)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico']:
            self.file_type = 'image'
        elif ext in ['.mp4', '.avi', '.mov', '.wmv', '.webm', '.mkv', '.flv', '.m4v']:
            self.file_type = 'video'
        elif ext in ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.wma']:
            self.file_type = 'audio'
        elif ext in ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz']:
            self.file_type = 'archive'
        elif ext in ['.txt', '.log', '.md', '.readme']:
            self.file_type = 'text'
        elif ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp']:
            self.file_type = 'document'
        elif ext in ['.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.php', '.rb', '.go', '.rs', '.ts', '.tsx', '.jsx', '.json', '.xml', '.yaml', '.yml', '.sh', '.bat', '.ps1']:
            self.file_type = 'code'
        else:
            self.file_type = 'other'
            
        if not self.file_size and self.file:
            self.file_size = self.file.size
            
        super().save(*args, **kwargs)

    @property
    def is_image(self):
        return self.file_type == 'image'

    @property
    def is_video(self):
        return self.file_type == 'video'

    @property
    def is_audio(self):
        return self.file_type == 'audio'

    @property
    def is_archive(self):
        return self.file_type == 'archive'

    @property
    def is_text(self):
        return self.file_type == 'text'

    @property
    def is_document(self):
        return self.file_type == 'document'

    @property
    def is_code(self):
        return self.file_type == 'code'

    def get_file_icon(self):
        """Возвращает иконку Font Awesome для типа файла"""
        # Определяем расширение файла для более точных иконок
        ext = os.path.splitext(self.filename)[1].lower()
        
        icon_map = {
            'image': 'fa-file-image',
            'video': 'fa-file-video',
            'audio': 'fa-file-audio',
            'archive': 'fa-file-archive',
            'text': 'fa-file-alt',
            'document': self._get_document_icon(ext),
            'code': self._get_code_icon(ext),
            'other': 'fa-file'
        }
        return icon_map.get(self.file_type, 'fa-file')
    
    def _get_document_icon(self, ext):
        """Возвращает иконку для типа документа"""
        doc_icons = {
            '.pdf': 'fa-file-pdf',
            '.doc': 'fa-file-word',
            '.docx': 'fa-file-word',
            '.xls': 'fa-file-excel',
            '.xlsx': 'fa-file-excel',
            '.ppt': 'fa-file-powerpoint',
            '.pptx': 'fa-file-powerpoint',
        }
        return doc_icons.get(ext, 'fa-file-pdf')
    
    def _get_code_icon(self, ext):
        """Возвращает иконку для типа кода"""
        code_icons = {
            '.py': 'fa-file-code',
            '.js': 'fa-file-code',
            '.html': 'fa-file-code',
            '.css': 'fa-file-code',
            '.json': 'fa-file-code',
            '.xml': 'fa-file-code',
            '.yaml': 'fa-file-code',
            '.yml': 'fa-file-code',
        }
        return code_icons.get(ext, 'fa-file-code')
    
    def get_file_icon_color(self):
        """Возвращает цвет иконки для типа файла"""
        color_map = {
            'image': 'text-primary',
            'video': 'text-danger',
            'audio': 'text-success',
            'archive': 'text-warning',
            'text': 'text-info',
            'document': 'text-danger',
            'code': 'text-purple',
            'other': 'text-muted'
        }
        return color_map.get(self.file_type, 'text-muted')

    def get_archive_contents(self):
        """Получить список файлов в архиве"""
        ext = os.path.splitext(self.filename)[1].lower()
        file_path = self.file.path
        
        try:
            if ext == '.zip':
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    return zip_ref.namelist()
            elif ext in ['.tar', '.gz']:
                with tarfile.open(file_path, 'r:*') as tar_ref:
                    return tar_ref.getnames()
        except:
            return []
        return []

    def extract_archive(self, extract_path):
        """Распаковать архив в указанную папку"""
        ext = os.path.splitext(self.filename)[1].lower()
        file_path = self.file.path
        
        try:
            if ext == '.zip':
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                return True
            elif ext in ['.tar', '.gz']:
                with tarfile.open(file_path, 'r:*') as tar_ref:
                    tar_ref.extractall(extract_path)
                return True
        except:
            return False
        return False

    def get_public_url(self):
        if self.is_public and self.public_token:
            return reverse('public_file', args=[self.public_token])
        return None
    
    def get_view_url(self, request=None):
        """
        Возвращает URL для просмотра файла через raw_file эндпоинт.
        Работает для файлов в хранилищах и стандартной папке media.
        """
        from urllib.parse import quote
        from .models import DownloadToken
        from django.utils import timezone
        from datetime import timedelta
        
        # Создаем или получаем токен для скачивания
        download_token, created = DownloadToken.objects.get_or_create(
            file=self,
            defaults={
                'token': generate_short_token(),
                'expires_at': timezone.now() + timedelta(days=1)
            }
        )
        
        # Если токен истек, создаем новый
        if not download_token.is_valid():
            download_token.token = generate_short_token()
            download_token.expires_at = timezone.now() + timedelta(days=1)
            download_token.save()
        
        # Кодируем имя файла для URL
        encoded_filename = quote(self.filename, safe='')
        
        # Если request передан, возвращаем полный URL
        if request:
            return request.build_absolute_uri(f'/storage/raw/{encoded_filename}?token={download_token.token}')
        
        # Иначе возвращаем относительный URL
        return f'/storage/raw/{encoded_filename}?token={download_token.token}'
    
    def get_file_size_formatted(self):
        """Возвращает отформатированный размер файла"""
        size = self.file_size if self.file_size else 0
        if not size and self.file:
            try:
                size = self.file.size
            except:
                size = 0
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}".rstrip('0').rstrip('.')
            size /= 1024.0
        return f"{size:.2f} PB"

class DownloadToken(models.Model):
    token = models.CharField(max_length=64, unique=True)
    file = models.ForeignKey(UserFile, on_delete=models.CASCADE, related_name='download_tokens')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)  # Оставляем для обратной совместимости, но не используем

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = generate_short_token()
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=1)
        super().save(*args, **kwargs)

    def is_valid(self):
        """Проверяет, действителен ли токен (не проверяет is_used, так как токен может использоваться многократно)"""
        return self.expires_at > timezone.now()
    
    @classmethod
    def get_or_create_valid_token(cls, file):
        """Получает валидный токен для файла или создает новый, если его нет или он устарел"""
        # Ищем последний валидный токен для файла
        valid_token = cls.objects.filter(
            file=file,
            expires_at__gt=timezone.now()
        ).order_by('-created_at').first()
        
        if valid_token:
            return valid_token
        
        # Если валидного токена нет, создаем новый
        return cls.objects.create(file=file)
