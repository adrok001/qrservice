# CLAUDE.md

Руководство для Claude Code при работе с этим репозиторием.

## Обзор проекта

QR Service — Django-приложение для генерации QR-кодов с поддержкой кастомных цветов и логотипов.

## Команды разработки

### Backend (Django)

```bash
# Активация окружения
source venv/bin/activate

# Запуск сервера
python manage.py runserver

# База данных
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser

# Проверка
python manage.py check
```

## Архитектура

### Структура проекта

```
qrservice/
├── manage.py
├── requirements.txt
├── venv/                    # Виртуальное окружение
├── qrservice/               # Настройки проекта
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── qrcode_app/              # Основное приложение
│   ├── models.py            # Модель QRCode
│   ├── views.py             # Views (тонкие!)
│   ├── urls.py
│   ├── admin.py
│   ├── static/              # CSS, JS
│   └── templates/           # HTML шаблоны
├── media/                   # Загруженные файлы
│   ├── qrcodes/
│   └── logos/
└── db.sqlite3
```

### Ключевые принципы

- **Тонкие views**: Логика в отдельных функциях, views только обрабатывают request/response
- **Service Layer**: Сложная бизнес-логика выносится в отдельные модули
- **Один CSS файл**: Вся тема в `static/qrcode_app/css/style.css`

## Static Files (Дизайн-система)

### ВАЖНО: Один CSS файл для всего проекта!

```
qrcode_app/static/qrcode_app/css/style.css  ← ЕДИНСТВЕННЫЙ файл темы
```

### CSS Переменные

```css
/* Используй ТОЛЬКО эти: */
--primary-color     /* Основной цвет (жёлтый) */
--text-dark, --text-gray, --text-light
--bg-white, --bg-light, --bg-gray
--border-color
--shadow-sm, --shadow-md, --shadow-lg
--radius-sm, --radius-md, --radius-lg
```

### Правила работы со стилями

1. **НЕ создавай отдельные CSS файлы** — всё в style.css
2. **Переиспользуй классы** — не дублируй стили
3. **Hard refresh после изменений** — Ctrl+Shift+R

## Coding Standards

### Python Style

- PEP 8
- snake_case для переменных и функций
- PascalCase для классов
- Type hints для публичных функций

### Django Patterns

- **FBV** для простых views
- **CBV** для сложных с несколькими HTTP методами
- **Thin Views**: Views только request/response
- **Валидация**: В Forms/Serializers, не в views

### Размеры файлов

- **< 300 строк** на файл
- **< 50 строк** на функцию
- **< 30 строк** на view

### Безопасность

- ✅ CSRF защита включена
- ✅ XSS защита через автоэкранирование Django
- ✅ SQL injection защита через ORM
- ⚠️ Валидация загружаемых файлов

## UI/UX Принципы

### ЗАПРЕЩЕНО

```
❌ Эмодзи в интерфейсе — используй SVG иконки
❌ Яркие градиенты — используй monochrome + акценты
❌ Inline <style> блоки — используй отдельный CSS файл
❌ Копирование CSS между файлами
```

### Принципы

1. **Минимум элементов** — только необходимое
2. **Крупная типографика** — удобно читать
3. **Явные действия** — понятно что нажимать
4. **Мгновенная обратная связь** — результат виден сразу
5. **Monochrome base** — чёрный/белый/серый + один акцент

### Иконки

- Только SVG (Feather Icons стиль)
- Формат: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">`
- Размеры: 16px/20px/24px

## URLs

- **Главная**: http://localhost:8000/
- **Генерация**: http://localhost:8000/generate/
- **Быстрая генерация**: http://localhost:8000/quick/
- **Админка**: http://localhost:8000/admin/
- **API скачивания**: http://localhost:8000/download/?data=...

## Workflow

### Добавление новой функции

1. Исследуй существующий код (grep, ls)
2. Составь план — покажи, жди подтверждения
3. Напиши код
4. `python manage.py check`
5. Протестируй вручную

### Изменение стилей

1. Редактируй `static/qrcode_app/css/style.css`
2. Hard refresh в браузере (Ctrl+Shift+R)

### Миграции

```bash
python manage.py makemigrations
python manage.py migrate
```

## Антипаттерны

| ❌ Плохо | ✅ Правильно |
|---------|-------------|
| Логика в view | Отдельная функция/сервис |
| Inline стили | CSS классы |
| Дублирование CSS | Переиспользование классов |
| Raw SQL | Django ORM |
| Захардкоженные значения | CSS переменные |

## Производительность

```python
# ❌ ПЛОХО: N+1 queries
for qr in QRCode.objects.all():
    print(qr.image.url)

# ✅ ХОРОШО: select_related для FK
qr_codes = QRCode.objects.select_related().all()
```
