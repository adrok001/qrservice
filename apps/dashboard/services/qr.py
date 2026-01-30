"""
QR code generation business logic.
"""
import re
from io import BytesIO
from typing import Optional
from uuid import UUID

import qrcode
from django.conf import settings
from django.core.files.base import ContentFile

from apps.qr.models import QR
from apps.companies.models import Company, Spot
from apps.accounts.models import User


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


def validate_color(color: str) -> bool:
    """
    Validate hex color format.

    Args:
        color: Color string to validate

    Returns:
        True if valid, False otherwise
    """
    if not color:
        return False
    return bool(re.match(r'^#[0-9A-Fa-f]{6}$', color))


def create_qr_code(
    company: Company,
    created_by: User,
    spot_id: Optional[str] = None,
    color: str = '#000000',
    background: str = '#FFFFFF'
) -> QR:
    """
    Create new QR code with validation.

    Args:
        company: Company to create QR for
        created_by: User creating the QR
        spot_id: Optional spot ID (UUID string)
        color: QR foreground color (hex)
        background: QR background color (hex)

    Returns:
        Created QR instance

    Raises:
        ValueError: If validation fails
    """
    # Validate colors
    if not validate_color(color):
        raise ValueError(f'Неверный формат цвета: {color}')
    if not validate_color(background):
        raise ValueError(f'Неверный формат фона: {background}')

    # Get spot if provided
    spot = None
    if spot_id:
        try:
            spot = Spot.objects.get(id=spot_id, company=company)
        except Spot.DoesNotExist:
            raise ValueError('Указанная точка не найдена')

    # Create QR
    qr = QR.objects.create(
        company=company,
        spot=spot,
        color=color,
        background=background,
        created_by=created_by
    )

    # Generate QR image
    generate_qr_image(qr)

    return qr


def update_qr_code(
    qr: QR,
    spot_id: Optional[str] = None,
    color: Optional[str] = None,
    background: Optional[str] = None
) -> QR:
    """
    Update existing QR code with validation.

    Args:
        qr: QR instance to update
        spot_id: Optional new spot ID
        color: Optional new color
        background: Optional new background

    Returns:
        Updated QR instance

    Raises:
        ValueError: If validation fails
    """
    updated = False

    # Update spot
    if spot_id is not None:
        if spot_id == '':
            qr.spot = None
            updated = True
        else:
            try:
                spot = Spot.objects.get(id=spot_id, company=qr.company)
                qr.spot = spot
                updated = True
            except Spot.DoesNotExist:
                raise ValueError('Указанная точка не найдена')

    # Update color
    if color is not None:
        if not validate_color(color):
            raise ValueError(f'Неверный формат цвета: {color}')
        qr.color = color
        updated = True

    # Update background
    if background is not None:
        if not validate_color(background):
            raise ValueError(f'Неверный формат фона: {background}')
        qr.background = background
        updated = True

    # Save and regenerate image if changed
    if updated:
        qr.save()
        generate_qr_image(qr)

    return qr
