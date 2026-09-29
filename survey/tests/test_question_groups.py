from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from survey.exporter.csv.survey2csv import Survey2Csv
from survey.forms import ResponseForm
from survey.impl.question_groups import (
    group_leads,
    export_name,
    mark_group_boundaries,
    mark_row_parity,
    parse_header_rows,
)
from survey.models import Category, Question, Survey
from survey.tests.test_other_option import make_question, make_survey


class GroupLeadsTests(TestCase):
    def setUp(self):
        self.survey = make_survey()

    def test_standalone_question_leads_itself(self):
        question = make_question(self.survey, Question.TEXT, order=1, text="Q1")
        leads = group_leads([question])
        self.assertEqual(leads[question.pk], question)

    def test_two_group_questions_join_preceding_standalone(self):
        lead = make_question(self.survey, Question.TEXT, order=1, text="Q1")
        follower_1 = Question.objects.create(
            survey=self.survey, text="", order=2, required=False, type=Question.TEXT, group_with_previous=True
        )
        follower_2 = Question.objects.create(
            survey=self.survey, text="", order=3, required=False, type=Question.TEXT, group_with_previous=True
        )
        leads = group_leads([lead, follower_1, follower_2])
        self.assertEqual(leads[lead.pk], lead)
        self.assertEqual(leads[follower_1.pk], lead)
        self.assertEqual(leads[follower_2.pk], lead)

    def test_group_question_first_in_list_leads_itself(self):
        follower = Question.objects.create(
            survey=self.survey, text="", order=1, required=False, type=Question.TEXT, group_with_previous=True
        )
        leads = group_leads([follower])
        self.assertEqual(leads[follower.pk], follower)

    def test_categories_kept_separate(self):
        category_a = Category.objects.create(survey=self.survey, name="A", order=1)
        category_b = Category.objects.create(survey=self.survey, name="B", order=2)
        lead_a = Question.objects.create(
            survey=self.survey, text="Lead A", order=1, required=False, type=Question.TEXT, category=category_a
        )
        lead_b = Question.objects.create(
            survey=self.survey, text="Lead B", order=2, required=False, type=Question.TEXT, category=category_b
        )
        follower_b = Question.objects.create(
            survey=self.survey,
            text="",
            order=3,
            required=False,
            type=Question.TEXT,
            category=category_b,
            group_with_previous=True,
        )
        # Questions belonging to different categories, given to group_leads in a
        # single flat list, must never merge into the same group.
        leads = group_leads([lead_a, lead_b])
        leads.update(group_leads([lead_b, follower_b]))
        self.assertEqual(leads[lead_a.pk], lead_a)
        self.assertEqual(leads[lead_b.pk], lead_b)
        self.assertEqual(leads[follower_b.pk], lead_b)


class MarkGroupBoundariesTests(TestCase):
    def test_wna_companion_field_closes_the_group(self):
        class FakeField:
            pass

        main_field = FakeField()
        main_field.group_id = 1
        wna_field = FakeField()
        wna_field.group_id = 1

        fields = {"question_1": main_field, "question_1_wna": wna_field}
        mark_group_boundaries(fields)

        self.assertTrue(main_field.starts_group)
        self.assertFalse(main_field.ends_group)
        self.assertFalse(wna_field.starts_group)
        self.assertTrue(wna_field.ends_group)


class ExportNameTests(TestCase):
    def test_export_name_uses_label_when_set(self):
        survey = make_survey()
        lead = make_question(survey, Question.TEXT, order=1, text="Flavors")
        follower = Question.objects.create(
            survey=survey, text="", order=2, required=False, type=Question.TEXT, label="Chocolate"
        )
        self.assertEqual(export_name(follower, lead), "Flavors - Chocolate")

    def test_export_name_is_lead_text_without_label(self):
        survey = make_survey()
        lead = make_question(survey, Question.TEXT, order=1, text="Flavors")
        self.assertEqual(export_name(lead, lead), "Flavors")


class ParseHeaderRowsTests(TestCase):
    def test_multiple_lines_become_multiple_rows(self):
        rows = parse_header_rows("0,1,2\nlow,,high", ",")
        self.assertEqual(rows, [["0", "1", "2"], ["low", "", "high"]])

    def test_blank_lines_are_skipped(self):
        rows = parse_header_rows("0,1\n\n   \n2,3", ",")
        self.assertEqual(rows, [["0", "1"], ["2", "3"]])

    def test_cells_are_stripped_but_empty_cells_kept(self):
        rows = parse_header_rows(" a , , b ", ",")
        self.assertEqual(rows, [["a", "", "b"]])

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(parse_header_rows("", ","), [])
        self.assertEqual(parse_header_rows(None, ","), [])


