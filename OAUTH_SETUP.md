# OAuth Setup Guide (Google + Yandex)

Полная инструкция по настройке OAuth входа через Google и Яндекс для ReplyQ.

---

## ЧТО СДЕЛАНО

✅ Установлен django-allauth
✅ Настроены settings.py и urls.py
✅ Созданы OAuth кнопки на страницах входа/регистрации
✅ Реализована логика автосоздания компании для OAuth пользователей
✅ Добавлен welcome banner для новых пользователей
✅ Создан management command для настройки Social Apps

---

## ШАГ 1: Установка зависимостей (ЛОКАЛЬНО)

```bash
cd /home/konstantin/qrservice

# Установить python3-venv если нет
sudo apt install python3.12-venv

# Переустановить venv
python3 -m venv venv --clear

# Активировать
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt
```

---

## ШАГ 2: Создание OAuth приложений

### Google Cloud Console

1. Перейдите: https://console.cloud.google.com/
2. Создайте проект или выберите существующий
3. **APIs & Services** → **Credentials**
4. **Create Credentials** → **OAuth 2.0 Client ID**
5. **Application type**: Web application
6. **Name**: ReplyQ OAuth
7. **Authorized redirect URIs**:
   - `http://localhost:8000/accounts/google/login/callback/`
   - `https://replyq.ru/accounts/google/login/callback/`
8. Сохраните **Client ID** и **Client Secret**

### Yandex OAuth

1. Перейдите: https://oauth.yandex.ru/
2. **Зарегистрировать новое приложение**
3. **Название**: ReplyQ
4. **Права доступа**: Доступ к email адресу
5. **Callback URL** (Redirect URI):
   - `http://localhost:8000/accounts/yandex/login/callback/`
   - `https://replyq.ru/accounts/yandex/login/callback/`
6. Сохраните **ID приложения** и **Пароль приложения**

---

## ШАГ 3: Настройка .env (ЛОКАЛЬНО)

Отредактируйте `/home/konstantin/qrservice/.env`:

```bash
# OAuth Authentication
GOOGLE_OAUTH_CLIENT_ID=ваш_google_client_id
GOOGLE_OAUTH_CLIENT_SECRET=ваш_google_secret
YANDEX_OAUTH_CLIENT_ID=ваш_yandex_id
YANDEX_OAUTH_CLIENT_SECRET=ваш_yandex_пароль
```

---

## ШАГ 4: Миграции и настройка Social Apps (ЛОКАЛЬНО)

```bash
source venv/bin/activate

# Применить миграции
python manage.py migrate

# Настроить Social Apps
python manage.py setup_oauth

# Проверка
python manage.py check

# Запустить сервер
python manage.py runserver
```

---

## ШАГ 5: Тестирование локально

1. Откройте http://localhost:8000/accounts/login/
2. Должны быть видны кнопки "Войти через Google" и "Войти через Яндекс"
3. Нажмите "Войти через Google"
4. Разрешите доступ Google
5. Должен произойти вход и создание компании
6. Проверьте welcome banner

Повторите с Яндекс.

---

## ШАГ 6: Коммит изменений

```bash
git status
git add .
git commit -m "$(cat <<'EOF'
Добавить OAuth вход через Google и Яндекс

- Установлен django-allauth==0.61.1
- Добавлены OAuth кнопки на login/register страницах
- Автосоздание компании для OAuth пользователей
- Гибридная логика связывания аккаунтов
- Welcome banner для новых пользователей
- Management command setup_oauth для настройки
- Стили перенесены из inline в style.css

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"

git push origin main
```

---

## ШАГ 7: Деплой на сервер Timeweb

### 7.1. Подключение к серверу

```bash
ssh root@46.149.66.180
```

### 7.2. Получение обновлений

```bash
cd /var/www/replyq
git pull origin main
```

### 7.3. Установка зависимостей

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 7.4. Настройка .env на сервере

```bash
nano .env
```

Добавьте (с вашими credentials):

