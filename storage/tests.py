"""
Основной файл тестов для приложения storage

Все тесты организованы в подкаталогах:
- tests/unit/ - Unit-тесты
- tests/integration/ - Интеграционные тесты  
- tests/e2e/ - E2E-тесты

См. tests/README.md для подробной информации.
"""
from django.test import TestCase

# Импортируем тесты из подкаталогов для удобного запуска
from .tests.unit import test_models, test_helpers
from .tests.integration import test_folder_operations, test_file_operations
from .tests.e2e import test_user_workflow

# Create your tests here.
