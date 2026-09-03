from django.test import TestCase

from survey.admin_impl.question_groups import grouped_rows_without_predecessor


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
