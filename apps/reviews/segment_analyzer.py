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

from .impression_categories import CATEGORY_LEMMAS, IMPRESSION_CATEGORIES, SUBCATEGORY_MARKERS
from .dictionaries import (
    NEGATIVE_LEMMAS, POSITIVE_LEMMAS, NEGATABLE_WORDS,
    NEGATIVE_PHRASES, POSITIVE_PHRASES,
    ASPECT_WAIT_TIME_PATTERNS, ADVERB_TO_ADJ, EXTENDED_CATEGORY_MARKERS,
    PERSONNEL_NEGATIVE_PATTERNS, EXCLUDED_FROM_SENTIMENT,
    LITOTES, COMPARATIVE_CONTEXT_MARKERS,
)
from .lemmatizer import get_lemma

logger = logging.getLogger(__name__)

# Типы данных
SentimentWord = Tuple[str, str, str, int]  # (word, lemma, sentiment, pos)
CategoryMarker = Tuple[str, str, int]  # (category, marker_word, pos)

# Кэши
_rusentilex: Optional[Dict[str, str]] = None
_category_lemmas_extended: Optional[Dict[str, set]] = None
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
                    lemma, sentiment = parts[2].strip(), parts[3].strip()
                    if sentiment in ('positive', 'negative'):
                        _rusentilex[lemma] = sentiment
        logger.info(f"RuSentiLex loaded: {len(_rusentilex)} words")
    except Exception as e:
        logger.error(f"Failed to load RuSentiLex: {e}")
    return _rusentilex


def _get_category_lemmas() -> Dict[str, set]:
    """Получить расширенные маркеры категорий для HoReCa."""
    global _category_lemmas_extended
    if _category_lemmas_extended is not None:
        return _category_lemmas_extended

    extended = {k: v.copy() for k, v in CATEGORY_LEMMAS.items()}
    for category, markers in EXTENDED_CATEGORY_MARKERS.items():
        extended[category].update(markers)
    _category_lemmas_extended = extended
    return _category_lemmas_extended


def _find_word_position(text: str, word: str) -> int:
    """Найти позицию слова в тексте."""
    match = re.search(r'\b' + re.escape(word.lower()) + r'\b', text.lower())
    return match.start() if match else -1


def _find_all_word_positions(text: str, word: str) -> List[int]:
    """Найти все позиции слова в тексте."""
    positions = []
    for match in re.finditer(r'\b' + re.escape(word.lower()) + r'\b', text.lower()):
        positions.append(match.start())
    return positions


def _get_text_ranges(text: str) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    """Получить диапазоны фраз и предложений."""
    text_lower = text.lower()

    def split_to_ranges(pattern: str) -> List[Tuple[int, int]]:
        parts = re.split(pattern, text_lower)
        ranges, pos = [], 0
        for part in parts:
            ranges.append((pos, pos + len(part)))
            pos += len(part) + 1
        return ranges

    return split_to_ranges(r'[,;.!?]'), split_to_ranges(r'[.!?]')


def _position_in_range(position: int, ranges: List[Tuple[int, int]]) -> Tuple[int, int]:
    """Найти диапазон, содержащий позицию."""
    for start, end in ranges:
        if start <= position < end:
            return (start, end)
    return (0, ranges[-1][1] if ranges else 0)


def _collect_pattern_sentiments(text: str, text_lower: str) -> Tuple[List[SentimentWord], List[str], List[str], List[CategoryMarker]]:
    """Собрать тональность из паттернов времени и фраз.

    Returns:
        (sentiment_words, positive_found, negative_found, implicit_category_markers)
        implicit_category_markers — неявные маркеры категорий от паттернов персонала
    """
    sentiment_words: List[SentimentWord] = []
    positive_found, negative_found = [], []
    implicit_markers: List[CategoryMarker] = []

    for pattern, desc in ASPECT_WAIT_TIME_PATTERNS:
        search_text = text if 'ЧАС' in pattern else text_lower
        match = re.search(pattern, search_text)
        if match:
            sentiment_words.append((match.group(0), desc, 'negative', match.start()))
            negative_found.append(match.group(0))

    # Паттерны "персонал + действие" → негатив + неявный маркер Сервис
    for pattern, desc in PERSONNEL_NEGATIVE_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            sentiment_words.append((match.group(0), desc, 'negative', match.start()))
            negative_found.append(match.group(0))
            implicit_markers.append(('Сервис', match.group(0), match.start()))

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

    return sentiment_words, positive_found, negative_found, implicit_markers


