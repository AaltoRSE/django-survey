"""Correcting an invalid answer on a category-paged survey.

A participant who leaves a required question empty gets the step back with
its error, fixes the answer and submits again. The survey here is paged by
category, so the correction happens on a step whose answers are still only in
the session.
"""

from django.test import TestCase
from django.urls import reverse

from survey.models import Answer, Category, Question, Response, Survey
from survey.tests.test_other_option import make_survey


class CategoryPagedResubmitTests(TestCase):
    def setUp(self):
        self.survey = make_survey(display_method=Survey.BY_CATEGORY)
        self.first = Category.objects.create(survey=self.survey, name="First", order=1)
        self.second = Category.objects.create(survey=self.survey, name="Second", order=2)
        self.question_1 = Question.objects.create(
            survey=self.survey, text="Name", order=1, required=True, type=Question.TEXT, category=self.first
        )
        self.question_2 = Question.objects.create(
            survey=self.survey, text="Town", order=2, required=True, type=Question.TEXT, category=self.second
        )

    def step_url(self, step):
        if step == 0:
            return reverse("survey-detail", kwargs={"id": self.survey.pk})
        return reverse("survey-detail-step", kwargs={"id": self.survey.pk, "step": step})

    def answer(self, question, body):
        return {f"question_{question.pk}": body}

    def test_missing_required_answer_is_reported_on_the_same_step(self):
        response = self.client.post(self.step_url(0), {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")
        self.assertContains(response, "Name")

    def test_corrected_answer_advances_to_the_next_category(self):
        self.client.post(self.step_url(0), {})
        response = self.client.post(self.step_url(0), self.answer(self.question_1, "Alice"))
        self.assertRedirects(response, self.step_url(1))

    def test_answers_corrected_on_both_steps_are_saved(self):
        self.client.post(self.step_url(0), {})
        self.client.post(self.step_url(0), self.answer(self.question_1, "Alice"))
        self.client.post(self.step_url(1), {})
        self.client.post(self.step_url(1), self.answer(self.question_2, "Espoo"))

        self.assertEqual(Response.objects.filter(survey=self.survey).count(), 1)
        bodies = {answer.question_id: answer.body for answer in Answer.objects.all()}
        self.assertEqual(bodies[self.question_1.pk], "Alice")
        self.assertEqual(bodies[self.question_2.pk], "Espoo")

    def test_invalid_step_is_redisplayed_with_the_submitted_answers(self):
        self.client.post(self.step_url(0), self.answer(self.question_1, "Alice"))
        response = self.client.post(self.step_url(1), {"unrelated": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Town")

    def test_invalid_step_keeps_posting_to_its_own_step(self):
        self.client.post(self.step_url(0), self.answer(self.question_1, "Alice"))
        response = self.client.post(self.step_url(1), {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'action="{self.step_url(1)}"')


class InvalidDateStepAssetTests(TestCase):
    """A date question needs its picker on the redisplayed invalid form too."""

    def setUp(self):
        self.survey = make_survey(display_method=Survey.BY_CATEGORY)
        self.category = Category.objects.create(survey=self.survey, name="Dates", order=1)
        self.date_question = Question.objects.create(
            survey=self.survey, text="Born", order=1, required=True, type=Question.DATE, category=self.category
        )
        self.url = reverse("survey-detail", kwargs={"id": self.survey.pk})

    def test_the_picker_is_loaded_when_the_form_is_first_shown(self):
        self.assertContains(self.client.get(self.url), "flatpickr.min.js")

    def test_the_picker_is_loaded_on_a_redisplayed_invalid_form(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "flatpickr.min.js")
