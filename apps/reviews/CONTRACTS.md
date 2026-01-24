# Контракты модулей анализа отзывов

## Архитектура

```
services.py (точка входа)
    ├── ml_analyzer.py (ML-анализ общей тональности)
    └── segment_analyzer.py (аспектный анализ)
            ├── dictionaries.py (словари тональности)
            ├── impression_categories.py (категории аспектов)
            └── lemmatizer.py (лемматизация)
```

---

## Блок 1: dictionaries.py — Словари тональности

### Назначение
Хранит наборы слов и паттернов для определения тональности.

### Экспортируемые данные

| Константа | Тип | Описание |
|-----------|-----|----------|
| `NEGATIVE_LEMMAS` | `Set[str]` | Негативные леммы (ужасный, невкусный, грубый...) |
| `POSITIVE_LEMMAS` | `Set[str]` | Позитивные леммы (вкусный, отличный, приятный...) |
| `NEGATIVE_PHRASES` | `Set[str]` | Негативные фразы ("не рекомендую", "час ждали"...) |
| `POSITIVE_PHRASES` | `Set[str]` | Позитивные фразы ("в восторге", "пять звезд"...) |
| `NEGATABLE_WORDS` | `Set[str]` | Слова, негативные при отрицании ("не извинились") |
| `NEGATIVE_WITHOUT_CONSTRUCTS` | `Set[str]` | Слова для "без X" конструкций |
| `WAIT_TIME_PATTERNS` | `List[str]` | Regex паттерны времени ожидания |
| `ASPECT_WAIT_TIME_PATTERNS` | `List[Tuple[str,str]]` | Паттерны (regex, описание) |
| `PERSONNEL_NEGATIVE_PATTERNS` | `List[Tuple[str,str]]` | Паттерны "персонал + действие" |
| `ADVERB_TO_ADJ` | `Dict[str,str]` | Маппинг наречий к прилагательным |

### Контракт данных
- Все леммы в нижнем регистре
- Фразы в нижнем регистре
- Regex паттерны совместимы с `re.search()`

---

## Блок 2: lemmatizer.py — Лемматизация

### Назначение
Приведение слов к начальной форме (лемме) через pymorphy3.

### Функции

#### `get_lemma(word: str) -> str`
```python
# Вход: слово в любом регистре/форме
# Выход: лемма (начальная форма) в нижнем регистре

get_lemma("вкусные") → "вкусный"
get_lemma("ждали") → "ждать"
get_lemma("официанта") → "официант"
```

#### `lemmatize_text(text: str) -> List[str]`
```python
# Вход: текст отзыва
# Выход: список лемм (только русские слова)

lemmatize_text("Вкусные блюда, но долго ждали")
→ ["вкусный", "блюдо", "но", "долго", "ждать"]
```

### Зависимости
- pymorphy3

---

## Блок 3: impression_categories.py — Категории аспектов

### Назначение
Определяет иерархию категорий впечатлений для HoReCa.

### Экспортируемые данные

#### `IMPRESSION_CATEGORIES: Dict[str, List[str]]`
```python
{
    "Безопасность": ["Отравление/симптомы"],
    "Сервис": ["Сервис/персонал", "Вежливость/уважение", ...],
    "Скорость": ["Скорость/ожидание", ...],
    "Продукт": ["Еда/кухня", "Напитки/бар", ...],
    "Цена": ["Цена/ценность"],
    "Комфорт": ["Интерьер/атмосфера", "Чистота/санитария"],
    "Процесс": ["Бронирование/стол", ...],
    "Общее": ["Общее впечатление"],
}
```

#### `CATEGORY_LEMMAS: Dict[str, Set[str]]`
Маркеры категорий (леммы слов-триггеров):
```python
{
    "Сервис": {"официант", "персонал", "обслуживание", ...},
    "Продукт": {"еда", "блюдо", "вкус", "пицца", ...},
    ...
}
```

#### `CATEGORY_MARKERS: Dict[str, List[str]]`
Паттерны для поиска категорий (подстроки):
```python
{
    "Продукт": ["еда", "блюд", "вкус", "пицц", "борщ", ...],
    ...
}
```

---

## Блок 4: segment_analyzer.py — Аспектный анализ

### Назначение
Главный модуль. Находит категории в тексте и определяет их тональность.

### Главная функция

#### `find_aspect_tags(text: str) -> List[Dict[str, str]]`

