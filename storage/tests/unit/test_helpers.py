"""
Unit-тесты для вспомогательных функций storage/helpers.py
"""
from django.test import TestCase
from django.contrib.auth.models import User
from storage.helpers import ensure_user_folder_exists, generate_unique_filename
import os
import tempfile
import shutil


class HelpersTest(TestCase):
    """Тесты для вспомогательных функций"""
    
    def setUp(self):
        """Настройка тестового окружения"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        # Используем временную директорию для тестов
        self.test_media_root = tempfile.mkdtemp()
        # Сохраняем оригинальное значение MEDIA_ROOT
        from django.conf import settings
        self.original_media_root = settings.MEDIA_ROOT
        settings.MEDIA_ROOT = self.test_media_root
    
    def tearDown(self):
        """Очистка после тестов"""
        # Восстанавливаем оригинальное значение MEDIA_ROOT
        from django.conf import settings
        settings.MEDIA_ROOT = self.original_media_root
        # Удаляем временную директорию
        if os.path.exists(self.test_media_root):
            shutil.rmtree(self.test_media_root)
    
    def test_ensure_user_folder_exists(self):
        """Тест создания папки пользователя"""
        user_folder = ensure_user_folder_exists(self.user.id)
        expected_path = os.path.join(self.test_media_root, str(self.user.id))
        self.assertEqual(user_folder, expected_path)
        self.assertTrue(os.path.exists(user_folder))
        self.assertTrue(os.path.isdir(user_folder))
    
    def test_ensure_user_folder_exists_already_exists(self):
        """Тест что функция не создает дубликаты папок"""
        user_folder1 = ensure_user_folder_exists(self.user.id)
        user_folder2 = ensure_user_folder_exists(self.user.id)
        self.assertEqual(user_folder1, user_folder2)
        # Проверяем что папка существует только один раз
        expected_path = os.path.join(self.test_media_root, str(self.user.id))
        self.assertEqual(user_folder1, expected_path)
    
    def test_generate_unique_filename_no_conflict(self):
        """Тест генерации уникального имени файла без конфликтов"""
        user_folder = ensure_user_folder_exists(self.user.id)
        filename = generate_unique_filename(user_folder, 'test.txt')
        self.assertEqual(filename, 'test.txt')
    
    def test_generate_unique_filename_with_conflict(self):
        """Тест генерации уникального имени файла с конфликтом"""
        user_folder = ensure_user_folder_exists(self.user.id)
        # Создаем файл с именем test.txt
        existing_file = os.path.join(user_folder, 'test.txt')
        with open(existing_file, 'w') as f:
            f.write('existing')
        
        # Генерируем уникальное имя
        filename = generate_unique_filename(user_folder, 'test.txt')
        self.assertEqual(filename, 'test_1.txt')
        
        # Проверяем что файл с новым именем не существует
        new_file = os.path.join(user_folder, filename)
        self.assertFalse(os.path.exists(new_file))
    
    def test_generate_unique_filename_multiple_conflicts(self):
        """Тест генерации уникального имени при множественных конфликтах"""
        user_folder = ensure_user_folder_exists(self.user.id)
        # Создаем несколько файлов
        for i in range(3):
            file_path = os.path.join(user_folder, f'test_{i}.txt' if i > 0 else 'test.txt')
            with open(file_path, 'w') as f:
                f.write(f'file {i}')
        
        # Генерируем уникальное имя
        filename = generate_unique_filename(user_folder, 'test.txt')
        self.assertEqual(filename, 'test_3.txt')

