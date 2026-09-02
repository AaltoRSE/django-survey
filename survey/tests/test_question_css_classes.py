from django.test import TestCase
from django.urls import reverse

from survey.models import Question, Survey
from survey.tests.test_other_option import make_question, make_survey


class QuestionCssClassesRenderingTests(TestCase):
    """Renders a survey page and asserts the three-tier CSS class scheme
    (generic / type-prefixed / pk-specific) plus companion-field classes and
    the legacy likert classes are all present in the markup."""

    def setUp(self):
        self.survey = make_survey(display_method=Survey.ALL_IN_ONE_PAGE)
        self.radio_q = make_question(
            self.survey, Question.RADIO, order=1, choices="Yes,No", text="Radio question"
        )
        self.scale_q = Question.objects.create(
            survey=self.survey,
            text="Scale question",
            order=2,
            required=True,
            type=Question.INTEGER_SCALE,
            choices="",
            scale_min=0,
            scale_max=10,
            will_not_answer_option=True,
        )
        self.text_q = make_question(self.survey, Question.TEXT, order=3, text="Text question")
        response = self.client.get(reverse("survey-detail", kwargs={"id": self.survey.pk}))
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()

    def test_survey_and_questions_containers_have_classes(self):
        self.assertIn(f'class="survey-container survey-{self.survey.pk}"', self.html)
        self.assertIn('class="survey-questions-container"', self.html)

    def test_generic_classes_present_for_every_question(self):
        self.assertIn("survey-question-label", self.html)
        self.assertIn("survey-question-row", self.html)
        self.assertIn("survey-question-option", self.html)

    def test_radio_question_has_type_prefixed_and_pk_specific_classes(self):
        self.assertIn("radio-question-option", self.html)
        self.assertIn("radio-question-row", self.html)
        self.assertIn("radio-question-label", self.html)
        self.assertIn(f"question-{self.radio_q.pk}-option", self.html)
        self.assertIn(f"question-{self.radio_q.pk}-row", self.html)
        self.assertIn(f"question-{self.radio_q.pk}-label", self.html)

    def test_each_option_has_a_numbered_pk_specific_class(self):
        self.assertIn(f"question-{self.radio_q.pk}-option-1", self.html)
        self.assertIn(f"question-{self.radio_q.pk}-option-2", self.html)
        self.assertNotIn(f"question-{self.radio_q.pk}-option-3", self.html)
        self.assertIn(f"question-{self.scale_q.pk}-option-11", self.html)

    def test_integer_scale_question_has_type_prefixed_and_pk_specific_classes(self):
        self.assertIn("integer-scale-question-row", self.html)
        self.assertIn("integer-scale-question-option", self.html)
        self.assertIn(f"question-{self.scale_q.pk}-row", self.html)
        self.assertIn(f"question-{self.scale_q.pk}-option", self.html)

    def test_integer_scale_question_keeps_legacy_likert_classes(self):
        self.assertIn("likert-row", self.html)
        self.assertIn("likert-option", self.html)
        self.assertIn("likert-option-label", self.html)

    def test_text_question_has_type_prefixed_row_class(self):
        self.assertIn("text-question-row", self.html)
        self.assertIn(f"question-{self.text_q.pk}-row", self.html)

    def test_will_not_answer_companion_field_has_wna_classes(self):
        self.assertIn("wna-question-row", self.html)
        self.assertIn(f"question-{self.scale_q.pk}-wna-row", self.html)

    def test_radio_options_no_longer_render_as_default_ul(self):
        self.assertNotIn(f'<ul id="id_question_{self.radio_q.pk}"', self.html)
