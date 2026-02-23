"""Yandex Business Reviews service — fetch and reply via session cookies."""

import json
import logging
import re
from datetime import datetime
from typing import Optional

import requests
from datetime import timezone as dt_timezone

from django.utils import timezone

from apps.companies.models import Connection
from apps.reviews.models import Review

logger = logging.getLogger(__name__)

# Minimum cookies required for Yandex Business session
REQUIRED_COOKIES = ['Session_id', 'sessionid2', 'yandexuid']

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/145.0.0.0 Safari/537.36'
)


class YandexSessionError(Exception):
    """Raised when Yandex session is invalid or expired."""


class YandexReviewsService:
    """
    Service for syncing reviews from Yandex Business (Яндекс Бизнес).

    Authentication: session cookies from browser (no official API).
    Cookies are stored as JSON in Connection.access_token.

    Usage:
        service = YandexReviewsService(connection)
        created, updated = service.sync_reviews_to_db()
        service.reply_to_review(external_id, "Спасибо!")
    """

    BASE_URL = 'https://yandex.ru/sprav'
    REVIEWS_PER_PAGE = 20  # Yandex default

    def __init__(self, connection: Connection):
        self.connection = connection
        self.company_id = connection.external_id  # Yandex org ID
        self._session: Optional[requests.Session] = None
        self._cookies: dict = {}
        self._first_page_html: Optional[str] = None
        self._pager: dict = {}
        self._load_cookies()

    def _load_cookies(self):
        """Load cookies from connection.access_token (JSON string)."""
        if not self.connection.access_token:
            raise YandexSessionError('No cookies stored in connection')
        try:
            self._cookies = json.loads(self.connection.access_token)
        except json.JSONDecodeError:
            raise YandexSessionError('Invalid cookies JSON in connection')

        missing = [c for c in REQUIRED_COOKIES if c not in self._cookies]
        if missing:
            raise YandexSessionError(f'Missing required cookies: {", ".join(missing)}')

    @property
    def session(self) -> requests.Session:
        """Get or create requests session with cookies."""
        if self._session is None:
            self._session = requests.Session()
            self._session.cookies.update(self._cookies)
            self._session.headers.update({'user-agent': USER_AGENT})
        return self._session

    def check_session_valid(self) -> bool:
        """Check if cookies are still valid by loading the reviews page."""
        try:
            html = self._fetch_reviews_html(page=1)
            return '"items"' in html
        except Exception:
            return False

    def fetch_reviews(self, max_pages: int = 10) -> list[dict]:
        """
        Fetch all reviews from Yandex Business.

        Returns list of parsed review dicts.
        """
        all_reviews = []
        total = None

        for page in range(1, max_pages + 1):
            try:
                html = self._fetch_reviews_html(page=page)
            except (YandexSessionError, Exception) as e:
                logger.warning(
                    f'Stopped fetching at page {page}: {e}. '
                    f'Returning {len(all_reviews)} reviews fetched so far.'
                )
                break

            reviews, pager = self._parse_reviews_from_html(html)

            # Cache first page data for platform rating extraction
            if page == 1:
                self._first_page_html = html
                self._pager = pager

            if not reviews:
                break

            all_reviews.extend(reviews)

            # Check if there are more pages
            if total is None and pager:
                total = pager.get('total', 0)

            if total and len(all_reviews) >= total:
                break

        logger.info(
            f'Fetched {len(all_reviews)} reviews for Yandex org {self.company_id}'
        )
        return all_reviews

    def sync_reviews_to_db(self) -> tuple[int, int]:
        """
        Sync reviews from Yandex to local database.

        Returns:
            Tuple of (created_count, updated_count)
        """
        yandex_reviews = self.fetch_reviews()
        created = 0
        updated = 0

        for review_data in yandex_reviews:
            review, was_created = self._save_review(review_data)
            if was_created:
                created += 1
            else:
                updated += 1

        # Update platform rating from cached first-page HTML
        self._update_platform_rating()

        # Update sync status
        self.connection.last_sync = timezone.now()
        self.connection.last_sync_status = Connection.SyncStatus.SUCCESS
        self.connection.last_sync_error = ''
        self.connection.save(update_fields=[
            'last_sync', 'last_sync_status', 'last_sync_error',
            'platform_rating', 'platform_review_count', 'updated_at',
        ])

        logger.info(
            f'Synced Yandex reviews for {self.connection.company.name}: '
            f'{created} created, {updated} updated'
        )
        return created, updated

    def reply_to_review(self, external_id: str, text: str) -> bool:
        """
        Reply to a review on Yandex.

        Args:
            external_id: Yandex review ID (cmnt_entity_id)
            text: Reply text

        Returns:
            True if successful
        """
        # Need to fetch the page to get fresh CSRF tokens
        html = self._fetch_reviews_html(page=1)
        csrf_tokens = self._find_csrf_tokens(html)

        x_csrf = csrf_tokens.get('x-csrf-token')
        reviews_csrf = csrf_tokens.get('reviewsCsrfToken')

        if not x_csrf or not reviews_csrf:
            logger.error('Could not extract CSRF tokens for reply')
            return False

        # Find the per-review answer token
        answer_token = self._find_answer_token(html, external_id)
        if not answer_token:
            # Review might be on a different page, fetch all pages
            answer_token = self._find_answer_token_all_pages(external_id)
            if not answer_token:
                logger.error(f'Could not find answer token for review {external_id}')
                return False

        url = f'{self.BASE_URL}/api/ugcpub/business-answer'
        headers = {
            'accept': 'application/json; charset=UTF-8',
            'content-type': 'application/json; charset=UTF-8',
            'origin': 'https://yandex.ru',
            'x-requested-with': 'XMLHttpRequest',
            'x-csrf-token': x_csrf,
            'referer': (
                f'{self.BASE_URL}/{self.company_id}/p/edit/reviews/'
                f'?ranking=by_time&page=1&type=company'
            ),
        }
        body = {
            'reviewId': external_id,
            'text': text,
            'answerCsrfToken': answer_token,
            'reviewsCsrfToken': reviews_csrf,
        }

        resp = self.session.post(url, json=body, headers=headers)

        if resp.status_code == 200:
            logger.info(f'Posted reply to Yandex review {external_id}')
            return True

        logger.error(
            f'Failed to reply to Yandex review {external_id}: '
            f'status={resp.status_code}, body={resp.text[:200]}'
        )
        return False

    # --- Private methods ---

    def _update_platform_rating(self):
        """Extract org rating from cached first-page HTML and update connection."""
        html = self._first_page_html
        if not html:
            return

        # Review count from pager
        if self._pager.get('total'):
            self.connection.platform_review_count = self._pager['total']

        # Org-level rating — try several known patterns
        rating = self._parse_org_rating(html)
        if rating:
            from decimal import Decimal
            self.connection.platform_rating = Decimal(str(rating))
            logger.info(
                f'Platform rating for {self.connection.company.name}: '
                f'{rating} ({self.connection.platform_review_count} reviews)'
            )

    @staticmethod
    def _parse_org_rating(html: str) -> Optional[float]:
        """Try to extract the organization's overall rating from HTML."""
        patterns = [
            # "rating":4.9},"tdsCompany" — org rating near tdsCompany block
            r'"rating"\s*:\s*(\d\.\d)\s*\}\s*,\s*"tdsCompany"',
            # "orgRating":4.9
            r'"orgRating"\s*:\s*(\d\.\d)',
            # "averageGrade":4.9
            r'"averageGrade"\s*:\s*(\d\.?\d?)',
            # "totalScore":4.9
            r'"totalScore"\s*:\s*(\d\.\d)',
            # "rating":{"value":4.9, ...}  (org-level, not review-level)
            r'"rating"\s*:\s*\{\s*"value"\s*:\s*(\d\.\d)',
            # "ratingValue":"4.9"
            r'"ratingValue"\s*:\s*"(\d\.\d)"',
        ]
        for pattern in patterns:
            m = re.search(pattern, html)
            if m:
                val = float(m.group(1))
                if 1.0 <= val <= 5.0:
                    return val
        return None

    def _fetch_reviews_html(self, page: int = 1) -> str:
        """Fetch reviews page HTML."""
        url = f'{self.BASE_URL}/{self.company_id}/p/edit/reviews/'
        params = {'ranking': 'by_time', 'page': page, 'type': 'company'}

        resp = self.session.get(url, params=params)
        resp.raise_for_status()

        if '"items"' not in resp.text:
            raise YandexSessionError(
                'Reviews page does not contain items — session likely expired'
            )

        return resp.text

    def _parse_reviews_from_html(self, html: str) -> tuple[list[dict], dict]:
        """
        Parse reviews and pager from HTML.

        Returns:
            Tuple of (reviews_list, pager_dict)
        """
        reviews = []

        # Extract pager: "pager":{"limit":20,"offset":0,"total":16}
        pager = {}
        pager_match = re.search(
            r'"pager"\s*:\s*\{"limit"\s*:\s*(\d+)\s*,'
            r'\s*"offset"\s*:\s*(\d+)\s*,'
            r'\s*"total"\s*:\s*(\d+)\s*\}',
            html
        )
        if pager_match:
            pager = {
                'limit': int(pager_match.group(1)),
                'offset': int(pager_match.group(2)),
                'total': int(pager_match.group(3)),
            }

        # Find all review IDs and their tokens
        review_ids = re.findall(r'"cmnt_entity_id"\s*:\s*"([^"]+)"', html)
        tokens = re.findall(r'"business_answer_csrf_token"\s*:\s*"([^"]+)"', html)

        for rid, token in zip(review_ids, tokens):
            review_data = self._extract_review_data(html, rid, token)
            if review_data:
                reviews.append(review_data)

        return reviews, pager

    def _extract_review_data(self, html: str, review_id: str, token: str) -> Optional[dict]:
        """Extract a single review's data from HTML context."""
        pos = html.find(f'"cmnt_entity_id":"{review_id}"')
        if pos < 0:
            return None

        # Get context: 3000 chars before (contains review data)
        start = max(0, pos - 3000)
        end = min(len(html), pos + 200)
        chunk = html[start:end]

        # Find the boundary of THIS review's data by locating
        # the previous review's cmnt_entity_id in the chunk.
        # Everything after it belongs to the current review.
        review_offset = 0
        current_cmnt_marker = f'"cmnt_entity_id":"{review_id}"'
        current_cmnt_pos = chunk.find(current_cmnt_marker)
        if current_cmnt_pos > 0:
            # Find any cmnt_entity_id BEFORE the current one
            prev_cmnt = chunk.rfind('"cmnt_entity_id"', 0, current_cmnt_pos)
            if prev_cmnt >= 0:
                review_offset = prev_cmnt + 80  # skip past previous review's tail

        # Use only this review's data for field extraction
        review_chunk = chunk[review_offset:]

        # Author name and profile URL
        author = 'Пользователь Яндекс'
        author_profile_url = ''
        author_match = re.search(
            r'"author"\s*:\s*\{[^}]*"user"\s*:\s*"([^"]+)"', review_chunk
        )
        if author_match:
            author = author_match.group(1)

        public_id_match = re.search(
            r'"public_id"\s*:\s*"([^"]+)"', review_chunk
        )
        if public_id_match:
            author_profile_url = (
                f'https://yandex.ru/maps/user/{public_id_match.group(1)}'
            )

        # Review text (snippet or full_text)
        text = ''
        for field in ['full_text', 'snippet']:
            text_match = re.search(
                rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)"', review_chunk
            )
            if text_match:
                text = text_match.group(1)
                text = self._decode_text(text)
                break

        # Rating
        rating = 5
        rating_match = re.search(r'"rating"\s*:\s*(\d)', review_chunk)
        if rating_match:
            rating = int(rating_match.group(1))

        # Created timestamp (ms) — use time_created that is NOT inside owner_comment
        platform_date = None
        oc_pos = review_chunk.find('"owner_comment"')
        # Search for time_created only before owner_comment (review's own date)
        search_area = review_chunk[:oc_pos] if oc_pos > 0 else review_chunk
        time_match = re.search(r'"time_created"\s*:\s*(\d{13})', search_area)
        if time_match:
            ts_ms = int(time_match.group(1))
            platform_date = datetime.fromtimestamp(ts_ms / 1000, tz=dt_timezone.utc)

        # Owner response
        response = ''
        oc_match = re.search(
            r'"owner_comment"\s*:\s*\{[^}]*"text"\s*:\s*"((?:[^"\\]|\\.)*)"',
            review_chunk
        )
        if oc_match:
            response = self._decode_text(oc_match.group(1))

        # Response date
        response_at = None
        oc_time_match = re.search(
            r'"owner_comment"\s*:\s*\{"time_created"\s*:\s*(\d{13})', review_chunk
        )
        if oc_time_match:
            ts_ms = int(oc_time_match.group(1))
            response_at = datetime.fromtimestamp(ts_ms / 1000, tz=dt_timezone.utc)

        # Decode token
        token_decoded = self._decode_unicode_escapes(token)

        return {
            'external_id': review_id,
            'author_name': author,
            'author_profile_url': author_profile_url,
            'text': text,
            'rating': rating,
            'platform_date': platform_date,
            'response': response,
            'response_at': response_at,
            'answer_csrf_token': token_decoded,
        }

    def _save_review(self, review_data: dict) -> tuple[Review, bool]:
        """Save or update a single review from Yandex."""
        external_url = (
            f'https://yandex.ru/maps/org/{self.company_id}/reviews/'
        )

        defaults = {
            'rating': review_data['rating'],
            'text': review_data['text'],
            'author_name': review_data['author_name'],
            'author_contact': review_data.get('author_profile_url', ''),
            'external_url': external_url,
            'platform_date': review_data['platform_date'],
        }

        # Only update response if Yandex has one and we don't have a local one yet
        if review_data['response']:
            defaults['response'] = review_data['response']
            defaults['response_at'] = review_data['response_at']

        review, created = Review.objects.update_or_create(
            company=self.connection.company,
            source=Review.Source.YANDEX,
            external_id=review_data['external_id'],
            defaults=defaults,
        )

        return review, created

    def _find_csrf_tokens(self, html: str) -> dict:
        """Extract page-level CSRF tokens from HTML."""
        tokens = {}

        # x-csrf-token: "csrf":"hash:timestamp"
        csrf_match = re.search(r'"csrf"\s*:\s*"([a-f0-9]+:[0-9]+)"', html)
        if csrf_match:
            tokens['x-csrf-token'] = csrf_match.group(1)

        # reviewsCsrfToken: "csrf_token":"..." (near pager)
        csrf_token_match = re.search(r'"csrf_token"\s*:\s*"([^"]+)"', html)
        if csrf_token_match:
            tokens['reviewsCsrfToken'] = self._decode_unicode_escapes(csrf_token_match.group(1))

        return tokens

    def _find_answer_token(self, html: str, external_id: str) -> Optional[str]:
        """Find per-review answer CSRF token."""
        pos = html.find(f'"cmnt_entity_id":"{external_id}"')
        if pos < 0:
            return None

        # Token is after cmnt_entity_id in the HTML
        chunk = html[pos:pos + 500]
        token_match = re.search(
            r'"business_answer_csrf_token"\s*:\s*"([^"]+)"', chunk
        )
        if token_match:
            return self._decode_unicode_escapes(token_match.group(1))
        return None

    def _find_answer_token_all_pages(self, external_id: str) -> Optional[str]:
        """Search all pages for a review's answer token."""
        for page in range(1, 20):
            try:
                html = self._fetch_reviews_html(page=page)
                token = self._find_answer_token(html, external_id)
                if token:
                    return token
                # Check if we've gone past the last page
                if f'"cmnt_entity_id"' not in html:
                    break
            except Exception:
                break
        return None

    @staticmethod
    def _decode_unicode_escapes(s: str) -> str:
        """Decode \\u002F-style escapes in tokens. Use only for CSRF tokens."""
        if '\\u' not in s:
            return s
        try:
            return s.encode().decode('unicode_escape')
        except (UnicodeDecodeError, UnicodeEncodeError):
            return s.replace('\\u002F', '/')

    @staticmethod
    def _decode_text(s: str) -> str:
        """Clean up review text — handle \\n but don't mangle UTF-8."""
        return s.replace('\\n', '\n').replace('\\/', '/')
