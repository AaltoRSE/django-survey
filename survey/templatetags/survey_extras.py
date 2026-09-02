from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from survey.models import CssSnippet

register = template.Library()


def collapse_form(form, category):
    """Permit to return the class of the collapsible according to errors in
    the form."""
    categories_with_error = set()
    for field in form:
        if field.errors:
            categories_with_error.add(field.field.widget.attrs["category"])
    if category.name in categories_with_error:
        return "in"
    return ""


register.filter("collapse_form", collapse_form)


class CounterNode(template.Node):
    def __init__(self):
        self.count = 0

    def render(self, context):
        self.count += 1
        return self.count


@register.tag
def counter(parser, token):
    return CounterNode()


@register.simple_tag
def survey_custom_css():
    """One <style> block per CssSnippet row, in name order."""
    blocks = [
        format_html('<style data-css-snippet="{}">{}</style>', snippet.name, mark_safe(snippet.css))
        for snippet in CssSnippet.objects.order_by("name")
    ]
    return mark_safe("".join(blocks))
