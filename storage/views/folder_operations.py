"""
Операции с папками: создание, удаление, переименование, перемещение файлов
"""
import os
import logging
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from ..models import Folder, UserFile
from ..helpers import create_json_response

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def create_folder(request):
    """Создание новой папки"""
    try:
        name = request.POST.get('name', '').strip()
        parent_id = request.POST.get('parent_id', None)
        
        if not name:
            return create_json_response(False, 'Имя папки не может быть пустым', status=400)
        
        # Проверка на существующую папку с таким же именем
        parent = None
        if parent_id:
            try:
                parent = Folder.objects.get(id=parent_id, user=request.user)
            except Folder.DoesNotExist:
                return create_json_response(False, 'Родительская папка не найдена', status=404)
        
        # Проверка уникальности имени в текущей папке
        if Folder.objects.filter(user=request.user, name=name, parent=parent).exists():
            return create_json_response(False, 'Папка с таким именем уже существует', status=400)
        
        # Создание папки
        folder = Folder.objects.create(
            user=request.user,
            name=name,
            parent=parent
        )
        
        logger.info(f"Folder {folder.id} created by user {request.user.id}")
        
        return create_json_response(True, 'Папка успешно создана', {
            'folder_id': folder.id,
            'folder_name': folder.name,
            'folder_path': folder.get_full_path()
        })
        
    except Exception as e:
        logger.error(f"Error creating folder: {e}")
        return create_json_response(False, f'Ошибка при создании папки: {str(e)}', status=500)


@login_required
@require_http_methods(["POST"])
def rename_folder(request, folder_id):
    """Переименование папки"""
    try:
        folder = Folder.objects.get(id=folder_id, user=request.user)
        
        new_name = request.POST.get('name', '').strip()
        if not new_name:
            return create_json_response(False, 'Имя папки не может быть пустым', status=400)
        
        # Проверка на существующую папку с таким же именем в той же родительской папке
        if Folder.objects.filter(user=request.user, name=new_name, parent=folder.parent).exclude(id=folder_id).exists():
            return create_json_response(False, 'Папка с таким именем уже существует', status=400)
        
        old_name = folder.name
        folder.name = new_name
        folder.save()
        
        logger.info(f"Folder {folder_id} renamed from '{old_name}' to '{new_name}' by user {request.user.id}")
        
        return create_json_response(True, 'Папка успешно переименована', {
            'folder_id': folder.id,
            'folder_name': folder.name,
            'folder_path': folder.get_full_path()
        })
        
    except Folder.DoesNotExist:
        return create_json_response(False, 'Папка не найдена', status=404)
    except Exception as e:
        logger.error(f"Error renaming folder {folder_id}: {e}")
        return create_json_response(False, f'Ошибка при переименовании папки: {str(e)}', status=500)


@login_required
@require_http_methods(["POST"])
def delete_folder(request, folder_id):
    """Удаление папки (только если она пустая)"""
    try:
        folder = Folder.objects.get(id=folder_id, user=request.user)
        
        # Проверка на наличие файлов
        if folder.files.exists():
            return create_json_response(False, 'Невозможно удалить папку с файлами', status=400)
        
        # Проверка на наличие подпапок
        if folder.subfolders.exists():
            return create_json_response(False, 'Невозможно удалить папку с подпапками', status=400)
        
        folder_name = folder.name
        folder.delete()
        
        logger.info(f"Folder {folder_id} ({folder_name}) deleted by user {request.user.id}")
        
        return create_json_response(True, 'Папка успешно удалена')
        
    except Folder.DoesNotExist:
        return create_json_response(False, 'Папка не найдена', status=404)
    except Exception as e:
        logger.error(f"Error deleting folder {folder_id}: {e}")
        return create_json_response(False, f'Ошибка при удалении папки: {str(e)}', status=500)


@login_required
@require_http_methods(["POST"])
def move_files(request):
    """Перемещение выбранных файлов в папку"""
    try:
        file_ids = request.POST.getlist('file_ids[]')
        folder_id = request.POST.get('folder_id', None)
        
        if not file_ids:
            return create_json_response(False, 'Не выбраны файлы для перемещения', status=400)
        
        # Получаем целевую папку
        target_folder = None
        if folder_id:
            try:
                target_folder = Folder.objects.get(id=folder_id, user=request.user)
            except Folder.DoesNotExist:
                return create_json_response(False, 'Целевая папка не найдена', status=404)
        
        # Получаем файлы и перемещаем их
        files = UserFile.objects.filter(id__in=file_ids, user=request.user)
        moved_count = 0
        
        for file in files:
            file.folder = target_folder
            file.save()
            moved_count += 1
        
        logger.info(f"{moved_count} files moved to folder {folder_id or 'root'} by user {request.user.id}")
        
        return create_json_response(True, f'{moved_count} файлов успешно перемещено', {
            'moved_count': moved_count
        })
        
    except Exception as e:
        logger.error(f"Error moving files: {e}")
        return create_json_response(False, f'Ошибка при перемещении файлов: {str(e)}', status=500)


@login_required
@require_http_methods(["POST"])
def rename_file(request, file_id):
    """Переименование файла"""
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        
        new_name = request.POST.get('name', '').strip()
        if not new_name:
            return create_json_response(False, 'Имя файла не может быть пустым', status=400)
        
        # Проверка на существующий файл с таким же именем в той же папке
        if UserFile.objects.filter(user=request.user, filename=new_name, folder=file.folder).exclude(id=file_id).exists():
            return create_json_response(False, 'Файл с таким именем уже существует в этой папке', status=400)
        
        old_name = file.filename
        file.filename = new_name
        file.save()
        
        logger.info(f"File {file_id} renamed from '{old_name}' to '{new_name}' by user {request.user.id}")
        
        return create_json_response(True, 'Файл успешно переименован', {
            'file_id': file.id,
            'filename': file.filename
        })
        
    except UserFile.DoesNotExist:
        return create_json_response(False, 'Файл не найден', status=404)
    except Exception as e:
        logger.error(f"Error renaming file {file_id}: {e}")
        return create_json_response(False, f'Ошибка при переименовании файла: {str(e)}', status=500)


@login_required
@require_http_methods(["GET"])
def get_folders_tree(request):
    """Получение дерева папок пользователя"""
    try:
        def build_folder_tree(parent_id=None):
            """Рекурсивно строит дерево папок"""
            folders = Folder.objects.filter(user=request.user, parent=parent_id).order_by('name')
            result = []
            for folder in folders:
                result.append({
                    'id': folder.id,
                    'name': folder.name,
                    'path': folder.get_full_path(),
                    'children': build_folder_tree(folder.id)
                })
            return result
        
        tree = build_folder_tree()
        
        return JsonResponse({
            'success': True,
            'folders': tree
        })
        
    except Exception as e:
        logger.error(f"Error getting folders tree: {e}")
        return create_json_response(False, f'Ошибка при получении дерева папок: {str(e)}', status=500)