```python
# Вход: текст отзыва
# Выход: список тегов аспектов

find_aspect_tags("Еда вкусная, но официант хамил")
→ [
    {"category": "Продукт", "subcategory": "Еда/кухня", "sentiment": "positive", "marker": "еда", "evidence": ["вкусная"]},
    {"category": "Сервис", "subcategory": "Сервис/персонал", "sentiment": "negative", "marker": "официант", "evidence": ["хамил"]},
]
```

### Формат выходных данных

| Поле | Тип | Описание |
|------|-----|----------|
| `category` | `str` | Основная категория (Продукт, Сервис, ...) |
| `subcategory` | `str` | Подкатегория |
| `sentiment` | `str` | `"positive"` / `"negative"` / `"neutral"` |
| `marker` | `str` | Слово-триггер категории |
| `evidence` | `List[str]` | До 3 слов-доказательств тональности |

### Алгоритм (упрощённо)
1. Найти слова тональности (словари + RuSentiLex)
2. Обработать отрицания ("не вкусно" → negative)
3. Найти маркеры категорий
4. Для каждой категории определить тональность в контексте:
   - Сначала в пределах фразы (до запятой)
   - Затем в пределах предложения (до точки)
   - Затем по всему тексту
5. Вернуть список тегов

### Зависимости
- `dictionaries.py` — словари
- `impression_categories.py` — категории
- `lemmatizer.py` — лемматизация
- `data/rusentilex.txt` — словарь RuSentiLex

---

## Блок 5: ml_analyzer.py — ML-анализ

### Назначение
Определение общей тональности через нейросеть (RuBERT).

### Функции

#### `analyze_sentiment_ml(text: str) -> Tuple[str, float]`
```python
# Вход: текст отзыва
# Выход: (sentiment, confidence)

analyze_sentiment_ml("Отличное место!")
→ ("positive", 0.95)

analyze_sentiment_ml("Ужасный сервис")
→ ("negative", 0.89)
```

#### `sentiment_to_score(sentiment: str, confidence: float) -> float`
```python
# Конвертация в score [-1.0, +1.0]

sentiment_to_score("positive", 0.9) → 0.9
sentiment_to_score("negative", 0.8) → -0.8
sentiment_to_score("neutral", 0.7) → 0.0
```

### Модели (приоритет)
1. ONNX Runtime (`models/rubert-sentiment-onnx/`)
2. Transformers (`seara/rubert-tiny2-russian-sentiment`)
3. Fallback: `("neutral", 0.5)`

---

## Блок 6: services.py — Бизнес-логика

### Назначение
Объединяет ML и аспектный анализ, предоставляет API для views.

### Главная функция

#### `analyze_review_impressions(text: str, rating: int) -> Tuple[List[Dict], float]`

```python
# Вход: текст отзыва, рейтинг клиента (1-5)
# Выход: (tags, sentiment_score)

analyze_review_impressions("Вкусно, но долго ждали", 3)
→ (
    [
        {"category": "Продукт", "subcategory": "Еда/кухня", "sentiment": "positive"},
        {"category": "Скорость", "subcategory": "Скорость/ожидание", "sentiment": "negative"},
    ],
    -0.3  # ML score
)
```

### Логика
1. Получить ML-тональность и score
2. Получить аспектные теги через `find_aspect_tags()`
3. Если нет тегов — создать fallback "Общее"
4. Вернуть (tags, ml_score)

---

## Блок 7: cache.py — Кэширование

### Назначение
Кэширование результатов анализа (Django cache).

### Функции

#### `get_analysis_cached(text: str, rating: int) -> Tuple[List[Dict], float]`
```python
# Возвращает результат из кэша или вычисляет
# TTL: 7 дней
```

### Ключ кэша
```python
f"review_analysis:{md5(text)[:16]}:{rating}"
```

---

## Интеграция модулей

### Поток данных

```
Текст отзыва + Рейтинг
        │
        ▼
    cache.py (проверка кэша)
        │
        ▼ (cache miss)
    services.py
        │
        ├──► ml_analyzer.py → (sentiment, score)
        │
        └──► segment_analyzer.py
                │
                ├── dictionaries.py (словари)
                ├── impression_categories.py (категории)
                └── lemmatizer.py (леммы)
                        │
                        ▼
                    [aspect_tags]
        │
        ▼
    (tags, ml_score) → cache.py (сохранение)
        │
        ▼
    Review.objects.create(tags=tags, sentiment_score=ml_score)
```

### Критические точки интеграции

1. **lemmatizer → dictionaries**: леммы должны совпадать с ключами словарей
2. **segment_analyzer → impression_categories**: категории должны существовать
3. **services → segment_analyzer**: формат тегов должен быть валидным
4. **cache → services**: сериализуемость результатов
