from django.contrib import admin

from .models import MinuteBar


@admin.register(MinuteBar)
class MinuteBarAdmin(admin.ModelAdmin):
    list_display = (
        'symbol',
        'name',
        'trade_date',
        'bar_time',
        'open_price',
        'high_price',
        'low_price',
        'close_price',
        'volume',
        'source',
    )
    list_filter = ('trade_date', 'source')
    search_fields = ('symbol', 'name')
    ordering = ('-trade_date', '-bar_time', 'symbol')
