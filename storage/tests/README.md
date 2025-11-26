# Тесты для приложения Storage

Этот каталог содержит автоматические тесты для приложения storage, разделенные на три категории:

## Структура тестов

```
tests/
├── unit/              # Unit-тесты: Проверяют отдельные функции/модули
│   ├── test_models.py
│   └── test_helpers.py
├── integration/       # Интеграционные тесты: Проверяют взаимодействие между компонентами
│   ├── test_folder_operations.py
│   └── test_file_operations.py
└── e2e/              # E2E-тесты: Имитируют действия пользователя в готовом приложении
    └── test_user_workflow.py
```

## Типы тестов

### Unit-тесты
Проверяют отдельные функции и модули изолированно, без зависимостей от других компонентов.

**Примеры:**
- Тесты моделей (создание, валидация, методы)
- Тесты вспомогательных функций
- Тесты утилит

**Запуск:**
```bash
python manage.py test storage.tests.unit
```

### Интеграционные тесты
Проверяют взаимодействие между компонентами системы (модели, views, API).

**Примеры:**
- Тесты операций с папками через API
- Тесты операций с файлами через API
- Тесты взаимодействия моделей и views

**Запуск:**
```bash
python manage.py test storage.tests.integration
```

### E2E-тесты
Имитируют действия пользователя в готовом приложении, проверяя полные сценарии использования.

**Примеры:**
- Полный цикл работы с файлами (создание, переименование, удаление)
- Работа с папками через UI
- Авторизация и навигация

**Запуск:**
```bash
python manage.py test storage.tests.e2e
```

## Запуск всех тестов

```bash
# Запустить все тесты
python manage.py test storage.tests

# Запустить с подробным выводом
python manage.py test storage.tests --verbosity=2

# Запустить конкретный тест
python manage.py test storage.tests.unit.test_models.FolderModelTest

# Запустить с покрытием кода (требует coverage)
coverage run --source='storage' manage.py test storage.tests
coverage report
coverage html  # Создаст HTML отчет в htmlcov/
```

## Настройка для E2E тестов с Selenium

Для полноценных E2E тестов с использованием Selenium:

1. Установите Selenium:
```bash
pip install selenium
```

2. Установите драйвер браузера (например, ChromeDriver):
   - Скачайте с https://chromedriver.chromium.org/
   - Или используйте `webdriver-manager`: `pip install webdriver-manager`

3. Раскомментируйте код в `test_user_workflow.py`

4. Запустите сервер разработки:
```bash
python manage.py runserver
```

5. Запустите E2E тесты:
```bash
python manage.py test storage.tests.e2e.SeleniumE2ETest
```

## Покрытие кода

Для проверки покрытия кода тестами:

```bash
pip install coverage

# Запуск тестов с покрытием
coverage run --source='storage' manage.py test storage.tests

# Просмотр отчета
coverage report

# HTML отчет
coverage html
# Откройте htmlcov/index.html в браузере
```

## Написание новых тестов

### Структура Unit-теста:
```python
from django.test import TestCase

class MyModelTest(TestCase):
    def setUp(self):
        # Настройка тестовых данных
        pass
    
    def test_something(self):
        # Тест конкретной функциональности
        self.assertEqual(expected, actual)
```

### Структура Интеграционного теста:
```python
from django.test import TestCase, Client
from django.urls import reverse

class MyIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()
        # Настройка пользователя и данных
    
    def test_api_endpoint(self):
        url = reverse('my_view')
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
```

### Структура E2E теста:
```python
from django.test import TestCase, Client

class MyE2ETest(TestCase):
    def test_complete_workflow(self):
        # Симуляция полного сценария пользователя
        # 1. Действие 1
        # 2. Действие 2
        # 3. Проверка результата
        pass
```

## Best Practices

1. **Изоляция**: Каждый тест должен быть независимым
2. **Именование**: Используйте понятные имена тестов
3. **Очистка**: Используйте `setUp` и `tearDown` для подготовки и очистки
4. **Покрытие**: Стремитесь к покрытию критически важных функций
5. **Скорость**: Unit-тесты должны быть быстрыми, E2E могут быть медленнее
6. **Документация**: Комментируйте сложные тесты

## CI/CD Integration

Для автоматического запуска тестов в CI/CD:

```yaml
# Пример для GitHub Actions
- name: Run tests
  run: |
    python manage.py test storage.tests
    coverage run --source='storage' manage.py test storage.tests
    coverage report --fail-under=80
```

## Полезные ссылки

- [Django Testing Documentation](https://docs.djangoproject.com/en/stable/topics/testing/)
- [Selenium Documentation](https://www.selenium.dev/documentation/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)

