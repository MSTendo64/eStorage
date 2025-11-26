"""
Unit-тесты для моделей storage
"""
from django.test import TestCase
from django.contrib.auth.models import User
from storage.models import Folder, UserFile
import tempfile
import os


class FolderModelTest(TestCase):
    """Тесты для модели Folder"""
    
    def setUp(self):
        """Создаем тестового пользователя"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_folder_creation(self):
        """Тест создания папки"""
        folder = Folder.objects.create(
            user=self.user,
            name='Test Folder'
        )
        self.assertEqual(folder.name, 'Test Folder')
        self.assertEqual(folder.user, self.user)
        self.assertIsNone(folder.parent)
    
    def test_folder_full_path_root(self):
        """Тест получения полного пути для корневой папки"""
        folder = Folder.objects.create(
            user=self.user,
            name='Root Folder'
        )
        self.assertEqual(folder.get_full_path(), 'Root Folder')
    
    def test_folder_full_path_nested(self):
        """Тест получения полного пути для вложенной папки"""
        parent = Folder.objects.create(
            user=self.user,
            name='Parent'
        )
        child = Folder.objects.create(
            user=self.user,
            name='Child',
            parent=parent
        )
        self.assertEqual(child.get_full_path(), 'Parent/Child')
    
    def test_folder_unique_together(self):
        """Тест уникальности папок с одинаковым именем в одной родительской папке"""
        Folder.objects.create(
            user=self.user,
            name='Duplicate'
        )
        # Попытка создать папку с тем же именем должна вызвать ошибку
        with self.assertRaises(Exception):
            Folder.objects.create(
                user=self.user,
                name='Duplicate'
            )
    
    def test_folder_different_users_same_name(self):
        """Тест что разные пользователи могут иметь папки с одинаковым именем"""
        user2 = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )
        folder1 = Folder.objects.create(user=self.user, name='Shared Name')
        folder2 = Folder.objects.create(user=user2, name='Shared Name')
        
        self.assertEqual(folder1.name, folder2.name)
        self.assertNotEqual(folder1.user, folder2.user)


class UserFileModelTest(TestCase):
    """Тесты для модели UserFile"""
    
    def setUp(self):
        """Создаем тестового пользователя и папку"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.folder = Folder.objects.create(
            user=self.user,
            name='Test Folder'
        )
    
    def test_user_file_creation(self):
        """Тест создания файла"""
        file_obj = UserFile.objects.create(
            user=self.user,
            file='1/test.txt',
            filename='test.txt',
            file_type='text',
            file_size=1024,
            folder=self.folder
        )
        self.assertEqual(file_obj.filename, 'test.txt')
        self.assertEqual(file_obj.user, self.user)
        self.assertEqual(file_obj.folder, self.folder)
        self.assertEqual(file_obj.file_type, 'text')
    
    def test_user_file_without_folder(self):
        """Тест создания файла без папки"""
        file_obj = UserFile.objects.create(
            user=self.user,
            file='1/test.txt',
            filename='test.txt',
            file_type='text',
            file_size=1024
        )
        self.assertIsNone(file_obj.folder)
    
    def test_user_file_file_type_choices(self):
        """Тест валидных типов файлов"""
        valid_types = ['image', 'video', 'audio', 'archive', 'text', 'document', 'code', 'other']
        for file_type in valid_types:
            file_obj = UserFile.objects.create(
                user=self.user,
                file=f'1/test.{file_type}',
                filename=f'test.{file_type}',
                file_type=file_type,
                file_size=1024
            )
            self.assertEqual(file_obj.file_type, file_type)
    
    def test_user_file_public_token_generation(self):
        """Тест генерации публичного токена"""
        file_obj = UserFile.objects.create(
            user=self.user,
            file='1/test.txt',
            filename='test.txt',
            file_type='text',
            file_size=1024,
            is_public=True
        )
        # Обновляем из БД чтобы получить сгенерированный токен
        file_obj.refresh_from_db()
        # Токен должен быть сгенерирован при сохранении
        self.assertIsNotNone(file_obj.public_token)
        self.assertEqual(len(file_obj.public_token), 32)  # uuid4().hex возвращает 32 символа

