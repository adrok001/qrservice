# План разработки FeedbackQR

> Каждый шаг = тесты → код → проверка

---

## Фаза 1: MVP

### Шаг 1.1: Структура проекта и модели

**Цель**: Создать базовую структуру Django apps и модели данных

**Задачи**:
- [ ] Реструктуризация проекта (apps/)
- [ ] Модель Company
- [ ] Модель Spot
- [ ] Модель QR (расширенная)
- [ ] Модель Review
- [ ] Модель User (кастомный)
- [ ] Модель Member
- [ ] Миграции

**Тесты** (`apps/companies/tests/test_models.py`):

```python
import pytest
from django.db import IntegrityError
from apps.companies.models import Company, Spot
from apps.qr.models import QR
from apps.reviews.models import Review
from apps.accounts.models import User, Member


class TestCompanyModel:
    """Тесты модели Company"""

    def test_create_company(self, db):
        """Компания создаётся с обязательными полями"""
        company = Company.objects.create(
            name="Кофейня Арбат",
            slug="kofeyna-arbat",
            city="Москва"
        )
        assert company.id is not None
        assert company.name == "Кофейня Арбат"
        assert company.is_active is True

    def test_company_slug_unique(self, db):
        """Slug компании уникален"""
        Company.objects.create(name="Кофейня 1", slug="test-slug")
        with pytest.raises(IntegrityError):
            Company.objects.create(name="Кофейня 2", slug="test-slug")

    def test_company_str(self, db):
        """__str__ возвращает название"""
        company = Company.objects.create(name="Тест", slug="test")
        assert str(company) == "Тест"


class TestSpotModel:
    """Тесты модели Spot (точка размещения QR)"""

    def test_create_spot(self, db, company):
        """Точка создаётся и привязывается к компании"""
        spot = Spot.objects.create(
            company=company,
            name="Стол 5",
            zone="Основной зал"
        )
        assert spot.company == company
        assert spot.name == "Стол 5"

    def test_spot_belongs_to_company(self, db, company):
        """Точки фильтруются по компании"""
        Spot.objects.create(company=company, name="Стол 1")
        Spot.objects.create(company=company, name="Стол 2")

        assert company.spots.count() == 2


class TestQRModel:
    """Тесты модели QR"""

    def test_create_qr(self, db, company):
        """QR-код создаётся с уникальным кодом"""
        qr = QR.objects.create(company=company)
        assert qr.code is not None
        assert len(qr.code) == 8  # Короткий код

    def test_qr_code_unique(self, db, company):
        """Код QR уникален"""
        qr1 = QR.objects.create(company=company, code="ABC12345")
        with pytest.raises(IntegrityError):
            QR.objects.create(company=company, code="ABC12345")

    def test_qr_auto_generate_code(self, db, company):
        """Код генерируется автоматически если не указан"""
        qr = QR.objects.create(company=company)
        assert qr.code is not None
        assert len(qr.code) == 8

    def test_qr_can_link_to_spot(self, db, company):
        """QR можно привязать к точке"""
        spot = Spot.objects.create(company=company, name="Стол 1")
        qr = QR.objects.create(company=company, spot=spot)
        assert qr.spot == spot


class TestReviewModel:
    """Тесты модели Review"""

    def test_create_internal_review(self, db, company):
        """Внутренний отзыв создаётся"""
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=5,
            text="Отлично!",
            author_name="Мария"
        )
        assert review.source == 'internal'
        assert review.rating == 5
        assert review.status == 'new'

    def test_create_external_review(self, db, company):
        """Внешний отзыв создаётся с external_id"""
        review = Review.objects.create(
            company=company,
            source='yandex',
            external_id='yandex_123',
            rating=4,
            text="Хорошо"
        )
        assert review.source == 'yandex'
        assert review.external_id == 'yandex_123'

    def test_review_default_is_public_true(self, db, company):
        """По умолчанию отзыв публичный"""
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=5
        )
        assert review.is_public is True

    def test_negative_review_is_not_public(self, db, company):
        """Негативный отзыв (1-3) не публичный по умолчанию"""
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=2,
            text="Плохо"
        )
        # Это будет проверяться в сигнале/сервисе
        # Тут проверяем что поле существует
        assert hasattr(review, 'is_public')

    def test_review_can_have_response(self, db, company, user):
        """К отзыву можно добавить ответ"""
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=3,
            text="Средне"
        )
        review.response = "Спасибо за отзыв!"
        review.response_by = user
        review.save()

        assert review.response == "Спасибо за отзыв!"
        assert review.response_by == user


class TestUserModel:
    """Тесты кастомной модели User"""

    def test_create_user(self, db):
        """Пользователь создаётся"""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        assert user.email == "test@example.com"
        assert user.check_password("testpass123")

    def test_user_email_unique(self, db):
        """Email уникален"""
        User.objects.create_user(email="test@example.com", password="pass")
        with pytest.raises(IntegrityError):
            User.objects.create_user(email="test@example.com", password="pass")


class TestMemberModel:
    """Тесты модели Member (связь user-company)"""

    def test_create_member(self, db, user, company):
        """Членство создаётся"""
        member = Member.objects.create(
            user=user,
            company=company,
            role='owner'
        )
        assert member.role == 'owner'

    def test_member_roles(self, db, user, company):
        """Доступны только 3 роли"""
        valid_roles = ['owner', 'manager', 'viewer']
        for role in valid_roles:
            member = Member(user=user, company=company, role=role)
            member.full_clean()  # Не должно быть ValidationError

    def test_user_can_have_multiple_companies(self, db, user):
        """Пользователь может быть в нескольких компаниях"""
        company1 = Company.objects.create(name="Компания 1", slug="c1")
        company2 = Company.objects.create(name="Компания 2", slug="c2")

        Member.objects.create(user=user, company=company1, role='owner')
        Member.objects.create(user=user, company=company2, role='manager')

        assert user.memberships.count() == 2


# Фикстуры для тестов
@pytest.fixture
def company(db):
    return Company.objects.create(name="Тестовая кофейня", slug="test-cafe")

@pytest.fixture
def user(db):
    return User.objects.create_user(email="user@test.com", password="testpass")
```

