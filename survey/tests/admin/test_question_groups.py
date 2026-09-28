from django.test import TestCase

from survey.admin_impl.question_groups import grouped_rows_without_predecessor, propagate_lead_settings


def row(order, pk=None, category_id=None, grouped=False):
    return {"order": order, "pk": pk, "category_id": category_id, "group_with_previous": grouped}


class GroupedRowsWithoutPredecessorTests(TestCase):
    def test_grouped_row_after_a_question_is_fine(self):
        rows = [row(1, pk=1), row(2, pk=2, grouped=True)]
        self.assertEqual(grouped_rows_without_predecessor(rows), [])

    def test_first_grouped_row_is_reported(self):
        first = row(1, pk=1, grouped=True)
        self.assertEqual(grouped_rows_without_predecessor([first, row(2, pk=2)]), [first])

    def test_predecessor_must_be_in_the_same_category(self):
        lonely = row(2, pk=2, category_id=7, grouped=True)
        rows = [row(1, pk=1, category_id=3), lonely, row(3, pk=3, category_id=7, grouped=True)]
        self.assertEqual(grouped_rows_without_predecessor(rows), [lonely])

    def test_predecessor_may_itself_be_grouped(self):
        rows = [row(1, pk=1), row(2, pk=2, grouped=True), row(3, pk=3, grouped=True)]
        self.assertEqual(grouped_rows_without_predecessor(rows), [])

    def test_new_row_sorts_after_existing_row_with_same_order(self):
        rows = [row(1, pk=None, grouped=True), row(1, pk=5)]
        self.assertEqual(grouped_rows_without_predecessor(rows), [])

    def test_rows_are_ordered_by_order_not_input_position(self):
        rows = [row(2, pk=2), row(1, pk=1, grouped=True)]
        self.assertEqual(grouped_rows_without_predecessor(rows), [rows[1]])


class QuestionInlineFormSetTests(TestCase):
    """Wire-up check: the inline formset rejects a grouped first question."""

    def formset(self, grouped_first):
        from unittest import mock

        from django.contrib.admin.sites import AdminSite

        from survey.admin import QuestionInline
        from survey.models import Survey

        survey = Survey.objects.create(name="S", description="d", need_logged_user=False)
        formset_class = QuestionInline(Survey, AdminSite()).get_formset(mock.Mock(), survey)
        prefix = formset_class.get_default_prefix()
        data = {
            f"{prefix}-TOTAL_FORMS": "2",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
        }
        for index, (text, grouped) in enumerate((("First", grouped_first), ("", True))):
            data.update(
                {
                    f"{prefix}-{index}-text": text,
                    f"{prefix}-{index}-order": str(index + 1),
                    f"{prefix}-{index}-type": "text",
                    f"{prefix}-{index}-condition_operator": "in",
                    f"{prefix}-{index}-will_not_answer_label": "I will not answer",
                }
            )
            if grouped:
                data[f"{prefix}-{index}-group_with_previous"] = "on"
        return formset_class(data, instance=survey, prefix=prefix)

    def test_grouped_second_question_is_valid(self):
        formset = self.formset(grouped_first=False)
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_grouped_first_question_is_rejected(self):
        formset = self.formset(grouped_first=True)
        self.assertFalse(formset.is_valid())
        self.assertIn("group_with_previous", formset.forms[0].errors)
        self.assertNotIn("group_with_previous", formset.forms[1].errors)


