"""Integration tests for QR module."""

from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse

from apps.accounts.models import User, Member
from apps.companies.models import Company, Spot
from .models import QR, QRScan, generate_short_code


class QRCodeGenerationTests(TestCase):
    """Tests for QR code generation and uniqueness."""

    def test_short_code_generation(self):
        """Short code should be 8 characters and unique."""
        code = generate_short_code()
        self.assertEqual(len(code), 8)
        # Should not contain confusing characters
        self.assertNotIn('0', code)
        self.assertNotIn('O', code)
        self.assertNotIn('I', code)
        self.assertNotIn('L', code)

    def test_multiple_codes_unique(self):
        """Multiple generated codes should be unique."""
        codes = {generate_short_code() for _ in range(100)}
        # All codes should be unique (set size = 100)
        self.assertEqual(len(codes), 100)


class QRModelTests(TestCase):
    """Tests for QR model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='pass123'
        )
        self.company = Company.objects.create(name='Test Company')
        Member.objects.create(
            user=self.user,
            company=self.company,
            role=Member.Role.OWNER
        )

    def test_qr_creation(self):
        """QR code should be created with auto-generated code."""
        qr = QR.objects.create(
            company=self.company,
            created_by=self.user
        )

        self.assertIsNotNone(qr.id)
        self.assertIsNotNone(qr.code)
        self.assertEqual(len(qr.code), 8)
        self.assertTrue(qr.is_active)
        self.assertEqual(qr.scans, 0)

    def test_qr_with_spot(self):
        """QR code can be linked to a specific spot."""
        spot = Spot.objects.create(
            company=self.company,
            name='Main Hall'
        )
        qr = QR.objects.create(
            company=self.company,
            spot=spot,
            created_by=self.user
        )

        self.assertEqual(qr.spot, spot)
        self.assertIn(spot.name, str(qr))

    def test_qr_custom_colors(self):
        """QR code should support custom colors."""
        qr = QR.objects.create(
            company=self.company,
            color='#FF0000',
            background='#00FF00',
            created_by=self.user
        )

        self.assertEqual(qr.color, '#FF0000')
        self.assertEqual(qr.background, '#00FF00')

    def test_qr_get_absolute_url(self):
        """QR should return correct absolute URL."""
        qr = QR.objects.create(company=self.company)
        url = qr.get_absolute_url()
        self.assertEqual(url, f'/{qr.code}')

    def test_qr_get_redirect_url_without_spot(self):
        """QR without spot should redirect to company feedback form."""
        qr = QR.objects.create(company=self.company)
        redirect = qr.get_redirect_url()

        expected = f'/f/{self.company.slug}/?qr={qr.code}'
        self.assertEqual(redirect, expected)

    def test_qr_get_redirect_url_with_spot(self):
        """QR with spot should include spot ID in redirect."""
        spot = Spot.objects.create(company=self.company, name='Терраса')
        qr = QR.objects.create(company=self.company, spot=spot)
        redirect = qr.get_redirect_url()

        self.assertIn(f'spot={spot.id}', redirect)
        self.assertIn(f'qr={qr.code}', redirect)

    def test_qr_increment_scans(self):
        """QR increment_scans should update counter and timestamp."""
        qr = QR.objects.create(company=self.company)
        self.assertEqual(qr.scans, 0)
        self.assertIsNone(qr.last_scan_at)

        # First scan
        qr.increment_scans()
        qr.refresh_from_db()
        self.assertEqual(qr.scans, 1)
        self.assertIsNotNone(qr.last_scan_at)

        first_scan_time = qr.last_scan_at

        # Second scan
        qr.increment_scans()
        qr.refresh_from_db()
        self.assertEqual(qr.scans, 2)
        self.assertGreater(qr.last_scan_at, first_scan_time)

    def test_qr_cascade_delete_with_company(self):
        """Deleting company should delete QR codes."""
        qr = QR.objects.create(company=self.company)
        qr_id = qr.id

        self.company.delete()

        # QR should be deleted via CASCADE
        self.assertFalse(QR.objects.filter(id=qr_id).exists())

    def test_qr_spot_set_null_when_spot_deleted(self):
        """Deleting spot should set QR.spot to NULL (not delete QR)."""
        spot = Spot.objects.create(company=self.company, name='Test')
        qr = QR.objects.create(company=self.company, spot=spot)

        spot.delete()

        qr.refresh_from_db()
        self.assertIsNone(qr.spot)
        # QR should still exist
        self.assertTrue(QR.objects.filter(id=qr.id).exists())


class QRScanTests(TestCase):
    """Tests for QR scan tracking."""

    def setUp(self):
        self.company = Company.objects.create(name='Test')
        self.qr = QR.objects.create(company=self.company)

    def test_qrscan_creation(self):
        """QRScan should be created with timestamp."""
        scan = QRScan.objects.create(
            qr=self.qr,
            ip_address='192.168.1.1',
            user_agent='Mozilla/5.0...'
        )

        self.assertIsNotNone(scan.scanned_at)
        self.assertEqual(scan.qr, self.qr)

    def test_qrscan_tracks_multiple_scans(self):
        """Multiple scans should be tracked separately."""
        QRScan.objects.create(qr=self.qr, ip_address='192.168.1.1')
        QRScan.objects.create(qr=self.qr, ip_address='192.168.1.2')
        QRScan.objects.create(qr=self.qr, ip_address='192.168.1.3')

        scans = QRScan.objects.filter(qr=self.qr)
        self.assertEqual(scans.count(), 3)

    def test_qrscan_cascade_delete_with_qr(self):
        """Deleting QR should delete scan logs."""
        QRScan.objects.create(qr=self.qr)
        QRScan.objects.create(qr=self.qr)

        qr_id = self.qr.id
        self.qr.delete()

        # Scans should be deleted via CASCADE
        self.assertFalse(QRScan.objects.filter(qr_id=qr_id).exists())


class QRRedirectViewTests(TestCase):
    """Integration tests for QR redirect functionality."""

    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name='Test Cafe')
        self.qr = QR.objects.create(company=self.company)

    def test_qr_redirect_increments_counter(self):
        """Accessing QR URL should increment scan counter."""
        initial_scans = self.qr.scans

        response = self.client.get(f'/{self.qr.code}')

        self.qr.refresh_from_db()
        self.assertEqual(response.status_code, 302)  # Redirect
        self.assertEqual(self.qr.scans, initial_scans + 1)

    def test_qr_redirect_creates_scan_log(self):
        """Accessing QR URL should create scan log entry."""
        initial_logs = QRScan.objects.filter(qr=self.qr).count()

        self.client.get(f'/{self.qr.code}')

        logs = QRScan.objects.filter(qr=self.qr)
        self.assertEqual(logs.count(), initial_logs + 1)

    def test_qr_redirect_to_feedback_form(self):
        """QR should redirect to company feedback form."""
        response = self.client.get(f'/{self.qr.code}')

        self.assertEqual(response.status_code, 302)
        self.assertIn(self.company.slug, response.url)
        self.assertIn(self.qr.code, response.url)

    def test_inactive_qr_returns_404(self):
        """Inactive QR code should return 404."""
        self.qr.is_active = False
        self.qr.save()

        response = self.client.get(f'/{self.qr.code}')
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_qr_returns_404(self):
        """Non-existent QR code should return 404."""
        response = self.client.get('/FAKECODE')
        self.assertEqual(response.status_code, 404)


class QRIntegrationFlowTests(TestCase):
    """End-to-end integration tests for QR workflow."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='owner@test.com',
            password='pass123'
        )
        self.company = Company.objects.create(name='Restaurant Test')
        Member.objects.create(
            user=self.user,
            company=self.company,
            role=Member.Role.OWNER
        )

    def test_complete_qr_lifecycle(self):
        """Test complete QR lifecycle: create -> scan -> track -> delete."""
        # 1. Create QR
        qr = QR.objects.create(
            company=self.company,
            color='#FF5733',
            background='#FFFFFF',
            created_by=self.user
        )

        self.assertTrue(qr.is_active)
        self.assertEqual(qr.scans, 0)

        # 2. Scan QR multiple times
        for _ in range(5):
            response = self.client.get(f'/{qr.code}')
            self.assertEqual(response.status_code, 302)

        # 3. Verify scan tracking
        qr.refresh_from_db()
        self.assertEqual(qr.scans, 5)
        self.assertIsNotNone(qr.last_scan_at)

        scan_logs = QRScan.objects.filter(qr=qr)
        self.assertEqual(scan_logs.count(), 5)

        # 4. Deactivate QR
        qr.is_active = False
        qr.save()

        response = self.client.get(f'/{qr.code}')
        self.assertEqual(response.status_code, 404)

        # 5. Delete QR
        qr_id = qr.id
        qr.delete()

        self.assertFalse(QR.objects.filter(id=qr_id).exists())
        self.assertFalse(QRScan.objects.filter(qr_id=qr_id).exists())

    def test_qr_with_spot_complete_flow(self):
        """Test QR with spot: create spot -> create QR -> scan -> redirect."""
        # Create spot
        spot = Spot.objects.create(
            company=self.company,
            name='Summer Terrace'
        )

        # Create QR for spot
        qr = QR.objects.create(
            company=self.company,
            spot=spot,
            created_by=self.user
        )

        # Scan QR
        response = self.client.get(f'/{qr.code}')

        # Should redirect with spot parameter
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'spot={spot.id}', response.url)

        # Delete spot (QR should remain but with spot=NULL)
        spot.delete()
        qr.refresh_from_db()
        self.assertIsNone(qr.spot)
        self.assertTrue(QR.objects.filter(id=qr.id).exists())
