"""
Прочие операции: статистика
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from eventshock_auth.models import UserProfile


@login_required
def storage_stats(request):
    """Получение статистики хранилища пользователя"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return JsonResponse({
        'percent': profile.get_storage_percent(),
        'used_formatted': profile.get_used_storage_formatted(),
        'quota_formatted': profile.get_quota_formatted()
    })

