"""Integration tests for dashboard app."""

import time
from unittest.mock import Mock, patch
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User, Member
from apps.companies.models import Company, Spot
from apps.qr.models import QR
from apps.reviews.models import Review


class DashboardAccessTests(TestCase):
    """Tests for dashboard access control."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='pass123'
        )
        self.company = Company.objects.create(name='Test Co')
        Member.objects.create(
            user=self.user,
            company=self.company,
            role=Member.Role.OWNER
        )

    def test_dashboard_requires_authentication(self):
        """Dashboard should require login."""
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_authenticated_user_can_access_dashboard(self):
        """Authenticated user with company should access dashboard."""
        self.client.login(email='test@example.com', password='pass123')
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_displays_company_data(self):
        """Dashboard should display user's company data."""
        self.client.login(email='test@example.com', password='pass123')
        response = self.client.get(reverse('dashboard:index'))

        self.assertContains(response, self.company.name)


class DashboardQRManagementTests(TestCase):
    """Tests for QR management in dashboard."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='owner@test.com',
            password='pass123'
        )
        self.company = Company.objects.create(name='Cafe Test')
        Member.objects.create(
            user=self.user,
            company=self.company,
            role=Member.Role.OWNER
        )
        self.client.login(email='owner@test.com', password='pass123')

    def test_qr_list_page_loads(self):
        """QR list page should load for authenticated user."""
        response = self.client.get(reverse('dashboard:qr'))
        self.assertEqual(response.status_code, 200)

    def test_qr_create_page_loads(self):
        """QR create page should load."""
        response = self.client.get(reverse('dashboard:qr_create'))
        self.assertEqual(response.status_code, 200)

    def test_qr_creation_via_dashboard(self):
        """User should be able to create QR via dashboard."""
        data = {
            'color': '#FF0000',
            'background': '#FFFFFF',
        }
        response = self.client.post(reverse('dashboard:qr_create'), data)

        # Should redirect after creation
        self.assertEqual(response.status_code, 302)

        # QR should be created
        qr = QR.objects.filter(company=self.company).first()
        self.assertIsNotNone(qr)
        self.assertEqual(qr.color, '#FF0000')
        self.assertEqual(qr.created_by, self.user)

    def test_qr_edit_page_loads(self):
        """QR edit page should load with existing QR."""
        qr = QR.objects.create(company=self.company)
        response = self.client.get(reverse('dashboard:qr_edit', args=[qr.id]))
        self.assertEqual(response.status_code, 200)

    def test_qr_update_via_dashboard(self):
        """User should be able to update QR via dashboard."""
        qr = QR.objects.create(
            company=self.company,
            color='#000000'
        )

        data = {
            'color': '#00FF00',
            'background': '#CCCCCC',
        }
        response = self.client.post(
            reverse('dashboard:qr_edit', args=[qr.id]),
            data
        )

        qr.refresh_from_db()
        self.assertEqual(qr.color, '#00FF00')
        self.assertEqual(qr.background, '#CCCCCC')

    def test_qr_deletion_via_dashboard(self):
        """User should be able to delete QR via dashboard."""
        qr = QR.objects.create(company=self.company)
        qr_id = qr.id

        response = self.client.post(reverse('dashboard:qr_delete', args=[qr.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(QR.objects.filter(id=qr_id).exists())

    def test_user_cannot_access_other_company_qr(self):
        """User should not access QR from different company."""
        other_company = Company.objects.create(name='Other Co')
        other_qr = QR.objects.create(company=other_company)

        response = self.client.get(reverse('dashboard:qr_edit', args=[other_qr.id]))
        self.assertEqual(response.status_code, 404)


class DashboardSettingsTests(TestCase):
    """Tests for company settings management."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='admin@test.com',
            password='pass123'
        )
        self.company = Company.objects.create(name='Settings Test')
        Member.objects.create(
            user=self.user,
            company=self.company,
            role=Member.Role.OWNER
        )
        self.client.login(email='admin@test.com', password='pass123')

    def test_company_settings_page_loads(self):
        """Company settings page should load."""
        response = self.client.get(reverse('dashboard:company_settings'))
        self.assertEqual(response.status_code, 200)

    def test_company_settings_update(self):
        """User should be able to update company settings."""
        data = {
            'name': 'Updated Company Name',
            'address': 'New Address 123',
            'phone': '+7 999 123-45-67',
        }
        response = self.client.post(reverse('dashboard:company_settings'), data)

        self.company.refresh_from_db()
        self.assertEqual(self.company.name, 'Updated Company Name')
        self.assertEqual(self.company.address, 'New Address 123')

    def test_form_settings_page_loads(self):
        """Form settings page should load."""
        response = self.client.get(reverse('dashboard:form_settings'))
        self.assertEqual(response.status_code, 200)

    def test_form_settings_update(self):
        """User should be able to update feedback form settings."""
        data = {
            'title': 'Кастомный заголовок',
            'subtitle': 'Кастомный подзаголовок',
            'bg_color': '#f0f0f0',
        }
        response = self.client.post(reverse('dashboard:form_settings'), data)

        self.company.refresh_from_db()
        settings = self.company.get_feedback_settings()
        self.assertEqual(settings['title'], 'Кастомный заголовок')
        self.assertEqual(settings['bg_color'], '#f0f0f0')


