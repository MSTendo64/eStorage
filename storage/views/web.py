import os
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib import messages
from ..models import UserFile

@login_required
def dashboard(request):
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        user_folder = os.path.join(settings.MEDIA_ROOT, str(request.user.id))
        
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
            
        file_path = os.path.join(user_folder, uploaded_file.name)
        
        with open(file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
                
        UserFile.objects.create(
            user=request.user,
            file=f'{request.user.id}/{uploaded_file.name}',
            filename=uploaded_file.name
        )
        messages.success(request, 'Файл успешно загружен')
        return redirect('dashboard')
        
    user_files = UserFile.objects.filter(user=request.user)
    return render(request, 'storage/dashboard.html', {'files': user_files})

@login_required
def delete_file(request, file_id):
    try:
        file = UserFile.objects.get(id=file_id, user=request.user)
        file_path = os.path.join(settings.MEDIA_ROOT, str(file.file))
        if os.path.exists(file_path):
            os.remove(file_path)
        file.delete()
        messages.success(request, 'Файл успешно удален')
    except UserFile.DoesNotExist:
        messages.error(request, 'Файл не найден')
    return redirect('dashboard') 