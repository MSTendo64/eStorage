"""
Операции с публичным доступом к файлам
"""
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse

from ..models import UserFile
from ..helpers import create_json_response
from ..constants import SUCCESS_PUBLIC_ENABLED, SUCCESS_PUBLIC_DISABLED

logger = __import__('logging').getLogger(__name__)


@login_required
def toggle_file_publicity(request, file_id):
    """Переключение публичного доступа к файлу"""
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        file.is_public = not file.is_public
        file.save()
        
        if file.is_public:
            messages.success(request, SUCCESS_PUBLIC_ENABLED)
            return JsonResponse({
                'status': 'success',
                'is_public': True,
                'public_url': request.build_absolute_uri(file.get_public_url())
            })
        else:
            messages.success(request, SUCCESS_PUBLIC_DISABLED)
            return JsonResponse({
                'status': 'success',
                'is_public': False
            })
            
    except UserFile.DoesNotExist:
        return create_json_response(False, 'Файл не найден', status=404)
    except Exception as e:
        logger.error(f"Error in toggle_file_publicity: {e}")
        return create_json_response(False, f'Ошибка: {str(e)}', status=500)

