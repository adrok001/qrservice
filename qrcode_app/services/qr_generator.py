"""
QR Code Generation Service

Вся логика генерации QR-кодов вынесена сюда.
Views остаются тонкими — только request/response.
"""
import io
import re
import base64
import qrcode
from PIL import Image


class QRGeneratorService:
    """Сервис генерации QR-кодов с поддержкой цветов и логотипов."""

    DEFAULT_FILL_COLOR = 'black'
    DEFAULT_BACK_COLOR = 'white'
    LOGO_SIZE_PERCENT = 25

    @staticmethod
    def validate_color(color: str, default: str) -> str:
        """Валидация цвета (hex или именованный)."""
        if not color:
            return default
        color = color.strip()
        if re.match(r'^#[0-9A-Fa-f]{6}$', color):
            return color
        if re.match(r'^[a-zA-Z]+$', color):
            return color
        return default

    @classmethod
    def add_logo(cls, qr_img: Image.Image, logo_file) -> Image.Image:
        """Добавление логотипа в центр QR-кода."""
        qr_img = qr_img.convert('RGBA')

        logo = Image.open(logo_file)
        logo = logo.convert('RGBA')

        qr_width, qr_height = qr_img.size
        logo_max_size = int(min(qr_width, qr_height) * cls.LOGO_SIZE_PERCENT / 100)

        logo_width, logo_height = logo.size
        ratio = min(logo_max_size / logo_width, logo_max_size / logo_height)
        new_logo_size = (int(logo_width * ratio), int(logo_height * ratio))
        logo = logo.resize(new_logo_size, Image.Resampling.LANCZOS)

        logo_pos = (
            (qr_width - logo.size[0]) // 2,
            (qr_height - logo.size[1]) // 2
        )

        qr_img.paste(logo, logo_pos, logo)
        return qr_img.convert('RGB')

    @classmethod
    def generate(
        cls,
        data: str,
        fill_color: str = None,
        back_color: str = None,
        logo_file=None
    ) -> Image.Image:
        """
        Генерация QR-кода.

        Args:
            data: Данные для кодирования
            fill_color: Цвет QR-кода (hex или название)
            back_color: Цвет фона (hex или название)
            logo_file: Файл логотипа (опционально)

        Returns:
            PIL Image объект
        """
        fill_color = cls.validate_color(fill_color, cls.DEFAULT_FILL_COLOR)
        back_color = cls.validate_color(back_color, cls.DEFAULT_BACK_COLOR)

        # Высокая коррекция ошибок если есть логотип
        error_correction = (
            qrcode.constants.ERROR_CORRECT_H if logo_file
            else qrcode.constants.ERROR_CORRECT_L
        )

        qr = qrcode.QRCode(
            version=1,
            error_correction=error_correction,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color=fill_color, back_color=back_color)

        if logo_file:
            img = cls.add_logo(img, logo_file)

        return img

    @classmethod
    def generate_to_buffer(cls, data: str, **kwargs) -> io.BytesIO:
        """Генерация QR-кода в буфер."""
        img = cls.generate(data, **kwargs)
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

    @classmethod
    def generate_to_base64(cls, data: str, **kwargs) -> str:
        """Генерация QR-кода в base64 строку."""
        buffer = cls.generate_to_buffer(data, **kwargs)
        return base64.b64encode(buffer.getvalue()).decode()
