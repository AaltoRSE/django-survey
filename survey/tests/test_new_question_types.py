import uuid

from django import forms
from django.contrib.auth.models import AnonymousUser, User
from django.http import QueryDict
from django.test import TestCase

from survey.forms import ResponseForm
from survey.models import Answer, Question, Response, Survey
from survey.widgets import NativeDateTimeInput, NativeTimeInput


def make_survey(**kwargs):
    defaults = {
        "name": "Test survey",
        "description": "desc",
        "need_logged_user": False,
        "display_method": Survey.ALL_IN_ONE_PAGE,
    }
    defaults.update(kwargs)
    return Survey.objects.create(**defaults)


def make_question(survey, qtype, order, choices="", required=True, text="Question"):
    return Question.objects.create(
        survey=survey,
        text=text,
        order=order,
        required=required,
        type=qtype,
        choices=choices,
    )


def qd(data):
    """Build a mutable QueryDict from a plain dict (mirrors an HTML form POST)."""
    query_dict = QueryDict(mutable=True)
    for key, value in data.items():
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


class QuestionTypeRegistrationTests(TestCase):
    def test_new_types_are_registered_as_question_type_choices(self):
        choices = Question._meta.get_field("type").choices
        self.assertIn((Question.LIKERT_5, "5-point likert"), choices)
        self.assertIn((Question.TIME, "time"), choices)
        self.assertIn((Question.DATETIME, "date and time"), choices)

    def test_likert_question_does_not_require_choices(self):
        survey = make_survey()
        question = Question(survey=survey, text="Satisfaction", order=1, required=True, type=Question.LIKERT_5, choices="")
        question.full_clean()
        question.save()
        question.refresh_from_db()
        self.assertEqual(question.type, Question.LIKERT_5)
        self.assertEqual(question.choices, "")


class FieldWidgetMappingTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.likert = make_question(self.survey, Question.LIKERT_5, order=1, choices="", text="Satisfaction")
        self.time_q = make_question(self.survey, Question.TIME, order=2, choices="", required=False, text="When")
        self.datetime_q = make_question(
            self.survey, Question.DATETIME, order=3, choices="", required=False, text="Date and time"
        )
        self.form = ResponseForm(survey=self.survey, user=AnonymousUser(), step=0)

    def test_time_field_is_time_field_with_native_time_widget(self):
        field = self.form.fields[f"question_{self.time_q.pk}"]
        self.assertIsInstance(field, forms.TimeField)
        self.assertIsInstance(field.widget, NativeTimeInput)
        self.assertEqual(field.widget.input_type, "time")

    def test_datetime_field_is_datetime_field_with_native_datetime_widget(self):
        field = self.form.fields[f"question_{self.datetime_q.pk}"]
        self.assertIsInstance(field, forms.DateTimeField)
        self.assertIsInstance(field.widget, NativeDateTimeInput)
        self.assertEqual(field.widget.input_type, "datetime-local")

    def test_likert_field_is_choice_field_with_radio_widget(self):
        field = self.form.fields[f"question_{self.likert.pk}"]
        self.assertIsInstance(field, forms.ChoiceField)
        self.assertIsInstance(field.widget, forms.RadioSelect)

    def test_likert_choices_are_the_fixed_five_point_scale(self):
        field = self.form.fields[f"question_{self.likert.pk}"]
        choices = list(field.choices)
        self.assertEqual(len(choices), 5)
        slugs = [value for value, _ in choices]
        self.assertEqual(slugs, ["strongly-disagree", "disagree", "neutral", "agree", "strongly-agree"])
        labels = [label for _, label in choices]
        self.assertEqual(labels, ["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"])

    def test_new_type_fields_expose_question_type_in_widget_attrs(self):
        for question in (self.likert, self.time_q, self.datetime_q):
            field = self.form.fields[f"question_{question.pk}"]
            self.assertEqual(field.widget.attrs["question_type"], question.type)


class PostRoundTripTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.time_q = make_question(self.survey, Question.TIME, order=1, choices="", required=True, text="When")
        self.datetime_q = make_question(
            self.survey, Question.DATETIME, order=2, choices="", required=True, text="Date and time"
        )
        self.likert = make_question(self.survey, Question.LIKERT_5, order=3, choices="", required=True, text="Satisfaction")

    def _valid_data(self):
        return qd(
            {
                f"question_{self.time_q.pk}": "14:30",
                f"question_{self.datetime_q.pk}": "2026-08-10T14:30",
                f"question_{self.likert.pk}": "agree",
            }
        )

    def test_time_answer_stored_as_hh_mm_ss(self):
        form = ResponseForm(self._valid_data(), survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        self.assertEqual(Answer.objects.get(response=response, question=self.time_q).body, "14:30:00")

    def test_datetime_answer_stored_as_aware_isoformat(self):
        form = ResponseForm(self._valid_data(), survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        self.assertEqual(
            Answer.objects.get(response=response, question=self.datetime_q).body,
            "2026-08-10T14:30:00+00:00",
        )

    def test_likert_answer_stored_as_slug(self):
        form = ResponseForm(self._valid_data(), survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        self.assertEqual(Answer.objects.get(response=response, question=self.likert).body, "agree")

    def test_time_and_datetime_cleaned_data_are_json_serializable_strings(self):
        form = ResponseForm(self._valid_data(), survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        time_value = form.cleaned_data[f"question_{self.time_q.pk}"]
        datetime_value = form.cleaned_data[f"question_{self.datetime_q.pk}"]
        self.assertIsInstance(time_value, str)
        self.assertIsInstance(datetime_value, str)
        self.assertEqual(time_value, "14:30:00")
        self.assertEqual(datetime_value, "2026-08-10T14:30:00+00:00")


class RedisplayTests(TestCase):
    """Covers editable_answers redisplay: stored Answer bodies must be parsed
    back into the native-input widgets' expected value= format."""

    def setUp(self):
        self.survey = make_survey(need_logged_user=True, editable_answers=True)
        self.time_q = make_question(self.survey, Question.TIME, order=1, choices="", required=False, text="When")
        self.datetime_q = make_question(
            self.survey, Question.DATETIME, order=2, choices="", required=False, text="Date and time"
        )
        self.user = User.objects.create_user(username="redisplay", password="testpass")
        self.response = Response.objects.create(survey=self.survey, user=self.user, interview_uuid=str(uuid.uuid4()))
        store_answer(self.time_q, self.response, "14:30:00")
        # Legacy stored format (space separator instead of "T"), as produced
        # by str(aware_datetime) rather than .isoformat().
        store_answer(self.datetime_q, self.response, "2026-08-10 14:30:00+00:00")

    def test_time_field_redisplays_stored_value(self):
        form = ResponseForm(survey=self.survey, user=self.user, step=0)
        self.assertIn('value="14:30:00"', str(form))

    def test_datetime_field_redisplays_legacy_stored_value(self):
        form = ResponseForm(survey=self.survey, user=self.user, step=0)
        self.assertIn('value="2026-08-10T14:30"', str(form))


class InvalidDatetimePostTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.time_q = make_question(self.survey, Question.TIME, order=1, choices="", required=False, text="When")
        self.datetime_q = make_question(
            self.survey, Question.DATETIME, order=2, choices="", required=False, text="Date and time"
        )

    def _data(self):
        return qd({f"question_{self.time_q.pk}": "14:30", f"question_{self.datetime_q.pk}": "not-a-date"})

    def test_invalid_datetime_value_errors_only_on_that_field(self):
        form = ResponseForm(self._data(), survey=self.survey, user=AnonymousUser(), step=0)
        self.assertFalse(form.is_valid())
        self.assertIn(f"question_{self.datetime_q.pk}", form.errors)
        self.assertNotIn(f"question_{self.time_q.pk}", form.errors)

    def test_invalid_datetime_raw_value_is_retained_in_rendered_html(self):
        form = ResponseForm(self._data(), survey=self.survey, user=AnonymousUser(), step=0)
        form.is_valid()
        self.assertIn("not-a-date", str(form))
