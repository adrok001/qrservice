# План интеграции DeepSeek API

> Дата: 2026-02-06
> Статус: Готов к реализации

## Результаты исследования

### Тестирование API

- **DeepSeek API работает из России** (сервер Timeweb, Москва, IP 46.149.66.180)
- API ключ: настроен в личном кабинете platform.deepseek.com
- Баланс: $10 (~50,000 отзывов)
- Стоимость: ~$0.0003 за отзыв (0.03₽)

### Сравнение качества (10 тестовых отзывов)

| Метрика | Текущая система | DeepSeek |
|---------|-----------------|----------|
| Покрытие жалоб/похвал | 40% | **100%** |
| Найдено жалоб | 4 | **24** |
| Ложные срабатывания | 2 | **0** |
| Детализация подкатегорий | Низкая | **Высокая** |

**Ключевое преимущество DeepSeek:** Разбивает "Сервис/персонал" на конкретные проблемы:
- Хамство/грубость
- Невнимательность
- Невежливость

---

## Архитектура решения

### Принцип работы

```
[Отзыв создан]
     │
     ▼
[segment_analyzer] ──► tags = [...] (мгновенно, локально)
     │                 ai_status = 'pending'
     ▼
[Сохранён в БД] ──► Пользователь получил ответ


[Cron каждые 5 мин]
     │
     ▼
[analyze_reviews command]
     │
     ├── DEEPSEEK_ENABLED = False? ──► Выход
     │
     ▼
[Отзывы: pending, retry < 3, негативные первыми]
     │
     ▼
[DeepSeek API]
     │
     ├── Успех ──► ai_tags = [...], ai_status = 'completed'
     │
     └── Ошибка ──► retry_count++, если ≥3: status = 'failed'
```

### Защита от отказов

1. **Fallback:** Текущая система (segment_analyzer) работает ВСЕГДА локально
2. **Retry:** Максимум 3 попытки на отзыв
3. **Приоритет:** Негативные отзывы (rating ≤ 3) анализируются первыми
4. **Ручное отключение:** Флаг `DEEPSEEK_ENABLED` в настройках
5. **Graceful degradation:** Если DeepSeek недоступен — показываем базовые категории

---

## Изменения в коде

### 1. Модель Review (`apps/reviews/models.py`)

```python
# Новые поля
AI_STATUS_CHOICES = [
    ('pending', 'Ожидает'),
    ('completed', 'Готово'),
    ('failed', 'Ошибка'),
]

ai_tags = models.JSONField(null=True, blank=True)
ai_status = models.CharField(max_length=20, choices=AI_STATUS_CHOICES, default='pending')
ai_retry_count = models.PositiveSmallIntegerField(default=0)
ai_analyzed_at = models.DateTimeField(null=True, blank=True)
```

### 2. DeepSeek клиент (`apps/reviews/services/deepseek.py`)

```python
class DeepSeekAnalyzer:
    API_URL = "https://api.deepseek.com/v1/chat/completions"
    TIMEOUT = 30

    SYSTEM_PROMPT = """Ты анализируешь отзывы о ресторане.
Категории: Безопасность, Сервис, Скорость, Продукт, Цена, Комфорт, Процесс, Общее

Подкатегории Сервиса:
- Хамство/грубость/конфликт
- Внимание/вовлечённость
- Вежливость/уважение
- Компетентность/знание меню

Тональность: positive, negative, neutral

Ответ JSON: [{"category": "", "subcategory": "", "sentiment": "", "evidence": ""}]"""

    def analyze(self, text: str) -> list | None:
        # HTTP запрос к API
        # Валидация ответа
        # Возврат тегов или None при ошибке
```

### 3. Management command (`apps/reviews/management/commands/analyze_reviews.py`)

```python
class Command(BaseCommand):
    def handle(self, *args, **options):
        if not settings.DEEPSEEK_ENABLED:
            return

        reviews = Review.objects.filter(
            ai_status='pending',
            ai_retry_count__lt=3
        ).order_by('rating', '-created_at')[:20]

        for review in reviews:
            tags = analyzer.analyze(review.text)
            if tags:
                review.ai_tags = tags
                review.ai_status = 'completed'
            else:
                review.ai_retry_count += 1
                if review.ai_retry_count >= 3:
                    review.ai_status = 'failed'
            review.save()
```

### 4. Настройки (`qrservice/settings.py`)

```python
DEEPSEEK_ENABLED = env.bool('DEEPSEEK_ENABLED', default=False)
DEEPSEEK_API_KEY = env.str('DEEPSEEK_API_KEY', default='')
```

### 5. Дашборд (`apps/dashboard/services/insights.py`)

```python
def get_review_tags(review) -> list:
    """Получить теги с приоритетом AI."""
    if review.ai_status == 'completed' and review.ai_tags:
        return review.ai_tags
    return review.tags or []
```

### 6. Cron задача

```bash
*/5 * * * * cd /var/www/replyq && source venv/bin/activate && python manage.py analyze_reviews --limit=20
```

---

## Файлы для изменения

| Файл | Действие |
|------|----------|
| `apps/reviews/models.py` | Добавить 4 поля |
| `apps/reviews/services/deepseek.py` | Создать |
| `apps/reviews/management/commands/analyze_reviews.py` | Создать |
| `apps/reviews/management/commands/reanalyze_all.py` | Создать |
| `apps/reviews/admin.py` | Добавить AI поля |
| `apps/dashboard/services/insights.py` | Изменить get_review_tags() |
| `qrservice/settings.py` | Добавить 2 настройки |
| `.env` | Добавить ключ API |

---

## Порядок реализации

1. Миграция модели (15 мин)
2. DeepSeek клиент (20 мин)
3. Management command (20 мин)
4. Настройки (5 мин)
5. Изменить insights.py (15 мин)
6. Админка (10 мин)
7. Тест на 10 отзывах (10 мин)
8. Cron на сервере (5 мин)
9. Переанализ истории (10 мин)

**Итого: ~2 часа**

---

## Стоимость

- ~200 токенов на отзыв
- $0.27/1M токенов (вход) + $1.10/1M (выход)
- **1 отзыв ≈ $0.0003 (0.03₽)**
- **1000 отзывов ≈ 30₽**
- **$10 баланса ≈ 50,000 отзывов**

---

## Переменные окружения

```bash
# .env на сервере
DEEPSEEK_ENABLED=true
DEEPSEEK_API_KEY=sk-71859affb94d49dca0c3a2551c54f3e1
```

---

## Режимы работы системы

| Режим | DeepSeek | Текущая система | Результат |
|-------|----------|-----------------|-----------|
| Норма | ✅ | ✅ | Детальные подкатегории |
| DeepSeek упал | ❌ | ✅ | Базовые категории |
| Отключён вручную | ❌ | ✅ | Базовые категории |

**Гарантия:** Пользователь ВСЕГДА видит категории (минимум от локальной системы).
