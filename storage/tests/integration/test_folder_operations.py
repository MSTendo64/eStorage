"""
Интеграционные тесты для операций с папками
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from storage.models import Folder
import json


class FolderOperationsIntegrationTest(TestCase):
    """Интеграционные тесты для операций с папками"""
    
    def setUp(self):
        """Настройка тестового окружения"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_create_folder_integration(self):
        """Интеграционный тест создания папки через API"""
        url = reverse('storage:create_folder')
        response = self.client.post(url, {
            'name': 'New Folder',
            'parent_id': ''
        })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get('success'))
        self.assertIn('folder_id', data)
        
        # Проверяем что папка создана в БД
        folder = Folder.objects.get(id=data['folder_id'])
        self.assertEqual(folder.name, 'New Folder')
        self.assertEqual(folder.user, self.user)
    
    def test_create_nested_folder_integration(self):
        """Интеграционный тест создания вложенной папки"""
        # Создаем родительскую папку
        parent = Folder.objects.create(user=self.user, name='Parent')
        
        url = reverse('storage:create_folder')
        response = self.client.post(url, {
            'name': 'Child Folder',
            'parent_id': str(parent.id)
        })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get('success'))
        
        # Проверяем что дочерняя папка создана
        child = Folder.objects.get(id=data['folder_id'])
        self.assertEqual(child.name, 'Child Folder')
        self.assertEqual(child.parent, parent)
    
    def test_rename_folder_integration(self):
        """Интеграционный тест переименования папки"""
        folder = Folder.objects.create(user=self.user, name='Old Name')
        
        url = reverse('storage:rename_folder', args=[folder.id])
        response = self.client.post(url, {
            'name': 'New Name'
        })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get('success'))
        
        # Проверяем что папка переименована
        folder.refresh_from_db()
        self.assertEqual(folder.name, 'New Name')
    
    def test_delete_folder_integration(self):
        """Интеграционный тест удаления папки"""
        folder = Folder.objects.create(user=self.user, name='To Delete')
        folder_id = folder.id
        
        url = reverse('storage:delete_folder', args=[folder.id])
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get('success'))
        
        # Проверяем что папка удалена
        self.assertFalse(Folder.objects.filter(id=folder_id).exists())
    
    def test_create_folder_requires_authentication(self):
        """Тест что создание папки требует аутентификации"""
        self.client.logout()
        
        url = reverse('storage:create_folder')
        response = self.client.post(url, {
            'name': 'Unauthorized Folder'
        })
        
        # Должен быть редирект на страницу входа
        self.assertIn(response.status_code, [302, 403])
    
    def test_rename_folder_other_user_forbidden(self):
        """Тест что нельзя переименовать папку другого пользователя"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )
        other_folder = Folder.objects.create(user=other_user, name='Other Folder')
        
        url = reverse('storage:rename_folder', args=[other_folder.id])
        response = self.client.post(url, {
            'name': 'Hacked Name'
        })
        
        # Должна быть ошибка доступа
        self.assertEqual(response.status_code, 404)  # Или 403 в зависимости от реализации

