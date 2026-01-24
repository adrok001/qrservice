"""Tests for integrations app."""

import json
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.urls import reverse

from apps.accounts.models import User, Member
from apps.companies.models import Company


class TelegramWebhookTests(TestCase):
    """Tests for Telegram webhook endpoint."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    def test_webhook_with_invalid_json(self):
        """Webhook should return 400 for invalid JSON."""
        response = self.client.post(
            reverse('integrations:telegram_webhook'),
            data='invalid json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_webhook_with_no_message(self):
        """Webhook should return OK for updates without message."""
        response = self.client.post(
            reverse('integrations:telegram_webhook'),
            data=json.dumps({'update_id': 123}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

    @patch('apps.integrations.views._send_telegram_confirmation')
    def test_webhook_links_telegram_account(self, mock_send):
        """Webhook should link telegram_id when valid token is provided."""
        # Set up user with link token
        self.user.telegram_link_token = 'valid_token_123'
        self.user.save()

        # Simulate Telegram /start command
        data = {
            'message': {
                'chat': {'id': 12345678},
                'text': '/start valid_token_123'
            }
        }

        response = self.client.post(
            reverse('integrations:telegram_webhook'),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        # User should have telegram_id set
        self.user.refresh_from_db()
        self.assertEqual(self.user.telegram_id, 12345678)
        self.assertIsNone(self.user.telegram_link_token)  # Token should be cleared

    def test_webhook_with_invalid_token(self):
        """Webhook should not link account with invalid token."""
        # User has no token
        data = {
            'message': {
                'chat': {'id': 12345678},
                'text': '/start invalid_token'
            }
        }

        response = self.client.post(
            reverse('integrations:telegram_webhook'),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        # User should not have telegram_id set
        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)


class TelegramConnectTests(TestCase):
    """Tests for Telegram connect/disconnect views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.company = Company.objects.create(name='Test Company')
        Member.objects.create(user=self.user, company=self.company, role=Member.Role.OWNER)

    def test_connect_requires_login(self):
        """Connect view should require authentication."""
        response = self.client.get(reverse('integrations:telegram_connect'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    @override_settings(TELEGRAM_BOT_USERNAME='test_bot')
    def test_connect_generates_token_and_redirects(self):
        """Connect should generate token and redirect to Telegram."""
        self.client.login(username='test@example.com', password='testpass123')

        response = self.client.get(reverse('integrations:telegram_connect'))
        self.assertEqual(response.status_code, 302)

        # User should have a token set
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.telegram_link_token)

        # Should redirect to Telegram
        self.assertIn('t.me', response.url)

    def test_disconnect_removes_telegram_id(self):
        """Disconnect should remove telegram_id."""
        self.user.telegram_id = 12345678
        self.user.save()

        self.client.login(username='test@example.com', password='testpass123')

        response = self.client.post(reverse('integrations:telegram_disconnect'))
        self.assertEqual(response.status_code, 302)

        # User should not have telegram_id
        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)


class NotificationTests(TestCase):
    """Tests for Telegram notifications."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            telegram_id=12345678
        )
        self.company = Company.objects.create(name='Test Company')
        Member.objects.create(user=self.user, company=self.company, role=Member.Role.OWNER)

    @patch('apps.notifications.telegram.send_telegram_message')
    @override_settings(TELEGRAM_BOT_TOKEN='test_token')
    def test_notify_negative_review_sends_to_members(self, mock_send):
        """Notification should be sent to all members with telegram_id."""
        from apps.reviews.models import Review
        from apps.notifications.telegram import notify_negative_review

        mock_send.return_value = True

        # Create a review
        review = Review.objects.create(
            company=self.company,
            rating=2,
            text='Bad service',
            author_name='John'
        )

        result = notify_negative_review(review)

        self.assertTrue(result)
        mock_send.assert_called_once()

        # Check the call arguments
        call_args = mock_send.call_args
        self.assertEqual(call_args[0][0], 'test_token')  # bot_token
        self.assertEqual(call_args[0][1], '12345678')  # chat_id (telegram_id)

    @patch('apps.notifications.telegram.send_telegram_message')
    @override_settings(TELEGRAM_BOT_TOKEN='test_token')
    def test_notify_no_telegram_members(self, mock_send):
        """Notification should return False if no members have telegram_id."""
        from apps.reviews.models import Review
        from apps.notifications.telegram import notify_negative_review

        # Remove telegram_id from user
        self.user.telegram_id = None
        self.user.save()

        review = Review.objects.create(
            company=self.company,
            rating=2,
            text='Bad service',
            author_name='John'
        )

        result = notify_negative_review(review)

        self.assertFalse(result)
        mock_send.assert_not_called()
