"""
Операции с общим доступом к папкам: поделиться, отозвать, настройки доступа
"""
import uuid
import logging
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.urls import reverse

from ..models import Folder, SharedFolderAccess, SharedFolderLinkUser, MountedFolder
from ..helpers import create_json_response

logger = logging.getLogger(__name__)


@login_required
def share_folder_wizard(request, folder_id):
    """Мастер распространения папки - первый шаг выбора способа доступа"""
    folder = get_object_or_404(Folder, id=folder_id, user=request.user)
    
    if request.method == 'POST':
        access_type = request.POST.get('access_type', 'email')
        
        # Переход ко второму шагу
        return render(request, 'storage/share_wizard_step2.html', {
            'folder': folder,
            'access_type': access_type
        })
    
    return render(request, 'storage/share_wizard_step1.html', {
        'folder': folder
    })


@login_required
@require_http_methods(["POST"])
def share_folder_email(request, folder_id):
    """Предоставление доступа к папке по email"""
    try:
        folder = get_object_or_404(Folder, id=folder_id, user=request.user)
        
        email = request.POST.get('email', '').strip()
        can_view = request.POST.get('can_view', 'true') == 'true'
        can_download = request.POST.get('can_download', 'true') == 'true'
        can_modify = request.POST.get('can_modify', 'false') == 'true'
        can_delete = request.POST.get('can_delete', 'false') == 'true'
        
        if not email:
            return create_json_response(False, 'Email не указан', status=400)
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return create_json_response(False, 'Пользователь с таким email не найден', status=404)
        
        if user == request.user:
            return create_json_response(False, 'Нельзя предоставить доступ самому себе', status=400)
        
        # Создаем или обновляем доступ
        access, created = SharedFolderAccess.objects.get_or_create(
            folder=folder,
            granted_to_user=user,
            defaults={
                'owner': request.user,
                'access_type': 'email',
                'can_view': can_view,
                'can_download': can_download,
                'can_modify': can_modify,
                'can_delete': can_delete
            }
        )
        
        if not created:
            # Обновляем модификаторы доступа
            access.can_view = can_view
            access.can_download = can_download
            access.can_modify = can_modify
            access.can_delete = can_delete
            access.save()
        
        logger.info(f"Folder {folder_id} shared with user {user.id} by email by user {request.user.id}")
        
        return create_json_response(True, f'Доступ предоставлен пользователю {user.username}', {
            'access_id': access.id,
            'user_id': user.id,
            'username': user.username
        })
        
    except Exception as e:
        logger.error(f"Error sharing folder by email: {e}")
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


@login_required
@require_http_methods(["POST"])
def share_folder_link(request, folder_id):
    """Предоставление доступа к папке по ссылке"""
    try:
        folder = get_object_or_404(Folder, id=folder_id, user=request.user)
        
        max_users = int(request.POST.get('max_users', 0))
        can_view = request.POST.get('can_view', 'true') == 'true'
        can_download = request.POST.get('can_download', 'true') == 'true'
        can_modify = request.POST.get('can_modify', 'false') == 'true'
        can_delete = request.POST.get('can_delete', 'false') == 'true'
        allow_unregistered_view = request.POST.get('allow_unregistered_view', 'true') == 'true'
        allow_unregistered_download = request.POST.get('allow_unregistered_download', 'false') == 'true'
        
        # Проверяем, есть ли уже доступ по ссылке для этой папки
        access = SharedFolderAccess.objects.filter(
            folder=folder,
            access_type='link',
            owner=request.user
        ).first()
        
        if access:
            # Обновляем настройки
            access.max_users = max_users
            access.can_view = can_view
            access.can_download = can_download
            access.can_modify = can_modify
            access.can_delete = can_delete
            access.allow_unregistered_view = allow_unregistered_view
            access.allow_unregistered_download = allow_unregistered_download
            access.save()
        else:
            # Создаем новый доступ
            share_token = uuid.uuid4().hex
            access = SharedFolderAccess.objects.create(
                folder=folder,
                owner=request.user,
                access_type='link',
                share_token=share_token,
                max_users=max_users,
                can_view=can_view,
                can_download=can_download,
                can_modify=can_modify,
                can_delete=can_delete,
                allow_unregistered_view=allow_unregistered_view,
                allow_unregistered_download=allow_unregistered_download
            )
        
        share_url = request.build_absolute_uri(
            reverse('shared_folder_view', args=[access.share_token])
        )
        
        logger.info(f"Folder {folder_id} shared via link by user {request.user.id}")
        
        return create_json_response(True, 'Доступ по ссылке создан', {
            'access_id': access.id,
            'share_token': access.share_token,
            'share_url': share_url,
            'max_users': max_users
        })
        
    except Exception as e:
        logger.error(f"Error sharing folder by link: {e}")
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


