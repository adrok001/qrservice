"""Google Business Profile Reviews API service."""

import logging
from datetime import datetime
from typing import Optional
from dateutil import parser as date_parser

from django.utils import timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from apps.companies.models import Connection
from apps.reviews.models import Review
from .google_auth import GoogleAuthService

logger = logging.getLogger(__name__)


class GoogleReviewsService:
    """
    Service for syncing reviews from Google Business Profile API.

    Usage:
        service = GoogleReviewsService(connection)
        reviews = service.fetch_reviews()
        service.reply_to_review(review_id, "Thank you!")
    """

    API_SERVICE_NAME = 'mybusiness'
    API_VERSION = 'v4'

    def __init__(self, connection: Connection):
        """
        Initialize service with a Connection object.

        Args:
            connection: Connection object with OAuth tokens and Google IDs
        """
        self.connection = connection
        self.auth_service = GoogleAuthService()
        self._client = None

    @property
    def client(self):
        """Get or create Google API client."""
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self):
        """Build Google My Business API client."""
        credentials = self.auth_service.get_credentials(self.connection)
        if not credentials:
            raise ValueError('No valid credentials for this connection')

        return build(
            self.API_SERVICE_NAME,
            self.API_VERSION,
            credentials=credentials,
            cache_discovery=False,
        )

    def fetch_reviews(self, page_size: int = 50) -> list[dict]:
        """
        Fetch all reviews from Google Business Profile.

        Args:
            page_size: Number of reviews per page (max 50)

        Returns:
            List of review dictionaries
        """
        if not self.connection.google_resource_name:
            logger.warning(f'No Google resource name for connection {self.connection.id}')
            return []

        reviews = []
        page_token = None

        try:
            while True:
                request = self.client.accounts().locations().reviews().list(
                    parent=self.connection.google_resource_name,
                    pageSize=min(page_size, 50),
                    pageToken=page_token,
                )
                response = request.execute()

                reviews.extend(response.get('reviews', []))

                page_token = response.get('nextPageToken')
                if not page_token:
                    break

            logger.info(
                f'Fetched {len(reviews)} reviews for connection {self.connection.id}'
            )
            return reviews

        except HttpError as e:
            logger.error(f'Google API error fetching reviews: {e}')
            self._handle_api_error(e)
            return []

    def sync_reviews_to_db(self) -> tuple[int, int]:
        """
        Sync reviews from Google to local database.

        Returns:
            Tuple of (created_count, updated_count)
        """
        google_reviews = self.fetch_reviews()
        created = 0
        updated = 0

        for google_review in google_reviews:
            review, was_created = self._save_review(google_review)
            if was_created:
                created += 1
            else:
                updated += 1

        # Update sync status
        self.connection.last_sync = timezone.now()
        self.connection.last_sync_status = Connection.SyncStatus.SUCCESS
        self.connection.last_sync_error = ''
        self.connection.save(update_fields=[
            'last_sync', 'last_sync_status', 'last_sync_error', 'updated_at'
        ])

        logger.info(
            f'Synced reviews for {self.connection.company.name}: '
            f'{created} created, {updated} updated'
        )
        return created, updated

    def _save_review(self, google_review: dict) -> tuple[Review, bool]:
        """
        Save or update a single review from Google.

        Args:
            google_review: Review data from Google API

        Returns:
            Tuple of (Review object, was_created)
        """
        review_id = google_review.get('reviewId', '')
        reviewer = google_review.get('reviewer', {})
        reply = google_review.get('reviewReply', {})

        # Parse dates
        created_at = self._parse_datetime(google_review.get('createTime'))
        response_at = self._parse_datetime(reply.get('updateTime')) if reply else None

        # Build review URL
        external_url = self._build_review_url(review_id)

        review, created = Review.objects.update_or_create(
            company=self.connection.company,
            source=Review.Source.GOOGLE,
            external_id=review_id,
            defaults={
                'rating': google_review.get('starRating', 0),
                'text': google_review.get('comment', ''),
                'author_name': reviewer.get('displayName', 'Google User'),
                'external_url': external_url,
                'platform_date': created_at,
                'response': reply.get('comment', '') if reply else '',
                'response_at': response_at,
                # Don't overwrite local status if review was processed
                # 'status': Review.Status.NEW if created else review.status,
            }
        )

        return review, created

    def reply_to_review(self, review_id: str, text: str) -> bool:
        """
        Reply to a review on Google.

        Args:
            review_id: Google review ID
            text: Reply text

        Returns:
            True if successful, False otherwise
        """
        if not self.connection.google_resource_name:
            logger.error('No Google resource name configured')
            return False

        try:
            name = f'{self.connection.google_resource_name}/reviews/{review_id}'
            self.client.accounts().locations().reviews().updateReply(
                name=name,
                body={'comment': text}
            ).execute()

            logger.info(f'Posted reply to review {review_id}')
            return True

        except HttpError as e:
            logger.error(f'Failed to reply to review {review_id}: {e}')
            self._handle_api_error(e)
            return False

    def delete_reply(self, review_id: str) -> bool:
        """
        Delete a reply from a review on Google.

        Args:
            review_id: Google review ID

        Returns:
            True if successful, False otherwise
        """
        if not self.connection.google_resource_name:
            return False

        try:
            name = f'{self.connection.google_resource_name}/reviews/{review_id}/reply'
            self.client.accounts().locations().reviews().deleteReply(
                name=name
            ).execute()

            logger.info(f'Deleted reply from review {review_id}')
            return True

        except HttpError as e:
            logger.error(f'Failed to delete reply from review {review_id}: {e}')
            return False

    def _parse_datetime(self, dt_string: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string."""
        if not dt_string:
            return None
        try:
            return date_parser.parse(dt_string)
        except (ValueError, TypeError):
            return None

    def _build_review_url(self, review_id: str) -> str:
        """Build Google Maps review URL."""
        # Google doesn't provide direct review links, use search URL
        if self.connection.external_url:
            return self.connection.external_url
        return ''

    def _handle_api_error(self, error: HttpError):
        """Handle Google API errors and update connection status."""
        error_code = error.resp.status

        if error_code == 401:
            # Token expired or invalid
            self.connection.last_sync_status = Connection.SyncStatus.ERROR
            self.connection.last_sync_error = 'Authentication failed. Please reconnect.'
        elif error_code == 403:
            self.connection.last_sync_status = Connection.SyncStatus.ERROR
            self.connection.last_sync_error = 'Access denied. Check permissions.'
        elif error_code == 429:
            self.connection.last_sync_status = Connection.SyncStatus.ERROR
            self.connection.last_sync_error = 'Rate limit exceeded. Try again later.'
        else:
            self.connection.last_sync_status = Connection.SyncStatus.ERROR
            self.connection.last_sync_error = f'API error: {error_code}'

        self.connection.save(update_fields=[
            'last_sync_status', 'last_sync_error', 'updated_at'
        ])