def _collect_negation_sentiments(words: List[str], text_lower: str, text: str,
                                  sentiment_words: List[SentimentWord],
                                  positive_found: List[str], negative_found: List[str]) -> None:
    """Обработать отрицания (не + слово) и литоты (не + негатив = позитив)."""
    for i, word in enumerate(words):
        if i > 0 and words[i - 1] in ('не', 'нет', 'ни'):
            lemma = get_lemma(word)

            # Литота: "не плохо" → позитив
            if lemma in LITOTES:
                phrase = f'не {word}'
                pos = text_lower.find(phrase)
                if pos == -1:
                    pos = _find_word_position(text, word)
                sentiment_words.append((phrase, lemma, 'positive', pos))
                positive_found.append(phrase)
                continue

            # Стандартная обработка: "не вкусно" → негатив
            if lemma in POSITIVE_LEMMAS or lemma in NEGATABLE_WORDS:
                neg_phrase = f'не {word}'
                pos = text_lower.find(neg_phrase)
                if pos == -1:
                    pos = _find_word_position(text, word)
                sentiment_words.append((neg_phrase, lemma, 'negative', pos))
                negative_found.append(neg_phrase)


def _collect_word_sentiments(words: List[str], text: str, rusentilex: Dict[str, str],
                              sentiment_words: List[SentimentWord],
                              positive_found: List[str], negative_found: List[str]) -> None:
    """Собрать тональность отдельных слов."""
    text_lower = text.lower()

    for word in words:
        lemma = get_lemma(word)
        if any(word in sw[0] for sw in sentiment_words):
            continue

        # Пропускаем позитивные слова после "не очень", "не особо"
        word_pos = text_lower.find(word)
        if word_pos > 0:
            prefix = text_lower[max(0, word_pos - 12):word_pos].strip()
            if prefix.endswith(('не очень', 'не особо', 'не слишком', 'не так')):
                continue

        # Пропускаем компаративы в сравнительном контексте ("в другом месте было быстрее")
        if word.endswith(('ее', 'ей', 'ше')) and len(word) > 3 and word_pos >= 0:
            context = text_lower[max(0, word_pos - 50):word_pos + len(word) + 50]
            if any(marker in context for marker in COMPARATIVE_CONTEXT_MARKERS):
                continue

        # Применяем маппинг наречий к прилагательным
        lookup_lemma = ADVERB_TO_ADJ.get(lemma, lemma)

        sentiment = None
        if lemma in NEGATIVE_LEMMAS or lookup_lemma in NEGATIVE_LEMMAS:
            sentiment = 'negative'
        elif lemma in POSITIVE_LEMMAS or lookup_lemma in POSITIVE_LEMMAS:
            sentiment = 'positive'

        if sentiment is None:
            # Исключаем слова которые дают ложные срабатывания
            if lemma not in EXCLUDED_FROM_SENTIMENT and lookup_lemma in rusentilex:
                sentiment = rusentilex[lookup_lemma]

        if sentiment in ('positive', 'negative'):
            pos = _find_word_position(text, word)
            sentiment_words.append((word, lemma, sentiment, pos))
            (positive_found if sentiment == 'positive' else negative_found).append(word)


def _find_category_markers(words: List[str], text: str) -> List[CategoryMarker]:
    """Найти маркеры категорий в тексте."""
    category_lemmas = _get_category_lemmas()
    markers: List[CategoryMarker] = []
    seen_positions: set = set()
    for category, lemma_set in category_lemmas.items():
        for word in words:
            if get_lemma(word) in lemma_set:
                for pos in _find_all_word_positions(text, word):
                    if (category, pos) not in seen_positions:
                        seen_positions.add((category, pos))
                        markers.append((category, word, pos))
    return markers


def _count_sentiment_in_range(sentiment_words: List[SentimentWord], start: int, end: int) -> Tuple[int, int, List[str]]:
    """Подсчитать позитив/негатив в диапазоне.

    Отрицания (слова начинающиеся с «не ») получают вес ×2,
    т.к. человек намеренно написал отрицание — это сильнее единичного позитива.
    """
    pos_count, neg_count, evidence = 0, 0, []
    for word, _, sentiment, word_pos in sentiment_words:
        if word_pos >= 0 and start <= word_pos < end:
            weight = 2 if word.startswith('не ') else 1
            if sentiment == 'positive':
                pos_count += weight
            elif sentiment == 'negative':
                neg_count += weight
            evidence.append(word)
    return pos_count, neg_count, evidence


