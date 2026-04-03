from django import template

from dashboard.data import HOLDINGS_DATA, WATCHLIST_DATA

register = template.Library()

SYMBOL_NAME_MAP = {
    item['code']: item.get('name', '') for item in (WATCHLIST_DATA + HOLDINGS_DATA)
}


@register.filter
def split_csv(value):
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]


@register.filter
def symbol_with_name(value):
    if not value:
        return ''
    name = SYMBOL_NAME_MAP.get(value, '')
    return f"{value} {name}".strip()


@register.filter
def symbols_with_names(value):
    if not value:
        return []
    result = []
    for item in [part.strip() for part in value.split(',') if part.strip()]:
        name = SYMBOL_NAME_MAP.get(item, '')
        result.append(f"{item} {name}".strip())
    return result