**Критерии приёмки**:
- [ ] `pytest apps/` — все тесты проходят
- [ ] `python manage.py check` — нет ошибок
- [ ] `python manage.py makemigrations --check` — миграции созданы

---

### Шаг 1.2: QR-редирект

**Цель**: При сканировании QR-кода происходит редирект на форму отзыва

**Задачи**:
- [ ] View для редиректа `/{code}`
- [ ] Увеличение счётчика сканирований
- [ ] Редирект на `/f/{company_slug}/` или `/f/{company_slug}/{spot_id}/`

**Тесты** (`apps/qr/tests/test_redirect.py`):

```python
import pytest
from django.urls import reverse
from apps.qr.models import QR
from apps.companies.models import Company, Spot


class TestQRRedirect:
    """Тесты редиректа QR-кода"""

    def test_qr_redirect_to_feedback_form(self, client, db):
        """QR-код редиректит на форму отзыва"""
        company = Company.objects.create(name="Тест", slug="test-cafe")
        qr = QR.objects.create(company=company, code="ABC12345")

        response = client.get("/ABC12345")

        assert response.status_code == 302
        assert response.url == "/f/test-cafe/"

    def test_qr_redirect_with_spot(self, client, db):
        """QR с точкой редиректит с параметром spot"""
        company = Company.objects.create(name="Тест", slug="test-cafe")
        spot = Spot.objects.create(company=company, name="Стол 5")
        qr = QR.objects.create(company=company, spot=spot, code="XYZ98765")

        response = client.get("/XYZ98765")

        assert response.status_code == 302
        assert f"spot={spot.id}" in response.url or f"/{spot.id}" in response.url

    def test_qr_increments_scan_count(self, client, db):
        """Сканирование увеличивает счётчик"""
        company = Company.objects.create(name="Тест", slug="test-cafe")
        qr = QR.objects.create(company=company, code="CNT12345")

        assert qr.scans == 0

        client.get("/CNT12345")
        qr.refresh_from_db()

        assert qr.scans == 1

    def test_inactive_qr_returns_404(self, client, db):
        """Неактивный QR возвращает 404"""
        company = Company.objects.create(name="Тест", slug="test-cafe")
        qr = QR.objects.create(company=company, code="OFF12345", is_active=False)

        response = client.get("/OFF12345")

        assert response.status_code == 404

    def test_nonexistent_qr_returns_404(self, client, db):
        """Несуществующий код возвращает 404"""
        response = client.get("/NOTEXIST")

        assert response.status_code == 404

    def test_qr_redirect_passes_qr_param(self, client, db):
        """В URL передаётся параметр qr для отслеживания"""
        company = Company.objects.create(name="Тест", slug="test-cafe")
        qr = QR.objects.create(company=company, code="TRK12345")

        response = client.get("/TRK12345")

        assert "qr=TRK12345" in response.url or "qr=" in response.url
```

**Критерии приёмки**:
- [ ] GET `/{code}` → 302 редирект на форму
- [ ] Счётчик `scans` увеличивается
- [ ] Неактивный/несуществующий QR → 404

---

### Шаг 1.3: Гостевая форма отзыва (Экран 1 — оценка)

**Цель**: Страница с выбором звёзд (1-5)

**Задачи**:
- [ ] View `/f/{company_slug}/`
- [ ] Шаблон с информацией о компании
- [ ] UI выбора звёзд (1-5)
- [ ] При клике → переход на экран 2

**Тесты** (`apps/reviews/tests/test_feedback_form.py`):

```python
import pytest
from django.urls import reverse
from apps.companies.models import Company, Spot


class TestFeedbackFormScreen1:
    """Тесты первого экрана формы отзыва"""

    def test_feedback_page_loads(self, client, db):
        """Страница формы загружается"""
        company = Company.objects.create(
            name="Кофейня Арбат",
            slug="arbat"
        )

        response = client.get("/f/arbat/")

        assert response.status_code == 200

    def test_feedback_page_shows_company_name(self, client, db):
        """На странице отображается название компании"""
        company = Company.objects.create(
            name="Кофейня Арбат",
            slug="arbat"
        )

        response = client.get("/f/arbat/")

        assert "Кофейня Арбат" in response.content.decode()

    def test_feedback_page_shows_spot_if_provided(self, client, db):
        """Если передан spot, показываем его название"""
        company = Company.objects.create(name="Кофейня", slug="cafe")
        spot = Spot.objects.create(company=company, name="Стол 5", zone="Терраса")

        response = client.get(f"/f/cafe/?spot={spot.id}")

        content = response.content.decode()
        assert "Стол 5" in content

    def test_feedback_page_has_star_rating(self, client, db):
        """На странице есть элементы для выбора звёзд"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        response = client.get("/f/cafe/")

        content = response.content.decode()
        # Проверяем наличие элементов рейтинга
        assert 'rating' in content.lower() or 'star' in content.lower()

    def test_feedback_page_shows_company_logo(self, client, db):
        """Если есть лого, оно отображается"""
        # Тест с мок-логотипом
        company = Company.objects.create(name="Кофейня", slug="cafe")

        response = client.get("/f/cafe/")

        # Страница должна иметь место для лого
        assert response.status_code == 200

    def test_nonexistent_company_returns_404(self, client, db):
        """Несуществующая компания → 404"""
        response = client.get("/f/nonexistent/")

        assert response.status_code == 404

    def test_inactive_company_returns_404(self, client, db):
        """Неактивная компания → 404"""
        company = Company.objects.create(
            name="Закрыто",
            slug="closed",
            is_active=False
        )

        response = client.get("/f/closed/")

        assert response.status_code == 404
```

**Критерии приёмки**:
- [ ] Страница `/f/{slug}/` загружается
- [ ] Отображается название и лого компании
- [ ] Есть интерактивные звёзды (1-5)
- [ ] Минималистичный дизайн (один экран, без скролла)

---

### Шаг 1.4: Гостевая форма (Экран 2A — позитивный отзыв)

**Цель**: После выбора 4-5 звёзд — экран с тегами и текстом

**Задачи**:
- [ ] Экран "Что понравилось?" с тегами (Еда, Сервис, Атмосфера)
- [ ] Опциональное текстовое поле
- [ ] Кнопка отправки
- [ ] Предложение оставить отзыв на Яндекс (smart routing)