@login_required
@require_http_methods(["POST"])
def revoke_folder_access(request, folder_id):
    """Отзыв доступа к папке"""
    try:
        folder = get_object_or_404(Folder, id=folder_id, user=request.user)
        
        # Удаляем все доступы к папке
        deleted_count = SharedFolderAccess.objects.filter(folder=folder).delete()[0]
        
        logger.info(f"All access revoked for folder {folder_id} by user {request.user.id}")
        
        return create_json_response(True, f'Доступ к папке отозван', {
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        logger.error(f"Error revoking folder access: {e}")
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


@login_required
@require_http_methods(["POST"])
def update_access_permissions(request, access_id):
    """Обновление модификаторов доступа"""
    try:
        access = get_object_or_404(SharedFolderAccess, id=access_id, owner=request.user)
        
        can_view = request.POST.get('can_view', 'true') == 'true'
        can_download = request.POST.get('can_download', 'true') == 'true'
        can_modify = request.POST.get('can_modify', 'false') == 'true'
        can_delete = request.POST.get('can_delete', 'false') == 'true'
        
        access.can_view = can_view
        access.can_download = can_download
        access.can_modify = can_modify
        access.can_delete = can_delete
        
        if access.access_type == 'link':
            allow_unregistered_view = request.POST.get('allow_unregistered_view', 'true') == 'true'
            allow_unregistered_download = request.POST.get('allow_unregistered_download', 'false') == 'true'
            access.allow_unregistered_view = allow_unregistered_view
            access.allow_unregistered_download = allow_unregistered_download
        
        access.save()
        
        logger.info(f"Access permissions updated for access {access_id} by user {request.user.id}")
        
        return create_json_response(True, 'Модификаторы доступа обновлены', {
            'access_id': access.id
        })
        
    except Exception as e:
        logger.error(f"Error updating access permissions: {e}")
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


@login_required
def shared_folders_list(request):
    """Список папок, к которым предоставлен доступ"""
    # Доступы по email
    email_accesses = SharedFolderAccess.objects.filter(
        granted_to_user=request.user,
        access_type='email'
    ).select_related('folder', 'owner')
    
    # Примонтированные папки
    mounted_objects = MountedFolder.objects.filter(
        user=request.user
    ).select_related('shared_access', 'shared_access__folder', 'shared_access__owner')
    
    # Получаем ID примонтированных доступов, чтобы исключить их из списка доступов по ссылке
    mounted_access_ids = [mount.shared_access.id for mount in mounted_objects]
    
    # Доступы по ссылке (исключаем примонтированные)
    link_accesses = SharedFolderLinkUser.objects.filter(
        user=request.user
    ).exclude(
        share_access__id__in=mounted_access_ids
    ).select_related('share_access', 'share_access__folder', 'share_access__owner')
    
    mounted_folders = []
    for mount in mounted_objects:
        mounted_folders.append({
            'id': mount.id,
            'shared_access': mount.shared_access,
            'mounted_at': mount.mounted_at
        })
    
    # Папки, которыми пользователь поделился (владелец)
    owned_folders = SharedFolderAccess.objects.filter(
        owner=request.user
    ).select_related('folder').order_by('-created_at')
    
    context = {
        'email_accesses': email_accesses,
        'link_accesses': link_accesses,
        'mounted_folders': mounted_folders,
        'owned_folders': owned_folders
    }
    
    return render(request, 'storage/shared_folders.html', context)


@login_required
@require_http_methods(["POST"])
def mount_folder(request, access_id):
    """Примонтировать папку в корень хранилища"""
    try:
        access = get_object_or_404(SharedFolderAccess, id=access_id)
        
        # Проверяем, есть ли доступ
        has_access = False
        is_owner = access.owner == request.user
        
        if is_owner:
            # Владелец всегда имеет доступ
            has_access = True
        elif access.access_type == 'email' and access.granted_to_user == request.user:
            has_access = True
        elif access.access_type == 'link':
            # Для доступа по ссылке - если есть can_view или пользователь уже получил доступ
            if access.can_view:
                # Регистрируем доступ, если еще не зарегистрирован
                SharedFolderLinkUser.objects.get_or_create(
                    share_access=access,
                    user=request.user
                )
                has_access = True
        
        if not has_access:
            return create_json_response(False, 'У вас нет доступа к этой папке', status=403)
        
        # Примонтируем папку
        mounted, created = MountedFolder.objects.get_or_create(
            user=request.user,
            shared_access=access
        )
        
        if not created:
            return create_json_response(False, 'Папка уже примонтирована', status=400)
        
        logger.info(f"Folder {access.folder.id} mounted by user {request.user.id}")
        
        return create_json_response(True, 'Папка успешно примонтирована', {
            'mounted_id': mounted.id,
            'folder_id': access.folder.id,
            'folder_name': access.folder.name
        })
        
    except Exception as e:
        logger.error(f"Error mounting folder: {e}")
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


@login_required
@require_http_methods(["POST"])
def unmount_folder(request, mounted_id):
    """Отмонтировать папку"""
    try:
        mounted = get_object_or_404(MountedFolder, id=mounted_id, user=request.user)
        folder_id = mounted.shared_access.folder.id
        mounted.delete()
        
        logger.info(f"Folder {folder_id} unmounted by user {request.user.id}")
        
        return create_json_response(True, 'Папка отмонтирована')
        
    except Exception as e:
        logger.error(f"Error unmounting folder: {e}")
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


@login_required
def get_link_access_users(request, access_id):
    """Получить список пользователей с доступом по ссылке"""
    try:
        access = get_object_or_404(SharedFolderAccess, id=access_id, owner=request.user)
        
        if access.access_type != 'link':
            return create_json_response(False, 'Это не доступ по ссылке', status=400)
        
        link_users = SharedFolderLinkUser.objects.filter(
            share_access=access
        ).select_related('user').order_by('-accessed_at')
        
        users_data = [{
            'id': lu.user.id,
            'username': lu.user.username,
            'email': lu.user.email,
            'accessed_at': lu.accessed_at.strftime('%d.%m.%Y %H:%M')
        } for lu in link_users]
        
        return JsonResponse({
            'success': True,
            'users': users_data,
            'total': len(users_data),
            'max_users': access.max_users
        })
        
    except Exception as e:
        logger.error(f"Error getting link access users: {e}")
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


def shared_folder_view(request, token):
    """Просмотр общей папки по ссылке (для незарегистрированных и зарегистрированных)"""
    try:
        access = get_object_or_404(SharedFolderAccess, share_token=token, access_type='link')
        
        # Проверяем, является ли пользователь владельцем
        is_owner = request.user.is_authenticated and access.owner == request.user
        
        # Проверяем лимит пользователей (только для зарегистрированных, не владельцев)
        if request.user.is_authenticated and not is_owner:
            # Регистрируем доступ для зарегистрированного пользователя
            SharedFolderLinkUser.objects.get_or_create(
                share_access=access,
                user=request.user
            )
            
            # Проверяем лимит (если не владелец)
            if access.is_access_limit_reached():
                # Для зарегистрированных показываем сообщение, но не блокируем доступ
                from django.contrib import messages
                messages.warning(request, 'Достигнут лимит пользователей для этой папки, но доступ сохранен')
        elif not request.user.is_authenticated:
            # Для незарегистрированных - проверяем настройки
            if not access.allow_unregistered_view:
                from django.shortcuts import redirect
                return redirect('login')
        
        # Получаем файлы и папки
        folder = access.folder
        files = folder.files.all()
        subfolders = folder.subfolders.all()
        
        # Проверяем, примонтирована ли папка (для зарегистрированных)
        is_mounted = False
        if request.user.is_authenticated:
            is_mounted = MountedFolder.objects.filter(
                user=request.user,
                shared_access=access
            ).exists()
        
        # Проверяем, является ли пользователь владельцем
        is_owner = request.user.is_authenticated and access.owner == request.user
        
        context = {
            'folder': folder,
            'files': files,
            'subfolders': subfolders,
            'access': access,
            'is_mounted': is_mounted,
            'owner': access.owner,
            'is_owner': is_owner,
            'is_authenticated': request.user.is_authenticated,
            'user': request.user if request.user.is_authenticated else None
        }
        
        return render(request, 'storage/shared_folder_view.html', context)
        
    except Exception as e:
        logger.error(f"Error viewing shared folder: {e}")
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.error(request, 'Ошибка при доступе к папке')
        if request.user.is_authenticated:
            return redirect('dashboard')
        else:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.path)


@require_http_methods(["GET"])
def shared_file_download(request, token, file_id):
    """Скачивание файла из общей папки"""
    try:
        access = get_object_or_404(SharedFolderAccess, share_token=token, access_type='link')
        
        if not access.can_download:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("У вас нет прав на скачивание файлов из этой папки")
        
        # Получаем файл
        from ..models import UserFile
        file = get_object_or_404(UserFile, id=file_id, folder=access.folder)
        
        # Проверяем доступ для незарегистрированных
        if not request.user.is_authenticated:
            if not access.allow_unregistered_download:
                from django.shortcuts import redirect
                return redirect('login')
        else:
            # Для зарегистрированных - регистрируем доступ
            SharedFolderLinkUser.objects.get_or_create(
                share_access=access,
                user=request.user
            )
        
        # Скачиваем файл
        from django.http import FileResponse
        from urllib.parse import quote
        file_path = file.file.path
        encoded_filename = quote(file.filename)
        
        response = FileResponse(open(file_path, 'rb'))
        response['Content-Type'] = 'application/octet-stream'
        response['Content-Disposition'] = (
            f'attachment; filename="{encoded_filename}"; '
            f'filename*=UTF-8\'\'{encoded_filename}'
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error downloading shared file: {e}")
        from django.http import Http404
        raise Http404("Файл не найден или недоступен")

