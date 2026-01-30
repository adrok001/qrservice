"""Integration tests for companies app."""

from django.test import TestCase
from django.core.exceptions import ValidationError

from apps.accounts.models import User, Member
from .models import Company, Spot


class CompanyModelTests(TestCase):
    """Tests for Company model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test User'
        )

    def test_company_creation(self):
        """Company should be created with auto-generated slug."""
        company = Company.objects.create(
            name='Кафе "У Вани"',
            address='Москва, ул. Ленина, 1'
        )
        self.assertIsNotNone(company.id)
        self.assertEqual(company.slug, 'kafe-u-vani')
        self.assertTrue(company.is_active)

    def test_company_slug_uniqueness(self):
        """Duplicate company names should get unique slugs."""
        company1 = Company.objects.create(name='Test Cafe')
        company2 = Company.objects.create(name='Test Cafe')
        company3 = Company.objects.create(name='Test Cafe')

        self.assertEqual(company1.slug, 'test-cafe')
        self.assertEqual(company2.slug, 'test-cafe-1')
        self.assertEqual(company3.slug, 'test-cafe-2')

    def test_company_feedback_url(self):
        """Company should return correct feedback URL."""
        company = Company.objects.create(name='Test')
        self.assertEqual(company.get_feedback_url(), '/f/test/')

    def test_company_default_feedback_settings(self):
        """Company should return default feedback settings."""
        company = Company.objects.create(name='Test')
        settings = company.get_feedback_settings()

        self.assertEqual(settings['title'], 'Как вам у нас?')
        self.assertTrue(settings['show_internal_form'])
        self.assertEqual(settings['bg_color'], '#f8f9fa')

    def test_company_custom_feedback_settings(self):
        """Company should merge custom settings with defaults."""
        company = Company.objects.create(
            name='Test',
            settings={
                'feedback': {
                    'title': 'Кастомный заголовок',
                    'bg_color': '#ffffff',
                }
            }
        )
        settings = company.get_feedback_settings()

        # Custom settings should override defaults
        self.assertEqual(settings['title'], 'Кастомный заголовок')
        self.assertEqual(settings['bg_color'], '#ffffff')
        # Defaults should still be present
        self.assertTrue(settings['show_internal_form'])

    def test_company_telegram_settings(self):
        """Company should handle Telegram settings correctly."""
        company = Company.objects.create(name='Test')

        # Default settings
        telegram = company.get_telegram_settings()
        self.assertFalse(telegram['enabled'])

        # Set custom settings
        company.set_telegram_settings(
            bot_token='123:ABC',
            chat_id='456',
            enabled=True
        )

        telegram = company.get_telegram_settings()
        self.assertTrue(telegram['enabled'])
        self.assertEqual(telegram['bot_token'], '123:ABC')
        self.assertEqual(telegram['chat_id'], '456')


class MemberIntegrationTests(TestCase):
    """Tests for Member relationships."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='owner@example.com',
            password='pass123',
            first_name='Owner'
        )
        self.company = Company.objects.create(name='Test Company')

    def test_member_creation_as_owner(self):
        """Member should be created with OWNER role."""
        member = Member.objects.create(
            user=self.user,
            company=self.company,
            role=Member.Role.OWNER
        )

        self.assertEqual(member.role, Member.Role.OWNER)
        self.assertEqual(member.user, self.user)
        self.assertEqual(member.company, self.company)

    def test_member_can_switch_companies(self):
        """User can be member of multiple companies."""
        company1 = Company.objects.create(name='Company 1')
        company2 = Company.objects.create(name='Company 2')

        Member.objects.create(user=self.user, company=company1, role=Member.Role.OWNER)
        Member.objects.create(user=self.user, company=company2, role=Member.Role.MANAGER)

        members = Member.objects.filter(user=self.user)
        self.assertEqual(members.count(), 2)

    def test_company_deletion_removes_members(self):
        """Deleting company should remove associated members."""
        Member.objects.create(
            user=self.user,
            company=self.company,
            role=Member.Role.OWNER
        )

        company_id = self.company.id
        self.company.delete()

        # Member should be deleted via CASCADE
        self.assertFalse(Member.objects.filter(company_id=company_id).exists())


class SpotIntegrationTests(TestCase):
    """Tests for Spot model."""

    def setUp(self):
        self.company = Company.objects.create(name='Test Restaurant')

    def test_spot_creation(self):
        """Spot should be created and linked to company."""
        spot = Spot.objects.create(
            company=self.company,
            name='Основной зал',
            description='Главный зал ресторана'
        )

        self.assertEqual(spot.company, self.company)
        self.assertEqual(spot.name, 'Основной зал')
        self.assertTrue(spot.is_active)

    def test_multiple_spots_for_company(self):
        """Company can have multiple spots."""
        Spot.objects.create(company=self.company, name='Зал 1')
        Spot.objects.create(company=self.company, name='Зал 2')
        Spot.objects.create(company=self.company, name='Терраса')

        spots = Spot.objects.filter(company=self.company, is_active=True)
        self.assertEqual(spots.count(), 3)

    def test_spot_deletion_with_company(self):
        """Deleting company should delete associated spots."""
        Spot.objects.create(company=self.company, name='Test Spot')

        company_id = self.company.id
        self.company.delete()

        # Spots should be deleted via CASCADE
        self.assertFalse(Spot.objects.filter(company_id=company_id).exists())


class CompanyDataIntegrityTests(TestCase):
    """Tests for data integrity across companies module."""

    def test_full_company_setup_flow(self):
        """Test complete flow: User -> Company -> Member -> Spot."""
        # 1. Create user
        user = User.objects.create_user(
            email='owner@test.com',
            password='pass123',
            first_name='Owner'
        )

        # 2. Create company
        company = Company.objects.create(
            name='Ресторан "Тест"',
            address='Москва, ул. Тестовая, 1',
            phone='+7 (999) 123-45-67'
        )

        # 3. Create member (owner)
        member = Member.objects.create(
            user=user,
            company=company,
            role=Member.Role.OWNER
        )

        # 4. Create spots
        spot1 = Spot.objects.create(company=company, name='Основной зал')
        spot2 = Spot.objects.create(company=company, name='Летняя терраса')

        # Verify all relationships
        self.assertEqual(company.members.count(), 1)
        self.assertEqual(company.spots.count(), 2)

        # Verify cascade delete
        company.delete()
        self.assertFalse(Member.objects.filter(id=member.id).exists())
        self.assertFalse(Spot.objects.filter(id__in=[spot1.id, spot2.id]).exists())
