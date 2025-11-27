"""
Вспомогательные функции и классы для работы с общим доступом к папкам
"""
import logging
from typing import Optional, Dict, Any, Tuple
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from ..models import Folder, SharedFolderAccess, SharedFolderLinkUser, MountedFolder

logger = logging.getLogger(__name__)


class AccessPermissionManager:
    """Менеджер для управления правами доступа к папкам"""
    
    @staticmethod
    def check_user_access(user: User, access: SharedFolderAccess) -> Tuple[bool, str]:
        """
        Проверяет, имеет ли пользователь доступ к папке.
        
        Args:
            user: Пользователь для проверки
            access: Объект доступа
            
        Returns:
            Кортеж (has_access, reason)
        """
        # Владелец всегда имеет доступ
        if access.owner == user:
            return True, "owner"
        
        # Проверяем тип доступа
        if access.access_type == 'email':
            if access.granted_to_user == user:
                return True, "email_granted"
            return False, "email_not_granted"
        
        elif access.access_type == 'link':
            # Проверяем, зарегистрирован ли доступ для пользователя
            if SharedFolderLinkUser.objects.filter(
                share_access=access,
                user=user
            ).exists():
                return True, "link_registered"
            
            # Если пользователь зарегистрирован и есть can_view, регистрируем доступ
            if user.is_authenticated and access.can_view:
                SharedFolderLinkUser.objects.get_or_create(
                    share_access=access,
                    user=user
                )
                return True, "link_auto_registered"
            
            return False, "link_no_access"
        
        return False, "unknown_access_type"
    
    @staticmethod
    def can_user_view(user: User, access: SharedFolderAccess) -> bool:
        """Проверяет, может ли пользователь просматривать папку"""
        has_access, reason = AccessPermissionManager.check_user_access(user, access)
        if not has_access:
            return False
        
        # Владелец всегда может просматривать
        if reason == "owner":
            return True
        
        return access.can_view
    
    @staticmethod
    def can_user_download(user: User, access: SharedFolderAccess) -> bool:
        """Проверяет, может ли пользователь скачивать файлы"""
        has_access, _ = AccessPermissionManager.check_user_access(user, access)
        if not has_access:
            return False
        
        # Владелец всегда может скачивать
        if access.owner == user:
            return True
        
        return access.can_download
    
    @staticmethod
    def can_user_modify(user: User, access: SharedFolderAccess) -> bool:
        """Проверяет, может ли пользователь изменять файлы"""
        has_access, _ = AccessPermissionManager.check_user_access(user, access)
        if not has_access:
            return False
        
        if access.owner == user:
            return True
        
        return access.can_modify
    
    @staticmethod
    def can_user_delete(user: User, access: SharedFolderAccess) -> bool:
        """Проверяет, может ли пользователь удалять файлы"""
        has_access, _ = AccessPermissionManager.check_user_access(user, access)
        if not has_access:
            return False
        
        if access.owner == user:
            return True
        
        return access.can_delete
    
    @staticmethod
    def can_unregistered_view(access: SharedFolderAccess) -> bool:
        """Проверяет, могут ли незарегистрированные пользователи просматривать"""
        if access.access_type != 'link':
            return False
        return access.allow_unregistered_view
    
    @staticmethod
    def can_unregistered_download(access: SharedFolderAccess) -> bool:
        """Проверяет, могут ли незарегистрированные пользователи скачивать"""
        if access.access_type != 'link':
            return False
        return access.allow_unregistered_download


def extract_permissions_from_request(request) -> Dict[str, Any]:
    """
    Извлекает права доступа из POST запроса.
    
    Returns:
        Словарь с правами доступа
    """
    return {
        'can_view': request.POST.get('can_view', 'true') == 'true',
        'can_download': request.POST.get('can_download', 'true') == 'true',
        'can_modify': request.POST.get('can_modify', 'false') == 'true',
        'can_delete': request.POST.get('can_delete', 'false') == 'true',
        'allow_unregistered_view': request.POST.get('allow_unregistered_view', 'true') == 'true',
        'allow_unregistered_download': request.POST.get('allow_unregistered_download', 'false') == 'true',
        'max_users': int(request.POST.get('max_users', 0))
    }


