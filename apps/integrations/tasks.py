"""Celery tasks for platform integrations."""

import logging
from uuid import UUID

from celery import shared_task
from django.utils import timezone

from apps.companies.models import Connection, Platform
from apps.reviews.models import Review

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1 minute
)
def sync_google_reviews(self, connection_id: str):
    """
    Sync reviews for a single Google connection.

    Args:
        connection_id: UUID of the Connection object
    """
    try:
        connection = Connection.objects.select_related('company', 'platform').get(
            id=connection_id,
            platform_id='google',
            sync_enabled=True,
        )
    except Connection.DoesNotExist:
        logger.warning(f'Connection {connection_id} not found or not enabled')
        return

    if not connection.is_token_valid and not connection.refresh_token:
        logger.warning(f'No valid token for connection {connection_id}')
        connection.last_sync_status = Connection.SyncStatus.ERROR
        connection.last_sync_error = 'No valid authentication token'
        connection.save(update_fields=['last_sync_status', 'last_sync_error'])
        return

    try:
        from .services import GoogleReviewsService
        service = GoogleReviewsService(connection)
        created, updated = service.sync_reviews_to_db()

        logger.info(
            f'Synced {created + updated} reviews for {connection.company.name}'
        )
    except Exception as e:
        logger.exception(f'Error syncing reviews for connection {connection_id}')
        connection.last_sync_status = Connection.SyncStatus.ERROR
        connection.last_sync_error = str(e)[:500]
        connection.save(update_fields=['last_sync_status', 'last_sync_error'])

        # Retry on transient errors
        raise self.retry(exc=e)


@shared_task
def sync_all_google_reviews():
    """
    Sync reviews for all active Google connections.

    This task is scheduled to run hourly via Celery Beat.
    """
    connections = Connection.objects.filter(
        platform_id='google',
        sync_enabled=True,
    ).values_list('id', flat=True)

    count = 0
    for connection_id in connections:
        sync_google_reviews.delay(str(connection_id))
        count += 1

    logger.info(f'Queued {count} Google review sync tasks')
    return count


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def push_review_reply(self, review_id: str):
    """
    Push a review reply to Google.

    This task is called after a user responds to a Google review
    through our dashboard.

    Args:
        review_id: UUID of the Review object
    """
    try:
        review = Review.objects.select_related('company').get(
            id=review_id,
            source=Review.Source.GOOGLE,
        )
    except Review.DoesNotExist:
        logger.warning(f'Review {review_id} not found or not from Google')
        return

    if not review.response or not review.external_id:
        logger.warning(f'Review {review_id} has no response or external_id')
        return

    # Get Google connection for this company
    try:
        connection = Connection.objects.get(
            company=review.company,
            platform_id='google',
            sync_enabled=True,
        )
    except Connection.DoesNotExist:
        logger.warning(f'No Google connection for company {review.company_id}')
        return

    try:
        from .services import GoogleReviewsService
        service = GoogleReviewsService(connection)
        success = service.reply_to_review(review.external_id, review.response)

        if success:
            logger.info(f'Pushed reply for review {review_id} to Google')
        else:
            raise Exception('Reply failed')

    except Exception as e:
        logger.exception(f'Error pushing reply for review {review_id}')
        raise self.retry(exc=e)


@shared_task
def cleanup_old_sync_errors():
    """
    Clear old sync errors that have been resolved.

    Run weekly to clean up error messages.
    """
    # Clear errors for connections that synced successfully recently
    cutoff = timezone.now() - timezone.timedelta(days=1)
    Connection.objects.filter(
        last_sync__gte=cutoff,
        last_sync_status=Connection.SyncStatus.SUCCESS,
    ).exclude(
        last_sync_error=''
    ).update(last_sync_error='')

    logger.info('Cleaned up old sync errors')
