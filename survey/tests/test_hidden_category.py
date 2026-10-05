from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from survey.forms import ResponseForm
from survey.models import Category, Question, Survey
from survey.tests.test_other_option import make_question, make_survey, qd


class HiddenCategoryTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.category_a = Category.objects.create(survey=self.survey, name="A", order=1)
        self.category_b = Category.objects.create(survey=self.survey, name="B", order=2)
        self.question_a = Question.objects.create(
            survey=self.survey, text="QA", order=1, required=True, type=Question.SHORT_TEXT, category=self.category_a
        )
        self.question_b = Question.objects.create(
            survey=self.survey, text="QB", order=2, required=True, type=Question.SHORT_TEXT, category=self.category_b
        )
        self.question_no_cat = make_question(self.survey, Question.SHORT_TEXT, order=3, text="QNoCat")

    def make_form(self, data=None, **kwargs):
        return ResponseForm(data, survey=self.survey, user=AnonymousUser(), **kwargs)

    def test_hidden_category_excluded_from_non_empty_categories(self):
        self.assertEqual(self.survey.non_empty_categories(), [self.category_a, self.category_b])
        self.category_b.hidden = True
        self.category_b.save()
        self.assertEqual(self.survey.non_empty_categories(), [self.category_a])

    def test_hidden_category_reduces_by_category_steps_count(self):
        self.survey.display_method = Survey.BY_CATEGORY
        self.survey.save()
        # Two categories plus one step for the uncategorized question.
        self.assertEqual(self.make_form(step=0).steps_count, 3)
        self.category_b.hidden = True
        self.category_b.save()
        self.assertEqual(self.make_form(step=0).steps_count, 2)

    def test_all_in_one_page_omits_hidden_category_fields(self):
        self.category_b.hidden = True
        self.category_b.save()
        form = self.make_form()
        self.assertIn(f"question_{self.question_a.pk}", form.fields)
        self.assertNotIn(f"question_{self.question_b.pk}", form.fields)
        # Uncategorized questions are unaffected by category hiding.
        self.assertIn(f"question_{self.question_no_cat.pk}", form.fields)

    def test_required_question_in_hidden_category_does_not_block_submission(self):
        self.category_b.hidden = True
        self.category_b.save()
        data = qd(
            {
                f"question_{self.question_a.pk}": "answer a",
                f"question_{self.question_no_cat.pk}": "answer no cat",
            }
        )
        form = self.make_form(data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_unhiding_restores_category_at_original_position(self):
        # Hide the first category so position, not just presence, is checked.
        self.category_a.hidden = True
        self.category_a.save()
        self.assertEqual(self.survey.non_empty_categories(), [self.category_b])
        self.category_a.hidden = False
        self.category_a.save()
        self.assertEqual(self.survey.non_empty_categories(), [self.category_a, self.category_b])
        form = self.make_form()
        self.assertIn(f"question_{self.question_a.pk}", form.fields)
