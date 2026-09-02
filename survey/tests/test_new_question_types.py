import re
import uuid

from django import forms
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.template.loader import render_to_string
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


def make_scale_question(survey, scale_min, scale_max, order=1, required=True, text="On this scale?"):
    question = make_question(survey, Question.INTEGER_SCALE, order=order, required=required, text=text)
    question.scale_min = scale_min
    question.scale_max = scale_max
    question.save()
    return question


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


class IntegerScaleRegistrationTests(TestCase):
    def test_integer_scale_is_registered_as_a_question_type_choice(self):
        choices = Question._meta.get_field("type").choices
        self.assertIn((Question.INTEGER_SCALE, "integer scale"), choices)

    def test_the_fixed_scale_types_it_replaces_are_gone(self):
        registered = [value for value, _label in Question._meta.get_field("type").choices]
        self.assertNotIn("scale-0-10", registered)
        self.assertNotIn("scale-minus5-5", registered)

    def test_labels_run_from_the_minimum_to_the_maximum_inclusive(self):
        survey = make_survey()
        for scale_min, scale_max in ((0, 10), (-5, 5), (1, 7)):
            question = make_scale_question(survey, scale_min, scale_max)
            self.assertEqual(
                question.get_clean_choices(), [str(step) for step in range(scale_min, scale_max + 1)]
            )

    def test_negative_values_keep_their_sign_instead_of_being_slugified(self):
        """slugify() would strip the leading '-' and collapse '-5' onto '5'."""
        question = make_scale_question(make_survey(), -5, 5)
        values = [value for value, _label in question.get_choices()]
        self.assertEqual(values, [str(step) for step in range(-5, 6)])
        self.assertEqual(len(set(values)), 11)

    def test_a_scale_without_limits_has_no_steps_rather_than_crashing(self):
        question = make_question(make_survey(), Question.INTEGER_SCALE, order=1, text="Unconfigured")
        self.assertEqual(question.get_clean_choices(), [])
        self.assertEqual(question.get_choices(), ())


class IntegerScaleLimitValidationTests(TestCase):
    def setUp(self):
        self.survey = make_survey()

    def _question(self, scale_min, scale_max):
        return Question(
            survey=self.survey, text="On this scale?", order=1, required=True,
            type=Question.INTEGER_SCALE, choices="", scale_min=scale_min, scale_max=scale_max,
        )

    def test_valid_limits_pass_full_clean(self):
        self._question(1, 7).full_clean()

    def test_missing_limits_are_rejected(self):
        with self.assertRaises(ValidationError):
            self._question(None, None).full_clean()
        with self.assertRaises(ValidationError):
            self._question(0, None).full_clean()

    def test_maximum_must_be_greater_than_minimum(self):
        with self.assertRaises(ValidationError):
            self._question(5, 5).full_clean()
        with self.assertRaises(ValidationError):
            self._question(5, 1).full_clean()

    def test_range_wider_than_the_step_cap_is_rejected(self):
        self._question(0, 50).full_clean()  # 51 steps, the widest allowed
        with self.assertRaises(ValidationError):
            self._question(0, 51).full_clean()

    def test_limits_are_not_required_on_other_question_types(self):
        question = Question(
            survey=self.survey, text="Satisfaction", order=1, required=True, type=Question.LIKERT_5, choices=""
        )
        question.full_clean()


class IntegerScaleFieldWidgetTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.scale = make_scale_question(self.survey, -5, 5, text="-5 = much worse, 5 = much better")
        self.form = ResponseForm(survey=self.survey, user=AnonymousUser(), step=0)

    def test_scale_field_is_choice_field_with_radio_widget(self):
        field = self.form.fields[f"question_{self.scale.pk}"]
        self.assertIsInstance(field, forms.ChoiceField)
        self.assertIsInstance(field.widget, forms.RadioSelect)

    def test_scale_choices_use_the_number_as_both_value_and_label(self):
        field = self.form.fields[f"question_{self.scale.pk}"]
        choices = list(field.choices)
        self.assertEqual(len(choices), 11)
        self.assertEqual([value for value, _ in choices], [str(step) for step in range(-5, 6)])
        self.assertEqual([label for _, label in choices], [str(step) for step in range(-5, 6)])

    def test_scale_field_exposes_question_type_in_widget_attrs(self):
        field = self.form.fields[f"question_{self.scale.pk}"]
        self.assertEqual(field.widget.attrs["question_type"], Question.INTEGER_SCALE)


class IntegerScalePostTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.scale = make_scale_question(self.survey, -5, 5)

    def _post(self, value):
        return ResponseForm(
            qd({f"question_{self.scale.pk}": value}), survey=self.survey, user=AnonymousUser(), step=0
        )

    def test_negative_answer_is_stored_with_its_sign(self):
        form = self._post("-5")
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        self.assertEqual(Answer.objects.get(response=response, question=self.scale).body, "-5")

    def test_zero_is_a_valid_answer(self):
        form = self._post("0")
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        self.assertEqual(Answer.objects.get(response=response, question=self.scale).body, "0")

    def test_positive_answer_is_stored_as_the_chosen_number(self):
        form = self._post("5")
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        self.assertEqual(Answer.objects.get(response=response, question=self.scale).body, "5")

    def test_out_of_range_value_is_rejected_by_the_form(self):
        form = self._post("-6")
        self.assertFalse(form.is_valid())
        self.assertIn(f"question_{self.scale.pk}", form.errors)

    def test_required_scale_question_cannot_be_left_blank(self):
        form = self._post("")
        self.assertFalse(form.is_valid())
        self.assertIn(f"question_{self.scale.pk}", form.errors)

    def test_a_seven_point_scale_starting_at_one_accepts_its_own_range(self):
        survey = make_survey()
        scale = make_scale_question(survey, 1, 7)
        form = ResponseForm(qd({f"question_{scale.pk}": "7"}), survey=survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        self.assertEqual(Answer.objects.get(response=response, question=scale).body, "7")
        rejected = ResponseForm(qd({f"question_{scale.pk}": "0"}), survey=survey, user=AnonymousUser(), step=0)
        self.assertFalse(rejected.is_valid())


class IntegerScaleAnswerValidationTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.scale = make_scale_question(self.survey, -5, 5)
        self.response = Response.objects.create(survey=self.survey, interview_uuid=str(uuid.uuid4()))

    def test_answer_inside_the_scale_is_accepted(self):
        answer = Answer(question=self.scale, response=self.response, body="-3")
        answer.save()
        self.assertEqual(Answer.objects.get(pk=answer.pk).body, "-3")

    def test_answer_outside_the_scale_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            Answer(question=self.scale, response=self.response, body="6")

    def test_non_numeric_answer_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            Answer(question=self.scale, response=self.response, body="Agree")


class IntegerScaleRedisplayTests(TestCase):
    """A stored negative answer must select its own radio again on redisplay."""

    def setUp(self):
        self.survey = make_survey(need_logged_user=True, editable_answers=True)
        self.scale = make_scale_question(self.survey, -5, 5, required=False)
        self.user = User.objects.create_user(username="scale-redisplay", password="testpass")
        self.response = Response.objects.create(survey=self.survey, user=self.user, interview_uuid=str(uuid.uuid4()))
        store_answer(self.scale, self.response, "-4")

    def test_stored_negative_answer_is_the_initial_value(self):
        form = ResponseForm(survey=self.survey, user=self.user, step=0)
        self.assertEqual(form.fields[f"question_{self.scale.pk}"].initial, "-4")

    def test_only_the_stored_value_is_checked_in_the_rendered_html(self):
        html = str(ResponseForm(survey=self.survey, user=self.user, step=0))
        checked = re.findall(r'<input[^>]*\bchecked\b[^>]*>', html)
        self.assertEqual(len(checked), 1)
        self.assertIn('value="-4"', checked[0])


class IntegerScaleTemplateTests(TestCase):
    """The integer scale shares the horizontal likert layout in question.html."""

    def setUp(self):
        self.survey = make_survey()
        self.scale = make_scale_question(self.survey, -5, 5)
        self.form = ResponseForm(survey=self.survey, user=AnonymousUser(), step=0)

    def _render(self):
        return render_to_string(
            "survey/question.html", {"response_form": self.form, "category": {"name": "No category"}}
        )

    def test_scale_question_is_rendered_with_the_horizontal_scale_layout(self):
        html = self._render()
        self.assertIn('likert-row', html)
        self.assertEqual(html.count('likert-option"'), 11)

    def test_every_step_of_the_scale_is_rendered_as_a_radio_input(self):
        html = self._render()
        for value in range(-5, 6):
            self.assertIn(f'value="{value}"', html)
