"""
Операции с общим доступом к папкам: поделиться, отозвать, настройки доступа
"""
import logging
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden, FileResponse, Http404
from django.contrib import messages
from django.urls import reverse
from urllib.parse import quote

from ..models import Folder, SharedFolderAccess, SharedFolderLinkUser, MountedFolder, UserFile
from ..helpers import create_json_response
from .share_helpers import (
    AccessPermissionManager,
    extract_permissions_from_request,
    validate_share_request,
    create_or_update_access,
    register_link_access,
    get_shared_folder_context,
    get_user_shared_folders
)

logger = logging.getLogger(__name__)


def get_share_url(access: SharedFolderAccess, request) -> str:
    """Генерирует полный URL для доступа к папке по ссылке"""
    if access.access_type != 'link' or not access.share_token:
        raise ValueError("Доступ не поддерживает ссылку")
    return request.build_absolute_uri(
        reverse('shared_folder_view', args=[access.share_token])
    )


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
        permissions = extract_permissions_from_request(request)
        
        # Валидация
        is_valid, error_msg = validate_share_request(folder, request.user, email)
        if not is_valid:
            return create_json_response(False, error_msg, status=400)
        
        # Получаем пользователя по email
        target_user = User.objects.get(email=email)
        
        # Создаем или обновляем доступ
        access, created = create_or_update_access(
            folder=folder,
            owner=request.user,
            access_type='email',
            permissions=permissions,
            granted_to_user=target_user
        )
        
        action = "обновлен" if not created else "создан"
        logger.info(f"Folder {folder_id} access {action} for user {target_user.id} by email by user {request.user.id}")
        
        return create_json_response(True, f'Доступ предоставлен пользователю {target_user.username}', {
            'access_id': access.id,
            'user_id': target_user.id,
            'username': target_user.username
        })
        
    except User.DoesNotExist:
        return create_json_response(False, 'Пользователь с таким email не найден', status=404)
    except ValueError as e:
        return create_json_response(False, str(e), status=400)
    except Exception as e:
        logger.error(f"Error sharing folder by email: {e}", exc_info=True)
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


@login_required
@require_http_methods(["POST"])
def share_folder_link(request, folder_id):
    """Предоставление доступа к папке по ссылке"""
    try:
        folder = get_object_or_404(Folder, id=folder_id, user=request.user)
        permissions = extract_permissions_from_request(request)
        
        # Валидация
        is_valid, error_msg = validate_share_request(folder, request.user)
        if not is_valid:
            return create_json_response(False, error_msg, status=400)
        
        # Создаем или обновляем доступ
        access, created = create_or_update_access(
            folder=folder,
            owner=request.user,
            access_type='link',
            permissions=permissions
        )
        
        share_url = get_share_url(access, request)
        
        action = "обновлен" if not created else "создан"
        logger.info(f"Folder {folder_id} link access {action} by user {request.user.id}")
        
        return create_json_response(True, 'Доступ по ссылке создан', {
            'access_id': access.id,
            'share_token': access.share_token,
            'share_url': share_url,
            'max_users': permissions['max_users']
        })
        
    except ValueError as e:
        return create_json_response(False, str(e), status=400)
    except Exception as e:
        logger.error(f"Error sharing folder by link: {e}", exc_info=True)
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
        permissions = extract_permissions_from_request(request)
        
        # Обновляем права доступа
        access.can_view = permissions['can_view']
        access.can_download = permissions['can_download']
        access.can_modify = permissions['can_modify']
        access.can_delete = permissions['can_delete']
        
        if access.access_type == 'link':
            access.max_users = permissions['max_users']
            access.allow_unregistered_view = permissions['allow_unregistered_view']
            access.allow_unregistered_download = permissions['allow_unregistered_download']
        
        access.save()
        
        logger.info(f"Access permissions updated for access {access_id} by user {request.user.id}")
        
        return create_json_response(True, 'Модификаторы доступа обновлены', {
            'access_id': access.id
        })
        
    except Exception as e:
        logger.error(f"Error updating access permissions: {e}", exc_info=True)
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)


@login_required
def shared_folders_list(request):
    """Список папок, к которым предоставлен доступ"""
    context = get_user_shared_folders(request.user)
    return render(request, 'storage/shared_folders.html', context)


