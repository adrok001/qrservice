"""Сервисы для работы с компаниями"""
import re
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


def extract_address_from_url(url: str) -> Optional[str]:
    """
    Извлекает адрес компании из URL геосервиса.

    Поддерживает:
    - Яндекс Карты
    - 2GIS
    - Google Maps
    """
    if not url:
        return None

    url = url.strip()

    try:
        if 'yandex.ru/maps' in url:
            return _extract_from_yandex(url)
        elif '2gis.ru' in url:
            return _extract_from_2gis(url)
        elif 'google' in url and ('maps' in url or 'g.page' in url):
            return _extract_from_google(url)
    except Exception as e:
        logger.error(f"Ошибка извлечения адреса из {url}: {e}")

    return None


def _decode_unicode(text: str) -> str:
    """Декодирует Unicode escape последовательности в нормальный текст"""
    try:
        # Декодируем \uXXXX последовательности
        return text.encode('utf-8').decode('unicode_escape').encode('latin1').decode('utf-8')
    except:
        try:
            return text.encode('utf-8').decode('unicode_escape')
        except:
            return text


def _extract_from_yandex(url: str) -> Optional[str]:
    """Извлекает адрес из Яндекс Карт"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        html = response.text

        # Ищем адрес в JSON данных страницы
        patterns = [
            r'"address":"([^"]+)"',
            r'"formattedAddress":"([^"]+)"',
            r'class="orgpage-header-view__address"[^>]*>([^<]+)<',
            r'<meta property="og:description" content="([^"]+)"',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                address = match.group(1)
                # Декодируем Unicode
                address = _decode_unicode(address)
                address = address.replace('\\/', '/')
                if len(address) > 10 and ('ул.' in address or 'г.' in address or 'пр.' in address or ',' in address):
                    return address.strip()

        return None

    except Exception as e:
        logger.error(f"Yandex parsing error: {e}")
        return None


def _extract_from_2gis(url: str) -> Optional[str]:
    """Извлекает адрес из 2GIS"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        html = response.text

        # 2GIS хранит данные в JSON
        patterns = [
            r'"address_name":"([^"]+)"',
            r'"full_address_name":"([^"]+)"',
            r'class="[^"]*address[^"]*"[^>]*>([^<]+)<',
            r'<meta name="description" content="([^"]+)"',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                address = match.group(1)
                # Декодируем Unicode
                address = _decode_unicode(address)
                # Из description берём только адрес (обычно после "Адрес:")
                if 'Адрес:' in address:
                    address = address.split('Адрес:')[1].split('.')[0].strip()
                if len(address) > 10 and ('ул.' in address or 'г.' in address or 'пр.' in address or ',' in address):
                    return address.strip()

        return None

    except Exception as e:
        logger.error(f"2GIS parsing error: {e}")
        return None


def _extract_from_google(url: str) -> Optional[str]:
    """Извлекает адрес из Google Maps"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    }

    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        response.raise_for_status()
        response.encoding = 'utf-8'
        html = response.text

        # Google Maps хранит адрес в разных местах
        patterns = [
            r'"address":"([^"]+)"',
            r'data-address="([^"]+)"',
            r'<meta content="([^"]+)" itemprop="address"',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                address = match.group(1)
                # Декодируем Unicode
                address = _decode_unicode(address)
                if len(address) > 10:
                    return address.strip()

        return None

    except Exception as e:
        logger.error(f"Google parsing error: {e}")
        return None


def extract_address_from_urls(urls: list) -> Optional[str]:
    """
    Пытается извлечь адрес из списка URL.
    Возвращает первый успешно извлечённый адрес.
    """
    for url in urls:
        if url:
            address = extract_address_from_url(url)
            if address:
                return address
    return None


def extract_company_info_from_yandex(url: str) -> dict:
    """
    Извлекает информацию о компании из URL Яндекс.Карт.

    Returns:
        dict: {'name': str, 'address': str} или пустой dict при ошибке
    """
    if not url or 'yandex.ru/maps' not in url:
        return {}

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        html = response.text

        result = {}

        # Извлекаем название
        name_patterns = [
            r'"name":"([^"]+)"',
            r'<title>([^|<]+)',
            r'"title":"([^"]+)"',
            r'class="orgpage-header-view__header"[^>]*>([^<]+)<',
            r'<meta property="og:title" content="([^"]+)"',
        ]

        for pattern in name_patterns:
            match = re.search(pattern, html)
            if match:
                name = match.group(1).strip()
                name = _decode_unicode(name)
                # Убираем суффиксы типа "— Яндекс Карты"
                name = re.sub(r'\s*[—\-]\s*Яндекс.*$', '', name)
                name = re.sub(r'\s*[—\-]\s*отзывы.*$', '', name, flags=re.IGNORECASE)
                if len(name) > 2 and len(name) < 200:
                    result['name'] = name.strip()
                    break

        # Извлекаем адрес
        address_patterns = [
            r'"address":"([^"]+)"',
            r'"formattedAddress":"([^"]+)"',
            r'class="orgpage-header-view__address"[^>]*>([^<]+)<',
        ]

        for pattern in address_patterns:
            match = re.search(pattern, html)
            if match:
                address = match.group(1)
                address = _decode_unicode(address)
                address = address.replace('\\/', '/')
                if len(address) > 5:
                    result['address'] = address.strip()
                    break

        return result

    except Exception as e:
        logger.error(f"Error extracting company info from Yandex: {e}")
        return {}