class OAuthIntegrationTests(TestCase):
    """Integration tests for OAuth authentication flow."""

    def setUp(self):
        self.client = Client()

    def test_oauth_user_signup_creates_company(self):
        """OAuth signup should create company and member automatically."""
        from apps.accounts.services.oauth import handle_oauth_signup

        # Create OAuth user
        user = User.objects.create_user(
            email='oauth@test.com',
            first_name='OAuth User'
        )

        # Simulate OAuth signup
        from django.test import RequestFactory
        request = RequestFactory().get('/')
        request.session = {}

        handle_oauth_signup(user, request)

        # Verify company was created
        member = Member.objects.filter(user=user).first()
        self.assertIsNotNone(member)
        self.assertEqual(member.role, Member.Role.OWNER)

        company = member.company
        self.assertIsNotNone(company)
        self.assertIn('OAuth User', company.name)

        # Verify session flags
        self.assertTrue(request.session.get('show_welcome'))
        self.assertEqual(request.session.get('selected_company_id'), str(company.id))

    def test_oauth_auto_link_with_no_password(self):
        """OAuth should auto-link to existing user without password."""
        from apps.accounts.services.oauth import can_auto_link_oauth

        # User without password (OAuth-only)
        user = User.objects.create(email='test@example.com')
        user.set_unusable_password()
        user.save()

        self.assertTrue(can_auto_link_oauth(user))

    def test_oauth_no_auto_link_with_password(self):
        """OAuth should NOT auto-link to user with password."""
        from apps.accounts.services.oauth import can_auto_link_oauth

        # User with password
        user = User.objects.create_user(
            email='test@example.com',
            password='secure123'
        )

        self.assertFalse(can_auto_link_oauth(user))


class DashboardDataIntegrityTests(TestCase):
    """Tests for data integrity across dashboard operations."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='pass123',
            first_name='Test User'
        )
        self.company = Company.objects.create(name='Integration Test Co')
        Member.objects.create(
            user=self.user,
            company=self.company,
            role=Member.Role.OWNER
        )
        self.client.login(email='test@example.com', password='pass123')

    def test_complete_dashboard_workflow(self):
        """Test complete workflow: create QR -> scan -> create review -> view analytics."""
        # 1. Create QR code
        response = self.client.post(reverse('dashboard:qr_create'), {
            'color': '#000000',
            'background': '#FFFFFF',
        })
        self.assertEqual(response.status_code, 302)

        qr = QR.objects.filter(company=self.company).first()
        self.assertIsNotNone(qr)

        # 2. Simulate QR scan (as anonymous user)
        self.client.logout()
        scan_response = self.client.get(f'/{qr.code}')
        self.assertEqual(scan_response.status_code, 302)

        qr.refresh_from_db()
        self.assertEqual(qr.scans, 1)

        # 3. Create review via feedback form
        review = Review.objects.create(
            company=self.company,
            qr=qr,
            rating=5,
            text='Отличное место!',
            author_name='Happy Customer'
        )

        # 4. Login back and view dashboard
        self.client.login(email='test@example.com', password='pass123')
        dashboard_response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(dashboard_response.status_code, 200)

        # Dashboard should show the review data
        reviews_count = Review.objects.filter(company=self.company).count()
        self.assertEqual(reviews_count, 1)

    def test_multi_company_isolation(self):
        """Users should only see data from their own companies."""
        # Create second user with different company
        user2 = User.objects.create_user(
            email='user2@test.com',
            password='pass123'
        )
        company2 = Company.objects.create(name='Company 2')
        Member.objects.create(
            user=user2,
            company=company2,
            role=Member.Role.OWNER
        )

        # Create QR for company 1
        qr1 = QR.objects.create(company=self.company)

        # Create QR for company 2
        qr2 = QR.objects.create(company=company2)

        # User 1 should only see QR 1
        response = self.client.get(reverse('dashboard:qr'))
        qr_list = response.context['qr_codes']
        self.assertIn(qr1, qr_list)
        self.assertNotIn(qr2, qr_list)

        # User 1 should NOT access QR 2
        response = self.client.get(reverse('dashboard:qr_edit', args=[qr2.id]))
        self.assertEqual(response.status_code, 404)


class DashboardPerformanceTests(TestCase):
    """Tests for dashboard performance and N+1 query issues."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='perf@test.com',
            password='pass123'
        )
        self.company = Company.objects.create(name='Perf Test')
        Member.objects.create(
            user=self.user,
            company=self.company,
            role=Member.Role.OWNER
        )
        self.client.login(email='perf@test.com', password='pass123')

    def test_dashboard_with_many_qr_codes(self):
        """Dashboard should handle many QR codes efficiently."""
        # Create 50 QR codes
        for i in range(50):
            QR.objects.create(
                company=self.company,
                created_by=self.user
            )

        # Dashboard should still load fast
        response = self.client.get(reverse('dashboard:qr'))
        self.assertEqual(response.status_code, 200)

        # Should have all QR codes
        qr_list = response.context.get('qr_codes', [])
        self.assertGreaterEqual(len(qr_list), 50)

    def test_dashboard_with_many_reviews(self):
        """Dashboard should handle many reviews efficiently."""
        # Create 100 reviews
        for i in range(100):
            Review.objects.create(
                company=self.company,
                rating=5 if i % 2 == 0 else 3,
                text=f'Review {i}',
                author_name=f'User {i}'
            )

        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)
