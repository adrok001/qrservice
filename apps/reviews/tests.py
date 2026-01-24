"""
Интеграционные тесты для анализа отзывов.

Проверяют взаимодействие между модулями:
- dictionaries <-> lemmatizer
- lemmatizer <-> segment_analyzer
- segment_analyzer <-> impression_categories
- segment_analyzer <-> services
"""
import unittest
from typing import List, Dict

# Модули для тестирования
from .dictionaries import (
    NEGATIVE_LEMMAS, POSITIVE_LEMMAS, NEGATABLE_WORDS,
    NEGATIVE_PHRASES, POSITIVE_PHRASES, ADVERB_TO_ADJ,
    PERSONNEL_NEGATIVE_PATTERNS, ASPECT_WAIT_TIME_PATTERNS,
)
from .lemmatizer import get_lemma, lemmatize_text
from .impression_categories import (
    IMPRESSION_CATEGORIES, CATEGORY_LEMMAS, CATEGORY_MARKERS,
    validate_impression_tag,
)
from .segment_analyzer import find_aspect_tags


# ============================================================================
# Блок 1: dictionaries <-> lemmatizer
# ============================================================================

class TestDictionariesLemmatizerIntegration(unittest.TestCase):
    """Интеграция dictionaries.py и lemmatizer.py"""

    def test_negative_lemmas_coverage(self):
        """Большинство NEGATIVE_LEMMAS должны быть валидными леммами."""
        # Некоторые слова сознательно хранятся в формах (виноват, дорогой)
        # для лучшего покрытия реальных отзывов
        valid_count = 0
        for lemma in NEGATIVE_LEMMAS:
            result = get_lemma(lemma)
            if result == lemma:
                valid_count += 1

        coverage = valid_count / len(NEGATIVE_LEMMAS)
        self.assertGreater(coverage, 0.8, f"Покрытие лемм: {coverage:.0%}")

    def test_positive_lemmas_coverage(self):
        """Большинство POSITIVE_LEMMAS должны быть валидными леммами."""
        # Некоторые слова хранятся в вариантах (четкий/чёткий)
        valid_count = 0
        for lemma in POSITIVE_LEMMAS:
            result = get_lemma(lemma)
            if result == lemma:
                valid_count += 1

        coverage = valid_count / len(POSITIVE_LEMMAS)
        self.assertGreater(coverage, 0.8, f"Покрытие лемм: {coverage:.0%}")

    def test_negatable_words_are_valid_lemmas(self):
        """Все NEGATABLE_WORDS должны быть валидными леммами."""
        invalid = []
        for lemma in NEGATABLE_WORDS:
            result = get_lemma(lemma)
            if result != lemma:
                invalid.append((lemma, result))

        self.assertEqual(invalid, [], f"Невалидные леммы: {invalid[:10]}")

    def test_adverb_to_adj_mapping_works(self):
        """ADVERB_TO_ADJ маппит наречия на прилагательные для RuSentiLex."""
        # Наречия часто лемматизируются в прилагательные
        # Маппинг нужен для поиска в RuSentiLex
        for adverb, adj in ADVERB_TO_ADJ.items():
            # Проверяем что значение - прилагательное
            self.assertTrue(adj.endswith(('ый', 'ий', 'ой')),
                          f"{adj} не похоже на прилагательное")

    def test_word_forms_lemmatize_to_dictionary_lemmas(self):
        """Словоформы должны лемматизироваться в леммы из словарей."""
        test_cases = [
            ("ужасная", "ужасный", NEGATIVE_LEMMAS),
            ("вкусное", "вкусный", POSITIVE_LEMMAS),
            ("грубые", "грубый", NEGATIVE_LEMMAS),
            ("шикарные", "шикарный", POSITIVE_LEMMAS),
        ]

        for word_form, expected_lemma, dictionary in test_cases:
            result = get_lemma(word_form)
            self.assertEqual(result, expected_lemma,
                           f"{word_form} -> {result}, ожидали {expected_lemma}")
            self.assertIn(expected_lemma, dictionary,
                         f"{expected_lemma} не в словаре")


# ============================================================================
# Блок 2: segment_analyzer <-> impression_categories
# ============================================================================

