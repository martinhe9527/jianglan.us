from django.urls import path
from .views import worklog_view

urlpatterns = [
    path('', worklog_view, name='worklog-home'),
]
