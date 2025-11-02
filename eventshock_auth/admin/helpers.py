"""
Вспомогательные функции для админ-панели
"""
from typing import Optional
from django.http import JsonResponse
from django.contrib.auth.models import User
from storage.models import UserFile
from django.db.models import Sum, Count, QuerySet
from .constants import BYTES_PER_GB


def format_storage_size(bytes_size: int) -> str:
    """
    Форматирует размер хранилища в GB.
    
    Args:
        bytes_size: Размер в байтах
        
    Returns:
        Строка с форматированным размером (например, "10.5 GB")
    """
    return f"{bytes_size / BYTES_PER_GB:.1f} GB"


def get_user_storage_stats(user: User) -> dict:
    """
    Получает статистику хранилища для пользователя.
    
    Args:
        user: Экземпляр User
        
    Returns:
        Словарь с ключами: storage_used (байты), storage_used_formatted (строка), files_count
    """
    storage_used = UserFile.objects.filter(user=user).aggregate(
        total=Sum('file_size')
    )['total'] or 0
    
    files_count = UserFile.objects.filter(user=user).count()
    
    return {
        'storage_used': storage_used,
        'storage_used_formatted': format_storage_size(storage_used),
        'files_count': files_count
    }


def get_global_storage_stats() -> dict:
    """
    Получает глобальную статистику хранилища.
    
    Returns:
        Словарь с ключами: total_storage (байты), total_storage_formatted (строка), total_files
    """
    total_storage = UserFile.objects.aggregate(total=Sum('file_size'))['total'] or 0
    total_files = UserFile.objects.count()
    
    return {
        'total_storage': total_storage,
        'total_storage_formatted': format_storage_size(total_storage),
        'total_files': total_files
    }


def get_users_with_storage() -> QuerySet:
    """
    Получает пользователей с их статистикой хранилища.
    
    Returns:
        QuerySet пользователей с аннотациями storage_used и files_count
    """
    return User.objects.annotate(
        storage_used=Sum('userfile__file_size'),
        files_count=Count('userfile')
    ).order_by('-storage_used')


def validate_storage_quota(quota_str: Optional[str]) -> tuple[bool, Optional[int]]:
    """
    Валидирует значение квоты хранилища.
    
    Args:
        quota_str: Строка с квотой в GB
        
    Returns:
        Кортеж (успешно, значение в байтах или None)
    """
    if not quota_str:
        return False, None
    
    try:
        quota_gb = int(quota_str)
        if quota_gb < 0:
            return False, None
        quota_bytes = quota_gb * BYTES_PER_GB
        return True, quota_bytes
    except (ValueError, TypeError):
        return False, None


def create_json_response(data: dict, status: int = 200) -> JsonResponse:
    """
    Создает JsonResponse с данными.
    
    Args:
        data: Словарь с данными для JSON
        status: HTTP статус код
        
    Returns:
        JsonResponse объект
    """
    return JsonResponse(data, status=status)

