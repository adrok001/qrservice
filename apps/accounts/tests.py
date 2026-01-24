"""Tests for accounts app."""

from django.test import TestCase, Client
from django.urls import reverse

from .models import User, Member
from apps.companies.models import Company


class RegistrationTests(TestCase):
    """Tests for user registration."""

    def setUp(self):
        self.client = Client()

    def test_registration_page_loads(self):
        """Registration page should load successfully."""
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Зарегистрироваться')

    def test_successful_registration(self):
        """User should be able to register with valid data."""
        data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
        }
        response = self.client.post(reverse('accounts:register'), data)
        self.assertEqual(response.status_code, 302)  # Redirect after success

        # User should be created
        self.assertTrue(User.objects.filter(email='test@example.com').exists())

    def test_registration_with_existing_email(self):
        """Registration should fail with existing email."""
        User.objects.create_user(email='test@example.com', password='pass123')

        data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
        }
        response = self.client.post(reverse('accounts:register'), data)
        self.assertEqual(response.status_code, 200)  # Stay on page with error

    def test_registration_with_short_password(self):
        """Registration should fail with password < 8 chars."""
        data = {
            'email': 'test@example.com',
            'password': 'short',
            'password_confirm': 'short',
        }
        response = self.client.post(reverse('accounts:register'), data)
        self.assertEqual(response.status_code, 200)  # Stay on page with error

    def test_registration_with_mismatched_passwords(self):
        """Registration should fail when passwords don't match."""
        data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'password_confirm': 'different123',
        }
        response = self.client.post(reverse('accounts:register'), data)
        self.assertEqual(response.status_code, 200)  # Stay on page with error


class LoginTests(TestCase):
    """Tests for user login."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    def test_login_page_loads(self):
        """Login page should load successfully."""
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)

    def test_successful_login(self):
        """User should be able to login with valid credentials."""
        data = {
            'email': 'test@example.com',
            'password': 'testpass123',
        }
        response = self.client.post(reverse('accounts:login'), data)
        self.assertEqual(response.status_code, 302)  # Redirect after success

    def test_login_with_wrong_password(self):
        """Login should fail with wrong password."""
        data = {
            'email': 'test@example.com',
            'password': 'wrongpass',
        }
        response = self.client.post(reverse('accounts:login'), data)
        self.assertEqual(response.status_code, 200)  # Stay on page with error


class DataIsolationTests(TestCase):
    """Tests for data isolation between users."""

    def setUp(self):
        # Create two users with their own companies
        self.user1 = User.objects.create_user(
            email='user1@example.com',
            password='pass123'
        )
        self.user2 = User.objects.create_user(
            email='user2@example.com',
            password='pass123'
        )

        self.company1 = Company.objects.create(name='Company 1')
        self.company2 = Company.objects.create(name='Company 2')

        Member.objects.create(user=self.user1, company=self.company1, role=Member.Role.OWNER)
        Member.objects.create(user=self.user2, company=self.company2, role=Member.Role.OWNER)

        self.client = Client()

    def test_user_sees_only_own_companies(self):
        """User should only see their own companies in dashboard."""
        self.client.login(username='user1@example.com', password='pass123')

        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)

        # Should see Company 1 but not Company 2
        self.assertContains(response, 'Company 1')
        self.assertNotContains(response, 'Company 2')

    def test_user_cannot_switch_to_other_company(self):
        """User should not be able to switch to another user's company."""
        self.client.login(username='user1@example.com', password='pass123')

        # Try to switch to company2
        response = self.client.get(
            reverse('dashboard:switch_company', args=[str(self.company2.id)])
        )
        self.assertEqual(response.status_code, 302)

        # Should still be on company1 (or nowhere)
        response = self.client.get(reverse('dashboard:index'))
        self.assertNotContains(response, 'Company 2')
