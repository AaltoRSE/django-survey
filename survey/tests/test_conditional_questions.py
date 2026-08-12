from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from survey.conditions import evaluate
from survey.forms import ResponseForm
from survey.models import Answer, Category, Question, QuestionCondition, Response, Survey
from survey.tests.test_other_option import make_question, make_survey, qd


def make_condition(question, depends_on, operator, choices="", number=None):
    condition = QuestionCondition(
        question=question, depends_on=depends_on, operator=operator, choices=choices, number=number
    )
    condition.full_clean()
    condition.save()
    return condition


def set_session(client, key, value):
    session = client.session
    session[key] = value
    session.save()


class ConditionalVisibilityTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.q1 = make_question(self.survey, Question.RADIO, order=1, choices="Yes,No", text="Q1")
        self.q2 = make_question(self.survey, Question.TEXT, order=2, text="Q2")
        make_condition(self.q2, self.q1, QuestionCondition.OP_IN, choices="Yes")

    def test_hidden_child_produces_no_required_error(self):
        data = qd({f"question_{self.q1.pk}": "no"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn(f"question_{self.q2.pk}", form.errors)

    def test_hidden_child_produces_no_answer_row(self):
        data = qd({f"question_{self.q1.pk}": "no"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        self.assertEqual(Answer.objects.filter(response=response, question=self.q2).count(), 0)

    def test_conditional_field_has_data_attrs(self):
        form = ResponseForm(survey=self.survey, user=AnonymousUser(), step=0)
        widget_attrs = form.fields[f"question_{self.q2.pk}"].widget.attrs
        self.assertEqual(widget_attrs["data-depends-on"], f"question_{self.q1.pk}")
        self.assertEqual(widget_attrs["data-operator"], QuestionCondition.OP_IN)
        self.assertEqual(widget_attrs["data-cond-choices"], "yes")

    def test_visible_required_conditional_left_blank_errors(self):
        data = qd({f"question_{self.q1.pk}": "yes", f"question_{self.q2.pk}": ""})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertFalse(form.is_valid())
        self.assertIn(f"question_{self.q2.pk}", form.errors)

    def test_visible_answered_conditional_is_valid(self):
        data = qd({f"question_{self.q1.pk}": "yes", f"question_{self.q2.pk}": "hello"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)


class CascadeVisibilityTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.q1 = make_question(self.survey, Question.RADIO, order=1, choices="Yes,No", text="Q1")
        self.q2 = make_question(self.survey, Question.RADIO, order=2, choices="A,B", required=False, text="Q2")
        make_condition(self.q2, self.q1, QuestionCondition.OP_IN, choices="Yes")
        self.q3 = make_question(self.survey, Question.TEXT, order=3, required=False, text="Q3")
        make_condition(self.q3, self.q2, QuestionCondition.OP_IN, choices="A")

    def test_grandchild_hidden_when_own_parent_hidden_even_if_its_own_condition_would_hold(self):
        # q1 = "no" hides q2. Craft data so that, taken in isolation, q3's own
        # condition on q2 == "a" would evaluate True -- it must still be hidden
        # because its parent (q2) is hidden.
        data = qd(
            {
                f"question_{self.q1.pk}": "no",
                f"question_{self.q2.pk}": "a",
                f"question_{self.q3.pk}": "some text",
            }
        )
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertFalse(form.is_visible(self.q2))
        self.assertFalse(form.is_visible(self.q3))

    def test_grandchild_visible_when_whole_chain_matches(self):
        data = qd(
            {
                f"question_{self.q1.pk}": "yes",
                f"question_{self.q2.pk}": "a",
                f"question_{self.q3.pk}": "some text",
            }
        )
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_visible(self.q2))
        self.assertTrue(form.is_visible(self.q3))


class NumericConditionTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.age = make_question(self.survey, Question.INTEGER, order=1, text="Age")
        self.senior = make_question(self.survey, Question.TEXT, order=2, required=False, text="Senior info")
        make_condition(self.senior, self.age, QuestionCondition.OP_GE, number=65)

    def test_ge_condition_shows_field_when_met(self):
        data = qd({f"question_{self.age.pk}": "70"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_visible(self.senior))

    def test_ge_condition_hides_field_when_not_met(self):
        data = qd({f"question_{self.age.pk}": "10"})
        form = ResponseForm(data, survey=self.survey, user=AnonymousUser(), step=0)
        self.assertFalse(form.is_visible(self.senior))


class EvaluateOperatorTests(TestCase):
    """Direct unit tests of conditions.evaluate() for every operator."""

    def test_in_operator_matches_slug(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_IN, choices="Yes")
        self.assertTrue(evaluate(condition, "yes"))

    def test_in_operator_no_match(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_IN, choices="Yes")
        self.assertFalse(evaluate(condition, "no"))

    def test_in_operator_matches_label_needing_slugify(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_IN, choices="I don't know")
        self.assertTrue(evaluate(condition, "i-dont-know"))

    def test_in_operator_select_multiple_list_intersection_true(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_IN, choices="A,B")
        self.assertTrue(evaluate(condition, ["c", "b"]))

    def test_in_operator_select_multiple_list_intersection_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_IN, choices="A,B")
        self.assertFalse(evaluate(condition, ["c", "d"]))

    def test_in_operator_select_multiple_stored_body_string(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_IN, choices="A,B")
        self.assertTrue(evaluate(condition, "[u'a', u'c']"))

    def test_in_operator_select_multiple_stored_body_string_no_match(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_IN, choices="A,B")
        self.assertFalse(evaluate(condition, "[u'c', u'd']"))

    def test_in_operator_missing_parent_value_is_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_IN, choices="Yes")
        self.assertFalse(evaluate(condition, None))

    def test_in_operator_empty_string_is_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_IN, choices="Yes")
        self.assertFalse(evaluate(condition, ""))

    def test_in_operator_empty_list_is_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_IN, choices="Yes")
        self.assertFalse(evaluate(condition, []))

    def test_eq_true(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_EQ, number=3)
        self.assertTrue(evaluate(condition, "3"))

    def test_eq_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_EQ, number=3)
        self.assertFalse(evaluate(condition, "4"))

    def test_ne_true(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_NE, number=3)
        self.assertTrue(evaluate(condition, "4"))

    def test_ne_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_NE, number=3)
        self.assertFalse(evaluate(condition, "3"))

    def test_lt_true(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_LT, number=3)
        self.assertTrue(evaluate(condition, "2"))

    def test_lt_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_LT, number=3)
        self.assertFalse(evaluate(condition, "3"))

    def test_le_true(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_LE, number=3)
        self.assertTrue(evaluate(condition, "3"))

    def test_le_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_LE, number=3)
        self.assertFalse(evaluate(condition, "4"))

    def test_gt_true(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_GT, number=3)
        self.assertTrue(evaluate(condition, "4"))

    def test_gt_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_GT, number=3)
        self.assertFalse(evaluate(condition, "3"))

    def test_ge_true_equal(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_GE, number=3)
        self.assertTrue(evaluate(condition, "3"))

    def test_ge_true_greater(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_GE, number=3)
        self.assertTrue(evaluate(condition, "10"))

    def test_ge_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_GE, number=3)
        self.assertFalse(evaluate(condition, "2"))

    def test_numeric_unparsable_value_is_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_GE, number=3)
        self.assertFalse(evaluate(condition, "not-a-number"))

    def test_numeric_empty_value_is_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_GE, number=3)
        self.assertFalse(evaluate(condition, ""))

    def test_numeric_none_value_is_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_GE, number=3)
        self.assertFalse(evaluate(condition, None))

    def test_numeric_missing_number_is_false(self):
        condition = QuestionCondition(operator=QuestionCondition.OP_GE, number=None)
        self.assertFalse(evaluate(condition, "5"))


class QuestionConditionCleanTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.other_survey = make_survey(name="Other survey")
        self.parent = make_question(self.survey, Question.RADIO, order=1, choices="Yes,No")
        self.child = make_question(self.survey, Question.TEXT, order=2)

    def test_valid_in_condition_does_not_raise(self):
        condition = QuestionCondition(
            question=self.child, depends_on=self.parent, operator=QuestionCondition.OP_IN, choices="Yes"
        )
        condition.clean()

    def test_valid_numeric_condition_does_not_raise(self):
        numeric_parent = make_question(self.survey, Question.INTEGER, order=1, text="Age")
        numeric_child = make_question(self.survey, Question.TEXT, order=2)
        condition = QuestionCondition(
            question=numeric_child, depends_on=numeric_parent, operator=QuestionCondition.OP_GE, number=3
        )
        condition.clean()

    def test_cross_survey_parent_rejected(self):
        other_parent = make_question(self.other_survey, Question.RADIO, order=1, choices="Yes,No")
        condition = QuestionCondition(
            question=self.child, depends_on=other_parent, operator=QuestionCondition.OP_IN, choices="Yes"
        )
        with self.assertRaises(ValidationError):
            condition.clean()

    def test_self_reference_rejected(self):
        condition = QuestionCondition(
            question=self.parent, depends_on=self.parent, operator=QuestionCondition.OP_IN, choices="Yes"
        )
        with self.assertRaises(ValidationError):
            condition.clean()

    def test_later_order_parent_rejected(self):
        later = make_question(self.survey, Question.RADIO, order=3, choices="Yes,No")
        condition = QuestionCondition(
            question=self.parent, depends_on=later, operator=QuestionCondition.OP_IN, choices="Yes"
        )
        with self.assertRaises(ValidationError):
            condition.clean()

    def test_in_operator_on_integer_parent_rejected(self):
        numeric_parent = make_question(self.survey, Question.INTEGER, order=1, text="Age")
        condition = QuestionCondition(
            question=self.child, depends_on=numeric_parent, operator=QuestionCondition.OP_IN, choices="Yes"
        )
        with self.assertRaises(ValidationError):
            condition.clean()

    def test_numeric_operator_on_radio_parent_rejected(self):
        condition = QuestionCondition(
            question=self.child, depends_on=self.parent, operator=QuestionCondition.OP_GE, number=3
        )
        with self.assertRaises(ValidationError):
            condition.clean()

    def test_in_operator_label_not_in_parent_choices_rejected(self):
        condition = QuestionCondition(
            question=self.child, depends_on=self.parent, operator=QuestionCondition.OP_IN, choices="Maybe"
        )
        with self.assertRaises(ValidationError):
            condition.clean()

    def test_numeric_operator_missing_number_rejected(self):
        numeric_parent = make_question(self.survey, Question.INTEGER, order=1, text="Age")
        condition = QuestionCondition(
            question=self.child, depends_on=numeric_parent, operator=QuestionCondition.OP_GE, number=None
        )
        with self.assertRaises(ValidationError):
            condition.clean()