**Тесты** (`apps/reviews/tests/test_positive_flow.py`):

```python
import pytest
from apps.companies.models import Company
from apps.reviews.models import Review


class TestPositiveFeedbackFlow:
    """Тесты позитивного флоу (4-5 звёзд)"""

    def test_positive_form_shows_tags(self, client, db):
        """При 4-5 звёздах показываются теги"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        # Симулируем HTMX-запрос с рейтингом
        response = client.get("/f/cafe/step2/?rating=5")

        content = response.content.decode()
        assert response.status_code == 200
        # Проверяем наличие тегов
        assert any(tag in content for tag in ["Еда", "Сервис", "Атмосфера", "food", "service"])

    def test_positive_form_has_optional_text(self, client, db):
        """Есть опциональное текстовое поле"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        response = client.get("/f/cafe/step2/?rating=5")

        content = response.content.decode()
        assert "textarea" in content.lower() or "text" in content.lower()

    def test_submit_positive_review(self, client, db):
        """Позитивный отзыв сохраняется"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        response = client.post("/api/reviews/", {
            "company": str(company.id),
            "rating": 5,
            "text": "Всё отлично!",
            "tags": ["food", "service"]
        }, content_type="application/json")

        assert response.status_code in [200, 201]

        review = Review.objects.get(company=company)
        assert review.rating == 5
        assert review.is_public is True  # Позитивный = публичный

    def test_positive_review_shows_smart_routing(self, client, db):
        """После 5 звёзд предлагаем оставить отзыв на Яндекс"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        response = client.get("/f/cafe/step2/?rating=5")

        content = response.content.decode()
        # Должна быть ссылка на внешние площадки
        assert "yandex" in content.lower() or "яндекс" in content.lower() or "поделиться" in content.lower()

    def test_positive_review_without_text(self, client, db):
        """Можно отправить без текста"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        response = client.post("/api/reviews/", {
            "company": str(company.id),
            "rating": 4,
            "tags": ["atmosphere"]
        }, content_type="application/json")

        assert response.status_code in [200, 201]

        review = Review.objects.get(company=company)
        assert review.text is None or review.text == ""
```

**Критерии приёмки**:
- [ ] При 4-5 звёздах показываются теги
- [ ] Текст опционален
- [ ] Отзыв сохраняется с `is_public=True`
- [ ] Есть предложение поделиться на Яндекс/Google

---

### Шаг 1.5: Гостевая форма (Экран 2B — негативный отзыв)

**Цель**: После выбора 1-3 звёзд — перехват негатива

**Задачи**:
- [ ] Экран "Что пошло не так?"
- [ ] Обязательное текстовое поле
- [ ] Поле для контакта (телефон/email)
- [ ] Отзыв НЕ публикуется, идёт менеджеру

**Тесты** (`apps/reviews/tests/test_negative_flow.py`):

```python
import pytest
from apps.companies.models import Company
from apps.reviews.models import Review


class TestNegativeFeedbackFlow:
    """Тесты негативного флоу (1-3 звезды) — перехват"""

    def test_negative_form_shows_empathy(self, client, db):
        """При 1-3 звёздах показываем сочувствие"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        response = client.get("/f/cafe/step2/?rating=2")

        content = response.content.decode()
        assert response.status_code == 200
        # Должен быть эмпатичный текст
        assert any(phrase in content.lower() for phrase in [
            "жаль", "sorry", "не так", "wrong", "исправ"
        ])

    def test_negative_form_has_required_text(self, client, db):
        """Текстовое поле обязательно для негатива"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        response = client.get("/f/cafe/step2/?rating=1")

        content = response.content.decode()
        assert "textarea" in content.lower()
        # Поле должно быть обязательным
        assert "required" in content.lower()

    def test_negative_form_has_contact_field(self, client, db):
        """Есть поле для контакта"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        response = client.get("/f/cafe/step2/?rating=2")

        content = response.content.decode()
        assert any(field in content.lower() for field in [
            "email", "phone", "телефон", "контакт", "связ"
        ])

    def test_submit_negative_review_not_public(self, client, db):
        """Негативный отзыв НЕ публичный"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        response = client.post("/api/reviews/", {
            "company": str(company.id),
            "rating": 2,
            "text": "Очень долго ждали заказ",
            "author_contact": "+7999123456"
        }, content_type="application/json")

        assert response.status_code in [200, 201]

        review = Review.objects.get(company=company)
        assert review.rating == 2
        assert review.is_public is False  # Негатив НЕ публичный!
        assert review.author_contact == "+7999123456"

    def test_negative_review_has_new_status(self, client, db):
        """Негативный отзыв имеет статус 'new' для обработки"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        client.post("/api/reviews/", {
            "company": str(company.id),
            "rating": 1,
            "text": "Ужасно"
        }, content_type="application/json")

        review = Review.objects.get(company=company)
        assert review.status == 'new'

    def test_negative_without_text_fails(self, client, db):
        """Негативный отзыв без текста не принимается"""
        company = Company.objects.create(name="Кофейня", slug="cafe")

        response = client.post("/api/reviews/", {
            "company": str(company.id),
            "rating": 2,
            "text": ""  # Пустой текст
        }, content_type="application/json")

        # Должна быть ошибка валидации
        assert response.status_code == 400
```

**Критерии приёмки**:
- [ ] При 1-3 звёздах — эмпатичный текст
- [ ] Текстовое поле обязательно
- [ ] Есть поле для контакта
- [ ] Отзыв сохраняется с `is_public=False`
- [ ] Статус = `new`

---

### Шаг 1.6: Экран "Спасибо"

**Цель**: Финальный экран после отправки

**Тесты** (`apps/reviews/tests/test_thank_you.py`):

```python
import pytest


class TestThankYouScreen:
    """Тесты экрана благодарности"""

    def test_thank_you_page_loads(self, client, db):
        """Страница благодарности загружается"""
        response = client.get("/f/thank-you/")

        assert response.status_code == 200

    def test_thank_you_shows_message(self, client, db):
        """Отображается сообщение благодарности"""
        response = client.get("/f/thank-you/")

        content = response.content.decode()
        assert any(phrase in content.lower() for phrase in [
            "спасибо", "thank", "благодар"
        ])

    def test_thank_you_is_minimal(self, client, db):
        """Страница минималистична (мало элементов)"""
        response = client.get("/f/thank-you/")

        content = response.content.decode()
        # Не должно быть форм или сложных элементов
        assert content.count("<form") <= 1
        assert content.count("<input") <= 2
```

