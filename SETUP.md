# Руководство по развертыванию eStorage

Это руководство поможет вам развернуть проект eStorage с нуля на локальной машине или сервере.

## Содержание

1. [Системные требования](#системные-требования)
2. [Быстрый старт](#быстрый-старт)
3. [Подробная установка](#подробная-установка)
4. [Настройка окружения](#настройка-окружения)
5. [Настройка базы данных](#настройка-базы-данных)
6. [Запуск проекта](#запуск-проекта)
7. [Опциональные настройки](#опциональные-настройки)
8. [Запуск тестов](#запуск-тестов)
9. [Развертывание в production](#развертывание-в-production)
10. [Решение проблем](#решение-проблем)

---

## Системные требования

### Обязательные требования

- **Python**: 3.8 или выше
- **pip**: Последняя версия
- **Git**: Для клонирования репозитория

### Опциональные зависимости

- **PostgreSQL**: 12+ (рекомендуется для production)
- **Redis**: 6+ (для кэширования)
- **Nginx**: Для production развертывания
- **FFmpeg**: Для обработки видео (если планируется работа с видео)

### Проверка версий

```bash
# Проверка Python
python --version
# Должно быть: Python 3.8.x или выше

# Проверка pip
pip --version

# Проверка Git
git --version
```

---

## Быстрый старт

Если вы хотите быстро запустить проект для разработки:

```bash
# 1. Клонируйте репозиторий
git clone <repository-url>
cd eStorage

# 2. Создайте виртуальное окружение
python -m venv venv

# 3. Активируйте виртуальное окружение
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 4. Установите зависимости
pip install -r requirements.txt

# 5. Создайте файл .env (см. раздел "Настройка окружения")

# 6. Примените миграции
python manage.py migrate

# 7. Создайте суперпользователя
python manage.py createsuperuser

# 8. Соберите статику
python manage.py collectstatic --noinput

# 9. Запустите сервер разработки
python manage.py runserver
```

Проект будет доступен по адресу: `http://127.0.0.1:8000`

---

## Подробная установка

### Шаг 1: Клонирование репозитория

```bash
git clone <repository-url>
cd eStorage
```

### Шаг 2: Создание виртуального окружения

Виртуальное окружение изолирует зависимости проекта от системных пакетов Python.

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

После активации в начале строки терминала должно появиться `(venv)`.

### Шаг 3: Установка зависимостей

```bash
# Обновите pip до последней версии
pip install --upgrade pip

# Установите все зависимости из requirements.txt
pip install -r requirements.txt
```

**Примечание:** Если у вас возникают проблемы с установкой некоторых пакетов (например, `psycopg2-binary` на Windows), вы можете временно закомментировать их в `requirements.txt` для локальной разработки.

### Шаг 4: Установка дополнительных инструментов (опционально)

**FFmpeg** (для обработки видео):
- **Windows**: Скачайте с [ffmpeg.org](https://ffmpeg.org/download.html) и добавьте в PATH
- **Linux**: `sudo apt-get install ffmpeg` (Ubuntu/Debian) или `sudo yum install ffmpeg` (CentOS/RHEL)
- **Mac**: `brew install ffmpeg`

**Redis** (для кэширования):
- **Windows**: Используйте WSL или установите через Docker
- **Linux**: `sudo apt-get install redis-server` (Ubuntu/Debian)
- **Mac**: `brew install redis`

---

## Настройка окружения

### Создание файла .env

Создайте файл `.env` в корне проекта на основе `example.env`:

```bash
# Windows
copy example.env .env

# Linux/Mac
cp example.env .env
```

### Настройка переменных окружения

Откройте файл `.env` и настройте следующие переменные:

```env
# Секретный ключ Django (обязательно!)
# Сгенерируйте новый ключ: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY=your_secret_key_here

# Режим отладки (True для разработки, False для production)
DEBUG=True

# Разрешенные хосты (через запятую)
ALLOWED_HOSTS=127.0.0.1,localhost

# Настройки базы данных (если используете PostgreSQL)
# Для SQLite оставьте пустым
DB_ENGINE=django.db.backends.postgresql
DB_NAME=estorage
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432

# Настройки Redis (если используете)
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=1

# Настройки безопасности (для production)
SECURE_SSL_REDIRECT=False  # True для production с HTTPS
SESSION_COOKIE_SECURE=False  # True для production с HTTPS
CSRF_COOKIE_SECURE=False  # True для production с HTTPS
```

### Генерация SECRET_KEY

Для генерации безопасного секретного ключа выполните:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Скопируйте сгенерированный ключ в файл `.env`.

**⚠️ ВАЖНО:** Никогда не коммитьте файл `.env` в репозиторий! Он должен быть в `.gitignore`.

---

## Настройка базы данных

### Вариант 1: SQLite (по умолчанию, для разработки)

SQLite не требует дополнительной настройки. Просто убедитесь, что в `estorage/settings.py` используется конфигурация по умолчанию:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

### Вариант 2: PostgreSQL (рекомендуется для production)

1. **Установите PostgreSQL** (если еще не установлен)

2. **Создайте базу данных и пользователя:**

```bash
# Войдите в PostgreSQL
sudo -u postgres psql

# Создайте базу данных
CREATE DATABASE estorage;

# Создайте пользователя
CREATE USER estorage_user WITH PASSWORD 'your_secure_password';

# Выдайте права
GRANT ALL PRIVILEGES ON DATABASE estorage TO estorage_user;
ALTER USER estorage_user CREATEDB;

# Выйдите
\q
```

3. **Обновите настройки в `estorage/settings.py`:**

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'estorage'),
        'USER': os.getenv('DB_USER', 'estorage_user'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'your_secure_password'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}
```

Или используйте переменные окружения из `.env` файла.

---

## Запуск проекта

### Шаг 1: Применение миграций

Миграции создают структуру базы данных:

```bash
python manage.py migrate
```

### Шаг 2: Создание суперпользователя

Создайте администратора для доступа к админ-панели:

```bash
python manage.py createsuperuser
```

Введите:
- Username (имя пользователя)
- Email address (email)
- Password (пароль)

### Шаг 3: Сбор статических файлов

Соберите все статические файлы (CSS, JavaScript, изображения):

```bash
python manage.py collectstatic --noinput
```

### Шаг 4: Создание необходимых директорий

Убедитесь, что существуют необходимые директории:

```bash
# Windows
mkdir media static tmp

# Linux/Mac
mkdir -p media static tmp
```

### Шаг 5: Запуск сервера разработки

```bash
python manage.py runserver
```

Или с указанием хоста и порта:

```bash
python manage.py runserver 0.0.0.0:8000
```

Проект будет доступен по адресу: `http://127.0.0.1:8000`

### Шаг 6: Проверка работы

1. Откройте браузер и перейдите на `http://127.0.0.1:8000`
2. Зарегистрируйте нового пользователя или войдите как суперпользователь
3. Проверьте работу основных функций

---

## Опциональные настройки

### Настройка Redis для кэширования

1. **Установите и запустите Redis:**

```bash
# Linux
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Mac
brew services start redis
```

2. **Проверьте подключение:**

```bash
redis-cli ping
# Должно вернуть: PONG
```

3. **Настройки уже включены в `settings.py`** (если Redis запущен на localhost:6379)

### Настройка прокси для загрузки файлов

См. файл `PROXY_SETUP.md` для подробных инструкций по настройке прокси-сервера.

### Настройка Nginx для production

См. файл `NGINX_TIMEOUT_CONFIG.md` для конфигурации Nginx.

---

## Запуск тестов

Проект включает автоматические тесты (Unit, Integration, E2E).

### Установка зависимостей для тестов

```bash
pip install coverage selenium webdriver-manager
```

### Запуск всех тестов

```bash
# Все тесты
python manage.py test storage.tests

# Только Unit-тесты
python manage.py test storage.tests.unit

# Только Интеграционные тесты
python manage.py test storage.tests.integration

# Только E2E-тесты
python manage.py test storage.tests.e2e

# С подробным выводом
python manage.py test storage.tests --verbosity=2
```

### Проверка покрытия кода

```bash
# Установите coverage (если еще не установлен)
pip install coverage

# Запустите тесты с покрытием
coverage run --source='storage' manage.py test storage.tests

# Просмотр отчета
coverage report

# HTML отчет
coverage html
# Откройте htmlcov/index.html в браузере
```

Подробнее см. `storage/tests/README.md`.

---

## Развертывание в production

### Важные настройки для production

1. **Измените `DEBUG = False`** в `estorage/settings.py` или `.env`

2. **Настройте `ALLOWED_HOSTS`:**

```python
ALLOWED_HOSTS = ['your-domain.com', 'www.your-domain.com']
```

3. **Включите HTTPS настройки:**

```python
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

4. **Используйте PostgreSQL** вместо SQLite

5. **Настройте логирование:**

Создайте директорию для логов:
```bash
sudo mkdir -p /var/log/estorage
sudo chown www-data:www-data /var/log/estorage
```

6. **Используйте WSGI сервер:**

```bash
# Установите gunicorn
pip install gunicorn

# Запустите через gunicorn
gunicorn estorage.wsgi:application --bind 0.0.0.0:8000
```

7. **Настройте systemd service** (Linux):

Создайте файл `/etc/systemd/system/estorage.service`:

```ini
[Unit]
Description=eStorage Gunicorn daemon
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/eStorage
ExecStart=/path/to/venv/bin/gunicorn estorage.wsgi:application --bind 127.0.0.1:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Запустите сервис:
```bash
sudo systemctl daemon-reload
sudo systemctl start estorage
sudo systemctl enable estorage
```

8. **Настройте Nginx** как reverse proxy (см. `NGINX_TIMEOUT_CONFIG.md`)

### Резервное копирование

Регулярно создавайте резервные копии базы данных:

```bash
# PostgreSQL
pg_dump -U estorage_user estorage > backup_$(date +%Y%m%d).sql

# SQLite
cp db.sqlite3 backup_$(date +%Y%m%d).sqlite3
```

---

## Решение проблем

### Проблема: `ModuleNotFoundError: No module named 'django'`

**Решение:** Убедитесь, что виртуальное окружение активировано и зависимости установлены:
```bash
# Активируйте виртуальное окружение
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Переустановите зависимости
pip install -r requirements.txt
```

### Проблема: `django.db.utils.OperationalError: no such table`

**Решение:** Примените миграции:
```bash
python manage.py migrate
```

### Проблема: Ошибки при установке `psycopg2-binary`

**Решение:** 
- На Windows: Установите Visual C++ Build Tools
- Или временно закомментируйте `psycopg2-binary` в `requirements.txt` для разработки с SQLite

### Проблема: Статические файлы не загружаются

**Решение:**
```bash
# Соберите статику
python manage.py collectstatic --noinput

# Проверьте настройки STATIC_ROOT и STATIC_URL в settings.py
```

### Проблема: Ошибка подключения к Redis

**Решение:**
- Убедитесь, что Redis запущен: `redis-cli ping`
- Проверьте настройки в `settings.py`
- Для разработки можно временно использовать файловый кэш

### Проблема: `CSRF verification failed`

**Решение:**
- Добавьте домен в `CSRF_TRUSTED_ORIGINS` в `settings.py`
- Убедитесь, что используете правильный домен в `ALLOWED_HOSTS`

### Проблема: Медленная загрузка больших файлов

**Решение:**
- Проверьте настройки `MAX_FILE_SIZE` и `CHUNK_SIZE` в `settings.py`
- Убедитесь, что Nginx настроен правильно (см. `NGINX_TIMEOUT_CONFIG.md`)
- Используйте chunked upload для больших файлов

---

## Полезные команды

### Управление миграциями

```bash
# Создать миграции
python manage.py makemigrations

# Применить миграции
python manage.py migrate

# Откатить последнюю миграцию
python manage.py migrate app_name previous_migration_name
```

### Управление пользователями

```bash
# Создать суперпользователя
python manage.py createsuperuser

# Изменить пароль пользователя
python manage.py changepassword username
```

### Работа с статикой

```bash
# Собрать статические файлы
python manage.py collectstatic

# Очистить кэш статики
python manage.py collectstatic --clear
```

### Django shell

```bash
# Открыть интерактивную консоль Django
python manage.py shell
```

---

## Дополнительная документация

- **Тесты**: `storage/tests/README.md`
- **Настройка прокси**: `PROXY_SETUP.md`
- **Конфигурация Nginx**: `NGINX_TIMEOUT_CONFIG.md`
- **Основной README**: `README.md`

---

## Получение помощи

Если у вас возникли проблемы:

1. Проверьте раздел "Решение проблем" выше
2. Проверьте логи приложения
3. Убедитесь, что все зависимости установлены
4. Проверьте настройки в `settings.py` и `.env`

---

## Лицензия

[Укажите лицензию проекта]

---

**Удачной разработки! 🚀**

