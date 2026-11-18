from django.core.exceptions import ValidationError

from survey.models import Answer, Question
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


class TestAnswerDecodeBody(BaseModelTest):
    MULTI = Question.SELECT_MULTIPLE

    def test_plain_string_is_a_single_value(self):
        self.assertEqual(Answer.decode_body("Mytext", self.MULTI), ["Mytext"])

    def test_json_list_body(self):
        self.assertEqual(Answer.decode_body('["a", "b"]', self.MULTI), ["a", "b"])

    def test_values_with_commas_apostrophes_signs_and_non_ascii(self):
        values = ["Yes, sometimes", "I don't know", "\u22124", "+4", "\u00e9t\u00e9, ok"]
        self.assertEqual(Answer.decode_body(Answer.encode_list(values), self.MULTI), values)

    def test_encode_list_keeps_non_ascii(self):
        self.assertEqual(Answer.encode_list(["\u00e9t\u00e9"]), '["\u00e9t\u00e9"]')

    def test_empty_list(self):
        self.assertEqual(Answer.decode_body("[]", self.MULTI), [])

    def test_none_and_empty_string(self):
        self.assertEqual(Answer.decode_body(None, self.MULTI), [])
        self.assertEqual(Answer.decode_body("", self.MULTI), [])

    def test_malformed_list_falls_back_to_whole_body(self):
        self.assertEqual(Answer.decode_body('["a"', self.MULTI), ['["a"'])

    def test_legacy_python_list_falls_back_to_whole_body(self):
        self.assertEqual(Answer.decode_body("['a', 'b']", self.MULTI), ["['a', 'b']"])

    def test_non_list_json_falls_back_to_whole_body(self):
        self.assertEqual(Answer.decode_body('{"a": 1}', self.MULTI), ['{"a": 1}'])
        self.assertEqual(Answer.decode_body("42", self.MULTI), ["42"])

    def test_other_types_are_never_split(self):
        self.assertEqual(Answer.decode_body('["a", "b"]', Question.TEXT), ['["a", "b"]'])
        self.assertEqual(Answer.decode_body("[1, 2]", Question.RADIO), ["[1, 2]"])