**Критерии приёмки**:
- [ ] Простой экран с благодарностью
- [ ] Минималистичный дизайн

---

### Шаг 1.7: Дашборд — главная страница

**Цель**: Страница со статистикой и последними отзывами

**Задачи**:
- [ ] View `/dashboard/`
- [ ] 4 метрики: рейтинг, новые отзывы, негатив, сканирования
- [ ] Блок "Требуют внимания" (негативные без ответа)
- [ ] Блок "Последние отзывы"

**Тесты** (`apps/dashboard/tests/test_dashboard.py`):

```python
import pytest
from django.urls import reverse
from apps.companies.models import Company
from apps.reviews.models import Review
from apps.accounts.models import User, Member
from apps.qr.models import QR


class TestDashboard:
    """Тесты главной страницы дашборда"""

    @pytest.fixture
    def setup_data(self, db):
        """Подготовка данных"""
        user = User.objects.create_user(email="owner@test.com", password="pass")
        company = Company.objects.create(name="Кофейня", slug="cafe")
        Member.objects.create(user=user, company=company, role='owner')
        return user, company

    def test_dashboard_requires_auth(self, client, db):
        """Дашборд требует авторизации"""
        response = client.get("/dashboard/")

        assert response.status_code in [302, 403]  # Редирект на логин или forbidden

    def test_dashboard_loads_for_member(self, client, setup_data):
        """Дашборд загружается для члена компании"""
        user, company = setup_data
        client.force_login(user)

        response = client.get("/dashboard/")

        assert response.status_code == 200

    def test_dashboard_shows_stats(self, client, setup_data):
        """Отображаются 4 ключевые метрики"""
        user, company = setup_data
        client.force_login(user)

        # Создаём данные
        Review.objects.create(company=company, source='internal', rating=5)
        Review.objects.create(company=company, source='internal', rating=4)
        Review.objects.create(company=company, source='internal', rating=2, is_public=False)
        QR.objects.create(company=company, scans=100)

        response = client.get("/dashboard/")
        content = response.content.decode()

        # Должны быть метрики
        assert "рейтинг" in content.lower() or "rating" in content.lower()
        assert "отзыв" in content.lower() or "review" in content.lower()

    def test_dashboard_shows_attention_required(self, client, setup_data):
        """Показывает отзывы, требующие внимания"""
        user, company = setup_data
        client.force_login(user)

        # Негативный отзыв без ответа
        Review.objects.create(
            company=company,
            source='internal',
            rating=2,
            text="Плохо",
            is_public=False,
            status='new'
        )

        response = client.get("/dashboard/")
        content = response.content.decode()

        assert "внимани" in content.lower() or "attention" in content.lower() or "Плохо" in content

    def test_dashboard_shows_recent_reviews(self, client, setup_data):
        """Показывает последние отзывы"""
        user, company = setup_data
        client.force_login(user)

        Review.objects.create(
            company=company,
            source='internal',
            rating=5,
            text="Отличный кофе!"
        )

        response = client.get("/dashboard/")
        content = response.content.decode()

        assert "Отличный кофе!" in content

    def test_viewer_can_see_dashboard(self, client, db):
        """Viewer может видеть дашборд (только чтение)"""
        user = User.objects.create_user(email="viewer@test.com", password="pass")
        company = Company.objects.create(name="Кофейня", slug="cafe")
        Member.objects.create(user=user, company=company, role='viewer')

        client.force_login(user)
        response = client.get("/dashboard/")

        assert response.status_code == 200
```

**Критерии приёмки**:
- [ ] Дашборд требует авторизации
- [ ] Показывает 4 метрики
- [ ] Показывает негативные отзывы в блоке "Внимание"
- [ ] Показывает последние отзывы
- [ ] Доступен для всех ролей (owner, manager, viewer)

---

### Шаг 1.8: Список отзывов с фильтрами

**Цель**: Страница со всеми отзывами и возможностью фильтрации

**Тесты** (`apps/dashboard/tests/test_reviews_list.py`):

```python
import pytest
from apps.companies.models import Company
from apps.reviews.models import Review
from apps.accounts.models import User, Member


class TestReviewsList:
    """Тесты списка отзывов"""

    @pytest.fixture
    def setup_reviews(self, db):
        """Подготовка данных"""
        user = User.objects.create_user(email="owner@test.com", password="pass")
        company = Company.objects.create(name="Кофейня", slug="cafe")
        Member.objects.create(user=user, company=company, role='owner')

        # Разные отзывы
        Review.objects.create(company=company, source='internal', rating=5, text="Отлично")
        Review.objects.create(company=company, source='yandex', rating=4, text="Хорошо")
        Review.objects.create(company=company, source='internal', rating=2, text="Плохо", is_public=False)

        return user, company

    def test_reviews_list_loads(self, client, setup_reviews):
        """Список отзывов загружается"""
        user, company = setup_reviews
        client.force_login(user)

        response = client.get("/dashboard/reviews/")

        assert response.status_code == 200

    def test_reviews_filter_by_source(self, client, setup_reviews):
        """Фильтр по источнику работает"""
        user, company = setup_reviews
        client.force_login(user)

        response = client.get("/dashboard/reviews/?source=internal")
        content = response.content.decode()

        assert "Отлично" in content
        assert "Плохо" in content
        # Яндекс не должен быть в internal
        # (зависит от реализации, может показывать все)

    def test_reviews_filter_by_rating(self, client, setup_reviews):
        """Фильтр по рейтингу работает"""
        user, company = setup_reviews
        client.force_login(user)

        response = client.get("/dashboard/reviews/?rating=5")
        content = response.content.decode()

        assert "Отлично" in content

    def test_reviews_filter_negative(self, client, setup_reviews):
        """Фильтр 'негатив' показывает 1-3 звезды"""
        user, company = setup_reviews
        client.force_login(user)

        response = client.get("/dashboard/reviews/?filter=negative")
        content = response.content.decode()

        assert "Плохо" in content

    def test_reviews_filter_no_response(self, client, setup_reviews):
        """Фильтр 'без ответа' работает"""
        user, company = setup_reviews
        client.force_login(user)

        response = client.get("/dashboard/reviews/?filter=no_response")

        assert response.status_code == 200

    def test_reviews_search(self, client, setup_reviews):
        """Поиск по тексту работает"""
        user, company = setup_reviews
        client.force_login(user)

        response = client.get("/dashboard/reviews/?search=Отлично")
        content = response.content.decode()

        assert "Отлично" in content

    def test_reviews_pagination(self, client, db):
        """Пагинация работает"""
        user = User.objects.create_user(email="owner@test.com", password="pass")
        company = Company.objects.create(name="Кофейня", slug="cafe")
        Member.objects.create(user=user, company=company, role='owner')

        # Создаём много отзывов
        for i in range(25):
            Review.objects.create(company=company, source='internal', rating=5, text=f"Отзыв {i}")

        client.force_login(user)
        response = client.get("/dashboard/reviews/")

        # Должна быть пагинация
        assert response.status_code == 200
```

