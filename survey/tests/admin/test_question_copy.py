"""Tests for copying questions and their categories into another survey."""

from django.test import TestCase

from survey.admin.question_copy import copy_questions_to_survey
from survey.models import Category, Question, Survey


class TestCopyQuestionsToSurvey(TestCase):
    """Copy part of a 12-question survey into an 11-question one.

    Both surveys have two categories; "Background" exists in both.
    """

    def setUp(self):
        self.source = Survey.objects.create(name="Source", description="d", need_logged_user=False)
        self.target = Survey.objects.create(name="Target", description="d", need_logged_user=False)
        source_background = self.make_category(self.source, "Background", 1, "Source background")
        source_habits = self.make_category(self.source, "Habits", 2, "Daily habits")
        for order in range(1, 13):
            category = source_background if order <= 6 else source_habits
            self.make_question(self.source, f"S{order}", order, category)
        target_background = self.make_category(self.target, "Background", 1, "Target background")
        target_other = self.make_category(self.target, "Other", 2, "")
        for order in range(1, 12):
            category = target_background if order <= 5 else target_other
            self.make_question(self.target, f"T{order}", order, category)
        self.source_state = self.question_rows(self.source)

    def make_category(self, survey, name, order, description):
        return Category.objects.create(survey=survey, name=name, order=order, description=description)

    def make_question(self, survey, text, order, category):
        return Question.objects.create(
            survey=survey, text=text, order=order, category=category, required=True, type=Question.TEXT
        )

    def question_rows(self, survey):
        """(text, order, category name) of the survey's questions in order."""
        return [(q.text, q.order, q.category.name) for q in survey.questions.order_by("order", "id")]

    def category_rows(self, survey):
        """(name, order, description) of the survey's categories in order."""
        return [(c.name, c.order, c.description) for c in survey.categories.order_by("order", "id")]

    def copy(self):
        """Copy S3, S4 (Background) and S8, S9, S10 (Habits) to the target from order 5,
        passed out of order, with Background at category order 2 and Habits at 3."""
        questions = list(self.source.questions.filter(text__in=["S9", "S3", "S10", "S8", "S4"]).order_by("-order"))
        category_orders = {
            Category.objects.get(survey=self.source, name="Background"): 2,
            Category.objects.get(survey=self.source, name="Habits"): 3,
        }
        copy_questions_to_survey(questions, self.target, 5, category_orders)

    def test_copied_questions_are_inserted_sequentially(self):
        self.copy()
        self.assertEqual(
            [(text, order) for text, order, _ in self.question_rows(self.target)],
            [("T1", 1), ("T2", 2), ("T3", 3), ("T4", 4)]
            + [("S3", 5), ("S4", 6), ("S8", 7), ("S9", 8), ("S10", 9)]
            + [(f"T{n}", n + 5) for n in range(5, 12)],
        )

    def test_categories_are_copied_and_existing_ones_shifted(self):
        self.copy()
        self.assertEqual(
            self.category_rows(self.target),
            [
                ("Background", 1, "Target background"),
                ("Background", 2, "Source background"),
                ("Habits", 3, "Daily habits"),
                ("Other", 4, ""),
            ],
        )

    def test_copied_questions_use_the_copied_categories(self):
        self.copy()
        copied = self.target.questions.filter(text__startswith="S")
        self.assertEqual(
            {(q.text, q.category.name, q.category.description) for q in copied},
            {
                ("S3", "Background", "Source background"),
                ("S4", "Background", "Source background"),
                ("S8", "Habits", "Daily habits"),
                ("S9", "Habits", "Daily habits"),
                ("S10", "Habits", "Daily habits"),
            },
        )
        self.assertTrue(all(q.category.survey == self.target for q in copied))

    def test_existing_target_questions_keep_their_categories(self):
        self.copy()
        existing = [row for row in self.question_rows(self.target) if row[0].startswith("T")]
        self.assertEqual([category for _, _, category in existing], ["Background"] * 5 + ["Other"] * 6)
        target_background = Category.objects.get(survey=self.target, description="Target background")
        self.assertEqual(target_background.questions.count(), 5)

    def test_source_survey_is_unchanged(self):
        self.copy()
        self.assertEqual(self.question_rows(self.source), self.source_state)
        self.assertEqual(
            self.category_rows(self.source),
            [("Background", 1, "Source background"), ("Habits", 2, "Daily habits")],
        )