class MarkRowParityTests(TestCase):
    def test_parity_alternates_within_a_group(self):
        class FakeField:
            pass

        fields = {}
        for i in range(4):
            field = FakeField()
            field.group_id = 1
            fields[f"question_{i}"] = field
        mark_row_parity(fields)
        parities = [field.row_parity for field in fields.values()]
        self.assertEqual(parities, ["odd", "even", "odd", "even"])

    def test_parity_restarts_for_each_group(self):
        class FakeField:
            pass

        first, second, third = FakeField(), FakeField(), FakeField()
        first.group_id = 1
        second.group_id = 1
        third.group_id = 2

        fields = {"a": first, "b": second, "c": third}
        mark_row_parity(fields)

        self.assertEqual(first.row_parity, "odd")
        self.assertEqual(second.row_parity, "even")
        self.assertEqual(third.row_parity, "odd")

    def test_fields_without_group_id_are_odd(self):
        class FakeField:
            pass

        first, second = FakeField(), FakeField()

        fields = {"a": first, "b": second}
        mark_row_parity(fields)

        self.assertEqual(first.row_parity, "odd")
        self.assertEqual(second.row_parity, "odd")


class QuestionGroupRenderingTests(TestCase):
    def setUp(self):
        self.survey = make_survey(display_method=Survey.ALL_IN_ONE_PAGE)
        self.standalone = make_question(self.survey, Question.TEXT, order=1, text="Standalone question")
        self.lead = make_question(self.survey, Question.TEXT, order=2, text="Flavors")
        self.follower_1 = Question.objects.create(
            survey=self.survey,
            text="",
            order=3,
            required=False,
            type=Question.TEXT,
            group_with_previous=True,
            label="Chocolate",
        )
        self.follower_2 = Question.objects.create(
            survey=self.survey,
            text="",
            order=4,
            required=False,
            type=Question.TEXT,
            group_with_previous=True,
            label="Strawberry",
        )
        response = self.client.get(reverse("survey-detail", kwargs={"id": self.survey.pk}))
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()

    def test_one_group_per_standalone_question(self):
        self.assertIn(f'class="survey-question text-question question-{self.standalone.pk}"', self.html)

    def test_group_present_once_for_lead(self):
        self.assertIn(f'class="survey-question text-question question-{self.lead.pk}"', self.html)
        self.assertIn(f"question-{self.lead.pk}-line", self.html)
        self.assertEqual(self.html.count(">Flavors"), 1)

    def test_group_shows_each_row_label(self):
        self.assertIn(">Chocolate<", self.html)
        self.assertIn(">Strawberry<", self.html)


class GroupRowLabelsOnAllQuestionsRenderingTests(TestCase):
    """Row labels populated on every question of a group, the lead included.

    Follower questions look like real admin-created grouped questions: the
    admin hides text/description for grouped questions, so they stay blank.
    """

    def setUp(self):
        self.survey = make_survey(display_method=Survey.ALL_IN_ONE_PAGE)
        self.lead = make_question(self.survey, Question.TEXT, order=1, text="Flavors")
        self.lead.label = "Vanilla"
        self.lead.save()
        self.follower_1 = Question.objects.create(
            survey=self.survey,
            text="",
            order=2,
            required=False,
            type=Question.TEXT,
            group_with_previous=True,
            label="Chocolate",
        )
        self.follower_2 = Question.objects.create(
            survey=self.survey,
            text="",
            order=3,
            required=False,
            type=Question.TEXT,
            group_with_previous=True,
            label="Strawberry",
        )
        response = self.client.get(reverse("survey-detail", kwargs={"id": self.survey.pk}))
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()

    def test_every_row_label_rendered_when_all_questions_have_labels(self):
        self.assertIn(">Vanilla<", self.html)
        self.assertIn(">Chocolate<", self.html)
        self.assertIn(">Strawberry<", self.html)


class GroupRowLabelsPagedSurveyRenderingTests(TestCase):
    """A grouped question block on a paged (one question per page) survey.

    The rows of a group form a single table and only make sense together, so
    the page on which the group appears must show every row of the group,
    each with its row label.
    """

    def setUp(self):
        self.survey = make_survey(display_method=Survey.BY_QUESTION)
        self.lead = make_question(self.survey, Question.TEXT, order=1, text="Flavors")
        self.lead.label = "Vanilla"
        self.lead.save()
        self.follower_1 = Question.objects.create(
            survey=self.survey,
            text="",
            order=2,
            required=False,
            type=Question.TEXT,
            group_with_previous=True,
            label="Chocolate",
        )
        self.follower_2 = Question.objects.create(
            survey=self.survey,
            text="",
            order=3,
            required=False,
            type=Question.TEXT,
            group_with_previous=True,
            label="Strawberry",
        )
        response = self.client.get(reverse("survey-detail", kwargs={"id": self.survey.pk}))
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()

    def test_every_row_label_rendered_on_the_group_page(self):
        self.assertIn(">Vanilla<", self.html)
        self.assertIn(">Chocolate<", self.html)
        self.assertIn(">Strawberry<", self.html)


