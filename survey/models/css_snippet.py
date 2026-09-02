from django.db import models
from django.utils.translation import gettext_lazy as _


class CssSnippet(models.Model):
    name = models.CharField(_("Name"), max_length=200, unique=True)
    css = models.TextField(_("CSS"))

    class Meta:
        # pylint: disable=too-few-public-methods
        verbose_name = _("CSS snippet")
        verbose_name_plural = _("CSS snippets")

    def __str__(self):
        return self.name
