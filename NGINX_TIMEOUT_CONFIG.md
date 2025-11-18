# Настройка таймаутов для nginx

## Полный конфиг

Полный конфигурационный файл nginx находится в `nginx.conf` в корне проекта.

## Быстрая установка

1. Скопируйте конфиг:
```bash
sudo cp nginx.conf /etc/nginx/sites-available/estorage
```

2. Создайте симлинк:
```bash
sudo ln -s /etc/nginx/sites-available/estorage /etc/nginx/sites-enabled/
```

3. Проверьте конфигурацию:
```bash
sudo nginx -t
```

4. Перезапустите nginx:
```bash
sudo systemctl restart nginx
```

## Важные настройки для скачивания больших файлов

Если вы хотите добавить только настройки для скачивания в существующий конфиг, используйте следующий блок:

```nginx
server {
    # ... другие настройки ...
    
    location /storage/download/ {
        proxy_pass http://127.0.0.1:8000;  # или ваш WSGI сервер
        proxy_read_timeout 3600s;  # 1 час для больших файлов
        proxy_send_timeout 3600s;
        proxy_connect_timeout 60s;
        
        # Отключаем буферизацию для потоковой передачи
        proxy_buffering off;
        proxy_request_buffering off;
        
        # Увеличиваем размер буферов
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
        
        # Поддержка Range-запросов
        proxy_set_header Range $http_range;
        proxy_set_header If-Range $http_if_range;
        
        # Заголовки для предотвращения кэширования
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Для Apache

Если вы используете Apache, добавьте в конфигурацию:

```apache
<Location /storage/download/>
    ProxyPass http://127.0.0.1:8000/
    ProxyPassReverse http://127.0.0.1:8000/
    
    # Увеличиваем таймауты
    ProxyTimeout 3600
    
    # Отключаем буферизацию
    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
</Location>
```

## Для Gunicorn/uWSGI

Если вы используете Gunicorn, запустите с увеличенными таймаутами:

```bash
gunicorn estorage.wsgi:application \
    --bind 127.0.0.1:8000 \
    --timeout 3600 \
    --workers 4
```

Для uWSGI:

```ini
[uwsgi]
http-timeout = 3600
socket-timeout = 3600
```

