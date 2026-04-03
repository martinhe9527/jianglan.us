from django.db import models
from wagtail.models import Page


class HomePage(Page):
    intro = models.TextField(blank=True)

    content_panels = Page.content_panels + []