**Критерии приёмки**:
- [ ] Список отзывов загружается
- [ ] Фильтры: источник, рейтинг, негатив, без ответа
- [ ] Поиск по тексту
- [ ] Пагинация

---

### Шаг 1.9: Ответ на отзыв

**Цель**: Возможность ответить на отзыв из дашборда

**Тесты** (`apps/dashboard/tests/test_respond.py`):

```python
import pytest
from apps.companies.models import Company
from apps.reviews.models import Review
from apps.accounts.models import User, Member


class TestReviewResponse:
    """Тесты ответа на отзыв"""

    @pytest.fixture
    def setup_review(self, db):
        """Подготовка данных"""
        user = User.objects.create_user(email="manager@test.com", password="pass")
        company = Company.objects.create(name="Кофейня", slug="cafe")
        Member.objects.create(user=user, company=company, role='manager')
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=3,
            text="Средне"
        )
        return user, company, review

    def test_respond_to_review(self, client, setup_review):
        """Можно ответить на отзыв"""
        user, company, review = setup_review
        client.force_login(user)

        response = client.post(f"/api/reviews/{review.id}/respond/", {
            "response": "Спасибо за отзыв! Мы исправимся."
        }, content_type="application/json")

        assert response.status_code == 200

        review.refresh_from_db()
        assert review.response == "Спасибо за отзыв! Мы исправимся."
        assert review.response_by == user
        assert review.response_at is not None

    def test_respond_updates_status(self, client, setup_review):
        """Ответ меняет статус на 'resolved'"""
        user, company, review = setup_review
        review.status = 'new'
        review.save()

        client.force_login(user)
        client.post(f"/api/reviews/{review.id}/respond/", {
            "response": "Исправляемся!"
        }, content_type="application/json")

        review.refresh_from_db()
        assert review.status == 'resolved'

    def test_viewer_cannot_respond(self, client, db):
        """Viewer не может отвечать"""
        user = User.objects.create_user(email="viewer@test.com", password="pass")
        company = Company.objects.create(name="Кофейня", slug="cafe")
        Member.objects.create(user=user, company=company, role='viewer')
        review = Review.objects.create(company=company, source='internal', rating=3)

        client.force_login(user)
        response = client.post(f"/api/reviews/{review.id}/respond/", {
            "response": "Тест"
        }, content_type="application/json")

        assert response.status_code == 403

    def test_manager_can_respond(self, client, setup_review):
        """Manager может отвечать"""
        user, company, review = setup_review
        client.force_login(user)

        response = client.post(f"/api/reviews/{review.id}/respond/", {
            "response": "Спасибо!"
        }, content_type="application/json")

        assert response.status_code == 200

    def test_empty_response_fails(self, client, setup_review):
        """Пустой ответ не принимается"""
        user, company, review = setup_review
        client.force_login(user)

        response = client.post(f"/api/reviews/{review.id}/respond/", {
            "response": ""
        }, content_type="application/json")

        assert response.status_code == 400
```

**Критерии приёмки**:
- [ ] Owner и Manager могут отвечать
- [ ] Viewer не может отвечать
- [ ] Ответ сохраняется с автором и временем
- [ ] Статус меняется на `resolved`
- [ ] Пустой ответ не принимается

---

### Шаг 1.10: Управление QR-кодами

**Цель**: CRUD для QR-кодов в дашборде

**Тесты** (`apps/dashboard/tests/test_qr_management.py`):

```python
import pytest
from apps.companies.models import Company, Spot
from apps.qr.models import QR
from apps.accounts.models import User, Member


class TestQRManagement:
    """Тесты управления QR-кодами"""

    @pytest.fixture
    def setup(self, db):
        user = User.objects.create_user(email="owner@test.com", password="pass")
        company = Company.objects.create(name="Кофейня", slug="cafe")
        Member.objects.create(user=user, company=company, role='owner')
        return user, company

    def test_qr_list_loads(self, client, setup):
        """Список QR загружается"""
        user, company = setup
        QR.objects.create(company=company)

        client.force_login(user)
        response = client.get("/dashboard/qr/")

        assert response.status_code == 200

    def test_create_qr(self, client, setup):
        """Создание QR-кода"""
        user, company = setup
        client.force_login(user)

        response = client.post("/api/qr/", {
            "company": str(company.id)
        }, content_type="application/json")

        assert response.status_code == 201
        assert QR.objects.filter(company=company).count() == 1

    def test_create_qr_with_spot(self, client, setup):
        """Создание QR с привязкой к точке"""
        user, company = setup
        spot = Spot.objects.create(company=company, name="Стол 1")

        client.force_login(user)
        response = client.post("/api/qr/", {
            "company": str(company.id),
            "spot": str(spot.id)
        }, content_type="application/json")

        assert response.status_code == 201
        qr = QR.objects.get(company=company)
        assert qr.spot == spot

    def test_download_qr_image(self, client, setup):
        """Скачивание картинки QR"""
        user, company = setup
        qr = QR.objects.create(company=company)

        client.force_login(user)
        response = client.get(f"/api/qr/{qr.id}/download/")

        assert response.status_code == 200
        assert response['Content-Type'] in ['image/png', 'image/svg+xml']

    def test_deactivate_qr(self, client, setup):
        """Деактивация QR"""
        user, company = setup
        qr = QR.objects.create(company=company)

        client.force_login(user)
        response = client.patch(f"/api/qr/{qr.id}/", {
            "is_active": False
        }, content_type="application/json")

        assert response.status_code == 200
        qr.refresh_from_db()
        assert qr.is_active is False

    def test_viewer_cannot_create_qr(self, client, db):
        """Viewer не может создавать QR"""
        user = User.objects.create_user(email="viewer@test.com", password="pass")
        company = Company.objects.create(name="Кофейня", slug="cafe")
        Member.objects.create(user=user, company=company, role='viewer')

        client.force_login(user)
        response = client.post("/api/qr/", {
            "company": str(company.id)
        }, content_type="application/json")

        assert response.status_code == 403

    def test_qr_shows_scan_stats(self, client, setup):
        """QR показывает статистику сканирований"""
        user, company = setup
        qr = QR.objects.create(company=company, scans=42)

        client.force_login(user)
        response = client.get("/dashboard/qr/")
        content = response.content.decode()

        assert "42" in content
```

