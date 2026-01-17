"""
Операции со статистикой хранилища в админ-панели
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from ..helpers import get_global_storage_stats, get_users_with_storage
from .dashboard_views import is_superuser
from storage.models import Storage


@user_passes_test(is_superuser)
def storage_stats(request):
    """
    Статистика использования хранилища пользователями.
    """
    stats = get_global_storage_stats()
    users_storage = get_users_with_storage()
    
    context = {
        'active_tab': 'storage',
        'total_storage': stats['total_storage_formatted'],
        'total_files': stats['total_files'],
        'users_storage': users_storage
    }
    return render(request, 'eventshock_auth/admin/storage_stats.html', context)


@user_passes_test(is_superuser)
def storage_management(request):
    """
    Управление хранилищами: список, создание, редактирование, удаление.
    """
    storages = Storage.objects.all().order_by('-priority', 'name')
    
    # Добавляем статистику для каждого хранилища
    storages_with_stats = []
    for storage in storages:
        # Проверяем статус подключения для S3 хранилищ
        s3_status = None
        if storage.storage_type == 's3':
            s3_status = storage.get_s3_connection_status()
        
        storages_with_stats.append({
            'storage': storage,
            'used_size': storage.get_used_size(),
            'used_size_formatted': storage.get_used_size_formatted(),
            'available_size': storage.get_available_size(),
            'available_size_formatted': storage.get_available_size_formatted(),
            'usage_percent': storage.get_usage_percent(),
            'files_count': storage.get_files_count(),
            's3_status': s3_status,
        })
    
    context = {
        'active_tab': 'storage_management',
        'storages': storages_with_stats,
    }
    return render(request, 'eventshock_auth/admin/storage_management.html', context)


@user_passes_test(is_superuser)
def storage_create(request):
    """
    Создание нового хранилища.
    """
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            storage_type = request.POST.get('storage_type')
            is_active = request.POST.get('is_active') == 'on'
            
            # Обработка размера с учетом единицы измерения
            max_size_value = float(request.POST.get('max_size', 0))
            size_unit = request.POST.get('size_unit', 'bytes')
            
            # Валидация значения
            if max_size_value <= 0:
                raise ValueError('Размер хранилища должен быть больше нуля')
            
            # Конвертируем в байты
            if size_unit == 'mb':
                max_size_bytes = int(max_size_value * 1024 * 1024)
            elif size_unit == 'gb':
                max_size_bytes = int(max_size_value * 1024 * 1024 * 1024)
            elif size_unit == 'tb':
                max_size_bytes = int(max_size_value * 1024 * 1024 * 1024 * 1024)
            else:  # bytes
                max_size_bytes = int(max_size_value)
            
            # Проверяем, что значение не превышает максимальное для BigInteger
            # SQLite INTEGER может хранить до 2^63 - 1 (9223372036854775807)
            MAX_BIGINT = 9223372036854775807
            if max_size_bytes > MAX_BIGINT:
                raise ValueError(f'Размер хранилища слишком большой. Максимальное значение: ~8 ЭБ (эксабайт)')
            
            max_size = max_size_bytes
            
            priority = int(request.POST.get('priority', 0))
            
            storage = Storage(
                name=name,
                storage_type=storage_type,
                is_active=is_active,
                max_size=max_size,
                priority=priority
            )
            
            if storage_type == 'local':
                local_path = request.POST.get('local_path')
                storage.local_path = local_path
            elif storage_type == 's3':
                storage.s3_access_key = request.POST.get('s3_access_key')
                storage.s3_secret_key = request.POST.get('s3_secret_key')
                storage.s3_bucket_name = request.POST.get('s3_bucket_name')
                storage.s3_endpoint_url = request.POST.get('s3_endpoint_url', '')
                storage.s3_region = request.POST.get('s3_region', '')
            
            storage.save()
            messages.success(request, f'Хранилище "{name}" успешно создано')
            return redirect('esadmin:storage_management')
        except Exception as e:
            messages.error(request, f'Ошибка при создании хранилища: {str(e)}')
    
    # Определяем единицу измерения для отображения существующего размера
    size_unit = 'gb'  # По умолчанию гигабайты
    display_size = 0
    
    context = {
        'active_tab': 'storage_management',
        'size_unit': size_unit,
        'display_size': display_size,
    }
    return render(request, 'eventshock_auth/admin/storage_form.html', context)


@user_passes_test(is_superuser)
def storage_edit(request, storage_id):
    """
    Редактирование хранилища.
    """
    storage = get_object_or_404(Storage, id=storage_id)
    
    if request.method == 'POST':
        try:
            storage.name = request.POST.get('name')
            storage.storage_type = request.POST.get('storage_type')
            storage.is_active = request.POST.get('is_active') == 'on'
            
            # Обработка размера с учетом единицы измерения
            max_size_value = float(request.POST.get('max_size', 0))
            size_unit = request.POST.get('size_unit', 'bytes')
            
            # Валидация значения
            if max_size_value <= 0:
                raise ValueError('Размер хранилища должен быть больше нуля')
            
            # Конвертируем в байты
            if size_unit == 'mb':
                max_size_bytes = int(max_size_value * 1024 * 1024)
            elif size_unit == 'gb':
                max_size_bytes = int(max_size_value * 1024 * 1024 * 1024)
            elif size_unit == 'tb':
                max_size_bytes = int(max_size_value * 1024 * 1024 * 1024 * 1024)
            else:  # bytes
                max_size_bytes = int(max_size_value)
            
            # Проверяем, что значение не превышает максимальное для BigInteger
            # SQLite INTEGER может хранить до 2^63 - 1 (9223372036854775807)
            MAX_BIGINT = 9223372036854775807
            if max_size_bytes > MAX_BIGINT:
                raise ValueError(f'Размер хранилища слишком большой. Максимальное значение: ~8 ЭБ (эксабайт)')
            
            storage.max_size = max_size_bytes
            
            storage.priority = int(request.POST.get('priority', 0))
            
            if storage.storage_type == 'local':
                storage.local_path = request.POST.get('local_path')
                # Очищаем S3 поля
                storage.s3_access_key = None
                storage.s3_secret_key = None
                storage.s3_bucket_name = None
                storage.s3_endpoint_url = None
                storage.s3_region = None
            elif storage.storage_type == 's3':
                storage.s3_access_key = request.POST.get('s3_access_key')
                storage.s3_secret_key = request.POST.get('s3_secret_key')
                storage.s3_bucket_name = request.POST.get('s3_bucket_name')
                storage.s3_endpoint_url = request.POST.get('s3_endpoint_url', '')
                storage.s3_region = request.POST.get('s3_region', '')
                # Очищаем локальный путь
                storage.local_path = None
            
            storage.save()
            messages.success(request, f'Хранилище "{storage.name}" успешно обновлено')
            return redirect('esadmin:storage_management')
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении хранилища: {str(e)}')
    
    # Определяем единицу измерения для отображения существующего размера
    size_unit = 'gb'  # По умолчанию гигабайты
    display_size = storage.max_size
    
    # Автоматически определяем подходящую единицу измерения
    if storage.max_size >= 1099511627776:  # >= 1 TB
        size_unit = 'tb'
        display_size = storage.max_size / (1024 * 1024 * 1024 * 1024)
    elif storage.max_size >= 1073741824:  # >= 1 GB
        size_unit = 'gb'
        display_size = storage.max_size / (1024 * 1024 * 1024)
    elif storage.max_size >= 1048576:  # >= 1 MB
        size_unit = 'mb'
        display_size = storage.max_size / (1024 * 1024)
    else:
        size_unit = 'bytes'
        display_size = storage.max_size
    
    context = {
        'active_tab': 'storage_management',
        'storage': storage,
        'size_unit': size_unit,
        'display_size': display_size,
    }
    return render(request, 'eventshock_auth/admin/storage_form.html', context)


@user_passes_test(is_superuser)
def storage_delete(request, storage_id):
    """
    Удаление хранилища.
    """
    storage = get_object_or_404(Storage, id=storage_id)
    
    if request.method == 'POST':
        # Проверяем, есть ли файлы в хранилище
        files_count = storage.get_files_count()
        if files_count > 0:
            messages.error(request, f'Невозможно удалить хранилище: в нем находится {files_count} файлов')
            return redirect('esadmin:storage_management')
        
        storage_name = storage.name
        storage.delete()
        messages.success(request, f'Хранилище "{storage_name}" успешно удалено')
        return redirect('esadmin:storage_management')
    
    context = {
        'active_tab': 'storage_management',
        'storage': storage,
    }
    return render(request, 'eventshock_auth/admin/storage_delete.html', context)


@user_passes_test(is_superuser)
def storage_test_connection(request, storage_id):
    """
    Тестирование подключения к S3 хранилищу.
    """
    from django.http import JsonResponse
    storage = get_object_or_404(Storage, id=storage_id)
    
    if storage.storage_type != 's3':
        return JsonResponse({
            'success': False,
            'message': 'Это не S3 хранилище. Тест подключения доступен только для S3-совместимых хранилищ.'
        })
    
    success, message = storage.test_s3_connection()
    
    return JsonResponse({
        'success': success,
        'message': message
    })

