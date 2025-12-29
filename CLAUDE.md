# CLAUDE.md

Руководство для Claude Code при работе с этим репозиторием.

## Обзор проекта

FeedbackQR — Django-приложение для сбора обратной связи через QR-коды с аналитикой отзывов и картой впечатлений.

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
├── venv/                       # Виртуальное окружение
├── qrservice/                  # Настройки проекта
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/                       # Приложения
│   ├── accounts/               # Пользователи
│   ├── companies/              # Компании и платформы
│   ├── dashboard/              # Дашборд и аналитика
│   │   ├── views.py            # Views (тонкие!)
│   │   └── services/           # Бизнес-логика (модульная)
│   │       ├── __init__.py
│   │       ├── analytics.py    # Аналитика и KPI
│   │       ├── company.py      # Работа с компаниями
│   │       ├── reviews.py      # Работа с отзывами
│   │       └── qr.py           # Генерация QR
│   ├── integrations/           # Google, Яндекс и др.
│   ├── qr/                     # QR-коды
│   └── reviews/                # Отзывы и карта впечатлений
├── static/css/style.css        # ЕДИНСТВЕННЫЙ CSS файл
├── templates/                  # HTML шаблоны
├── media/                      # Загруженные файлы
└── db.sqlite3
```

### Ключевые принципы

- **Тонкие views**: Логика в services/, views только request/response
- **Модульные сервисы**: Бизнес-логика разбита по доменам (analytics, company, reviews, qr)
- **Один CSS файл**: Вся тема в `static/css/style.css`

## Static Files (Дизайн-система)

### ВАЖНО: Один CSS файл для всего проекта!

```
static/css/style.css  ← ЕДИНСТВЕННЫЙ файл темы
```

### CSS Переменные

```css
/* Основные цвета */
--color-primary: #000;
--color-secondary: #666;
--color-muted: #999;
--color-border: #e5e5e5;
--color-bg: #f8f9fa;
--color-white: #fff;

/* Семантические цвета */
--color-success: #22c55e;
--color-success-light: #dcfce7;
--color-warning: #fbbf24;
--color-error: #ef4444;
--color-error-light: #fee2e2;
--color-info: #3b82f6;

/* Рейтинг */
--color-rating-5: #22c55e;
--color-rating-4: #84cc16;
--color-rating-3: #fbbf24;
--color-rating-2: #f97316;
--color-rating-1: #ef4444;

/* Отступы, радиусы, тени */
--spacing-xs/sm/md/lg/xl
--radius-sm/md/lg/xl/full
--shadow-sm/md/lg
```

### Правила работы со стилями

1. **НЕ создавай отдельные CSS файлы** — всё в style.css
2. **Используй CSS переменные** — не хардкодь цвета
3. **Переиспользуй классы** — не дублируй стили
4. **Hard refresh после изменений** — Ctrl+Shift+R

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

- CSRF защита включена
- XSS защита через автоэкранирование Django
- SQL injection защита через ORM
- Валидация загружаемых файлов

## UI/UX Принципы

### ЗАПРЕЩЕНО

- Эмодзи в интерфейсе — используй SVG иконки
- Яркие градиенты — используй monochrome + акценты
- Inline style блоки — используй CSS классы
- Захардкоженные цвета — используй CSS переменные

### Принципы

1. **Минимум элементов** — только необходимое
2. **Крупная типографика** — удобно читать
3. **Явные действия** — понятно что нажимать
4. **Мгновенная обратная связь** — результат виден сразу
5. **Monochrome base** — чёрный/белый/серый + акценты

### Иконки

- Только SVG (Feather Icons стиль)
- Формат: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">`
- Размеры: 16px/20px/24px

## URLs

- **Главная**: http://localhost:8000/
- **Дашборд**: http://localhost:8000/dashboard/
- **Админка**: http://localhost:8000/admin/

## Workflow

### Добавление новой функции

1. Исследуй существующий код (grep, ls)
2. Составь план — покажи, жди подтверждения
3. Напиши код в соответствующем сервисе
4. `python manage.py check`
5. Протестируй вручную

### Изменение стилей

1. Редактируй `static/css/style.css`
2. Hard refresh в браузере (Ctrl+Shift+R)

### Миграции

```bash
python manage.py makemigrations
python manage.py migrate
```

## Антипаттерны

| Плохо | Правильно |
|-------|-----------|
| Логика в view | Отдельная функция/сервис |
| Inline стили | CSS классы |
| Дублирование CSS | Переиспользование классов |
| Raw SQL | Django ORM |
| Захардкоженные цвета | CSS переменные |

## Производительность

```python
# ПЛОХО: N+1 queries
for qr in QRCode.objects.all():
    print(qr.image.url)

# ХОРОШО: select_related для FK
qr_codes = QRCode.objects.select_related().all()
```
