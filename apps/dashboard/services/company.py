"""
Company-related business logic.
"""
from typing import Any

from django.http import HttpRequest

from apps.accounts.models import Member
from apps.companies.models import Company, Platform, Connection


def get_user_companies(user: Any) -> list[Company]:
    """Get all companies for user."""
    memberships = Member.objects.filter(
        user=user, is_active=True
    ).select_related('company')
    return [m.company for m in memberships]


def get_current_company(request: HttpRequest) -> tuple[Company | None, list[Company]]:
    """Get current company from session or first available."""
    user = request.user
    companies = get_user_companies(user)

    if not companies:
        return None, []

    selected_id = request.session.get('selected_company_id')
    if selected_id:
        for company in companies:
            if str(company.id) == selected_id:
                return company, companies

    return companies[0], companies


def get_platforms_with_connections(company: Company) -> tuple[list[Platform], dict]:
    """Get platforms sorted with their connections."""
    platform_order = {'yandex': 1, '2gis': 2, 'google': 3}
    platforms = sorted(
        Platform.objects.filter(is_active=True),
        key=lambda p: platform_order.get(p.id, 99)
    )
    connections = {
        c.platform_id: c
        for c in Connection.objects.filter(company=company)
    }
    return platforms, connections


def update_company_info(company: Company, post_data: dict, files: dict) -> None:
    """Update company name, address and logo."""
    name_changed = False
    address_changed = False

    name = post_data.get('name', '').strip()
    if name and name != company.name:
        company.name = name
        name_changed = True

    address = post_data.get('address', '').strip()
    if address != company.address:
        company.address = address
        address_changed = True

    # Ручное изменение slug (если передано)
    new_slug = post_data.get('slug', '').strip()
    if new_slug and new_slug != company.slug:
        # Валидируем slug
        from django.utils.text import slugify
        new_slug = slugify(new_slug)
        if new_slug and not Company.objects.filter(slug=new_slug).exclude(pk=company.pk).exists():
            company.slug = new_slug

    if 'logo' in files:
        logo = files['logo']
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if logo.content_type in allowed_types:
            if company.logo:
                company.logo.delete(save=False)
            company.logo = logo

    if post_data.get('delete_logo') == '1' and company.logo:
        company.logo.delete(save=False)
        company.logo = None

    company.save()

    # Автоматически обновляем slug если изменились название или адрес
    # и пользователь не ввёл свой slug вручную
    if (name_changed or address_changed) and not new_slug:
        company.update_slug_from_address()


def update_platform_connections(
    company: Company,
    platforms: list[Platform],
    post_data: dict,
    connections: dict
) -> None:
    """Update geo service platform connections."""
    for platform in platforms:
        url = post_data.get(f'platform_{platform.id}', '').strip()
        enabled = post_data.get(f'platform_{platform.id}_enabled') == 'on'
        existing = connections.get(platform.id)

        if url:
            if existing:
                existing.external_url = url
                existing.sync_enabled = enabled
                existing.save(update_fields=['external_url', 'sync_enabled'])
            else:
                Connection.objects.create(
                    company=company,
                    platform=platform,
                    external_id=url,
                    external_url=url,
                    sync_enabled=enabled,
                )
        elif existing and not existing.access_token:
            existing.external_url = ''
            existing.sync_enabled = False
            existing.save(update_fields=['external_url', 'sync_enabled'])


def auto_fill_address(company: Company, post_data: dict) -> None:
    """Auto-fill address from geo service URLs if empty."""
    if company.address:
        return

    from apps.companies.services import extract_address_from_urls
    urls = [
        post_data.get('platform_yandex', ''),
        post_data.get('platform_2gis', ''),
        post_data.get('platform_google', ''),
    ]
    extracted = extract_address_from_urls(urls)
    if extracted:
        company.address = extracted
        company.save(update_fields=['address'])


def build_platform_data(platforms: list[Platform], connections: dict) -> list[dict]:
    """Build platform data for template."""
    return [
        {
            'id': p.id,
            'name': p.name,
            'url': connections.get(p.id).external_url if connections.get(p.id) else '',
            'enabled': connections.get(p.id).sync_enabled if connections.get(p.id) else False,
            'has_oauth': bool(connections.get(p.id) and connections.get(p.id).access_token),
        }
        for p in platforms
    ]