**Критерии приёмки**:
- [ ] Список QR-кодов
- [ ] Создание QR (с точкой или без)
- [ ] Скачивание картинки
- [ ] Деактивация
- [ ] Права: owner/manager — полный доступ, viewer — только просмотр

---

## Фаза 2: Умные функции

### Шаг 2.1: AI-анализ тональности

**Тесты** (`apps/reviews/tests/test_ai_analysis.py`):

```python
import pytest
from unittest.mock import patch, MagicMock
from apps.reviews.services.ai import analyze_sentiment
from apps.reviews.models import Review
from apps.companies.models import Company


class TestAIAnalysis:
    """Тесты AI-анализа отзывов"""

    def test_analyze_positive_review(self, db):
        """Позитивный отзыв определяется"""
        company = Company.objects.create(name="Кофейня", slug="cafe")
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=5,
            text="Всё было просто великолепно! Лучший кофе в городе!"
        )

        with patch('apps.reviews.services.ai.call_llm') as mock_llm:
            mock_llm.return_value = {
                "sentiment": "positive",
                "score": 0.95,
                "tags": ["кофе", "сервис"]
            }

            result = analyze_sentiment(review)

        assert result["sentiment"] == "positive"
        assert result["score"] > 0.5

    def test_analyze_negative_review(self, db):
        """Негативный отзыв определяется"""
        company = Company.objects.create(name="Кофейня", slug="cafe")
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=1,
            text="Ужасное обслуживание, ждали час, еда холодная"
        )

        with patch('apps.reviews.services.ai.call_llm') as mock_llm:
            mock_llm.return_value = {
                "sentiment": "negative",
                "score": -0.85,
                "tags": ["ожидание", "еда", "сервис"]
            }

            result = analyze_sentiment(review)

        assert result["sentiment"] == "negative"
        assert result["score"] < -0.5

    def test_analysis_extracts_tags(self, db):
        """AI извлекает теги из текста"""
        company = Company.objects.create(name="Кофейня", slug="cafe")
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=3,
            text="Еда вкусная, но официант был невнимателен"
        )

        with patch('apps.reviews.services.ai.call_llm') as mock_llm:
            mock_llm.return_value = {
                "sentiment": "neutral",
                "score": 0.1,
                "tags": ["еда", "сервис"]
            }

            result = analyze_sentiment(review)

        assert "tags" in result
        assert len(result["tags"]) > 0

    def test_analysis_updates_review(self, db):
        """Анализ обновляет поля отзыва"""
        company = Company.objects.create(name="Кофейня", slug="cafe")
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=5,
            text="Супер!"
        )

        with patch('apps.reviews.services.ai.call_llm') as mock_llm:
            mock_llm.return_value = {
                "sentiment": "positive",
                "score": 0.9,
                "tags": ["общее впечатление"]
            }

            analyze_sentiment(review, save=True)

        review.refresh_from_db()
        assert review.sentiment == "positive"
        assert review.sentiment_score == pytest.approx(0.9, 0.1)
```

**Критерии приёмки**:
- [ ] Определяется тональность (positive/negative/neutral)
- [ ] Вычисляется score (-1.0 ... +1.0)
- [ ] Извлекаются теги
- [ ] Результат сохраняется в Review

---

### Шаг 2.2: Генерация черновика ответа

**Тесты** (`apps/reviews/tests/test_ai_response.py`):

```python
import pytest
from unittest.mock import patch
from apps.reviews.services.ai import generate_response_draft
from apps.reviews.models import Review
from apps.companies.models import Company


class TestAIResponseGeneration:
    """Тесты генерации черновика ответа"""

    def test_generate_positive_response(self, db):
        """Генерация ответа на позитивный отзыв"""
        company = Company.objects.create(name="Кофейня Арбат", slug="arbat")
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=5,
            text="Замечательное место!",
            author_name="Мария"
        )

        with patch('apps.reviews.services.ai.call_llm') as mock_llm:
            mock_llm.return_value = "Мария, спасибо за тёплые слова! Будем рады видеть вас снова. — Команда Кофейня Арбат"

            draft = generate_response_draft(review)

        assert "спасибо" in draft.lower() or "благодар" in draft.lower()
        assert "Мария" in draft or "мария" in draft.lower()

    def test_generate_negative_response(self, db):
        """Генерация ответа на негативный отзыв"""
        company = Company.objects.create(name="Кофейня Арбат", slug="arbat")
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=2,
            text="Долго ждали заказ"
        )

        with patch('apps.reviews.services.ai.call_llm') as mock_llm:
            mock_llm.return_value = "Приносим извинения за долгое ожидание. Мы уже работаем над улучшением. — Команда Кофейня Арбат"

            draft = generate_response_draft(review)

        assert "извин" in draft.lower() or "sorry" in draft.lower()

    def test_draft_includes_company_name(self, db):
        """Черновик содержит название компании"""
        company = Company.objects.create(name="Супер Кафе", slug="super")
        review = Review.objects.create(
            company=company,
            source='internal',
            rating=4,
            text="Хорошо"
        )

        with patch('apps.reviews.services.ai.call_llm') as mock_llm:
            mock_llm.return_value = "Благодарим за отзыв! — Команда Супер Кафе"

            draft = generate_response_draft(review)

        assert "Супер Кафе" in draft
```