class ByQuestionStepSkippingTests(TestCase):
    """3 steps: q0 unconditional radio, q1 conditional child of q0, q2 unconditional trailing."""

    def setUp(self):
        self.survey = make_survey(display_method=Survey.BY_QUESTION)
        self.q0 = make_question(self.survey, Question.RADIO, order=0, choices="Yes,No", text="Traveled?")
        self.q1 = make_question(self.survey, Question.TEXT, order=1, text="How many trips?")
        make_condition(self.q1, self.q0, QuestionCondition.OP_IN, choices="Yes")
        self.q2 = make_question(self.survey, Question.TEXT, order=2, required=False, text="Anything else?")
        self.session_key = f"survey_{self.survey.id}"

    def test_get_on_hidden_child_step_redirects_past_it(self):
        set_session(self.client, self.session_key, {f"question_{self.q0.pk}": "no"})
        url = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 1})
        response = self.client.get(url)
        expected = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 2})
        self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_get_on_visible_child_step_renders_normally(self):
        set_session(self.client, self.session_key, {f"question_{self.q0.pk}": "yes"})
        url = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_post_answering_parent_skips_hidden_child_step(self):
        url = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 0})
        response = self.client.post(url, {f"question_{self.q0.pk}": "no"})
        expected = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 2})
        self.assertRedirects(response, expected, fetch_redirect_response=False)


class AllTrailingStepsHiddenFinalizesTests(TestCase):
    """2 steps: q0 unconditional radio, q1 conditional child of q0 (the only other step)."""

    def setUp(self):
        self.survey = make_survey(display_method=Survey.BY_QUESTION)
        self.q0 = make_question(self.survey, Question.RADIO, order=0, choices="Yes,No", text="Traveled?")
        self.q1 = make_question(self.survey, Question.TEXT, order=1, text="How many trips?")
        make_condition(self.q1, self.q0, QuestionCondition.OP_IN, choices="Yes")
        self.session_key = f"survey_{self.survey.id}"

    def test_submission_finalizes_when_all_trailing_steps_hidden(self):
        url = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 0})
        response = self.client.post(url, {f"question_{self.q0.pk}": "no"})

        self.assertEqual(Response.objects.count(), 1)
        saved = Response.objects.get()
        self.assertNotIn(self.session_key, self.client.session)
        self.assertRedirects(
            response,
            reverse("survey-confirmation", kwargs={"uuid": saved.interview_uuid}),
            fetch_redirect_response=False,
        )
        self.assertEqual(Answer.objects.filter(response=saved, question=self.q0).count(), 1)
        self.assertEqual(Answer.objects.filter(response=saved, question=self.q1).count(), 0)