def _determine_subcategories(category: str, marker_word: str, evidence: List[str],
                             sentiment_words: List[SentimentWord],
                             marker_pos: int, sentence_ranges: List[Tuple[int, int]],
                             text: str = '') -> List[str]:
    """Определить подкатегории на основе контекста маркера и evidence.

    Возвращает список подкатегорий (1+). Если маркерные слова нескольких
    подкатегорий найдены в контексте — возвращает все совпавшие.
    Сканирует ВСЕ слова текста в окне ±1 предложение (не только sentiment_words).
    """
    if category not in SUBCATEGORY_MARKERS:
        return [IMPRESSION_CATEGORIES.get(category, [''])[0]]

    subcat_map = SUBCATEGORY_MARKERS[category]

    # Собираем все релевантные леммы из контекста
    relevant_lemmas = set()

    # Лемма маркера
    relevant_lemmas.add(get_lemma(marker_word))

    # Леммы из evidence-слов
    for word in evidence:
        for w in re.findall(r'[а-яёА-ЯЁ]+', word.lower()):
            relevant_lemmas.add(get_lemma(w))

    # Определяем окно ±1 предложение
    sent_idx = next(
        (i for i, (s, e) in enumerate(sentence_ranges) if s <= marker_pos < e),
        -1,
    )
    if sent_idx >= 0:
        ext_start = sentence_ranges[max(0, sent_idx - 1)][0]
        ext_end = sentence_ranges[min(len(sentence_ranges) - 1, sent_idx + 1)][1]
    else:
        ext_start, ext_end = 0, 0

    # Леммы из sentiment_words в окне
    for word, lemma, _, word_pos in sentiment_words:
        if word_pos >= 0 and ext_start <= word_pos < ext_end:
            for w in re.findall(r'[а-яёА-ЯЁ]+', lemma.lower()):
                relevant_lemmas.add(get_lemma(w))
            for w in re.findall(r'[а-яёА-ЯЁ]+', word.lower()):
                relevant_lemmas.add(get_lemma(w))

    # Все слова текста в окне (не только sentiment_words)
    # чтобы ловить «неприветлив», «вылавливать», «гостеприимным» и т.д.
    if text and ext_end > ext_start:
        window_text = text[ext_start:ext_end].lower()
        for w in re.findall(r'[а-яёА-ЯЁ]+', window_text):
            relevant_lemmas.add(get_lemma(w))

    # Ищем ВСЕ подкатегории с хотя бы 1 совпадением
    matched = []
    for subcat, markers in subcat_map.items():
        count = len(relevant_lemmas & markers)
        if count > 0:
            matched.append(subcat)

    if matched:
        return matched

    return [IMPRESSION_CATEGORIES.get(category, [''])[0]]


def _determine_category_sentiment(marker: CategoryMarker, sentiment_words: List[SentimentWord],
                                   phrase_ranges: List[Tuple[int, int]],
                                   sentence_ranges: List[Tuple[int, int]],
                                   text: str = '') -> List[Dict[str, str]]:
    """Определить тональность для категории.

    Приоритет контекста (гибридный):
    1. Фраза (до запятой) — если там есть тональность
    2. Предложение (до точки) — если в фразе пусто
    3. Соседние предложения (±1) — если в предложении пусто

    Возвращает список тегов (1+ если найдено несколько подкатегорий).
    """
    category, marker_word, marker_pos = marker
    phrase_range = _position_in_range(marker_pos, phrase_ranges)
    sent_range = _position_in_range(marker_pos, sentence_ranges)

    # Сначала пробуем фразу (до запятой)
    pos_count, neg_count, evidence = _count_sentiment_in_range(sentiment_words, phrase_range[0], phrase_range[1])

    # Если в фразе пусто — расширяемся до предложения
    if pos_count == 0 and neg_count == 0:
        pos_count, neg_count, evidence = _count_sentiment_in_range(sentiment_words, sent_range[0], sent_range[1])

    # Если в предложении тоже пусто — расширяемся до соседних предложений (±1)
    if pos_count == 0 and neg_count == 0:
        sent_idx = next(
            (i for i, (s, e) in enumerate(sentence_ranges) if s <= marker_pos < e),
            -1,
        )
        if sent_idx >= 0:
            ext_start = sentence_ranges[max(0, sent_idx - 1)][0]
            ext_end = sentence_ranges[min(len(sentence_ranges) - 1, sent_idx + 1)][1]
            pos_count, neg_count, evidence = _count_sentiment_in_range(
                sentiment_words, ext_start, ext_end
            )

    final_sentiment = 'negative' if neg_count > pos_count else 'positive' if pos_count > neg_count else 'neutral'
    subcategories = _determine_subcategories(
        category, marker_word, evidence, sentiment_words, marker_pos, sentence_ranges, text
    )
    results = []
    for subcat in subcategories:
        results.append({
            'category': category,
            'subcategory': subcat,
            'sentiment': final_sentiment,
            'marker': marker_word,
            'evidence': evidence[:3],
        })
    return results