def validate_share_request(folder: Folder, user: User, email: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Валидирует запрос на предоставление доступа.
    
    Returns:
        Кортеж (is_valid, error_message)
    """
    # Проверяем, что папка принадлежит пользователю
    if folder.user != user:
        return False, "Папка не принадлежит вам"
    
    # Если указан email, проверяем его
    if email:
        email = email.strip()
        if not email:
            return False, "Email не указан"
        
        try:
            target_user = User.objects.get(email=email)
            if target_user == user:
                return False, "Нельзя предоставить доступ самому себе"
        except User.DoesNotExist:
            return False, "Пользователь с таким email не найден"
    
    return True, None


def create_or_update_access(folder: Folder, owner: User, access_type: str, 
                            permissions: Dict[str, Any], 
                            granted_to_user: Optional[User] = None) -> Tuple[SharedFolderAccess, bool]:
    """
    Создает или обновляет доступ к папке.
    
    Args:
        folder: Папка для доступа
        owner: Владелец папки
        access_type: Тип доступа ('email' или 'link')
        permissions: Словарь с правами доступа
        granted_to_user: Пользователь для доступа по email (опционально)
        
    Returns:
        Кортеж (access, created)
    """
    if access_type == 'email':
        if not granted_to_user:
            raise ValueError("granted_to_user обязателен для доступа по email")
        
        access, created = SharedFolderAccess.objects.get_or_create(
            folder=folder,
            granted_to_user=granted_to_user,
            access_type='email',
            defaults={
                'owner': owner,
                'can_view': permissions['can_view'],
                'can_download': permissions['can_download'],
                'can_modify': permissions['can_modify'],
                'can_delete': permissions['can_delete']
            }
        )
        
        if not created:
            # Обновляем права
            access.can_view = permissions['can_view']
            access.can_download = permissions['can_download']
            access.can_modify = permissions['can_modify']
            access.can_delete = permissions['can_delete']
            access.save()
    
    elif access_type == 'link':
        # Для ссылки может быть только один доступ на папку от владельца
        access = SharedFolderAccess.objects.filter(
            folder=folder,
            access_type='link',
            owner=owner
        ).first()
        
        if access:
            # Обновляем настройки
            access.max_users = permissions['max_users']
            access.can_view = permissions['can_view']
            access.can_download = permissions['can_download']
            access.can_modify = permissions['can_modify']
            access.can_delete = permissions['can_delete']
            access.allow_unregistered_view = permissions['allow_unregistered_view']
            access.allow_unregistered_download = permissions['allow_unregistered_download']
            access.save()
            created = False
        else:
            # Создаем новый доступ
            from ..models import generate_short_token
            access = SharedFolderAccess.objects.create(
                folder=folder,
                owner=owner,
                access_type='link',
                share_token=generate_short_token(),
                max_users=permissions['max_users'],
                can_view=permissions['can_view'],
                can_download=permissions['can_download'],
                can_modify=permissions['can_modify'],
                can_delete=permissions['can_delete'],
                allow_unregistered_view=permissions['allow_unregistered_view'],
                allow_unregistered_download=permissions['allow_unregistered_download']
            )
            created = True
    
    else:
        raise ValueError(f"Неизвестный тип доступа: {access_type}")
    
    return access, created


def register_link_access(access: SharedFolderAccess, user: User) -> Tuple[SharedFolderLinkUser, bool]:
    """
    Регистрирует доступ пользователя по ссылке.
    
    Returns:
        Кортеж (link_user, created)
    """
    return SharedFolderLinkUser.objects.get_or_create(
        share_access=access,
        user=user
    )


def get_shared_folder_context(access: SharedFolderAccess, user: Optional[User] = None) -> Dict[str, Any]:
    """
    Получает контекст для отображения общей папки.
    
    Returns:
        Словарь с контекстом
    """
    folder = access.folder
    is_owner = user and user.is_authenticated and access.owner == user
    is_mounted = False
    
    if user and user.is_authenticated:
        is_mounted = MountedFolder.objects.filter(
            user=user,
            shared_access=access
        ).exists()
    
    return {
        'folder': folder,
        'files': folder.files.all(),
        'subfolders': folder.subfolders.all(),
        'access': access,
        'is_mounted': is_mounted,
        'owner': access.owner,
        'is_owner': is_owner,
        'is_authenticated': user.is_authenticated if user else False,
        'user': user if user and user.is_authenticated else None
    }


def get_user_shared_folders(user: User) -> Dict[str, Any]:
    """
    Получает все папки, связанные с пользователем (доступы, примонтированные, владение).
    
    Returns:
        Словарь с различными списками папок
    """
    # Доступы по email
    email_accesses = SharedFolderAccess.objects.filter(
        granted_to_user=user,
        access_type='email'
    ).select_related('folder', 'owner')
    
    # Примонтированные папки
    mounted_objects = MountedFolder.objects.filter(
        user=user
    ).select_related('shared_access', 'shared_access__folder', 'shared_access__owner')
    
    # ID примонтированных доступов для исключения
    mounted_access_ids = list(mounted_objects.values_list('shared_access_id', flat=True))
    
    # Доступы по ссылке (исключаем примонтированные)
    link_accesses = SharedFolderLinkUser.objects.filter(
        user=user
    ).exclude(
        share_access__id__in=mounted_access_ids
    ).select_related('share_access', 'share_access__folder', 'share_access__owner')
    
    # Папки, которыми пользователь поделился
    owned_folders = SharedFolderAccess.objects.filter(
        owner=user
    ).select_related('folder').order_by('-created_at')
    
    # Формируем список примонтированных папок
    mounted_folders = []
    for mount in mounted_objects:
        mounted_folders.append({
            'id': mount.id,
            'shared_access': mount.shared_access,
            'mounted_at': mount.mounted_at
        })
    
    return {
        'email_accesses': email_accesses,
        'link_accesses': link_accesses,
        'mounted_folders': mounted_folders,
        'owned_folders': owned_folders
    }

