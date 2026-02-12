# Развертывание Poll Kiosk в Docker

## Быстрый старт

### 1. Подготовка на сервере

```bash
# Клонируйте или загрузите проект на сервер
mkdir poll-kiosk
cd poll-kiosk

# Загрузите все файлы проекта:
# - Dockerfile
# - docker-compose.yml
# - requirements.txt
# - app.py
# - database.py
# - config.json
# - templates/index.html
# - templates/admin.html
```

### 2. Создание структуры папок

```bash
# Создайте папку для постоянного хранения данных
mkdir data

# Структура должна быть:
poll-kiosk/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── app.py
├── database.py
├── config.json
├── data/                  # Для SQLite базы
└── templates/
    ├── index.html
    └── admin.html
```

### 3. Настройка конфига

Отредактируйте `config.json`:

```json
{
  "admin_username": "admin",
  "admin_password": "ваш_надёжный_пароль",
  "current_poll_id": null
}
```

### 4. Сборка и запуск

```bash
# Сборка образа
docker-compose build

# Запуск в фоновом режиме
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f
```

## Доступ к приложению

После запуска приложение будет доступно:

- **Публичный экран**: `http://ВАШ_IP:14542/`
- **Бэк-офис**: `http://ВАШ_IP:14542/admin`
  - Логин: `admin`
  - Пароль: из `config.json`

## Настройка файрвола (если нужно)

### Ubuntu/Debian (ufw)

```bash
# Разрешить порт 14542
sudo ufw allow 14542/tcp

# Проверить статус
sudo ufw status
```

### CentOS/RHEL (firewalld)

```bash
# Разрешить порт 14542
sudo firewall-cmd --permanent --add-port=14542/tcp
sudo firewall-cmd --reload

# Проверить
sudo firewall-cmd --list-ports
```

## Управление контейнером

```bash
# Остановить
docker-compose down

# Перезапустить
docker-compose restart

# Обновить после изменений
docker-compose down
docker-compose build
docker-compose up -d

# Посмотреть логи
docker-compose logs -f poll-kiosk

# Войти в контейнер
docker-compose exec poll-kiosk /bin/bash
```

## Обновление приложения

```bash
# 1. Остановить контейнер
docker-compose down

# 2. Обновить файлы (app.py, templates и т.д.)

# 3. Пересобрать образ
docker-compose build

# 4. Запустить
docker-compose up -d
```

## Бэкап данных

База данных хранится в `./data/polls.db`:

```bash
# Создать бэкап
cp data/polls.db data/polls.db.backup-$(date +%Y%m%d)

# Или скопировать на другой сервер
scp data/polls.db user@backup-server:/backups/

# Автоматический бэкап (добавить в crontab)
0 2 * * * cp /path/to/poll-kiosk/data/polls.db /path/to/backups/polls.db.$(date +\%Y\%m\%d)
```

## Восстановление из бэкапа

```bash
# Остановить контейнер
docker-compose down

# Восстановить базу
cp data/polls.db.backup-20260212 data/polls.db

# Запустить
docker-compose up -d
```

## Мониторинг

### Проверка здоровья

```bash
# Проверить доступность
curl http://localhost:14542/

# Проверить из вне
curl http://ВАШ_IP:14542/
```

### Логирование

```bash
# Живые логи
docker-compose logs -f

# Последние 100 строк
docker-compose logs --tail=100

# Логи только для poll-kiosk
docker-compose logs poll-kiosk
```

## Производительность

### Ресурсы контейнера

Добавьте в `docker-compose.yml` под `poll-kiosk`:

```yaml
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

## Безопасность

### 1. Изменить пароль админа

Обязательно измените в `config.json`:

```json
{
  "admin_username": "admin",
  "admin_password": "очень_сложный_пароль_123!@#"
}
```

### 2. HTTPS (рекомендуется)

Используйте Nginx reverse proxy с Let's Encrypt:

```bash
# Установить Nginx
sudo apt install nginx certbot python3-certbot-nginx

# Создать конфиг Nginx
sudo nano /etc/nginx/sites-available/poll-kiosk
```

Конфигурация Nginx:

```nginx
server {
    listen 80;
    server_name ваш-домен.ru;

    location / {
        proxy_pass http://localhost:14542;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Активировать конфиг
sudo ln -s /etc/nginx/sites-available/poll-kiosk /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Получить SSL сертификат
sudo certbot --nginx -d ваш-домен.ru
```

### 3. Ограничить доступ к админке по IP

В `docker-compose.yml` можно добавить переменную окружения:

```yaml
    environment:
      - ADMIN_ALLOWED_IPS=192.168.1.0/24,10.0.0.0/8
```

## Автозапуск при перезагрузке

Docker Compose автоматически настроит автозапуск благодаря `restart: unless-stopped`.

Проверить:

```bash
# Перезагрузить сервер
sudo reboot

# После перезагрузки проверить
docker-compose ps
```

## Масштабирование

Для нескольких инстансов используйте Nginx load balancer:

```yaml
# docker-compose.yml
services:
  poll-kiosk-1:
    build: .
    ports:
      - "15001:5000"
    
  poll-kiosk-2:
    build: .
    ports:
      - "15002:5000"
```

## Troubleshooting

### Контейнер не запускается

```bash
# Проверить логи
docker-compose logs

# Проверить конфиг
docker-compose config

# Пересобрать без кэша
docker-compose build --no-cache
```

### Порт занят

```bash
# Найти процесс на порту 14542
sudo lsof -i :14542

# Или изменить порт в docker-compose.yml
ports:
  - "14543:5000"  # Используйте другой порт
```

### База данных заблокирована

```bash
# Проверить права
ls -la data/

# Исправить права
sudo chown -R 1000:1000 data/
```

## Проверка после установки

```bash
# 1. Контейнер запущен
docker-compose ps

# 2. Приложение отвечает
curl http://localhost:14542/

# 3. Извне доступно
curl http://ВАШ_IP:14542/

# 4. Админка работает
curl -u admin:пароль http://localhost:14542/admin
```

Готово! Приложение доступно на `http://ВАШ_IP:14542/`
