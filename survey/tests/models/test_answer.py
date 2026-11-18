from unittest import mock

from django.core.exceptions import ValidationError

from survey.models import Answer
from survey.models.answer import MAX_LIST_BODY_LENGTH
from survey.tests.models import BaseModelTest


class TestAnswer(BaseModelTest):
    def test_unicode(self):
        """Unicode generation."""
        for answer in self.answers:
            self.assertIsNotNone(str(answer))

    def test_init(self):
        """We raise validation error if the answer is not a possible choice"""
        self.assertRaises(ValidationError, Answer, response=self.response, question=self.questions[4], body="Dd")
        self.assertRaises(
            ValidationError, Answer, response=self.response, question=self.questions[5], body="not an int"
        )
        self.assertRaises(
            ValidationError, Answer, response=self.response, question=self.questions[7], body="not a float"
        )

    def test_values(self):
        """We can have multiple nasty values ans it will be detected."""
        self.assertEqual(self.answers[0].values, ["Mytext"])
        self.assertEqual(self.answers[4].values, ["Yes"])
        self.assertEqual(self.answers[5].body, 42)
        self.assertEqual(self.answers[6].values, ["2", "4"])
        self.assertEqual(self.answers[7].body, 28.5)


class TestAnswerParseBody(BaseModelTest):
    def test_plain_string_is_a_single_value(self):
        self.assertEqual(Answer.parse_body("Mytext"), ["Mytext"])

    def test_python3_list_body(self):
        self.assertEqual(Answer.parse_body("['a', 'b']"), ["a", "b"])

    def test_legacy_unicode_list_body(self):
        self.assertEqual(Answer.parse_body("[u'a', u'b']"), ["a", "b"])

    def test_values_with_commas_apostrophes_signs_and_non_ascii(self):
        values = ["Yes, sometimes", "I don't know", "\u22124", "+4", "\u00e9t\u00e9, ok"]
        self.assertEqual(Answer.parse_body(str(values)), values)

    def test_empty_list(self):
        self.assertEqual(Answer.parse_body("[]"), [])

    def test_none_and_empty_string(self):
        self.assertEqual(Answer.parse_body(None), [])
        self.assertEqual(Answer.parse_body(""), [])

    def test_malformed_list_falls_back_to_whole_body(self):
        self.assertEqual(Answer.parse_body("['a'"), ["['a'"])

    def test_non_literal_falls_back_without_executing(self):
        body = "[__import__('os').system('true')]"
        with mock.patch("os.system") as system:
            self.assertEqual(Answer.parse_body(body), [body])
        system.assert_not_called()

    def test_over_length_body_falls_back(self):
        body = str(["a" * MAX_LIST_BODY_LENGTH])
        with mock.patch("survey.models.answer.ast.literal_eval") as literal_eval:
            self.assertEqual(Answer.parse_body(body), [body])
        literal_eval.assert_not_called()
