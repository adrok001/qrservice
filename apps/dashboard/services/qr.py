"""
QR code generation business logic.
"""
from io import BytesIO

import qrcode
from django.conf import settings
from django.core.files.base import ContentFile

from apps.qr.models import QR


def generate_qr_image(qr: QR) -> None:
    """Generate QR code image and save to model."""
    base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
    url = f"{base_url}/{qr.code}"

    qr_image = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr_image.add_data(url)
    qr_image.make(fit=True)

    fill_color = qr.color or '#000000'
    back_color = qr.background or '#FFFFFF'

    img = qr_image.make_image(fill_color=fill_color, back_color=back_color)

    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    filename = f'qr_{qr.code}.png'
    qr.image.save(filename, ContentFile(buffer.read()), save=True)
