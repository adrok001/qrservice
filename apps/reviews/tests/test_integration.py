"""
Интеграционные тесты: взаимодействие модулей.

- dictionaries <-> lemmatizer
- segment_analyzer <-> impression_categories
- segment_analyzer <-> dictionaries
- Формат выходных данных
"""
import unittest

from ..dictionaries import (
    NEGATIVE_LEMMAS, POSITIVE_LEMMAS, NEGATABLE_WORDS, ADVERB_TO_ADJ,
)
from ..lemmatizer import get_lemma
from ..impression_categories import IMPRESSION_CATEGORIES
from ..segment_analyzer import find_aspect_tags


class TestDictionariesLemmatizer(unittest.TestCase):
    """Интеграция dictionaries.py и lemmatizer.py"""

    def test_negative_lemmas_coverage(self):
        """Большинство NEGATIVE_LEMMAS должны быть валидными леммами."""
        valid_count = sum(1 for l in NEGATIVE_LEMMAS if get_lemma(l) == l)
        coverage = valid_count / len(NEGATIVE_LEMMAS)
        self.assertGreater(coverage, 0.8)

    def test_positive_lemmas_coverage(self):
        """Большинство POSITIVE_LEMMAS должны быть валидными леммами."""
        valid_count = sum(1 for l in POSITIVE_LEMMAS if get_lemma(l) == l)
        coverage = valid_count / len(POSITIVE_LEMMAS)
        self.assertGreater(coverage, 0.8)

    def test_negatable_words_are_valid_lemmas(self):
        """Все NEGATABLE_WORDS должны быть валидными леммами."""
        invalid = [(l, get_lemma(l)) for l in NEGATABLE_WORDS if get_lemma(l) != l]
        self.assertEqual(invalid, [])

    def test_adverb_to_adj_mapping(self):
        """ADVERB_TO_ADJ маппит наречия на прилагательные."""
        for adj in ADVERB_TO_ADJ.values():
            self.assertTrue(adj.endswith(('ый', 'ий', 'ой')))

    def test_word_forms_lemmatize_correctly(self):
        """Словоформы лемматизируются в слова из словарей."""
        cases = [
            ("ужасная", "ужасный", NEGATIVE_LEMMAS),
            ("вкусное", "вкусный", POSITIVE_LEMMAS),
        ]
        for word, expected, dictionary in cases:
            self.assertEqual(get_lemma(word), expected)
            self.assertIn(expected, dictionary)


class TestSegmentAnalyzerCategories(unittest.TestCase):
    """Интеграция segment_analyzer.py и impression_categories.py"""

    def test_returned_categories_exist(self):
        """Все категории существуют в IMPRESSION_CATEGORIES."""
        for text in ["Еда вкусная", "Официант хамил", "Дорого"]:
            for tag in find_aspect_tags(text):
                self.assertIn(tag.get("category"), IMPRESSION_CATEGORIES)

    def test_returned_subcategories_exist(self):
        """Подкатегории соответствуют категориям."""
        for text in ["Еда невкусная", "Сервис отличный"]:
            for tag in find_aspect_tags(text):
                cat = tag.get("category")
                subcat = tag.get("subcategory")
                self.assertIn(subcat, IMPRESSION_CATEGORIES.get(cat, []))

    def test_returned_sentiments_valid(self):
        """Все sentiment значения валидны."""
        valid = {"positive", "negative", "neutral"}
        for text in ["Отлично!", "Ужасно", "Нормально"]:
            for tag in find_aspect_tags(text):
                self.assertIn(tag.get("sentiment"), valid)


class TestSegmentAnalyzerDictionaries(unittest.TestCase):
    """Интеграция segment_analyzer.py и dictionaries.py"""

    def test_negative_phrases_detected(self):
        """Негативные фразы детектируются."""
        for text in ["Не рекомендую", "Больше не приду"]:
            tags = find_aspect_tags(text)
            self.assertTrue(any(t.get("sentiment") == "negative" for t in tags))

    def test_positive_phrases_detected(self):
        """Позитивные фразы детектируются."""
        tags = find_aspect_tags("В восторге")
        self.assertTrue(any(t.get("sentiment") == "positive" for t in tags))

    def test_negation_handling(self):
        """Отрицания обрабатываются корректно."""
        for text in ["Не вкусно", "Не понравилось"]:
            tags = find_aspect_tags(text)
            self.assertTrue(any(t.get("sentiment") == "negative" for t in tags))

    def test_personnel_patterns_detected(self):
        """Паттерны персонала детектируются."""
        for text in ["Официант забыл", "Официант нахамил"]:
            tags = find_aspect_tags(text)
            self.assertTrue(any(t.get("sentiment") == "negative" for t in tags))


class TestOutputFormat(unittest.TestCase):
    """Проверка формата выходных данных."""

    def test_returns_list(self):
        """find_aspect_tags возвращает список."""
        self.assertIsInstance(find_aspect_tags("Тест"), list)

    def test_returns_dicts(self):
        """Элементы — словари."""
        for tag in find_aspect_tags("Вкусная еда"):
            self.assertIsInstance(tag, dict)

    def test_has_required_fields(self):
        """Теги имеют обязательные поля."""
        required = {"category", "subcategory", "sentiment"}
        for tag in find_aspect_tags("Отличный сервис"):
            self.assertEqual(required - set(tag.keys()), set())

    def test_empty_text_returns_empty(self):
        """Пустой текст — пустой список."""
        self.assertEqual(find_aspect_tags(""), [])
        self.assertEqual(find_aspect_tags("   "), [])


if __name__ == "__main__":
    unittest.main()