```bash
# OAuth Authentication
GOOGLE_OAUTH_CLIENT_ID=ваш_google_client_id
GOOGLE_OAUTH_CLIENT_SECRET=ваш_google_secret
YANDEX_OAUTH_CLIENT_ID=ваш_yandex_id
YANDEX_OAUTH_CLIENT_SECRET=ваш_yandex_пароль
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

### 7.5. Миграции и настройка

```bash
python manage.py migrate
python manage.py setup_oauth
python manage.py collectstatic --noinput
python manage.py check
```

### 7.6. Перезапуск Gunicorn

```bash
sudo pkill -HUP gunicorn
ps aux | grep gunicorn
```

---

## ШАГ 8: Проверка на продакшене

1. Откройте https://replyq.ru/accounts/login/
2. Hard refresh: `Ctrl+Shift+R`
3. Проверьте кнопки OAuth
4. Попробуйте войти через Google
5. Проверьте создание компании и welcome banner

---

## АРХИТЕКТУРА РЕШЕНИЯ

### Файлы которые были созданы/изменены:

```
requirements.txt                                 # + django-allauth
qrservice/settings.py                            # + allauth настройки
qrservice/urls.py                                # + allauth URLs
.env                                             # + OAuth credentials
static/css/style.css                             # + OAuth стили
templates/accounts/login.html                    # + OAuth кнопки
templates/accounts/register.html                 # + OAuth кнопки
apps/accounts/management/commands/setup_oauth.py # NEW
apps/accounts/services/oauth.py                  # NEW
apps/accounts/signals.py                         # NEW
apps/accounts/adapters.py                        # NEW
apps/accounts/apps.py                            # + ready() method
```

### Логика работы:

1. **Новый пользователь через OAuth:**
   - Кликает "Войти через Google/Яндекс"
   - OAuth провайдер проверяет и возвращает email
   - Django создаёт нового пользователя
   - Signal `user_signed_up` вызывается
   - `handle_oauth_signup()` создаёт компанию и Member
   - Устанавливаются флаги `show_welcome` в session
   - Redirect на `/dashboard/company_settings/`

2. **Существующий OAuth пользователь:**
   - Вход происходит нормально
   - Redirect на `/dashboard/`

3. **Email уже существует (автосвязывание):**
   - Если у пользователя НЕТ пароля → автоматически связать OAuth
   - Если у пользователя ЕСТЬ пароль → (TODO: страница связывания)

---

## БЕЗОПАСНОСТЬ

✅ CSRF protection включен
✅ OAuth credentials в .env, не в коде
✅ Email verification через OAuth провайдера
✅ Гибридная логика связывания аккаунтов
✅ Автоэкранирование XSS в Django templates

---

## TROUBLESHOOTING

### Кнопки OAuth не видны

```bash
# Hard refresh
Ctrl+Shift+R

# Проверить статику
python manage.py collectstatic --noinput

# Проверить что CSS загрузился
View Page Source → Ctrl+F "oauth-button"
```

### Ошибка при клике на кнопку OAuth

```bash
# Проверить что Social Apps настроены
python manage.py shell
>>> from allauth.socialaccount.models import SocialApp
>>> SocialApp.objects.all()
# Должно быть 2: Google и Yandex

# Если нет - запустить
python manage.py setup_oauth
```

### OAuth redirect не работает

Проверьте что redirect URI в Google/Yandex консолях совпадают ТОЧНО:
- `http://localhost:8000/accounts/google/login/callback/` (локально)
- `https://replyq.ru/accounts/google/login/callback/` (прод)

### ModuleNotFoundError: No module named 'allauth'

```bash
source venv/bin/activate
pip install django-allauth==0.61.1
```

---

## СЛЕДУЮЩИЕ ШАГИ (опционально)

1. ✨ Страница связывания аккаунтов (для случая когда email занят и есть пароль)
2. ✨ Настройки профиля - отвязка OAuth
3. ✨ Админка - просмотр OAuth подключений
4. ✨ Логирование OAuth событий

---

## КОНТАКТЫ

Вопросы? Проблемы?
- Создайте issue в репозитории
- Проверьте логи: `sudo journalctl -u gunicorn -n 100`
