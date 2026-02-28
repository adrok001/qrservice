"""Tests for accounts app including bot protection."""

import time
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.urls import reverse

from .models import User, Member
from apps.companies.models import Company


def get_valid_form_data(email='test@example.com', password='testpass123', name='Test User'):
    """Helper to create valid form data with bot protection fields."""
    return {
        'name': name,
        'email': email,
        'password': password,
        'password_confirm': password,
        'website': '',  # Honeypot - must be empty
        '_ts': str(int(time.time()) - 5),  # 5 seconds ago - valid timing
    }


def get_valid_login_data(email='test@example.com', password='testpass123'):
    """Helper to create valid login data with bot protection fields."""
    return {
        'email': email,
        'password': password,
        'website': '',  # Honeypot - must be empty
        '_ts': str(int(time.time()) - 5),  # 5 seconds ago - valid timing
    }


class RegistrationTests(TestCase):
    """Tests for user registration."""

    def setUp(self):
        self.client = Client()

    def test_registration_page_loads(self):
        """Registration page should load successfully."""
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Зарегистрироваться')

    def test_registration_page_contains_bot_protection_fields(self):
        """Registration page should contain honeypot and timestamp fields."""
        response = self.client.get(reverse('accounts:register'))
        self.assertContains(response, 'name="website"')
        self.assertContains(response, 'name="_ts"')

    def test_successful_registration(self):
        """User should be able to register with valid data."""
        data = get_valid_form_data()
        response = self.client.post(reverse('accounts:register'), data)
        self.assertEqual(response.status_code, 302)  # Redirect after success

        # User should be created
        self.assertTrue(User.objects.filter(email='test@example.com').exists())

    def test_registration_with_existing_email(self):
        """Registration should fail with existing email."""
        User.objects.create_user(email='test@example.com', password='pass123')

        data = get_valid_form_data()
        response = self.client.post(reverse('accounts:register'), data)
        self.assertEqual(response.status_code, 200)  # Stay on page with error

    def test_registration_with_short_password(self):
        """Registration should fail with password < 8 chars."""
        data = get_valid_form_data(password='short')
        data['password_confirm'] = 'short'
        response = self.client.post(reverse('accounts:register'), data)
        self.assertEqual(response.status_code, 200)  # Stay on page with error

    def test_registration_with_mismatched_passwords(self):
        """Registration should fail when passwords don't match."""
        data = get_valid_form_data()
        data['password_confirm'] = 'different123'
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

    def test_login_page_contains_bot_protection_fields(self):
        """Login page should contain honeypot and timestamp fields."""
        response = self.client.get(reverse('accounts:login'))
        self.assertContains(response, 'name="website"')
        self.assertContains(response, 'name="_ts"')

    def test_successful_login(self):
        """User should be able to login with valid credentials."""
        data = get_valid_login_data()
        response = self.client.post(reverse('accounts:login'), data)
        self.assertEqual(response.status_code, 302)  # Redirect after success

    def test_login_with_wrong_password(self):
        """Login should fail with wrong password."""
        data = get_valid_login_data(password='wrongpass')
        response = self.client.post(reverse('accounts:login'), data)
        self.assertEqual(response.status_code, 200)  # Stay on page with error