def _create_fallback_result(positive_found: List[str], negative_found: List[str]) -> Optional[Dict[str, str]]:
    """Создать fallback результат для категории 'Общее'."""
    if not positive_found and not negative_found:
        return None

    if len(negative_found) > len(positive_found):
        sentiment, evidence = 'negative', negative_found[:3]
    elif len(positive_found) > len(negative_found):
        sentiment, evidence = 'positive', positive_found[:3]
    else:
        sentiment, evidence = 'neutral', (negative_found + positive_found)[:3]

    return {'category': 'Общее', 'subcategory': 'Общее впечатление', 'sentiment': sentiment, 'marker': '-', 'evidence': evidence}


def find_aspect_tags(text: str) -> List[Dict[str, str]]:
    """Анализ тональности по аспектам."""
    if not text or not text.strip():
        return []

    text_lower = text.lower()
    words = re.findall(r'[а-яёА-ЯЁ]+', text_lower)
    rusentilex = _load_rusentilex()

    sentiment_words, positive_found, negative_found, implicit_markers = _collect_pattern_sentiments(text, text_lower)
    _collect_negation_sentiments(words, text_lower, text, sentiment_words, positive_found, negative_found)
    _collect_word_sentiments(words, text, rusentilex, sentiment_words, positive_found, negative_found)

    category_markers = _find_category_markers(words, text)
    category_markers.extend(implicit_markers)
    phrase_ranges, sentence_ranges = _get_text_ranges(text)
    results = []
    for m in category_markers:
        results.extend(_determine_category_sentiment(m, sentiment_words, phrase_ranges, sentence_ranges, text))

    # Дедупликация: убираем повторы одинаковых (category, subcategory)
    seen = set()
    unique_results = []
    for r in results:
        key = (r['category'], r['subcategory'])
        if key not in seen:
            seen.add(key)
            unique_results.append(r)
    results = unique_results

    # Убираем «Общее» если есть конкретные категории
    specific_results = [r for r in results if r['category'] != 'Общее']
    if specific_results:
        results = specific_results

    # Fallback: «Общее» только для коротких текстов без конкретных маркеров
    if not results:
        fallback = _create_fallback_result(positive_found, negative_found)
        if fallback:
            results.append(fallback)

    return results


def analyze_sentiment_dict(text: str) -> Tuple[str, int, int]:
    """
    Словарный анализ тональности текста.

    Использует RuSentiLex (13k слов) + HoReCa-словари.
    Точность 78% на 1593 реальных отзывах.

    Returns:
        (sentiment, pos_count, neg_count) — тональность и счётчики слов
    """
    if not text or not text.strip():
        return ('neutral', 0, 0)

    text_lower = text.lower()
    words = re.findall(r'[а-яёА-ЯЁ]+', text_lower)
    rusentilex = _load_rusentilex()

    sentiment_words, positive_found, negative_found, _ = _collect_pattern_sentiments(text, text_lower)
    _collect_negation_sentiments(words, text_lower, text, sentiment_words, positive_found, negative_found)
    _collect_word_sentiments(words, text, rusentilex, sentiment_words, positive_found, negative_found)

    pos_count = len(positive_found)
    neg_count = len(negative_found)

    if neg_count > pos_count:
        sentiment = 'negative'
    elif pos_count > neg_count:
        sentiment = 'positive'
    else:
        sentiment = 'neutral'

    return (sentiment, pos_count, neg_count)
