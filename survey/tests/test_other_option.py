import uuid

from django.contrib.auth.models import AnonymousUser, User
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse

from survey.forms import ResponseForm
from survey.models import Answer, Question, Response, Survey


def make_survey(**kwargs):
    defaults = {
        "name": "Test survey",
        "description": "desc",
        "need_logged_user": False,
        "display_method": Survey.ALL_IN_ONE_PAGE,
    }
    defaults.update(kwargs)
    return Survey.objects.create(**defaults)


def make_question(survey, qtype, order, choices="", required=True, text="Question", other_option=False):
    return Question.objects.create(
        survey=survey,
        text=text,
        order=order,
        required=required,
        type=qtype,
        choices=choices,
        other_option=other_option,
    )


def qd(data):
    """Build a mutable QueryDict from a plain dict, supporting list values for
    multi-valued fields (mirrors what an HTML form POST produces)."""
    query_dict = QueryDict(mutable=True)
    for key, value in data.items():
        if isinstance(value, (list, tuple)):
            query_dict.setlist(key, value)
        else:
            query_dict[key] = value
    return query_dict


def store_answer(question, response, body):
    """Create an Answer with the given body while bypassing Answer.__init__'s
    choice validation, exactly as ResponseForm.save() does (body is assigned
    after construction, not passed to the constructor)."""
    answer = Answer(question=question, response=response)
    answer.body = body
    answer.save()
    return answer


class OtherOptionTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.question = make_question(
            self.survey, Question.RADIO, order=1, choices="Red,Blue", text="Color", other_option=True
        )

    def test_other_text_alone_answers_a_required_question(self):
        data = qd({f"question_{self.question.pk}_other": "Chartreuse"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        answers = Answer.objects.filter(response=response, question=self.question)
        self.assertEqual(answers.count(), 1)
        self.assertEqual(answers.first().body, "")
        self.assertEqual(answers.first().other_text, "Chartreuse")

    def test_choice_and_other_text_are_both_stored(self):
        data = qd({f"question_{self.question.pk}": "red", f"question_{self.question.pk}_other": "Chartreuse"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        answer = Answer.objects.get(response=response, question=self.question)
        self.assertEqual(answer.body, "red")
        self.assertEqual(answer.other_text, "Chartreuse")

    def test_empty_answer_and_other_text_on_required_question_errors(self):
        data = qd({f"question_{self.question.pk}_other": "  "})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertFalse(form.is_valid())
        self.assertIn(f"question_{self.question.pk}", form.errors)

    def test_invalid_answer_errors_even_with_other_text(self):
        data = qd({f"question_{self.question.pk}": "green", f"question_{self.question.pk}_other": "Chartreuse"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertFalse(form.is_valid())
        self.assertIn(f"question_{self.question.pk}", form.errors)

    def test_other_label_shown_next_to_the_text_input(self):
        self.question.other_label = "Something else"
        self.question.save()
        page = self.client.get(reverse("survey-detail", kwargs={"id": self.survey.pk}))
        self.assertContains(page, f"question-{self.question.pk}-other-option")
        # Only next to the companion input: "other" is not one of the choices.
        self.assertContains(page, '<span class="survey-question-option-label">Something else</span>', count=1)

    def test_plain_question_input_not_wrapped_in_a_label(self):
        survey = make_survey(name="Plain survey")
        question = make_question(survey, Question.TEXT, order=1, text="Comments")
        page = self.client.get(reverse("survey-detail", kwargs={"id": survey.pk}))
        self.assertContains(page, f'name="question_{question.pk}"')
        self.assertNotContains(page, "survey-question-option-label")

    def test_regular_choice_still_stores_normally(self):
        data = qd({f"question_{self.question.pk}": "red"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        answers = Answer.objects.filter(response=response, question=self.question)
        self.assertEqual(answers.count(), 1)
        self.assertEqual(answers.first().body, "red")

    def test_reedit_moves_stale_value_to_other_field(self):
        user = User.objects.create_user(username="reeditor", password="testpass")
        response = Response.objects.create(survey=self.survey, user=user, interview_uuid=str(uuid.uuid4()))
        answer = store_answer(self.question, response, "Some random text")
        answer.other_text = "Typed"
        answer.save()

        form = ResponseForm(survey=self.survey, user=user, step=0)
        field = form.fields[f"question_{self.question.pk}"]
        other_field = form.fields[f"question_{self.question.pk}_other"]
        self.assertIsNone(field.initial)
        self.assertEqual(other_field.initial, "Typed; Some random text")

    def test_reedit_restores_stored_other_text(self):
        user = User.objects.create_user(username="reeditor4", password="testpass")
        response = Response.objects.create(survey=self.survey, user=user, interview_uuid=str(uuid.uuid4()))
        answer = store_answer(self.question, response, "red")
        answer.other_text = "Chartreuse"
        answer.save()

        form = ResponseForm(survey=self.survey, user=user, step=0)
        self.assertEqual(form.fields[f"question_{self.question.pk}"].initial, "red")
        self.assertEqual(form.fields[f"question_{self.question.pk}_other"].initial, "Chartreuse")

    def test_reedit_of_normal_choice_does_not_fill_other_field(self):
        user = User.objects.create_user(username="reeditor2", password="testpass")
        response = Response.objects.create(survey=self.survey, user=user, interview_uuid=str(uuid.uuid4()))
        store_answer(self.question, response, "red")

        form = ResponseForm(survey=self.survey, user=user, step=0)
        field = form.fields[f"question_{self.question.pk}"]
        self.assertEqual(field.initial, "red")
        self.assertFalse(form.fields[f"question_{self.question.pk}_other"].initial)

    def test_session_rebind_round_trips_other_text(self):
        # Mirrors SurveyDetail.treat_valid_form: the session stores the
        # cleaned answer and its "other" text as a plain dict, and the form
        # is rebuilt from it positionally.
        data = {f"question_{self.question.pk}": "red", f"question_{self.question.pk}_other": "Chartreuse"}
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        answer = Answer.objects.get(response=response, question=self.question)
        self.assertEqual(answer.body, "red")
        self.assertEqual(answer.other_text, "Chartreuse")


class OtherOptionValidationTests(TestCase):
    def setUp(self):
        self.survey = make_survey()

    def _question(self, qtype, choices="", other_option=False):
        return Question(
            survey=self.survey,
            text="Question",
            order=1,
            required=True,
            type=qtype,
            choices=choices,
            other_option=other_option,
        )

    def test_other_on_radio_allowed(self):
        question = self._question(Question.RADIO, choices="Red,Blue", other_option=True)
        question.full_clean()

    def test_other_on_select_allowed(self):
        question = self._question(Question.SELECT, choices="Red,Blue", other_option=True)
        question.full_clean()

    def test_other_on_select_multiple_allowed(self):
        question = self._question(Question.SELECT_MULTIPLE, choices="Red,Blue", other_option=True)
        question.full_clean()

    def test_other_on_text_allowed(self):
        question = self._question(Question.TEXT, other_option=True)
        question.full_clean()

    def test_other_disabled_on_text_does_not_raise(self):
        question = self._question(Question.TEXT, other_option=False)
        question.full_clean()


class OtherOptionOnTextQuestionTests(TestCase):
    """The "other" flag is honored on every question type: the companion field
    is attached and rendered even for a free-text question."""

    def setUp(self):
        self.survey = make_survey()
        self.question = make_question(self.survey, Question.TEXT, order=1, text="Comments", other_option=True)

    def test_companion_field_attached_and_rendered(self):
        form = ResponseForm(survey=self.survey, user=AnonymousUser(), step=0)
        self.assertIn(f"question_{self.question.pk}_other", form.fields)
        page = self.client.get(reverse("survey-detail", kwargs={"id": self.survey.pk}))
        self.assertContains(page, f"question_{self.question.pk}_other")

    def test_submitted_text_answer_stored_unchanged(self):
        data = qd({f"question_{self.question.pk}": "Free text"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        answers = Answer.objects.filter(response=response, question=self.question)
        self.assertEqual(answers.count(), 1)
        self.assertEqual(answers.first().body, "Free text")

    def test_reedit_keeps_stored_text_as_the_field_value(self):
        user = User.objects.create_user(username="reeditor3", password="testpass")
        response = Response.objects.create(survey=self.survey, user=user, interview_uuid=str(uuid.uuid4()))
        store_answer(self.question, response, "Free text")

        form = ResponseForm(survey=self.survey, user=user, step=0)
        self.assertEqual(form.fields[f"question_{self.question.pk}"].initial, "Free text")
