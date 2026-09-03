from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from survey.exporter.csv.survey2csv import Survey2Csv
from survey.forms import ResponseForm
from survey.impl.question_groups import group_leads, export_name, mark_group_boundaries
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