class ByCategorySkippedCategoryTests(TestCase):
    """3 categories: A unconditional, B conditional on A (hidden), C unconditional trailing."""

    def setUp(self):
        self.survey = make_survey(display_method=Survey.BY_CATEGORY)
        self.cat_a = Category.objects.create(survey=self.survey, name="A", order=0)
        self.cat_b = Category.objects.create(survey=self.survey, name="B", order=1)
        self.cat_c = Category.objects.create(survey=self.survey, name="C", order=2)

        self.q_a = Question.objects.create(
            survey=self.survey,
            text="Qa",
            order=0,
            required=True,
            type=Question.RADIO,
            choices="Yes,No",
            category=self.cat_a,
        )
        self.q_b = Question.objects.create(
            survey=self.survey, text="Qb", order=1, required=True, type=Question.TEXT, category=self.cat_b
        )
        make_condition(self.q_b, self.q_a, QuestionCondition.OP_IN, choices="Yes")
        self.q_c = Question.objects.create(
            survey=self.survey, text="Qc", order=2, required=True, type=Question.TEXT, category=self.cat_c
        )
        self.session_key = f"survey_{self.survey.id}"

    def test_get_on_fully_hidden_category_step_redirects_past_it(self):
        set_session(self.client, self.session_key, {f"question_{self.q_a.pk}": "no"})
        url = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 1})
        response = self.client.get(url)
        expected = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 2})
        self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_post_answering_parent_skips_fully_hidden_category(self):
        url = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 0})
        response = self.client.post(url, {f"question_{self.q_a.pk}": "no"})
        expected = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 2})
        self.assertRedirects(response, expected, fetch_redirect_response=False)


class StepBackPurgesStaleAnswerTests(TestCase):
    """2 steps: q_p (parent radio), q_c (child, visible only when q_p == 'yes')."""

    def setUp(self):
        self.survey = make_survey(display_method=Survey.BY_QUESTION, need_logged_user=True, editable_answers=True)
        self.q_p = make_question(self.survey, Question.RADIO, order=0, choices="Yes,No", text="Parent?")
        self.q_c = make_question(self.survey, Question.TEXT, order=1, text="Child")
        make_condition(self.q_c, self.q_p, QuestionCondition.OP_IN, choices="Yes")
        self.session_key = f"survey_{self.survey.id}"

        self.user = User.objects.create_user(username="participant", password="testpass")
        self.client.login(username="participant", password="testpass")

    def test_step_back_purges_stale_child_answer(self):
        step0_url = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 0})
        step1_url = reverse("survey-detail-step", kwargs={"id": self.survey.id, "step": 1})

        # Answer parent "yes" -> child becomes visible.
        response = self.client.post(step0_url, {f"question_{self.q_p.pk}": "yes"})
        self.assertRedirects(response, step1_url, fetch_redirect_response=False)

        # Answer the (now visible) child; this is the last step, so it finalizes.
        response = self.client.post(step1_url, {f"question_{self.q_c.pk}": "hello"})
        self.assertEqual(Response.objects.count(), 1)
        saved = Response.objects.get()
        self.assertEqual(Answer.objects.get(response=saved, question=self.q_p).body, "yes")
        self.assertEqual(Answer.objects.get(response=saved, question=self.q_c).body, "hello")
        self.assertNotIn(self.session_key, self.client.session)

        # Go back to step 0 and change the parent answer so the child becomes hidden.
        response = self.client.post(step0_url, {f"question_{self.q_p.pk}": "no"})

        # The whole survey is now finalized again (no visible trailing step).
        self.assertEqual(Response.objects.count(), 1)
        saved.refresh_from_db()
        self.assertEqual(Answer.objects.get(response=saved, question=self.q_p).body, "no")
        self.assertFalse(Answer.objects.filter(response=saved, question=self.q_c).exists())
        self.assertNotIn(self.session_key, self.client.session)
        self.assertRedirects(
            response,
            reverse("survey-confirmation", kwargs={"uuid": saved.interview_uuid}),
            fetch_redirect_response=False,
        )