class TestSegmentAnalyzerCategoriesIntegration(unittest.TestCase):
    """Интеграция segment_analyzer.py и impression_categories.py"""

    def test_all_returned_categories_exist(self):
        """Все категории из find_aspect_tags существуют в IMPRESSION_CATEGORIES."""
        test_texts = [
            "Еда вкусная",
            "Официант хамил",
            "Долго ждали",
            "Дорого",
            "Уютное место",
        ]

        for text in test_texts:
            tags = find_aspect_tags(text)
            for tag in tags:
                category = tag.get("category")
                self.assertIn(category, IMPRESSION_CATEGORIES,
                            f"Категория '{category}' не существует (текст: {text})")

    def test_all_returned_subcategories_exist(self):
        """Все подкатегории соответствуют своим категориям."""
        test_texts = [
            "Еда была невкусной",
            "Сервис отличный",
            "Очень дорого",
        ]

        for text in test_texts:
            tags = find_aspect_tags(text)
            for tag in tags:
                category = tag.get("category")
                subcategory = tag.get("subcategory")
                valid_subcats = IMPRESSION_CATEGORIES.get(category, [])
                self.assertIn(subcategory, valid_subcats,
                            f"Подкатегория '{subcategory}' не принадлежит '{category}'")

    def test_all_returned_sentiments_valid(self):
        """Все sentiment значения валидны."""
        valid_sentiments = {"positive", "negative", "neutral"}

        test_texts = [
            "Всё отлично!",
            "Ужасное место",
            "Нормально",
        ]

        for text in test_texts:
            tags = find_aspect_tags(text)
            for tag in tags:
                sentiment = tag.get("sentiment")
                self.assertIn(sentiment, valid_sentiments,
                            f"Невалидный sentiment: {sentiment}")


# ============================================================================
# Блок 3: segment_analyzer <-> dictionaries
# ============================================================================

class TestSegmentAnalyzerDictionariesIntegration(unittest.TestCase):
    """Интеграция segment_analyzer.py и dictionaries.py"""

    def test_negative_phrases_detected(self):
        """Негативные фразы из словаря детектируются."""
        test_cases = [
            ("Не рекомендую это место", "negative"),
            ("Больше не приду сюда", "negative"),
        ]

        for text, expected_sentiment in test_cases:
            tags = find_aspect_tags(text)
            self.assertGreater(len(tags), 0, f"Нет тегов для: {text}")
            sentiments = [t.get("sentiment") for t in tags]
            self.assertIn(expected_sentiment, sentiments,
                        f"Ожидали {expected_sentiment} в {sentiments} для: {text}")

    def test_positive_phrases_detected(self):
        """Позитивные фразы из словаря детектируются."""
        test_cases = [
            ("В восторге от этого места", "positive"),
        ]

        for text, expected_sentiment in test_cases:
            tags = find_aspect_tags(text)
            self.assertGreater(len(tags), 0, f"Нет тегов для: {text}")
            sentiments = [t.get("sentiment") for t in tags]
            self.assertIn(expected_sentiment, sentiments,
                        f"Ожидали {expected_sentiment} в {sentiments} для: {text}")

    def test_negation_handling(self):
        """Отрицания обрабатываются корректно."""
        test_cases = [
            ("Не вкусно", "negative"),
            ("Не понравилось", "negative"),
        ]

        for text, expected_sentiment in test_cases:
            tags = find_aspect_tags(text)
            self.assertGreater(len(tags), 0, f"Нет тегов для: {text}")
            sentiments = [t.get("sentiment") for t in tags]
            self.assertIn(expected_sentiment, sentiments,
                        f"Ожидали {expected_sentiment} для отрицания: {text}")

    def test_personnel_patterns_detected(self):
        """Паттерны персонала детектируются."""
        test_cases = [
            "Официант забыл про нас",
            "Официант нахамил",
            "Принесли не то",
        ]

        for text in test_cases:
            tags = find_aspect_tags(text)
            self.assertGreater(len(tags), 0, f"Нет тегов для: {text}")
            sentiments = [t.get("sentiment") for t in tags]
            self.assertIn("negative", sentiments, f"Ожидали negative для: {text}")


# ============================================================================
# Блок 4: Формат выходных данных
# ============================================================================