class HoneypotProtectionTests(TestCase):
    """Tests for honeypot bot protection."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='existing@example.com',
            password='testpass123'
        )

    def test_registration_blocked_when_honeypot_filled(self):
        """Registration should be blocked if honeypot field is filled (bot behavior)."""
        data = get_valid_form_data(email='newuser@example.com')
        data['website'] = 'http://spam.com'  # Bot fills this

        response = self.client.post(reverse('accounts:register'), data)

        # Should stay on page (not redirect)
        self.assertEqual(response.status_code, 200)
        # User should NOT be created
        self.assertFalse(User.objects.filter(email='newuser@example.com').exists())

    def test_login_blocked_when_honeypot_filled(self):
        """Login should be blocked if honeypot field is filled (bot behavior)."""
        data = get_valid_login_data(email='existing@example.com')
        data['website'] = 'http://spam.com'  # Bot fills this

        response = self.client.post(reverse('accounts:login'), data)

        # Should stay on page (not redirect)
        self.assertEqual(response.status_code, 200)
        # User should NOT be logged in
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_registration_succeeds_with_empty_honeypot(self):
        """Registration should succeed when honeypot is empty (human behavior)."""
        data = get_valid_form_data(email='human@example.com')
        data['website'] = ''

        response = self.client.post(reverse('accounts:register'), data)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='human@example.com').exists())


class TimeCheckProtectionTests(TestCase):
    """Tests for time-based bot protection."""

    def setUp(self):
        self.client = Client()

    def test_registration_blocked_when_too_fast(self):
        """Registration should be blocked if form submitted too quickly (< 3 seconds)."""
        data = get_valid_form_data(email='fast@example.com')
        data['_ts'] = str(int(time.time()))  # Just now - too fast!

        response = self.client.post(reverse('accounts:register'), data)

        # Should stay on page
        self.assertEqual(response.status_code, 200)
        # User should NOT be created
        self.assertFalse(User.objects.filter(email='fast@example.com').exists())

    def test_registration_blocked_when_form_expired(self):
        """Registration should be blocked if form is too old (> 1 hour)."""
        data = get_valid_form_data(email='slow@example.com')
        data['_ts'] = str(int(time.time()) - 7200)  # 2 hours ago - expired

        response = self.client.post(reverse('accounts:register'), data)

        # Should stay on page
        self.assertEqual(response.status_code, 200)
        # User should NOT be created
        self.assertFalse(User.objects.filter(email='slow@example.com').exists())

    def test_registration_succeeds_with_valid_timing(self):
        """Registration should succeed with valid timing (3s - 1h)."""
        data = get_valid_form_data(email='normal@example.com')
        data['_ts'] = str(int(time.time()) - 10)  # 10 seconds ago - valid

        response = self.client.post(reverse('accounts:register'), data)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='normal@example.com').exists())

    def test_registration_works_without_timestamp(self):
        """Registration should work even without timestamp (graceful degradation)."""
        data = get_valid_form_data(email='notimestamp@example.com')
        del data['_ts']

        response = self.client.post(reverse('accounts:register'), data)

        # Should succeed (timestamp check is optional)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='notimestamp@example.com').exists())


@override_settings(
    RATE_LIMIT_REQUESTS=3,
    RATE_LIMIT_WINDOW=60,
    RATE_LIMIT_PATHS=['/accounts/register/', '/accounts/login/']
)
class RateLimitingTests(TestCase):
    """Tests for rate limiting middleware."""

    def setUp(self):
        self.client = Client()
        # Create user for login tests
        self.user = User.objects.create_user(
            email='ratelimit@example.com',
            password='testpass123'
        )

    def test_rate_limit_blocks_after_threshold(self):
        """Should block requests after exceeding rate limit."""
        url = reverse('accounts:register')

        # Make requests up to limit (3 in test settings)
        for i in range(3):
            data = get_valid_form_data(email=f'user{i}@example.com')
            self.client.post(url, data)

        # Next request should be blocked
        data = get_valid_form_data(email='blocked@example.com')
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email='blocked@example.com').exists())

    def test_rate_limit_allows_get_requests(self):
        """GET requests should not be rate limited."""
        url = reverse('accounts:register')

        # Make many GET requests
        for _ in range(10):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

    def test_rate_limit_per_ip(self):
        """Rate limit should be per IP address."""
        url = reverse('accounts:register')

        # First client makes requests
        client1 = Client(REMOTE_ADDR='1.1.1.1')
        for i in range(3):
            data = get_valid_form_data(email=f'client1_{i}@example.com')
            client1.post(url, data)

        # Second client from different IP should not be blocked
        client2 = Client(REMOTE_ADDR='2.2.2.2')
        data = get_valid_form_data(email='client2@example.com')
        response = client2.post(url, data)

        # Should succeed (different IP)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='client2@example.com').exists())


class IntegrationTests(TestCase):
    """Full integration tests for authentication flow."""

    def setUp(self):
        self.client = Client()

    def test_full_registration_login_logout_flow(self):
        """Test complete user journey: register -> auto-login -> logout -> login."""
        register_url = reverse('accounts:register')
        login_url = reverse('accounts:login')
        logout_url = reverse('accounts:logout')
        dashboard_url = reverse('dashboard:index')

        # 1. Register new user
        reg_data = get_valid_form_data(email='journey@example.com')
        response = self.client.post(register_url, reg_data)
        self.assertEqual(response.status_code, 302)  # Redirect

        # 2. Should be auto-logged in after registration
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)

        # 3. Logout
        response = self.client.get(logout_url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

        # 4. Try accessing dashboard - should redirect to login
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

        # 5. Login again
        login_data = get_valid_login_data(email='journey@example.com')
        response = self.client.post(login_url, login_data)
        self.assertEqual(response.status_code, 302)  # Redirect to dashboard

        # 6. Should be logged in
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_redirected_from_register(self):
        """Logged in user should be redirected away from register page."""
        # Create and login user
        User.objects.create_user(email='loggedin@example.com', password='testpass123')
        self.client.login(username='loggedin@example.com', password='testpass123')

        # Try to access register page
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('dashboard', response.url)

    def test_authenticated_user_redirected_from_login(self):
        """Logged in user should be redirected away from login page."""
        # Create and login user
        User.objects.create_user(email='loggedin@example.com', password='testpass123')
        self.client.login(username='loggedin@example.com', password='testpass123')

        # Try to access login page
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('dashboard', response.url)

    def test_login_with_next_parameter(self):
        """Login should redirect to 'next' URL if provided."""
        User.objects.create_user(email='next@example.com', password='testpass123')

        login_url = reverse('accounts:login') + '?next=/dashboard/reviews/'
        data = get_valid_login_data(email='next@example.com')
        response = self.client.post(login_url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/reviews/')


class BotProtectionIntegrationTests(TestCase):
    """Integration tests combining all bot protection mechanisms."""

    def setUp(self):
        self.client = Client()

    def test_all_protections_pass_for_legitimate_user(self):
        """Legitimate user should pass all bot protections."""
        data = {
            'name': 'Тестовый Пользователь',
            'email': 'legitimate@example.com',
            'password': 'securepass123',
            'password_confirm': 'securepass123',
            'website': '',  # Empty honeypot
            '_ts': str(int(time.time()) - 8),  # 8 seconds - reasonable time
        }

        response = self.client.post(reverse('accounts:register'), data)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='legitimate@example.com').exists())

    def test_bot_with_honeypot_blocked_even_with_valid_timing(self):
        """Bot filling honeypot should be blocked even with valid timing."""
        data = {
            'email': 'bot1@example.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'website': 'http://malicious.com',  # Filled honeypot = bot
            '_ts': str(int(time.time()) - 10),  # Valid timing
        }

        response = self.client.post(reverse('accounts:register'), data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email='bot1@example.com').exists())

    def test_bot_with_fast_submission_blocked_even_with_empty_honeypot(self):
        """Bot submitting too fast should be blocked even with empty honeypot."""
        data = {
            'email': 'bot2@example.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'website': '',  # Empty honeypot
            '_ts': str(int(time.time())),  # Just now = too fast
        }

        response = self.client.post(reverse('accounts:register'), data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email='bot2@example.com').exists())

    def test_error_messages_do_not_reveal_bot_detection(self):
        """Error messages should not reveal that bot was detected."""
        # Bot with honeypot
        data = get_valid_form_data(email='sneaky@example.com')
        data['website'] = 'http://spam.com'

        response = self.client.post(reverse('accounts:register'), data)

        # Response content should not contain bot-related words
        content = response.content.decode('utf-8').lower()
        self.assertNotIn('бот', content)
        self.assertNotIn('bot detected', content)
        self.assertNotIn('honeypot', content)
        # Should show some error (generic message)
        self.assertIn('ошибка', content)


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


class MiddlewareTests(TestCase):
    """Tests for rate limit middleware functionality."""

    def test_middleware_extracts_ip_from_x_forwarded_for(self):
        """Middleware should extract IP from X-Forwarded-For header."""
        from apps.accounts.middleware import RateLimitMiddleware

        class MockRequest:
            META = {'HTTP_X_FORWARDED_FOR': '1.2.3.4, 5.6.7.8'}

        middleware = RateLimitMiddleware(lambda r: None)
        ip = middleware._get_client_ip(MockRequest())

        self.assertEqual(ip, '1.2.3.4')

    def test_middleware_extracts_ip_from_remote_addr(self):
        """Middleware should fall back to REMOTE_ADDR."""
        from apps.accounts.middleware import RateLimitMiddleware

        class MockRequest:
            META = {'REMOTE_ADDR': '9.9.9.9'}

        middleware = RateLimitMiddleware(lambda r: None)
        ip = middleware._get_client_ip(MockRequest())

        self.assertEqual(ip, '9.9.9.9')

    def test_middleware_handles_missing_ip(self):
        """Middleware should handle missing IP gracefully."""
        from apps.accounts.middleware import RateLimitMiddleware

        class MockRequest:
            META = {}

        middleware = RateLimitMiddleware(lambda r: None)
        ip = middleware._get_client_ip(MockRequest())

        self.assertEqual(ip, '0.0.0.0')
