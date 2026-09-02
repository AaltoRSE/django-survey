from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from survey.models import CssSnippet, Question
from survey.tests.test_other_option import make_question, make_survey


def make_published_survey(**kwargs):
    """A survey that satisfies IndexView's list-page filters (published, within
    the publish/expire window, no login required)."""
    defaults = {
        "is_published": True,
        "publish_date": date.today() - timedelta(days=1),
        "expire_date": date.today() + timedelta(days=1),
        "need_logged_user": False,
    }
    defaults.update(kwargs)
    return make_survey(**defaults)


class CssSnippetRenderingTests(TestCase):
    """Renders both the survey list page and a survey detail page and asserts
    that CssSnippet rows are emitted as <style data-css-snippet="..."> blocks
    at the end of <head>, per survey_custom_css / base.html."""

    def setUp(self):
        self.survey = make_published_survey()
        make_question(self.survey, Question.RADIO, order=1, choices="Yes,No", text="Radio question")

    def _get_pages(self):
        list_response = self.client.get(reverse("survey-list"))
        detail_response = self.client.get(reverse("survey-detail", kwargs={"id": self.survey.pk}))
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        return list_response.content.decode(), detail_response.content.decode()

    def test_single_snippet_rendered_on_list_and_detail_pages(self):
        CssSnippet.objects.create(name="theme", css=".survey-question-label { color: blue; }")
        list_html, detail_html = self._get_pages()
        for html in (list_html, detail_html):
            self.assertIn('data-css-snippet="theme"', html)
            self.assertIn(".survey-question-label { color: blue; }", html)

    def test_two_snippets_both_rendered_in_name_order(self):
        CssSnippet.objects.create(name="zeta", css=".zeta { color: red; }")
        CssSnippet.objects.create(name="alpha", css=".alpha { color: green; }")
        list_html, detail_html = self._get_pages()
        for html in (list_html, detail_html):
            self.assertIn('data-css-snippet="zeta"', html)
            self.assertIn('data-css-snippet="alpha"', html)
            self.assertLess(html.index('data-css-snippet="alpha"'), html.index('data-css-snippet="zeta"'))

    def test_no_snippets_omits_data_css_snippet_attribute(self):
        list_html, detail_html = self._get_pages()
        self.assertNotIn("data-css-snippet", list_html)
        self.assertNotIn("data-css-snippet", detail_html)

    def test_snippet_rendered_on_survey_without_date_fields(self):
        # This survey has only a radio question, so survey.html does not need
        # flatpickr and thus does not populate the extracss block. If
        # survey_custom_css were mistakenly placed inside extracss instead of
        # directly in base.html's <head>, this test would fail.
        CssSnippet.objects.create(name="theme", css=".survey-question-label { color: blue; }")
        detail_response = self.client.get(reverse("survey-detail", kwargs={"id": self.survey.pk}))
        self.assertEqual(detail_response.status_code, 200)
        detail_html = detail_response.content.decode()
        self.assertIn('data-css-snippet="theme"', detail_html)

    def test_snippet_name_is_escaped_but_css_body_is_raw(self):
        CssSnippet.objects.create(name='a"b<c', css=".a > .b { color: red; }")
        list_html, detail_html = self._get_pages()
        for html in (list_html, detail_html):
            self.assertIn('data-css-snippet="a&quot;b&lt;c"', html)
            self.assertNotIn('data-css-snippet="a"b<c"', html)
            self.assertIn(".a > .b { color: red; }", html)