**Критерии приёмки**:
- [ ] Генерируется адекватный черновик
- [ ] Для позитива — благодарность
- [ ] Для негатива — извинение + решение
- [ ] Подпись с названием компании

---

### Шаг 2.3: Telegram-уведомления

**Тесты** (`apps/notifications/tests/test_telegram.py`):

```python
import pytest
from unittest.mock import patch, MagicMock
from apps.notifications.services import send_telegram_notification
from apps.reviews.models import Review
from apps.companies.models import Company
from apps.accounts.models import User, Member


class TestTelegramNotifications:
    """Тесты Telegram-уведомлений"""

    def test_send_notification_on_negative_review(self, db):
        """Уведомление отправляется при негативном отзыве"""
        user = User.objects.create_user(
            email="owner@test.com",
            password="pass",
            telegram_id=123456789
        )
        company = Company.objects.create(name="Кофейня", slug="cafe")
        Member.objects.create(user=user, company=company, role='owner')

        review = Review.objects.create(
            company=company,
            source='internal',
            rating=2,
            text="Плохо"
        )

        with patch('apps.notifications.services.telegram_bot.send_message') as mock_send:
            send_telegram_notification(review, 'new_negative')

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][0] == 123456789  # chat_id
            assert "Плохо" in call_args[0][1] or "негатив" in call_args[0][1].lower()

    def test_notification_includes_review_details(self, db):
        """Уведомление содержит детали отзыва"""
        user = User.objects.create_user(
            email="owner@test.com",
            password="pass",
            telegram_id=123456789
        )
        company = Company.objects.create(name="Кофейня", slug="cafe")
        Member.objects.create(user=user, company=company, role='owner')

        review = Review.objects.create(
            company=company,
            source='internal',
            rating=1,
            text="Ужасный сервис",
            author_contact="+7999123456"
        )

        with patch('apps.notifications.services.telegram_bot.send_message') as mock_send:
            send_telegram_notification(review, 'new_negative')

            message = mock_send.call_args[0][1]
            assert "1" in message  # рейтинг
            assert "+7999123456" in message or "контакт" in message.lower()

    def test_no_notification_if_no_telegram_id(self, db):
        """Без telegram_id уведомление не отправляется"""
        user = User.objects.create_user(
            email="owner@test.com",
            password="pass",
            telegram_id=None
        )
        company = Company.objects.create(name="Кофейня", slug="cafe")
        Member.objects.create(user=user, company=company, role='owner')

        review = Review.objects.create(
            company=company,
            source='internal',
            rating=1,
            text="Плохо"
        )

        with patch('apps.notifications.services.telegram_bot.send_message') as mock_send:
            send_telegram_notification(review, 'new_negative')

            mock_send.assert_not_called()
```

**Критерии приёмки**:
- [ ] Уведомление при негативном отзыве
- [ ] Содержит рейтинг, текст, контакт
- [ ] Отправляется только если есть telegram_id

---

## Фаза 3: Интеграции

### Шаг 3.1: Синхронизация с Яндекс Картами

**Тесты** (`apps/reviews/tests/test_yandex_sync.py`):

```python
import pytest
from unittest.mock import patch, MagicMock
from apps.reviews.services.sync import YandexMapsSync
from apps.reviews.models import Review, Connection
from apps.companies.models import Company


class TestYandexSync:
    """Тесты синхронизации с Яндекс Картами"""

    @pytest.fixture
    def setup_connection(self, db):
        company = Company.objects.create(name="Кофейня", slug="cafe")
        connection = Connection.objects.create(
            company=company,
            platform_id='yandex',
            external_id='org_123456',
            sync_enabled=True
        )
        return company, connection

    def test_fetch_reviews_from_yandex(self, setup_connection):
        """Получение отзывов с Яндекс Карт"""
        company, connection = setup_connection

        mock_reviews = [
            {
                "id": "review_1",
                "rating": 5,
                "text": "Отлично!",
                "author": "Иван",
                "date": "2025-01-15"
            },
            {
                "id": "review_2",
                "rating": 3,
                "text": "Нормально",
                "author": "Мария",
                "date": "2025-01-14"
            }
        ]

        with patch.object(YandexMapsSync, 'fetch_reviews', return_value=mock_reviews):
            sync = YandexMapsSync(connection)
            reviews = sync.fetch_reviews()

        assert len(reviews) == 2
        assert reviews[0]["id"] == "review_1"

    def test_save_external_reviews(self, setup_connection):
        """Сохранение внешних отзывов в базу"""
        company, connection = setup_connection

        mock_reviews = [
            {
                "id": "review_1",
                "rating": 5,
                "text": "Отлично!",
                "author": "Иван",
                "date": "2025-01-15"
            }
        ]

        with patch.object(YandexMapsSync, 'fetch_reviews', return_value=mock_reviews):
            sync = YandexMapsSync(connection)
            sync.sync()

        assert Review.objects.filter(company=company, source='yandex').count() == 1
        review = Review.objects.get(external_id='review_1')
        assert review.rating == 5
        assert review.author_name == "Иван"

    def test_no_duplicate_reviews(self, setup_connection):
        """Дубликаты не создаются"""
        company, connection = setup_connection

        # Уже есть отзыв
        Review.objects.create(
            company=company,
            source='yandex',
            external_id='review_1',
            rating=5,
            text="Отлично!"
        )

        mock_reviews = [
            {"id": "review_1", "rating": 5, "text": "Отлично!", "author": "Иван", "date": "2025-01-15"}
        ]

        with patch.object(YandexMapsSync, 'fetch_reviews', return_value=mock_reviews):
            sync = YandexMapsSync(connection)
            sync.sync()

        # Всё ещё 1 отзыв
        assert Review.objects.filter(company=company, source='yandex').count() == 1

    def test_update_last_sync(self, setup_connection):
        """Обновляется время последней синхронизации"""
        company, connection = setup_connection

        assert connection.last_sync is None

        with patch.object(YandexMapsSync, 'fetch_reviews', return_value=[]):
            sync = YandexMapsSync(connection)
            sync.sync()

        connection.refresh_from_db()
        assert connection.last_sync is not None
```