class HeaderRowsRenderingTests(TestCase):
    def setUp(self):
        self.survey = make_survey(display_method=Survey.ALL_IN_ONE_PAGE)
        self.lead = make_question(self.survey, Question.RADIO, order=1, choices="Yes,No", text="Ratings")
        self.lead.header_rows = "0,1,2\nlow,,high"
        self.lead.save()
        self.follower = Question.objects.create(
            survey=self.survey,
            text="",
            order=2,
            required=False,
            type=Question.RADIO,
            choices="Yes,No",
            group_with_previous=True,
            label="Row 2",
        )
        response = self.client.get(reverse("survey-detail", kwargs={"id": self.survey.pk}))
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()

    def test_header_line_row_and_cell_classes_present(self):
        self.assertIn("survey-question-header-line", self.html)
        self.assertIn("survey-question-header-row", self.html)
        self.assertIn("survey-question-header-cell", self.html)

    def test_header_cell_has_numbered_pk_specific_class(self):
        self.assertIn(f"question-{self.lead.pk}-header-cell-1", self.html)

    def test_header_rendered_once_not_per_follower(self):
        self.assertEqual(self.html.count("survey-question-header-line"), 2)

    def test_row_parity_classes_present(self):
        self.assertIn("survey-question-line-odd", self.html)
        self.assertIn("survey-question-line-even", self.html)


class GroupHeaderFieldDefaultsTests(TestCase):
    def test_group_header_defaults_to_true(self):
        question = make_question(make_survey(), Question.TEXT, order=1, text="Q")
        self.assertTrue(question.group_header)

    def test_hide_answer_labels_defaults_to_false(self):
        question = make_question(make_survey(), Question.TEXT, order=1, text="Q")
        self.assertFalse(question.hide_answer_labels)

    def test_follower_cannot_be_a_group_header(self):
        survey = make_survey()
        make_question(survey, Question.TEXT, order=1, text="Lead")
        follower = Question.objects.create(
            survey=survey,
            text="",
            order=2,
            required=False,
            type=Question.TEXT,
            group_with_previous=True,
            group_header=True,
        )
        follower.refresh_from_db()
        self.assertFalse(follower.group_header)


class HideAnswerLabelsRenderingTests(TestCase):
    """hide_answer_labels on the group's lead removes the option-label texts
    for every row of the group; header rows remain as the replacement."""

    def render(self, hide):
        survey = make_survey(display_method=Survey.ALL_IN_ONE_PAGE)
        lead = make_question(survey, Question.RADIO, order=1, choices="Yes,No", text="Ratings")
        lead.header_rows = "Yes,No"
        lead.hide_answer_labels = hide
        lead.save()
        # The follower keeps the field's default: the flag is read from the lead.
        Question.objects.create(
            survey=survey,
            text="",
            order=2,
            required=False,
            type=Question.RADIO,
            choices="Yes,No",
            group_with_previous=True,
            label="Row 2",
        )
        response = self.client.get(reverse("survey-detail", kwargs={"id": survey.pk}))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_option_labels_hidden_for_the_whole_group(self):
        html = self.render(hide=True)
        self.assertNotIn("survey-question-option-label", html)
        self.assertIn(">Row 2<", html)

    def test_header_rows_still_rendered(self):
        html = self.render(hide=True)
        self.assertIn("survey-question-header-cell", html)

    def test_option_labels_rendered_without_the_flag(self):
        html = self.render(hide=False)
        self.assertIn('<span class="survey-question-option-label">Yes</span>', html)


class QuestionValidationTests(TestCase):
    def setUp(self):
        self.survey = make_survey()

    def test_standalone_with_blank_text_rejected(self):
        question = Question(
            survey=self.survey, text="", order=1, required=False, type=Question.TEXT, group_with_previous=False
        )
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_group_question_with_blank_text_accepted(self):
        question = Question(
            survey=self.survey, text="", order=1, required=False, type=Question.TEXT, group_with_previous=True
        )
        question.full_clean(exclude=["choices"])


class CsvHeaderTests(TestCase):
    def test_group_row_header_is_lead_text_and_label(self):
        survey = make_survey()
        lead = make_question(survey, Question.TEXT, order=1, text="Flavors")
        Question.objects.create(
            survey=survey,
            text="",
            order=2,
            required=False,
            type=Question.TEXT,
            group_with_previous=True,
            label="Chocolate",
        )
        exporter = Survey2Csv(survey)
        header, _order = exporter.get_header_and_order()
        self.assertIn("Flavors - Chocolate", header)
