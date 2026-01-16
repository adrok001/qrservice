"""
Dashboard services package.
Re-exports all functions for backwards compatibility.
"""
from .company import (
    get_user_companies,
    get_current_company,
    get_platforms_with_connections,
    update_company_info,
    update_platform_connections,
    auto_fill_address,
    build_platform_data,
)

from .reviews import (
    get_dashboard_stats,
    get_attention_reviews,
    get_recent_reviews,
    get_review_counts,
    filter_reviews,
    update_feedback_settings,
    build_form_settings_platform_data,
)

from .qr import generate_qr_image

from .periods import (
    get_period_labels,
    get_period_dates,
)

from .charts import (
    get_daily_reviews,
)

from .analytics import (
    calculate_kpi_metrics,
    calculate_reputation_risk,
    get_analytics_data,
    get_impression_map_data,
    build_dashboard_context,
)

__all__ = [
    # Company
    'get_user_companies',
    'get_current_company',
    'get_platforms_with_connections',
    'update_company_info',
    'update_platform_connections',
    'auto_fill_address',
    'build_platform_data',
    # Reviews
    'get_dashboard_stats',
    'get_attention_reviews',
    'get_recent_reviews',
    'get_review_counts',
    'filter_reviews',
    'update_feedback_settings',
    'build_form_settings_platform_data',
    # QR
    'generate_qr_image',
    # Analytics
    'get_period_labels',
    'get_period_dates',
    'calculate_kpi_metrics',
    'calculate_reputation_risk',
    'get_analytics_data',
    'get_daily_reviews',
    'get_impression_map_data',
    'build_dashboard_context',
]
