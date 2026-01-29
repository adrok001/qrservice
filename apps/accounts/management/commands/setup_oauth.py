"""Management command to setup OAuth Social Applications."""

from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp


class Command(BaseCommand):
    """Setup OAuth Social Applications for Google and Yandex."""

    help = 'Setup OAuth Social Applications (Google and Yandex)'

    def handle(self, *args, **options):
        """Create or update Social Apps for Google and Yandex."""
        # Get or create Site
        site, _ = Site.objects.get_or_create(
            id=settings.SITE_ID,
            defaults={
                'domain': 'replyq.ru' if 'replyq.ru' in settings.SITE_URL else 'localhost:8000',
                'name': 'ReplyQ'
            }
        )

        # Setup Google OAuth
        google_client_id = settings.SOCIALACCOUNT_PROVIDERS['google']['APP']['client_id']
        google_secret = settings.SOCIALACCOUNT_PROVIDERS['google']['APP']['secret']

        if google_client_id and google_secret:
            google_app, created = SocialApp.objects.update_or_create(
                provider='google',
                defaults={
                    'name': 'Google OAuth',
                    'client_id': google_client_id,
                    'secret': google_secret,
                }
            )
            google_app.sites.add(site)

            action = 'Created' if created else 'Updated'
            self.stdout.write(
                self.style.SUCCESS(f'{action} Google OAuth app')
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Skipping Google OAuth: GOOGLE_OAUTH_CLIENT_ID or '
                    'GOOGLE_OAUTH_CLIENT_SECRET not set in .env'
                )
            )

        # Setup Yandex OAuth
        yandex_client_id = settings.SOCIALACCOUNT_PROVIDERS['yandex']['APP']['client_id']
        yandex_secret = settings.SOCIALACCOUNT_PROVIDERS['yandex']['APP']['secret']

        if yandex_client_id and yandex_secret:
            yandex_app, created = SocialApp.objects.update_or_create(
                provider='yandex',
                defaults={
                    'name': 'Yandex OAuth',
                    'client_id': yandex_client_id,
                    'secret': yandex_secret,
                }
            )
            yandex_app.sites.add(site)

            action = 'Created' if created else 'Updated'
            self.stdout.write(
                self.style.SUCCESS(f'{action} Yandex OAuth app')
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Skipping Yandex OAuth: YANDEX_OAUTH_CLIENT_ID or '
                    'YANDEX_OAUTH_CLIENT_SECRET not set in .env'
                )
            )

        self.stdout.write(
            self.style.SUCCESS('\nOAuth setup complete!')
        )
        self.stdout.write(
            'You can now use /accounts/google/login/ and /accounts/yandex/login/'
        )
