"""
Интеграционные тесты для операций с файлами
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from storage.models import Folder, UserFile
import json
import tempfile
import os


class FileOperationsIntegrationTest(TestCase):
    """Интеграционные тесты для операций с файлами"""
    
    def setUp(self):
        """Настройка тестового окружения"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        self.folder = Folder.objects.create(user=self.user, name='Test Folder')
    
    def test_rename_file_integration(self):
        """Интеграционный тест переименования файла"""
        file_obj = UserFile.objects.create(
            user=self.user,
            file='1/test.txt',
            filename='old_name.txt',
            file_type='text',
            file_size=1024,
            folder=self.folder
        )
        
        url = reverse('storage:rename_file', args=[file_obj.id])
        response = self.client.post(
            url,
            json.dumps({'name': 'new_name.txt'}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get('success'))
        
        # Проверяем что файл переименован
        file_obj.refresh_from_db()
        self.assertEqual(file_obj.filename, 'new_name.txt')
    
    def test_rename_file_validation(self):
        """Тест валидации при переименовании файла"""
        file_obj = UserFile.objects.create(
            user=self.user,
            file='1/test.txt',
            filename='test.txt',
            file_type='text',
            file_size=1024
        )
        
        url = reverse('storage:rename_file', args=[file_obj.id])
        
        # Тест пустого имени
        response = self.client.post(
            url,
            json.dumps({'name': ''}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertFalse(data.get('success'))
        
        # Тест запрещенных символов
        response = self.client.post(
            url,
            json.dumps({'name': 'test<>file.txt'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertFalse(data.get('success'))
    
    def test_rename_file_duplicate_name(self):
        """Тест переименования файла с дублирующимся именем"""
        # Создаем два файла
        file1 = UserFile.objects.create(
            user=self.user,
            file='1/file1.txt',
            filename='file1.txt',
            file_type='text',
            file_size=1024,
            folder=self.folder
        )
        file2 = UserFile.objects.create(
            user=self.user,
            file='1/file2.txt',
            filename='file2.txt',
            file_type='text',
            file_size=1024,
            folder=self.folder
        )
        
        # Пытаемся переименовать file2 в file1
        url = reverse('storage:rename_file', args=[file2.id])
        response = self.client.post(
            url,
            json.dumps({'name': 'file1.txt'}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertFalse(data.get('success'))
        self.assertIn('уже существует', data.get('message', ''))
    
    def test_rename_file_other_user_forbidden(self):
        """Тест что нельзя переименовать файл другого пользователя"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )
        other_file = UserFile.objects.create(
            user=other_user,
            file='2/test.txt',
            filename='test.txt',
            file_type='text',
            file_size=1024
        )
        
        url = reverse('storage:rename_file', args=[other_file.id])
        response = self.client.post(
            url,
            json.dumps({'name': 'hacked.txt'}),
            content_type='application/json'
        )
        
        # Должна быть ошибка доступа
        self.assertEqual(response.status_code, 404)

