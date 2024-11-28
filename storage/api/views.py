from rest_framework import viewsets, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def auth(request):
    """
    Авторизация существующего пользователя
    """
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response({
            'error': 'Необходимо указать имя пользователя и пароль'
        }, status=400)
    
    user = authenticate(username=username, password=password)
    if user:
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key
        })
    
    return Response({
        'error': 'Неверные учетные данные'
    }, status=401)

# ... остальные API endpoints ... 