@login_required
@require_http_methods(["POST"])
def mount_folder(request, access_id):
    """Примонтировать папку в корень хранилища"""
    try:
        access = get_object_or_404(SharedFolderAccess, id=access_id)
        
        # Проверяем доступ через менеджер прав
        has_access, reason = AccessPermissionManager.check_user_access(request.user, access)
        
        if not has_access:
            return create_json_response(False, 'У вас нет доступа к этой папке', status=403)
        
        # Регистрируем доступ по ссылке, если нужно
        if access.access_type == 'link' and reason == "link_auto_registered":
            register_link_access(access, request.user)
        
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
        logger.error(f"Error mounting folder: {e}", exc_info=True)
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
        # Используем универсальную функцию поиска для обратной совместимости
        from ..models import find_token_in_model, SharedFolderAccess
        access = find_token_in_model(SharedFolderAccess, 'share_token', token)
        if not access:
            raise Http404("Доступ не найден")
        if access.access_type != 'link':
            raise Http404("Неверный тип доступа")
        
        # Проверка доступа для незарегистрированных пользователей
        if not request.user.is_authenticated:
            if not AccessPermissionManager.can_unregistered_view(access):
                return redirect('login')
        else:
            # Для зарегистрированных проверяем доступ и регистрируем
            has_access, reason = AccessPermissionManager.check_user_access(request.user, access)
            
            if not has_access:
                messages.error(request, 'У вас нет доступа к этой папке')
                return redirect('dashboard')
            
            # Регистрируем доступ по ссылке, если нужно
            if reason == "link_auto_registered":
                register_link_access(access, request.user)
            
            # Проверяем лимит (предупреждение, но не блокируем)
            if access.is_access_limit_reached() and reason != "owner":
                messages.warning(request, 'Достигнут лимит пользователей для этой папки, но доступ сохранен')
        
        # Получаем контекст через вспомогательную функцию
        context = get_shared_folder_context(access, request.user if request.user.is_authenticated else None)
        
        return render(request, 'storage/shared_folder_view.html', context)
        
    except Exception as e:
        logger.error(f"Error viewing shared folder: {e}", exc_info=True)
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
        # Используем универсальную функцию поиска для обратной совместимости
        from ..models import find_token_in_model, SharedFolderAccess
        access = find_token_in_model(SharedFolderAccess, 'share_token', token)
        if not access:
            raise Http404("Доступ не найден")
        if access.access_type != 'link':
            raise Http404("Неверный тип доступа")
        user = request.user if request.user.is_authenticated else None
        
        # Проверка прав на скачивание
        if user:
            if not AccessPermissionManager.can_user_download(user, access):
                return HttpResponseForbidden("У вас нет прав на скачивание файлов из этой папки")
        else:
            if not AccessPermissionManager.can_unregistered_download(access):
                return redirect('login')
        
        # Получаем файл
        file = get_object_or_404(UserFile, id=file_id, folder=access.folder)
        
        # Регистрируем доступ для зарегистрированных пользователей
        if user:
            register_link_access(access, user)
        
        # Скачиваем файл
        from ..helpers import get_file_for_response, generate_s3_presigned_url
        from django.http import HttpResponseRedirect
        import os
        
        # Проверяем, если файл в S3 хранилище, используем presigned URL
        if file.storage and file.storage.storage_type == 's3':
            s3_key = f"{file.user.id}/{file.filename}"
            presigned_url = generate_s3_presigned_url(file.storage, s3_key, expiration=3600)
            if presigned_url:
                # Перенаправляем на presigned URL для прямого скачивания
                return HttpResponseRedirect(presigned_url)
        
        # Для локальных файлов используем стандартный метод
        file_path, is_temp, temp_path = get_file_for_response(file)
        if not file_path:
            raise Http404("Файл не найден")
        
        try:
            encoded_filename = quote(file.filename)
            response = FileResponse(open(file_path, 'rb'))
            response['Content-Type'] = 'application/octet-stream'
            response['Content-Disposition'] = (
                f'attachment; filename="{encoded_filename}"; '
                f'filename*=UTF-8\'\'{encoded_filename}'
            )
            
            # Если это временный файл, удаляем его после отправки
            if is_temp and temp_path:
                import atexit
                atexit.register(lambda: os.remove(temp_path) if os.path.exists(temp_path) else None)
            
            return response
        except Exception as e:
            # Удаляем временный файл в случае ошибки
            if is_temp and temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            raise
        
    except Http404:
        raise
    except Exception as e:
        logger.error(f"Error downloading shared file: {e}", exc_info=True)
        raise Http404("Файл не найден или недоступен")

