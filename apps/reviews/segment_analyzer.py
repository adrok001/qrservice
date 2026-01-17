"""
Сегментный анализатор текста отзывов.
Разбивает текст на части с разной тональностью.
"""
import re
from typing import List, Tuple, Dict

from .impression_categories import (
    CATEGORY_MARKERS,
    IMPRESSION_CATEGORIES,
    POSITIVE_SEGMENT_MARKERS,
    NEGATIVE_SEGMENT_MARKERS,
)

_SEGMENT_PATTERN = None


def _build_segment_pattern():
    """Build combined regex pattern for segment detection."""
    all_patterns = []
    for p in POSITIVE_SEGMENT_MARKERS:
        all_patterns.append(f"(?P<pos_{len(all_patterns)}>{p})")
    for p in NEGATIVE_SEGMENT_MARKERS:
        all_patterns.append(f"(?P<neg_{len(all_patterns)}>{p})")
    return re.compile('|'.join(all_patterns), re.IGNORECASE)


def _get_segment_pattern():
    """Lazy init segment pattern."""
    global _SEGMENT_PATTERN
    if _SEGMENT_PATTERN is None:
        _SEGMENT_PATTERN = _build_segment_pattern()
    return _SEGMENT_PATTERN


def segment_text(text: str) -> List[Tuple[str, str]]:
    """
    Разбивает текст на сегменты с тональностью.

    Returns:
        List of (segment_text, sentiment_hint) where sentiment_hint is
        'positive', 'negative', or 'default'
    """
    text_lower = text.lower()
    pattern = _get_segment_pattern()

    markers = []
    for match in pattern.finditer(text_lower):
        for name in match.groupdict():
            if match.group(name) is not None:
                marker_type = 'positive' if name.startswith('pos_') else 'negative'
                markers.append((match.start(), match.end(), marker_type))
                break

    if not markers:
        return [(text_lower, 'default')]

    segments = []
    prev_end = 0
    prev_sentiment = 'default'

    for start, end, sentiment in markers:
        if start > prev_end:
            segment_text = text_lower[prev_end:start].strip()
            if segment_text:
                segments.append((segment_text, prev_sentiment))
        prev_end = end
        prev_sentiment = sentiment

    if prev_end < len(text_lower):
        segment_text = text_lower[prev_end:].strip()
        if segment_text:
            segments.append((segment_text, prev_sentiment))

    return segments if segments else [(text_lower, 'default')]


def find_tags_in_segment(segment: str, sentiment: str, found: set) -> List[Dict[str, str]]:
    """Find category tags in a single segment."""
    tags = []
    for category, markers in CATEGORY_MARKERS.items():
        if category in found:
            continue
        for marker in markers:
            if marker in segment:
                found.add(category)
                subcategory = IMPRESSION_CATEGORIES.get(category, [''])[0]
                tags.append({'category': category, 'subcategory': subcategory, 'sentiment': sentiment})
                break
    return tags


def find_tags(text_lower: str, base_sentiment: str) -> List[Dict[str, str]]:
    """Find category tags in text with segment-aware sentiment."""
    segments = segment_text(text_lower)
    found = set()
    tags = []

    for seg_text, seg_hint in segments:
        sentiment = base_sentiment if seg_hint == 'default' else seg_hint
        segment_tags = find_tags_in_segment(seg_text, sentiment, found)
        tags.extend(segment_tags)

    return tags
