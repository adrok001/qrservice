"""
Тесты анализа тональности.

- Мультиаспектный анализ
- Граничные случаи
- Регрессионные тесты
"""
import unittest

from ..segment_analyzer import find_aspect_tags


class TestMultiAspectAnalysis(unittest.TestCase):
    """Тесты мультиаспектного анализа."""

    def test_multiple_categories_detected(self):
        """Несколько категорий в одном отзыве."""
        tags = find_aspect_tags("Еда вкусная, но официант хамил")
        categories = {t.get("category") for t in tags}
        self.assertIn("Продукт", categories)
        self.assertIn("Сервис", categories)

    def test_mixed_sentiments_preserved(self):
        """Смешанные тональности сохраняются."""
        tags = find_aspect_tags("Еда вкусная, но официант хамил")
        by_cat = {t.get("category"): t.get("sentiment") for t in tags}
        self.assertEqual(by_cat.get("Продукт"), "positive")
        self.assertEqual(by_cat.get("Сервис"), "negative")


class TestEdgeCases(unittest.TestCase):
    """Тесты граничных случаев."""

    def test_category_marker_only(self):
        """Маркер категории без тональности."""
        tags = find_aspect_tags("Заказали пиццу")
        self.assertIsInstance(tags, list)

    def test_cyrillic_only(self):
        """Обрабатываются только кириллические символы."""
        tags = find_aspect_tags("Вкусно! 5/5 stars :)")
        self.assertIsInstance(tags, list)

    def test_long_text(self):
        """Длинный текст обрабатывается."""
        text = "Отличное место. " * 100 + "Еда вкусная."
        tags = find_aspect_tags(text)
        self.assertIsInstance(tags, list)

    def test_special_characters(self):
        """Специальные символы не ломают анализ."""
        for text in ["Еда вкусная!!!", "Сервис... такой", "Цена - 1000р"]:
            self.assertIsInstance(find_aspect_tags(text), list)


class TestRegressions(unittest.TestCase):
    """Регрессионные тесты."""

    def test_ne_vkusno_is_negative(self):
        """'не вкусно' = негатив."""
        tags = find_aspect_tags("Еда не вкусная")
        self.assertTrue(any(t.get("sentiment") == "negative" for t in tags))

    def test_shikarno_is_positive(self):
        """'шикарно' = позитив."""
        tags = find_aspect_tags("Шикарно!")
        self.assertTrue(any(t.get("sentiment") == "positive" for t in tags))

    def test_oficiant_zabyval_is_negative(self):
        """'официант забывал' = негатив."""
        tags = find_aspect_tags("Официант забывал заказы")
        self.assertTrue(any(t.get("sentiment") == "negative" for t in tags))

    def test_vryadli_vernus_is_negative(self):
        """'вряд ли вернусь' = негатив."""
        tags = find_aspect_tags("Вряд ли вернусь сюда")
        self.assertTrue(any(t.get("sentiment") == "negative" for t in tags))

    def test_topchik_is_positive(self):
        """'топчик' = позитив."""
        tags = find_aspect_tags("Еда топчик")
        self.assertTrue(any(t.get("sentiment") == "positive" for t in tags))

    def test_kroshechnye_is_negative(self):
        """'крошечные' = негатив."""
        tags = find_aspect_tags("Порции крошечные")
        self.assertTrue(any(t.get("sentiment") == "negative" for t in tags))

    def test_supper_is_positive(self):
        """'суппер' (опечатка) = позитив."""
        tags = find_aspect_tags("Все суппер")
        self.assertTrue(any(t.get("sentiment") == "positive" for t in tags))


if __name__ == "__main__":
    unittest.main()
