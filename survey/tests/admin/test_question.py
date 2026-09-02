from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.test import TestCase

from survey.admin import QuestionInline, QuestionInlineForm, ScalePresetForm
from survey.models.category import Category
from survey.models.question import Question
from survey.models.survey import Survey


class TestQuestionInlineAdmin(TestCase):
    def setUp(self):
        self.survey = Survey.objects.create(
            name="Survey One", description="Survey's Description", need_logged_user=False
        )
        another_survey = Survey.objects.create(
            name="Another Survey", description="Another Survey's Description", need_logged_user=False
        )
        self.category_1 = Category.objects.create(name="First Category", survey=self.survey)
        self.category_2 = Category.objects.create(name="Second Category", survey=self.survey)

        self.another_survey_category = Category.objects.create(name="Another Survey Category", survey=another_survey)

        self.site = AdminSite()
        self.request = mock.Mock()

    def test_question_admin_inline_filter_surveys_category(self):
        question_admin = QuestionInline(Survey, self.site)
        formset = question_admin.get_formset(self.request, self.survey)
        qs = formset.form.base_fields["category"].queryset

        self.assertEqual(qs.count(), 2)
        self.assertNotIn(self.another_survey_category, qs)

    def test_question_admin_inline_filter_no_surveys_yet(self):
        self.survey.delete()
        self.another_survey_category.delete()
        self.survey = None

        question_admin = QuestionInline(Survey, self.site)
        formset = question_admin.get_formset(self.request, self.survey)
        qs = formset.form.base_fields["category"].queryset

        self.assertEqual(qs.count(), 0)


class TestScalePresetForm(TestCase):
    """The preset dropdown is a convenience only: admin_scale.js copies the
    picked range into the minimum/maximum fields, and those are what is saved."""

    def setUp(self):
        self.survey = Survey.objects.create(name="Scale survey", description="desc", need_logged_user=False)

    def _question(self, scale_min, scale_max):
        return Question.objects.create(
            survey=self.survey, text="On this scale?", order=1, required=True,
            type=Question.INTEGER_SCALE, choices="", scale_min=scale_min, scale_max=scale_max,
        )

    def test_the_question_inline_offers_the_preset_and_limit_fields(self):
        formset = QuestionInline(Survey, AdminSite()).get_formset(mock.Mock(), self.survey)
        for name in ("scale_preset", "scale_min", "scale_max"):
            self.assertIn(name, formset.form.base_fields)

    def test_common_ranges_are_offered_as_presets(self):
        values = [value for value, _label in ScalePresetForm().fields["scale_preset"].choices]
        self.assertEqual(values, ["", "0:10", "-5:5", "1:7"])

    def test_preset_is_preselected_when_the_limits_match_one(self):
        form = ScalePresetForm(instance=self._question(1, 7))
        self.assertEqual(form.fields["scale_preset"].initial, "1:7")

    def test_preset_is_blank_for_a_custom_range(self):
        form = ScalePresetForm(instance=self._question(2, 9))
        self.assertIsNone(form.fields["scale_preset"].initial)

    def test_preset_is_blank_on_a_new_question(self):
        self.assertIsNone(ScalePresetForm().fields["scale_preset"].initial)

    def test_typed_limits_are_saved_and_the_preset_is_not_read(self):
        form = QuestionInlineForm(
            {
                "text": "On this scale?",
                "order": 1,
                "survey": self.survey.pk,
                "type": Question.INTEGER_SCALE,
                "choices": "",
                "other_label": "Other, please specify",
                # A stale preset must not override what the fields say.
                "scale_preset": "0:10",
                "scale_min": 2,
                "scale_max": 9,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        question = form.save()
        self.assertEqual((question.scale_min, question.scale_max), (2, 9))

    def test_the_preset_javascript_is_loaded_by_both_question_forms(self):
        self.assertIn("survey/js/admin_scale.js", str(ScalePresetForm().media))
        self.assertIn("survey/js/admin_scale.js", str(QuestionInlineForm().media))
        self.assertIn("survey/css/admin_condition.css", str(QuestionInlineForm().media))

    def test_the_question_type_javascript_is_loaded_by_both_question_forms(self):
        self.assertIn("survey/js/admin_question_type.js", str(ScalePresetForm().media))
        self.assertIn("survey/js/admin_question_type.js", str(QuestionInlineForm().media))