class GroupLeadSettingsPropagationTests(TestCase):
    """Saving the inline formset copies the lead's answer-defining settings
    onto every follower of its group, overwriting whatever was submitted for
    the followers (the admin hides those fields on grouped questions)."""

    def setUp(self):
        from unittest import mock

        from django.contrib.admin.sites import AdminSite

        from survey.admin import QuestionInline
        from survey.models import Survey

        self.survey = Survey.objects.create(name="S", description="d", need_logged_user=False)
        self.formset_class = QuestionInline(Survey, AdminSite()).get_formset(mock.Mock(), self.survey)
        self.prefix = self.formset_class.get_default_prefix()

    def save_formset(self, forms_data):
        data = {
            f"{self.prefix}-TOTAL_FORMS": str(len(forms_data)),
            f"{self.prefix}-INITIAL_FORMS": "0",
            f"{self.prefix}-MIN_NUM_FORMS": "0",
            f"{self.prefix}-MAX_NUM_FORMS": "1000",
        }
        for index, form_data in enumerate(forms_data):
            data[f"{self.prefix}-{index}-condition_operator"] = "in"
            data[f"{self.prefix}-{index}-will_not_answer_label"] = "I will not answer"
            for name, value in form_data.items():
                data[f"{self.prefix}-{index}-{name}"] = value
        formset = self.formset_class(data, instance=self.survey, prefix=self.prefix)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()

    def test_follower_fields_overwritten_with_lead_settings_on_save(self):
        from survey.models import Question

        self.save_formset(
            [
                {
                    "text": "Colors",
                    "order": "1",
                    "type": "radio",
                    "choices": "Red,Blue",
                    "other_option": "on",
                    "will_not_answer_option": "on",
                    "will_not_answer_label": "No answer",
                },
                {"order": "2", "type": "text", "group_with_previous": "on", "label": "Row 2"},
            ]
        )
        follower = self.survey.questions.get(order=2)
        self.assertEqual(follower.type, Question.RADIO)
        self.assertEqual(follower.choices, "Red,Blue")
        self.assertTrue(follower.other_option)
        self.assertTrue(follower.will_not_answer_option)
        self.assertEqual(follower.will_not_answer_label, "No answer")

    def test_scale_settings_propagate_to_followers(self):
        from survey.models import Question

        self.save_formset(
            [
                {"text": "Ratings", "order": "1", "type": "integer-scale", "scale_min": "0", "scale_max": "5"},
                {"order": "2", "type": "text", "group_with_previous": "on", "label": "Row 2"},
                {"order": "3", "type": "date", "group_with_previous": "on", "label": "Row 3"},
            ]
        )
        for order in (2, 3):
            follower = self.survey.questions.get(order=order)
            self.assertEqual(follower.type, Question.INTEGER_SCALE)
            self.assertEqual((follower.scale_min, follower.scale_max), (0, 5))


class PropagateLeadSettingsTests(TestCase):
    """A group holding divergent follower values ends up uniform, whichever
    way the questions were created."""

    def setUp(self):
        from survey.models import Survey

        self.survey = Survey.objects.create(name="S", description="d", need_logged_user=False)

    def question(self, order, grouped=False, category=None, **kwargs):
        from survey.models import Question

        defaults = {"text": "" if grouped else f"Question {order}", "required": False, "type": Question.TEXT}
        defaults.update(kwargs)
        return Question.objects.create(
            survey=self.survey, order=order, group_with_previous=grouped, category=category, **defaults
        )

    def test_divergent_follower_made_uniform(self):
        from survey.models import Question

        lead = self.question(1, type=Question.RADIO, choices="Red,Blue", other_option=True)
        follower = self.question(2, grouped=True, type=Question.TEXT, will_not_answer_option=True)
        changed = propagate_lead_settings(self.survey)
        self.assertEqual([question.pk for question in changed], [follower.pk])
        follower.refresh_from_db()
        self.assertEqual(follower.type, Question.RADIO)
        self.assertEqual(follower.choices, "Red,Blue")
        self.assertTrue(follower.other_option)
        self.assertFalse(follower.will_not_answer_option)
        lead.refresh_from_db()
        self.assertFalse(lead.will_not_answer_option)

    def test_uniform_group_left_alone(self):
        from survey.models import Question

        self.question(1, type=Question.RADIO, choices="Red,Blue")
        self.question(2, grouped=True, type=Question.RADIO, choices="Red,Blue")
        self.assertEqual(propagate_lead_settings(self.survey), [])

    def test_categories_kept_separate(self):
        from survey.models import Category, Question

        category_a = Category.objects.create(survey=self.survey, name="A", order=1)
        category_b = Category.objects.create(survey=self.survey, name="B", order=2)
        self.question(1, category=category_a, type=Question.RADIO, choices="Red,Blue")
        self.question(2, category=category_b, type=Question.TEXT)
        follower_b = self.question(3, grouped=True, category=category_b, type=Question.DATE)
        propagate_lead_settings(self.survey)
        follower_b.refresh_from_db()
        self.assertEqual(follower_b.type, Question.TEXT)
