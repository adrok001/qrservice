# Инструкция по развертыванию на Timeweb

## Домен
Проект развернут на: **https://replyq.ru**

## Переменные окружения для сервера

На сервере Timeweb необходимо установить следующие переменные окружения в файле `.env`:

```bash
# === ОБЯЗАТЕЛЬНЫЕ НАСТРОЙКИ ДЛЯ ПРОДАКШЕНА ===

# Site URL - используется для генерации QR-кодов и ссылок
SITE_URL=https://replyq.ru

# Google OAuth Redirect URI
GOOGLE_REDIRECT_URI=https://replyq.ru/integrations/google/callback/

# Безопасность
DEBUG=False
SECRET_KEY=your-secure-random-secret-key-here
ALLOWED_HOSTS=replyq.ru,www.replyq.ru

# === ОПЦИОНАЛЬНЫЕ НАСТРОЙКИ ===

# Google Business Profile API
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Redis (если используется)
REDIS_URL=redis://localhost:6379/1

# Celery (если используется)
CELERY_BROKER_URL=your_broker_url
CELERY_RESULT_BACKEND=your_result_backend
```

## Локальная разработка vs Продакшен

### Локально (.env на вашей машине)
```bash
SITE_URL=http://localhost:8000
GOOGLE_REDIRECT_URI=http://localhost:8000/integrations/google/callback/
DEBUG=True
```

### На сервере Timeweb (.env на сервере)
```bash
SITE_URL=https://replyq.ru
GOOGLE_REDIRECT_URI=https://replyq.ru/integrations/google/callback/
DEBUG=False
ALLOWED_HOSTS=replyq.ru,www.replyq.ru
```

## Как это работает

1. **QR-коды автоматически используют правильный домен**
   - Локально: QR-коды ведут на `http://localhost:8000/{code}`
   - На сервере: QR-коды ведут на `https://replyq.ru/{code}`

2. **Без изменения кода**
   - Код автоматически использует `SITE_URL` из переменных окружения
   - См. `/apps/dashboard/services/qr.py:15`

3. **Google OAuth тоже настроен**
   - Используйте правильный `GOOGLE_REDIRECT_URI` для каждого окружения

## Проверка после развертывания

После установки переменных окружения на сервере:

1. Создайте тестовый QR-код
2. Проверьте, что ссылка в QR-коде начинается с `https://replyq.ru/`
3. Отсканируйте QR-код и убедитесь, что он ведет на правильный URL

## Обновление существующих QR-кодов

Если у вас уже есть QR-коды со ссылками на localhost, вам нужно:

1. Установить переменную `SITE_URL=https://replyq.ru` на сервере
2. Перегенерировать все QR-коды (создать новые)

Старые QR-коды с localhost работать не будут, так как URL захардкожен в изображении.

## Команды на сервере

```bash
# Перейти в директорию проекта
cd /path/to/qrservice

# Активировать виртуальное окружение
source venv/bin/activate

# Применить миграции
python manage.py migrate

# Собрать статику
python manage.py collectstatic --noinput

# Перезапустить сервер (зависит от настройки Timeweb)
# Например, если используется systemd:
sudo systemctl restart qrservice
```

## CSRF и безопасность

Не забудьте также добавить в настройки на сервере:

```python
# В qrservice/settings.py или через переменные окружения
CSRF_TRUSTED_ORIGINS = ['https://replyq.ru', 'https://www.replyq.ru']
SECURE_SSL_REDIRECT = True  # Если используется HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```