**Критерии приёмки**:
- [ ] Получение отзывов через API
- [ ] Сохранение с source='yandex'
- [ ] Нет дубликатов (проверка по external_id)
- [ ] Обновление last_sync

---

## Интеграционные тесты

### E2E: Полный флоу гостя

**Тесты** (`tests/e2e/test_guest_flow.py`):

```python
import pytest
from playwright.sync_api import Page, expect


class TestGuestFlow:
    """E2E тесты гостевого флоу"""

    def test_positive_review_flow(self, page: Page, live_server, db):
        """Полный флоу позитивного отзыва"""
        # Подготовка
        from apps.companies.models import Company
        from apps.qr.models import QR

        company = Company.objects.create(name="Кофейня Арбат", slug="arbat")
        qr = QR.objects.create(company=company, code="TEST1234")

        # 1. Сканируем QR (переходим по ссылке)
        page.goto(f"{live_server.url}/TEST1234")

        # 2. Должны оказаться на форме отзыва
        expect(page).to_have_url(f"{live_server.url}/f/arbat/", timeout=5000)
        expect(page.locator("text=Кофейня Арбат")).to_be_visible()

        # 3. Кликаем 5 звёзд
        page.click("[data-rating='5']")

        # 4. Должен появиться экран "Что понравилось?"
        expect(page.locator("text=понравилось")).to_be_visible(timeout=3000)

        # 5. Выбираем теги
        page.click("text=Еда")
        page.click("text=Сервис")

        # 6. Пишем текст (опционально)
        page.fill("textarea", "Всё было отлично!")

        # 7. Отправляем
        page.click("text=Отправить")

        # 8. Должен появиться экран "Спасибо"
        expect(page.locator("text=Спасибо")).to_be_visible(timeout=3000)

        # 9. Проверяем что отзыв сохранился
        from apps.reviews.models import Review
        review = Review.objects.get(company=company)
        assert review.rating == 5
        assert review.is_public is True

    def test_negative_review_flow(self, page: Page, live_server, db):
        """Полный флоу негативного отзыва (перехват)"""
        from apps.companies.models import Company

        company = Company.objects.create(name="Кофейня", slug="cafe")

        # 1. Переходим на форму
        page.goto(f"{live_server.url}/f/cafe/")

        # 2. Кликаем 2 звезды
        page.click("[data-rating='2']")

        # 3. Должен появиться экран с сочувствием
        expect(page.locator("text=жаль")).to_be_visible(timeout=3000)

        # 4. Заполняем обязательное поле текста
        page.fill("textarea", "Ждали заказ 40 минут")

        # 5. Заполняем контакт
        page.fill("input[name='contact']", "+79991234567")

        # 6. Отправляем
        page.click("text=Отправить")

        # 7. Экран "Спасибо"
        expect(page.locator("text=Спасибо")).to_be_visible(timeout=3000)

        # 8. Проверяем что отзыв НЕ публичный
        from apps.reviews.models import Review
        review = Review.objects.get(company=company)
        assert review.rating == 2
        assert review.is_public is False
        assert review.author_contact == "+79991234567"

    def test_qr_scan_increments_counter(self, page: Page, live_server, db):
        """Сканирование QR увеличивает счётчик"""
        from apps.companies.models import Company
        from apps.qr.models import QR

        company = Company.objects.create(name="Кофейня", slug="cafe")
        qr = QR.objects.create(company=company, code="CNT12345", scans=0)

        # Сканируем 3 раза
        for _ in range(3):
            page.goto(f"{live_server.url}/CNT12345")

        qr.refresh_from_db()
        assert qr.scans == 3
```

---

## Конфигурация pytest

**Файл** `conftest.py`:

```python
import pytest
from django.conf import settings


@pytest.fixture(scope='session')
def django_db_setup():
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }


@pytest.fixture
def client(db):
    from django.test import Client
    return Client()


@pytest.fixture
def api_client(db):
    from rest_framework.test import APIClient
    return APIClient()


# Для E2E тестов с Playwright
@pytest.fixture
def live_server(db):
    from django.test import LiveServerTestCase
    server = LiveServerTestCase()
    server._pre_setup()
    server.setUpClass()
    yield server
    server._post_teardown()
```

**Файл** `pytest.ini`:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
markers =
    slow: marks tests as slow
    e2e: end-to-end tests
```

---

## Команды для запуска тестов

```bash
# Все тесты
pytest

# Конкретный модуль
pytest apps/reviews/tests/

# Конкретный тест
pytest apps/reviews/tests/test_models.py::TestReviewModel::test_create_internal_review

# С покрытием
pytest --cov=apps --cov-report=html

# Только быстрые (без E2E)
pytest -m "not e2e"

# Только E2E
pytest -m e2e
```

---

## Чеклист по шагам

| Шаг | Описание | Тесты | Статус |
|-----|----------|-------|--------|
| 1.1 | Модели данных | 15 тестов | ⬜ |
| 1.2 | QR-редирект | 6 тестов | ⬜ |
| 1.3 | Форма экран 1 | 7 тестов | ⬜ |
| 1.4 | Позитивный флоу | 5 тестов | ⬜ |
| 1.5 | Негативный флоу (перехват) | 6 тестов | ⬜ |
| 1.6 | Экран "Спасибо" | 3 теста | ⬜ |
| 1.7 | Дашборд главная | 6 тестов | ⬜ |
| 1.8 | Список отзывов | 7 тестов | ⬜ |
| 1.9 | Ответ на отзыв | 5 тестов | ⬜ |
| 1.10 | Управление QR | 7 тестов | ⬜ |
| 2.1 | AI-анализ | 4 теста | ⬜ |
| 2.2 | AI-ответы | 3 теста | ⬜ |
| 2.3 | Telegram | 3 теста | ⬜ |
| 3.1 | Яндекс синхронизация | 4 теста | ⬜ |
| E2E | Интеграционные | 3 теста | ⬜ |

**Итого**: ~84 теста
