"""
Анализатор аспектов отзывов v4.

Комбинированный подход:
1. RuSentiLex (13k слов) — базовый словарь тональности
2. NEGATIVE/POSITIVE_LEMMAS — HoReCa-специфика
3. Обработка отрицаний ("не извинился" = negative)
4. Паттерны времени ("ждали час" = negative)
5. Гибридный поиск: фраза → предложение → весь текст
"""
import re
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Optional

from .impression_categories import (
    CATEGORY_LEMMAS,
    IMPRESSION_CATEGORIES,
)
from .lemmatizer import (
    get_lemma,
    lemmatize_text,
    NEGATIVE_LEMMAS,
    POSITIVE_LEMMAS,
    NEGATABLE_WORDS,
    NEGATIVE_PHRASES,
    POSITIVE_PHRASES,
)

logger = logging.getLogger(__name__)

# ============================================================================
# RUSENTILEX — ленивая загрузка словаря тональности
# ============================================================================

_rusentilex: Optional[Dict[str, str]] = None
_rusentilex_path = Path(__file__).parent.parent.parent / 'data' / 'rusentilex.txt'


def _load_rusentilex() -> Dict[str, str]:
    """Загрузить RuSentiLex словарь (13k слов)."""
    global _rusentilex
    if _rusentilex is not None:
        return _rusentilex

    _rusentilex = {}

    if not _rusentilex_path.exists():
        logger.warning(f"RuSentiLex not found at {_rusentilex_path}")
        return _rusentilex

    try:
        with open(_rusentilex_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('!') or not line.strip():
                    continue
                parts = line.strip().split(', ')
                if len(parts) >= 4:
                    lemma = parts[2].strip()
                    sentiment = parts[3].strip()
                    if sentiment in ('positive', 'negative'):
                        _rusentilex[lemma] = sentiment
        logger.info(f"RuSentiLex loaded: {len(_rusentilex)} words")
    except Exception as e:
        logger.error(f"Failed to load RuSentiLex: {e}")

    return _rusentilex


# ============================================================================
# РАСШИРЕННЫЕ МАРКЕРЫ КАТЕГОРИЙ
# ============================================================================

def _get_extended_category_lemmas() -> Dict[str, set]:
    """Расширенные маркеры категорий для HoReCa."""
    extended = {k: v.copy() for k, v in CATEGORY_LEMMAS.items()}

    # Сервис — сокращения и разговорные формы
    extended["Сервис"].update({
        "админ",  # сокращение от администратор
        "обслужить", "обслуживать",
    })

    # Комфорт — внешние факторы
    extended["Комфорт"].update({
        "дым", "курить", "курящий",
        "кондиционер", "кондей",  # кондиционер, разг. "кондей"
        "кондицат", "конфиденцианер", "кондицонер",  # частые опечатки
        "капать",  # "капает с кондиционера"
    })

    # Продукт — наречия как маркеры
    extended["Продукт"].add("вкусно")

    return extended


# Кэшируем расширенные маркеры
_CATEGORY_LEMMAS_EXTENDED = None


def _get_category_lemmas() -> Dict[str, set]:
    global _CATEGORY_LEMMAS_EXTENDED
    if _CATEGORY_LEMMAS_EXTENDED is None:
        _CATEGORY_LEMMAS_EXTENDED = _get_extended_category_lemmas()
    return _CATEGORY_LEMMAS_EXTENDED


# ============================================================================
# ПАТТЕРНЫ ВРЕМЕНИ ОЖИДАНИЯ
# ============================================================================

WAIT_TIME_PATTERNS = [
    (r'ждал[иа]?\s+час', 'долгое ожидание'),
    (r'час\s+ждал', 'долгое ожидание'),
    (r'\d+\s*час', 'долгое ожидание'),
    (r'ЧАС', 'эмоциональный акцент'),  # uppercase = эмоция
    (r'не подтвердил', 'отказ'),
]

# Маппинг наречий к прилагательным для RuSentiLex
ADVERB_TO_ADJ = {
    "неприятно": "неприятный",
    "хорошо": "хороший",
    "плохо": "плохой",
    "отлично": "отличный",
    "ужасно": "ужасный",
    "прекрасно": "прекрасный",
    "вкусно": "вкусный",
    "невкусно": "невкусный",
    "быстро": "быстрый",
    "медленно": "медленный",
    "грубо": "грубый",
    "долго": "долгий",
}


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def _find_word_position(text: str, word: str) -> int:
    """Найти позицию слова в тексте."""
    match = re.search(r'\b' + re.escape(word.lower()) + r'\b', text.lower())
    return match.start() if match else -1


def _get_text_ranges(text: str) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    """Получить диапазоны фраз и предложений."""
    text_lower = text.lower()

    # Фразы (по запятым и другой пунктуации)
    phrases = re.split(r'[,;.!?]', text_lower)
    phrase_ranges = []
    pos = 0
    for phrase in phrases:
        phrase_ranges.append((pos, pos + len(phrase)))
        pos += len(phrase) + 1

    # Предложения (по точкам)
    sentences = re.split(r'[.!?]', text_lower)
    sentence_ranges = []
    pos = 0
    for sent in sentences:
        sentence_ranges.append((pos, pos + len(sent)))
        pos += len(sent) + 1

    return phrase_ranges, sentence_ranges


def _position_in_range(position: int, ranges: List[Tuple[int, int]]) -> Tuple[int, int]:
    """Найти диапазон, содержащий позицию."""
    for start, end in ranges:
        if start <= position < end:
            return (start, end)
    return (0, ranges[-1][1] if ranges else 0)


# ============================================================================
# ОСНОВНАЯ ФУНКЦИЯ АНАЛИЗА
# ============================================================================

def find_aspect_tags(text: str) -> List[Dict[str, str]]:
    """
    Анализ тональности по аспектам — комбинированный подход v4.

    Использует:
    - RuSentiLex (13k слов)
    - Наши HoReCa-словари (NEGATIVE_LEMMAS, POSITIVE_LEMMAS)
    - Обработку отрицаний
    - Паттерны времени ожидания
    - Гибридный поиск по фразам/предложениям

    Returns:
        List of {'category', 'subcategory', 'sentiment', 'marker', 'evidence'}
    """
    if not text or not text.strip():
        return []

    text_lower = text.lower()
    words = re.findall(r'[а-яёА-ЯЁ]+', text_lower)
    rusentilex = _load_rusentilex()

    # ========================================================================
    # ШАГ 1: Собираем все слова с тональностью
    # ========================================================================

    sentiment_words: List[Tuple[str, str, str, int]] = []  # (word, lemma, sentiment, pos)
    positive_found = []
    negative_found = []

    # 1a. Паттерны времени ожидания (высший приоритет)
    for pattern, desc in WAIT_TIME_PATTERNS:
        search_text = text if 'ЧАС' in pattern else text_lower
        match = re.search(pattern, search_text)
        if match:
            pos = match.start()
            sentiment_words.append((match.group(0), desc, 'negative', pos))
            negative_found.append(match.group(0))

    # 1b. Фразовые паттерны
    for phrase in NEGATIVE_PHRASES:
        if phrase in text_lower:
            pos = text_lower.find(phrase)
            sentiment_words.append((phrase, phrase, 'negative', pos))
            negative_found.append(phrase)

    for phrase in POSITIVE_PHRASES:
        if phrase in text_lower:
            pos = text_lower.find(phrase)
            sentiment_words.append((phrase, phrase, 'positive', pos))
            positive_found.append(phrase)

    # 1c. Обработка отрицаний
    for i, word in enumerate(words):
        if i > 0 and words[i - 1] in ('не', 'нет', 'ни'):
            lemma = get_lemma(word)
            if lemma in POSITIVE_LEMMAS or lemma in NEGATABLE_WORDS:
                neg_phrase = f'не {word}'
                pos = text_lower.find(neg_phrase)
                if pos == -1:
                    pos = _find_word_position(text, word)
                sentiment_words.append((neg_phrase, lemma, 'negative', pos))
                negative_found.append(neg_phrase)

    # 1d. Отдельные слова
    for word in words:
        lemma = get_lemma(word)

        # Пропускаем если уже обработано
        if any(word in sw[0] for sw in sentiment_words):
            continue

        sentiment = None

        # Приоритет 1: Наши HoReCa словари
        if lemma in NEGATIVE_LEMMAS:
            sentiment = 'negative'
        elif lemma in POSITIVE_LEMMAS:
            sentiment = 'positive'

        # Приоритет 2: RuSentiLex
        if sentiment is None:
            lookup_lemma = ADVERB_TO_ADJ.get(lemma, lemma)
            if lookup_lemma in rusentilex:
                sentiment = rusentilex[lookup_lemma]

        if sentiment and sentiment in ('positive', 'negative'):
            pos = _find_word_position(text, word)
            sentiment_words.append((word, lemma, sentiment, pos))
            if sentiment == 'positive':
                positive_found.append(word)
            else:
                negative_found.append(word)

    # ========================================================================
    # ШАГ 2: Находим маркеры категорий
    # ========================================================================

    category_lemmas = _get_category_lemmas()
    category_markers: List[Tuple[str, str, int]] = []  # (category, marker_word, pos)

    for category, lemma_set in category_lemmas.items():
        for word in words:
            lemma = get_lemma(word)
            if lemma in lemma_set:
                pos = _find_word_position(text, word)
                category_markers.append((category, word, pos))
                break  # Один маркер на категорию

    # ========================================================================
    # ШАГ 3: Определяем тональность каждой категории
    # ========================================================================

    phrase_ranges, sentence_ranges = _get_text_ranges(text)
    results = []

    for category, marker, marker_pos in category_markers:
        phrase_start, phrase_end = _position_in_range(marker_pos, phrase_ranges)
        sent_start, sent_end = _position_in_range(marker_pos, sentence_ranges)

        cat_positive = 0
        cat_negative = 0
        evidence = []

        # Уровень 1: В той же фразе
        for word, lemma, sentiment, word_pos in sentiment_words:
            if word_pos >= 0 and phrase_start <= word_pos < phrase_end:
                if sentiment == 'positive':
                    cat_positive += 1
                    evidence.append(word)
                elif sentiment == 'negative':
                    cat_negative += 1
                    evidence.append(word)

        # Уровень 2: В том же предложении (если фраза пустая)
        if cat_positive == 0 and cat_negative == 0:
            for word, lemma, sentiment, word_pos in sentiment_words:
                if word_pos >= 0 and sent_start <= word_pos < sent_end:
                    if sentiment == 'positive':
                        cat_positive += 1
                        evidence.append(word)
                    elif sentiment == 'negative':
                        cat_negative += 1
                        evidence.append(word)

        # Уровень 3: Во всём тексте (fallback)
        if cat_positive == 0 and cat_negative == 0:
            for word, lemma, sentiment, word_pos in sentiment_words:
                if sentiment == 'positive':
                    cat_positive += 1
                    evidence.append(word)
                elif sentiment == 'negative':
                    cat_negative += 1
                    evidence.append(word)

        # Определяем итоговую тональность
        if cat_negative > cat_positive:
            final_sentiment = 'negative'
        elif cat_positive > cat_negative:
            final_sentiment = 'positive'
        else:
            final_sentiment = 'neutral'

        subcategory = IMPRESSION_CATEGORIES.get(category, [''])[0]
        results.append({
            'category': category,
            'subcategory': subcategory,
            'sentiment': final_sentiment,
            'marker': marker,
            'evidence': evidence[:3],  # Топ-3 доказательства
        })

    # ========================================================================
    # ШАГ 4: Fallback на "Общее" если категории не найдены
    # ========================================================================

    if not results and (positive_found or negative_found):
        # Есть sentiment, но нет маркеров категорий → Общее впечатление
        if len(negative_found) > len(positive_found):
            overall_sentiment = 'negative'
            evidence = negative_found[:3]
        elif len(positive_found) > len(negative_found):
            overall_sentiment = 'positive'
            evidence = positive_found[:3]
        else:
            overall_sentiment = 'neutral'
            evidence = (negative_found + positive_found)[:3]

        results.append({
            'category': 'Общее',
            'subcategory': 'Общее впечатление',
            'sentiment': overall_sentiment,
            'marker': '-',
            'evidence': evidence,
        })

    return results
