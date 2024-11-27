from django import template

register = template.Library()

@register.filter
def filesizeformat_gb(bytes):
    """Конвертирует байты в гигабайты"""
    try:
        gb = int(bytes) / (1024 * 1024 * 1024)
        return int(gb)  # Округляем до целого числа
    except (ValueError, TypeError):
        return 10  # Значение по умолчанию - 10 ГБ 