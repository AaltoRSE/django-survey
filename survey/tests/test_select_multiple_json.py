"""Tests for JSON-stored select-multiple answers and the body migration.

Select-multiple answers are stored as JSON lists; every other question type
stores a plain string that is never split. Migration 0035 converts legacy
``str(list)`` bodies to JSON lists and back.
"""

import importlib
import json

from django.apps import apps
from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase, override_settings

from survey.conditions import evaluate
from survey.forms import ResponseForm
from survey.models import Answer, Question, QuestionCondition, Response
from survey.tests.test_conditional_questions import make_condition
from survey.tests.test_other_option import make_question, make_survey, qd, store_answer

MIGRATION = importlib.import_module("survey.migrations.0035_select_multiple_json_body")


class SelectMultipleJsonSaveTests(TestCase):
    def test_saving_select_multiple_stores_json_body(self):
        survey = make_survey()
        question = make_question(survey, Question.SELECT_MULTIPLE, order=1, choices="a,b,c", text="Pick")
        form = ResponseForm(qd({f"question_{question.pk}": ["a", "c"]}), survey=survey, user=AnonymousUser(), step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        body = Answer.objects.get(response=response, question=question).body
        self.assertEqual(json.loads(body), ["a", "c"])

    @override_settings(CHOICES_SEPARATOR="|")
    def test_round_trip_with_commas_apostrophes_signs_and_non_ascii(self):
        values = ["Yes, sometimes", "I don't know", "−4", "+4", "Ehkä"]
        survey = make_survey(need_logged_user=True, editable_answers=True)
        question = make_question(
            survey, Question.SELECT_MULTIPLE, order=1, choices="|".join([*values, "No"]), text="Pick"
        )
        user = User.objects.create_user(username="jsonround", password="testpass")
        form = ResponseForm(qd({f"question_{question.pk}": values}), survey=survey, user=user, step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        answer = Answer.objects.get(response=response, question=question)
        self.assertEqual(answer.body, json.dumps(values, ensure_ascii=False))
        self.assertEqual(answer.values, values)
        reloaded = ResponseForm(survey=survey, user=user, step=0)
        self.assertEqual(reloaded.fields[f"question_{question.pk}"].initial, values)

    def test_malformed_json_body_falls_back_to_one_value(self):
        survey = make_survey()
        question = make_question(survey, Question.SELECT_MULTIPLE, order=1, choices="a,b", text="Pick")
        response = Response.objects.create(survey=survey)
        answer = store_answer(question, response, '["a", "b"')
        self.assertEqual(answer.values, ['["a", "b"'])


class NonListTypesStayWholeTests(TestCase):
    def setUp(self):
        self.survey = make_survey()
        self.response = Response.objects.create(survey=self.survey)

    def test_text_answer_that_looks_like_a_list_is_one_value(self):
        question = make_question(self.survey, Question.TEXT, order=1, text="Free")
        answer = store_answer(question, self.response, "[1, 2]")
        self.assertEqual(answer.values, ["[1, 2]"])

    def test_radio_choice_starting_with_bracket_is_one_value(self):
        question = make_question(self.survey, Question.RADIO, order=1, choices="[a] first,b", text="Radio")
        answer = store_answer(question, self.response, "[a] first")
        self.assertEqual(answer.values, ["[a] first"])


class RadioApostropheChoiceTests(TestCase):
    def setUp(self):
        self.survey = make_survey(need_logged_user=True, editable_answers=True)
        self.parent = make_question(self.survey, Question.RADIO, order=1, choices="Yes,I don't know", text="Parent")
        self.child = make_question(self.survey, Question.TEXT, order=2, required=False, text="Child")
        self.condition = make_condition(self.child, self.parent, QuestionCondition.OP_IN, choices="I don't know")
        self.user = User.objects.create_user(username="apostrophe", password="testpass")

    def test_value_equals_label(self):
        self.assertIn(("I don't know", "I don't know"), self.parent.get_choices())

    def test_save_and_reload(self):
        data = qd({f"question_{self.parent.pk}": "I don't know"})
        form = ResponseForm(data, survey=self.survey, user=self.user, step=0)
        self.assertTrue(form.is_valid(), form.errors)
        response = form.save()
        self.assertEqual(Answer.objects.get(response=response, question=self.parent).body, "I don't know")
        reloaded = ResponseForm(survey=self.survey, user=self.user, step=0)
        self.assertEqual(reloaded.fields[f"question_{self.parent.pk}"].initial, "I don't know")

    def test_condition_in_matches(self):
        self.assertTrue(evaluate(self.condition, "I don't know"))
        self.assertFalse(evaluate(self.condition, "Yes"))


class SelectMultipleParentConditionTests(TestCase):
    def test_condition_matches_json_stored_parent_body(self):
        survey = make_survey()
        parent = make_question(survey, Question.SELECT_MULTIPLE, order=1, choices="a,I don't know,c", text="Parent")
        child = make_question(survey, Question.TEXT, order=2, text="Child")
        condition = make_condition(child, parent, QuestionCondition.OP_IN, choices="I don't know")
        response = Response.objects.create(survey=survey)
        matching = store_answer(parent, response, Answer.encode_list(["a", "I don't know"]))
        self.assertTrue(evaluate(condition, matching.body))
        self.assertFalse(evaluate(condition, Answer.encode_list(["a", "c"])))


class MigrationConversionTests(TestCase):
    def test_legacy_unicode_list_converts(self):
        self.assertEqual(MIGRATION.to_json_body("[u'a', u'b']"), '["a", "b"]')

    def test_legacy_list_with_apostrophe_converts(self):
        body = "['a', \"I don't\"]"
        self.assertEqual(MIGRATION.to_json_body(body), json.dumps(["a", "I don't"]))

    def test_non_ascii_is_kept(self):
        self.assertEqual(MIGRATION.to_json_body("[u'Yës']"), '["Yës"]')

    def test_already_json_unchanged(self):
        self.assertEqual(MIGRATION.to_json_body('["a", "b"]'), '["a", "b"]')

    def test_unparsable_unchanged(self):
        self.assertEqual(MIGRATION.to_json_body("['a'"), "['a'")
        self.assertEqual(MIGRATION.to_json_body("plain"), "plain")

    def test_sentinel_and_empty_unchanged(self):
        sentinel = ResponseForm.WILL_NOT_ANSWER_SENTINEL
        self.assertEqual(MIGRATION.WILL_NOT_ANSWER_SENTINEL, sentinel)
        self.assertEqual(MIGRATION.to_json_body(sentinel), sentinel)
        self.assertEqual(MIGRATION.to_json_body(""), "")
        self.assertIsNone(MIGRATION.to_json_body(None))

    def test_reverse_converts_json_list_to_python_list(self):
        self.assertEqual(MIGRATION.to_legacy_body('["a", "I don\'t"]'), str(["a", "I don't"]))

    def test_reverse_leaves_other_bodies_unchanged(self):
        sentinel = ResponseForm.WILL_NOT_ANSWER_SENTINEL
        for body in (sentinel, "plain", "", None, '{"a": 1}'):
            self.assertEqual(MIGRATION.to_legacy_body(body), body)

    def test_forwards_converts_only_select_multiple_rows(self):
        survey = make_survey()
        multi = make_question(survey, Question.SELECT_MULTIPLE, order=1, choices="a,b", text="Multi")
        text = make_question(survey, Question.TEXT, order=2, text="Text")
        response = Response.objects.create(survey=survey)
        multi_answer = store_answer(multi, response, "[u'a', u'b']")
        text_answer = store_answer(text, response, "[u'a', u'b']")
        MIGRATION.forwards(apps, None)
        multi_answer.refresh_from_db()
        text_answer.refresh_from_db()
        self.assertEqual(multi_answer.body, '["a", "b"]')
        self.assertEqual(text_answer.body, "[u'a', u'b']")
        MIGRATION.backwards(apps, None)
        multi_answer.refresh_from_db()
        self.assertEqual(multi_answer.body, "['a', 'b']")
