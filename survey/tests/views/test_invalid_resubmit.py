"""Correcting an invalid answer on a category-paged survey.

A participant who leaves a required question empty gets the step back with
its error, fixes the answer and submits again. The surveys come from
invalid_resubmit.json: one paged by category with a required question in each
of two categories, and one holding a date question.
"""

from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from survey.models import Answer, Response

HERE = Path(__file__).parent
FIXTURE = Path(HERE, "invalid_resubmit.json")

PAGED_SURVEY = 100
NAME_QUESTION = 100
TOWN_QUESTION = 101

DATE_SURVEY = 101


class CategoryPagedResubmitTests(TestCase):
    fixtures = [FIXTURE]

    def step_url(self, step):
        if step == 0:
            return reverse("survey-detail", kwargs={"id": PAGED_SURVEY})
        return reverse("survey-detail-step", kwargs={"id": PAGED_SURVEY, "step": step})

    def answer(self, question_id, body):
        return {f"question_{question_id}": body}

    def test_missing_required_answer_is_reported_on_the_same_step(self):
        response = self.client.post(self.step_url(0), {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")
        self.assertContains(response, "Name")

    def test_corrected_answer_advances_to_the_next_category(self):
        self.client.post(self.step_url(0), {})
        response = self.client.post(self.step_url(0), self.answer(NAME_QUESTION, "Alice"))
        self.assertRedirects(response, self.step_url(1))

    def test_answers_corrected_on_both_steps_are_saved(self):
        self.client.post(self.step_url(0), {})
        self.client.post(self.step_url(0), self.answer(NAME_QUESTION, "Alice"))
        self.client.post(self.step_url(1), {})
        self.client.post(self.step_url(1), self.answer(TOWN_QUESTION, "Espoo"))

        self.assertEqual(Response.objects.filter(survey_id=PAGED_SURVEY).count(), 1)
        bodies = {answer.question_id: answer.body for answer in Answer.objects.all()}
        self.assertEqual(bodies[NAME_QUESTION], "Alice")
        self.assertEqual(bodies[TOWN_QUESTION], "Espoo")

    def test_invalid_step_is_redisplayed_with_the_submitted_answers(self):
        self.client.post(self.step_url(0), self.answer(NAME_QUESTION, "Alice"))
        response = self.client.post(self.step_url(1), {"unrelated": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Town")

    def test_invalid_step_keeps_posting_to_its_own_step(self):
        self.client.post(self.step_url(0), self.answer(NAME_QUESTION, "Alice"))
        response = self.client.post(self.step_url(1), {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'action="{self.step_url(1)}"')


class InvalidDateStepAssetTests(TestCase):
    """A date question needs its picker on the redisplayed invalid form too."""

    fixtures = [FIXTURE]

    def setUp(self):
        self.url = reverse("survey-detail", kwargs={"id": DATE_SURVEY})

    def test_the_picker_is_loaded_when_the_form_is_first_shown(self):
        self.assertContains(self.client.get(self.url), "flatpickr.min.js")

    def test_the_picker_is_loaded_on_a_redisplayed_invalid_form(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "flatpickr.min.js")
