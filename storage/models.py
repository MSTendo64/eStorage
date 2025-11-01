from django.db import models
from django.contrib.auth.models import User
import uuid
from django.utils import timezone
from datetime import timedelta
import os
import zipfile
import tarfile
from django.urls import reverse

class UserFile(models.Model):
    FILE_TYPES = [
        ('image', 'Изображение'),
        ('video', 'Видео'),
        ('audio', 'Аудио'),
        ('archive', 'Архив'),
        ('other', 'Другое')
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='')
    filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_type = models.CharField(max_length=10, choices=FILE_TYPES, default='other')
    is_public = models.BooleanField(default=False)
    public_token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    file_size = models.BigIntegerField(default=0)
    
    # Добавляем поля для информации о видео
    title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)
    thumbnail_url = models.URLField(null=True, blank=True)
    
    class Meta:
        ordering = ['-uploaded_at']

    def save(self, *args, **kwargs):
        if self.is_public and not self.public_token:
            self.public_token = uuid.uuid4().hex
        elif not self.is_public:
            self.public_token = None
            
        # Определяем тип файла по расширению
        ext = os.path.splitext(self.filename)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            self.file_type = 'image'
        elif ext in ['.mp4', '.avi', '.mov', '.wmv', '.webm']:
            self.file_type = 'video'
        elif ext in ['.mp3', '.wav', '.ogg', '.m4a']:
            self.file_type = 'audio'
        elif ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
            self.file_type = 'archive'
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
    file = models.ForeignKey(UserFile, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = uuid.uuid4().hex
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=30)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.is_used and self.expires_at > timezone.now()

class YouTubeVideo(models.Model):
    title = models.CharField(max_length=255)
    url = models.URLField()
    file_path = models.FileField(upload_to='youtube_videos/')
    downloaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.title

class DownloadTask(models.Model):
    STATUS_CHOICES = [
        ('pending', 'В очереди'),
        ('processing', 'Загрузка'),
        ('completed', 'Заве��шено'),
        ('failed', 'Ошибка')
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    url = models.URLField()
    format_id = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.FloatField(default=0)
    speed = models.FloatField(default=0)
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    file = models.ForeignKey(UserFile, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
