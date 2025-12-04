from django.db import models
from django.contrib.auth.models import User
import uuid

class EventshockToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    access_token = models.CharField(max_length=255)
    refresh_token = models.CharField(max_length=255)
    expires_at = models.DateTimeField()

    def is_expired(self):
        from django.utils import timezone
        return self.expires_at <= timezone.now()

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_oauth_user = models.BooleanField(default=False)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    theme = models.CharField(max_length=20, choices=[
        ('light', 'Светлая'),
        ('dark', 'Темная'),
        ('auto', 'Системная')
    ], default='dark')
    language = models.CharField(max_length=2, default='ru', choices=[
        ('ru', 'Русский'),
        ('en', 'English'),
        ('ja', '日本語')
    ])
    developer_mode = models.BooleanField(default=False)
    storage_quota = models.BigIntegerField(default=10737418240)  # 10 GB в айтах
    background_image = models.ImageField(upload_to='backgrounds/', null=True, blank=True)
    accent_color = models.CharField(max_length=7, default='#0d6efd',  # Bootstrap primary color
                                  help_text='HEX color code')
    navbar_opacity = models.FloatField(default=1.0)  # Прозрачность навбара
    container_opacity = models.FloatField(default=1.0)  # Прозрачность контейнера
    navbar_color = models.CharField(max_length=7, default='#212529')  # Цвет навбара
    container_color = models.CharField(max_length=7, default='#f8f9fa')  # Цвет контейнеров
    custom_text_color = models.BooleanField(default=False)
    text_color = models.CharField(max_length=7, default='#000000',
                                help_text='HEX color code')
    custom_font = models.FileField(
        upload_to='fonts/', 
        null=True, 
        blank=True,
        help_text='Поддерживаемые форматы: .ttf, .otf, .woff, .woff2'
    )
    font_family_name = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text='Название шрифта для CSS'
    )
    font_format = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text='Формат шрифта для CSS (truetype, opentype, woff, woff2)'
    )
    video_player = models.CharField(
        max_length=20,
        choices=[
            ('plyr', 'Plyr'),
            ('native', 'HTML5 (Нативный)')
        ],
        default='plyr',
        help_text='Выбор видео проигрывателя'
    )
    
    def __str__(self):
        return self.user.username
    
    def get_used_storage(self):
        from django.db.models import Sum
        from storage.models import UserFile
        
        total = UserFile.objects.filter(user=self.user).aggregate(
            total=Sum('file_size'))['total'] or 0
        return total
        
    def get_storage_percent(self):
        used = self.get_used_storage()
        return min(round((used / self.storage_quota) * 100, 1), 100)
        
    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024

    def get_used_storage_formatted(self):
        """Возвращает отформатированный размер используемого хранилища"""
        return self.format_size(self.get_used_storage())
    
    def get_quota_formatted(self):
        """Возвращает отформатированный размер квоты"""
        return self.format_size(self.storage_quota)

    def accent_color_rgb(self):
        """Конвертирует HEX в RGB"""
        color = self.accent_color.lstrip('#')
        return f"{int(color[:2], 16)}, {int(color[2:4], 16)}, {int(color[4:], 16)}"

    def accent_color_darker(self):
        """Возвращает более темную версию акцентного цвета"""
        color = self.accent_color.lstrip('#')
        r = max(int(color[:2], 16) - 30, 0)
        g = max(int(color[2:4], 16) - 30, 0)
        b = max(int(color[4:], 16) - 30, 0)
        return f"#{r:02x}{g:02x}{b:02x}"

class LinkedAccount(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='linked_accounts')
    provider = models.CharField(max_length=50)  # 'google', 'github', etc.
    provider_user_id = models.CharField(max_length=255)
    provider_username = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('provider', 'provider_user_id')

class OAuthApplication(models.Model):
    name = models.CharField(max_length=255)
    client_id = models.CharField(max_length=100, unique=True)
    client_secret = models.CharField(max_length=255)
    redirect_uris = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class APIKey(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=100)
    key = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = uuid.uuid4().hex
        super().save(*args, **kwargs)

class ESIDToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='esid_tokens')
    name = models.CharField(max_length=100)
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    allowed_origins = models.TextField(blank=True)  # Список разрешенных доменов через запятую

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = f"esid_{uuid.uuid4().hex}"
        super().save(*args, **kwargs)

class SystemSettings(models.Model):
    LOGO_MODE_SINGLE = 'single'
    LOGO_MODE_THEME = 'theme'
    LOGO_MODE_CHOICES = [
        (LOGO_MODE_SINGLE, 'Общий логотип'),
        (LOGO_MODE_THEME, 'По выбору темы'),
    ]

    site_name = models.CharField(max_length=100, default='eStorage')
    site_logo = models.ImageField(upload_to='system/logo/', null=True, blank=True)
    logo_mode = models.CharField(
        max_length=16,
        choices=LOGO_MODE_CHOICES,
        default=LOGO_MODE_SINGLE,
    )
    logo_light = models.ImageField(upload_to='system/logo/', null=True, blank=True)
    logo_dark = models.ImageField(upload_to='system/logo/', null=True, blank=True)
    site_name_color = models.CharField(max_length=7, default='#ffffff', help_text='HEX color code')
    proxy_url = models.CharField(max_length=500, null=True, blank=True, help_text='URL прокси-сервера для загрузки файлов (например: https://api.allorigins.win/raw?url= или https://corsproxy.io/?)')
    proxy_domains = models.TextField(null=True, blank=True, help_text='Список доменов (по одному на строку), для которых сразу использовать прокси при загрузке')

    class Meta:
        verbose_name = 'System Settings'
        verbose_name_plural = 'System Settings'

    def __str__(self):
        return 'System Settings'

    @classmethod
    def get_settings(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings

    def get_logo_for_theme(self, theme: str = 'dark'):
        """
        Возвращает файл логотипа, подходящий для указанной темы.
        """
        theme = (theme or 'dark').lower()
        if theme not in ('light', 'dark'):
            theme = 'dark'

        if self.logo_mode == self.LOGO_MODE_THEME:
            if theme == 'light':
                if self.logo_light:
                    return self.logo_light
                if self.logo_dark:
                    return self.logo_dark
            else:
                if self.logo_dark:
                    return self.logo_dark
                if self.logo_light:
                    return self.logo_light

        return self.site_logo or self.logo_dark or self.logo_light

    def get_logo_config(self):
        """
        Возвращает словарь с URL логотипов для использования на клиенте.
        """
        return {
            'mode': self.logo_mode,
            'single': self.site_logo.url if self.site_logo else '',
            'dark': self.logo_dark.url if self.logo_dark else '',
            'light': self.logo_light.url if self.logo_light else '',
        }
