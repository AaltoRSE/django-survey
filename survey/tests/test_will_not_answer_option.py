import uuid

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.test import TestCase

from survey.forms import ResponseForm
from survey.models import Answer, Question, Response
from survey.tests.test_other_option import make_question, make_survey, qd, store_answer


def make_scale_question(survey, order=1, required=True, text="Rating", scale_min=0, scale_max=10):
    """Create an INTEGER_SCALE question with the "will not answer" option
    enabled. make_question() has no kwarg for this, so it is set afterwards."""
    question = make_question(survey, Question.INTEGER_SCALE, order=order, required=required, text=text)
    question.scale_min = scale_min
    question.scale_max = scale_max
    question.will_not_answer_option = True
    question.save()
    return question


class WillNotAnswerOptionTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.question = make_scale_question(self.survey)

    def test_checked_creates_single_answer_with_sentinel(self):
        data = qd(
            {
                f"question_{self.question.pk}_wna": "on",
            }
        )
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        answers = Answer.objects.filter(response=response, question=self.question)
        self.assertEqual(answers.count(), 1)
        self.assertEqual(answers.first().body, ResponseForm.WILL_NOT_ANSWER_SENTINEL)

    def test_checked_wins_over_a_scale_value_also_posted(self):
        data = qd(
            {
                f"question_{self.question.pk}": "7",
                f"question_{self.question.pk}_wna": "on",
            }
        )
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        answers = Answer.objects.filter(response=response, question=self.question)
        self.assertEqual(answers.count(), 1)
        self.assertEqual(answers.first().body, ResponseForm.WILL_NOT_ANSWER_SENTINEL)

    def test_unchecked_with_scale_value_stores_normal_answer(self):
        data = qd({f"question_{self.question.pk}": "7"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        answers = Answer.objects.filter(response=response, question=self.question)
        self.assertEqual(answers.count(), 1)
        self.assertEqual(answers.first().body, "7")

    def test_required_unchecked_with_no_value_errors(self):
        data = qd({})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertFalse(form.is_valid())
        self.assertIn(f"question_{self.question.pk}", form.errors)

    def test_required_checked_with_no_scale_value_is_valid(self):
        data = qd({f"question_{self.question.pk}_wna": "on"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)

    def test_reedit_maps_stored_sentinel_to_wna_checkbox(self):
        user = User.objects.create_user(username="reeditor", password="testpass")
        response = Response.objects.create(survey=self.survey, user=user, interview_uuid=str(uuid.uuid4()))
        store_answer(self.question, response, ResponseForm.WILL_NOT_ANSWER_SENTINEL)

        form = ResponseForm(survey=self.survey, user=user, step=0)
        field = form.fields[f"question_{self.question.pk}"]
        wna_field = form.fields[f"question_{self.question.pk}_wna"]
        self.assertIsNone(field.initial)
        self.assertEqual(wna_field.initial, True)

    def test_session_rebind_with_raw_sentinel_round_trips(self):
        # Mirrors SurveyDetail.treat_valid_form: the session stores the
        # cleaned answer body (the sentinel, not the checkbox flag) as a plain
        # dict, and the form is rebuilt from it positionally.
        data = {f"question_{self.question.pk}": ResponseForm.WILL_NOT_ANSWER_SENTINEL}
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        answers = Answer.objects.filter(response=response, question=self.question)
        self.assertEqual(answers.count(), 1)
        self.assertEqual(answers.first().body, ResponseForm.WILL_NOT_ANSWER_SENTINEL)


class WillNotAnswerOptionValidationTests(TestCase):
    def setUp(self):
        self.survey = make_survey()

    def _question(self, qtype, will_not_answer_option=False, scale_min=None, scale_max=None):
        return Question(
            survey=self.survey,
            text="Question",
            order=1,
            required=True,
            type=qtype,
            will_not_answer_option=will_not_answer_option,
            scale_min=scale_min,
            scale_max=scale_max,
        )

    def test_will_not_answer_on_integer_scale_allowed(self):
        question = self._question(Question.INTEGER_SCALE, will_not_answer_option=True, scale_min=0, scale_max=10)
        question.full_clean()

    def test_will_not_answer_on_text_rejected(self):
        question = self._question(Question.TEXT, will_not_answer_option=True)
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_will_not_answer_on_radio_rejected(self):
        question = self._question(Question.RADIO, will_not_answer_option=True)
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_will_not_answer_disabled_on_text_does_not_raise(self):
        question = self._question(Question.TEXT, will_not_answer_option=False)
        question.full_clean()
