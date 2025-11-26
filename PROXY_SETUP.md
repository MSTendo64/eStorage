# Настройка прокси-сервера на Ubuntu для загрузки файлов

## Вариант 1: Простой Python CORS Proxy (Рекомендуется)

### Установка зависимостей

```bash
sudo apt update
sudo apt install python3 python3-pip nginx
pip3 install flask flask-cors requests
```

### Создание прокси-сервера

Создайте файл `/opt/cors-proxy/app.py`:

```python
#!/usr/bin/env python3
from flask import Flask, request, Response, stream_with_context
from flask_cors import CORS
import requests
import urllib.parse

app = Flask(__name__)
CORS(app)  # Разрешаем CORS для всех доменов

@app.route('/proxy')
def proxy():
    """
    Прокси для загрузки файлов
    Использование: /proxy?url=https://example.com/file.jpg
    """
    url = request.args.get('url')
    if not url:
        return {'error': 'URL parameter is required'}, 400
    
    try:
        # Декодируем URL
        url = urllib.parse.unquote(url)
        
        # Заголовки для запроса
        headers = {
            'User-Agent': request.headers.get('User-Agent', 'Mozilla/5.0')
        }
        
        # Делаем запрос с потоковой передачей
        req = requests.get(url, headers=headers, stream=True, timeout=600, allow_redirects=True)
        req.raise_for_status()
        
        # Возвращаем потоковый ответ
        def generate():
            for chunk in req.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        
        response_headers = {
            'Content-Type': req.headers.get('Content-Type', 'application/octet-stream'),
            'Content-Length': req.headers.get('Content-Length', ''),
            'Content-Disposition': req.headers.get('Content-Disposition', ''),
        }
        
        return Response(
            stream_with_context(generate()),
            status=req.status_code,
            headers=response_headers
        )
    except Exception as e:
        return {'error': str(e)}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### Создание systemd сервиса

Создайте файл `/etc/systemd/system/cors-proxy.service`:

```ini
[Unit]
Description=CORS Proxy Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/cors-proxy
ExecStart=/usr/bin/python3 /opt/cors-proxy/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Настройка Nginx как reverse proxy

Создайте файл `/etc/nginx/sites-available/cors-proxy`:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Замените на ваш домен или IP

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Для больших файлов
        proxy_buffering off;
        proxy_request_buffering off;
        client_max_body_size 0;
    }
}
```

### Активация и запуск

```bash
# Создайте директорию
sudo mkdir -p /opt/cors-proxy
sudo chown www-data:www-data /opt/cors-proxy

# Скопируйте app.py в /opt/cors-proxy/

# Активируйте Nginx конфигурацию
sudo ln -s /etc/nginx/sites-available/cors-proxy /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Запустите прокси-сервис
sudo systemctl enable cors-proxy
sudo systemctl start cors-proxy

# Проверьте статус
sudo systemctl status cors-proxy
```

### Использование в системе

В настройках системы (Панель управления → Настройки) укажите:
```
http://your-domain.com/proxy?url=
```
или
```
http://your-server-ip/proxy?url=
```

---

## Вариант 2: Nginx как прямой прокси (Более простой)

### Установка Nginx

```bash
sudo apt update
sudo apt install nginx
```

### Настройка Nginx

Создайте файл `/etc/nginx/sites-available/file-proxy`:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Замените на ваш домен или IP

    # Увеличиваем таймауты для больших файлов
    proxy_connect_timeout 600s;
    proxy_send_timeout 600s;
    proxy_read_timeout 600s;
    send_timeout 600s;
    client_max_body_size 0;

    location /proxy {
        # Извлекаем URL из параметра
        set $target_url '';
        access_by_lua_block {
            local args = ngx.req.get_uri_args()
            if args.url then
                ngx.var.target_url = args.url
            else
                ngx.status = 400
                ngx.say('URL parameter is required')
                ngx.exit(400)
            end
        }

        # Проксируем запрос
        proxy_pass $target_url;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # Отключаем буферизацию для потоковой передачи
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

**Примечание**: Для этого варианта нужен Nginx с модулем Lua. Альтернатива - использовать Python прокси из Варианта 1.

---

## Вариант 3: Простой Node.js прокси (Альтернатива)

### Установка Node.js

```bash
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
```

### Создание прокси-сервера

Создайте файл `/opt/cors-proxy/server.js`:

```javascript
const http = require('http');
const https = require('https');
const url = require('url');

const PORT = 5000;

const server = http.createServer((req, res) => {
    const parsedUrl = url.parse(req.url, true);
    const targetUrl = parsedUrl.query.url;

    if (!targetUrl) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'URL parameter is required' }));
        return;
    }

    const targetParsed = url.parse(targetUrl);
    const protocol = targetParsed.protocol === 'https:' ? https : http;

    const options = {
        hostname: targetParsed.hostname,
        port: targetParsed.port || (targetParsed.protocol === 'https:' ? 443 : 80),
        path: targetParsed.path,
        method: 'GET',
        headers: {
            'User-Agent': req.headers['user-agent'] || 'Mozilla/5.0'
        }
    };

    const proxyReq = protocol.request(options, (proxyRes) => {
        res.writeHead(proxyRes.statusCode, {
            'Content-Type': proxyRes.headers['content-type'] || 'application/octet-stream',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        });

        proxyRes.pipe(res);
    });

    proxyReq.on('error', (err) => {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
    });

    req.pipe(proxyReq);
});

server.listen(PORT, '0.0.0.0', () => {
    console.log(`Proxy server running on port ${PORT}`);
});
```

### Создание systemd сервиса

Создайте файл `/etc/systemd/system/cors-proxy.service`:

```ini
[Unit]
Description=CORS Proxy Server (Node.js)
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/cors-proxy
ExecStart=/usr/bin/node /opt/cors-proxy/server.js
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## Настройка в системе eStorage

После настройки прокси-сервера:

1. Откройте **Панель управления → Настройки**
2. В поле **"Прокси для загрузки файлов"** укажите:
   - Для Python/Node.js прокси: `http://your-domain.com/proxy?url=`
   - Или: `http://your-server-ip/proxy?url=`

3. Сохраните настройки

Теперь при загрузке файлов по ссылке система будет использовать ваш прокси-сервер.

---

## Безопасность (Рекомендуется)

### Ограничение доступа по IP

В Nginx конфигурации добавьте:

```nginx
location /proxy {
    # Разрешаем только определенные IP
    allow 192.168.1.0/24;  # Ваша локальная сеть
    allow YOUR_PUBLIC_IP;   # IP вашего сервера eStorage
    deny all;
    
    # ... остальная конфигурация
}
```

### Использование HTTPS

Настройте SSL сертификат (Let's Encrypt):

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## Тестирование

Проверьте работу прокси:

```bash
curl "http://your-domain.com/proxy?url=https://example.com/image.jpg"
```

Если все работает, вы получите содержимое файла.