class TestOutputFormat(unittest.TestCase):
    """Проверка формата выходных данных."""

    def test_find_aspect_tags_returns_list(self):
        """find_aspect_tags возвращает список."""
        result = find_aspect_tags("Тестовый текст")
        self.assertIsInstance(result, list)

    def test_find_aspect_tags_returns_dicts(self):
        """find_aspect_tags возвращает список словарей."""
        result = find_aspect_tags("Вкусная еда")
        for tag in result:
            self.assertIsInstance(tag, dict)

    def test_tag_has_required_fields(self):
        """Каждый тег имеет обязательные поля."""
        required_fields = {"category", "subcategory", "sentiment"}

        result = find_aspect_tags("Отличный сервис")
        for tag in result:
            missing = required_fields - set(tag.keys())
            self.assertEqual(missing, set(), f"Отсутствуют поля: {missing}")

    def test_empty_text_returns_empty_list(self):
        """Пустой текст возвращает пустой список."""
        self.assertEqual(find_aspect_tags(""), [])
        self.assertEqual(find_aspect_tags("   "), [])


# ============================================================================
# Блок 5: Мультиаспектный анализ
# ============================================================================

class TestMultiAspectAnalysis(unittest.TestCase):
    """Тесты мультиаспектного анализа."""

    def test_multiple_categories_detected(self):
        """Несколько категорий детектируются в одном отзыве."""
        text = "Еда вкусная, но официант хамил"
        tags = find_aspect_tags(text)

        categories = {t.get("category") for t in tags}
        self.assertIn("Продукт", categories, "Не найдена категория Продукт")
        self.assertIn("Сервис", categories, "Не найдена категория Сервис")

    def test_mixed_sentiments_preserved(self):
        """Смешанные тональности сохраняются для разных категорий."""
        text = "Еда вкусная, но официант хамил"
        tags = find_aspect_tags(text)

        sentiments_by_cat = {t.get("category"): t.get("sentiment") for t in tags}

        self.assertEqual(sentiments_by_cat.get("Продукт"), "positive",
                        f"Продукт должен быть positive, получили {sentiments_by_cat}")
        self.assertEqual(sentiments_by_cat.get("Сервис"), "negative",
                        f"Сервис должен быть negative, получили {sentiments_by_cat}")


# ============================================================================
# Блок 6: Граничные случаи
# ============================================================================

class TestEdgeCases(unittest.TestCase):
    """Тесты граничных случаев."""

    def test_only_category_marker_no_sentiment(self):
        """Только маркер категории без явной тональности."""
        text = "Заказали пиццу"
        tags = find_aspect_tags(text)
        self.assertIsInstance(tags, list)

    def test_cyrillic_only(self):
        """Только кириллические символы обрабатываются."""
        text = "Вкусно! 5/5 stars :)"
        tags = find_aspect_tags(text)
        self.assertIsInstance(tags, list)

    def test_long_text(self):
        """Длинный текст обрабатывается."""
        text = "Отличное место. " * 100 + "Еда вкусная."
        tags = find_aspect_tags(text)
        self.assertIsInstance(tags, list)

    def test_special_characters(self):
        """Специальные символы не ломают анализ."""
        texts = [
            "Еда вкусная!!!",
            "Сервис... ну такой",
            "Цена - 1000р",
        ]
        for text in texts:
            tags = find_aspect_tags(text)
            self.assertIsInstance(tags, list, f"Ошибка для: {text}")


# ============================================================================
# Блок 7: Регрессионные тесты
# ============================================================================

class TestRegressions(unittest.TestCase):
    """Регрессионные тесты для известных проблем."""

    def test_ne_vkusno_is_negative(self):
        """'не вкусно' должно быть негативным."""
        tags = find_aspect_tags("Еда не вкусная")
        sentiments = [t.get("sentiment") for t in tags]
        self.assertIn("negative", sentiments)

    def test_shikarno_is_positive(self):
        """'шикарно' должно быть позитивным."""
        tags = find_aspect_tags("Шикарно!")
        sentiments = [t.get("sentiment") for t in tags]
        self.assertIn("positive", sentiments)

    def test_oficiant_zabyval_is_negative(self):
        """'официант забывал' должно быть негативным."""
        tags = find_aspect_tags("Официант забывал заказы")
        sentiments = [t.get("sentiment") for t in tags]
        self.assertIn("negative", sentiments)

    def test_vryadli_vernus_is_negative(self):
        """'вряд ли вернусь' должно быть негативным."""
        tags = find_aspect_tags("Вряд ли вернусь сюда")
        sentiments = [t.get("sentiment") for t in tags]
        self.assertIn("negative", sentiments)

    def test_topchik_is_positive(self):
        """'топчик' должно быть позитивным."""
        tags = find_aspect_tags("Еда топчик")
        sentiments = [t.get("sentiment") for t in tags]
        self.assertIn("positive", sentiments)


if __name__ == "__main__":
    unittest.main()
