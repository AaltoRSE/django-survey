"""
These type-specific answer models use a text field to allow for flexible
field sizes depending on the actual question this answer corresponds to any
"required" attribute will be enforced by the form.
"""

import json
import logging

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .question import Question
from .response import Response

LOGGER = logging.getLogger(__name__)


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, verbose_name=_("Question"), related_name="answers")
    response = models.ForeignKey(Response, on_delete=models.CASCADE, verbose_name=_("Response"), related_name="answers")
    created = models.DateTimeField(_("Creation date"), auto_now_add=True)
    updated = models.DateTimeField(_("Update date"), auto_now=True)
    body = models.TextField(_("Content"), blank=True, null=True)
    # Free text of the question's "other" field, kept apart from the answer.
    other_text = models.TextField(_("Other text"), blank=True, null=True)

    def __init__(self, *args, **kwargs):
        try:
            question = Question.objects.get(pk=kwargs["question_id"])
        except KeyError:
            question = kwargs.get("question")
        body = kwargs.get("body")
        if question and body:
            self.check_answer_body(question, body)
        super().__init__(*args, **kwargs)

    @staticmethod
    def encode_list(values):
        """Encode a select-multiple answer's values as a stored body.

        Args:
            values (Iterable[str]): The selected choice values.

        Returns:
            str: A JSON list, e.g. ``'["a", "b"]'``; non-ASCII is kept as is.
        """
        return json.dumps(list(values), ensure_ascii=False)

    @staticmethod
    def decode_body(body, question_type):
        """Decode a stored answer body into its list of values.

        Select-multiple answers are stored as a JSON list (see
        ``encode_list``); every other question type stores a plain string,
        which is returned whole even when it looks like a list.

        Args:
            body (str | None): The stored answer body.
            question_type (str): The type of the answer's question, e.g.
                ``Question.SELECT_MULTIPLE``.

        Returns:
            list[str]: The values; ``[]`` for ``None`` or ``""``. For a
            select-multiple body that is not a JSON list, the whole body as
            the single value.
        """
        if body is None or body == "":
            return []
        if question_type != Question.SELECT_MULTIPLE:
            return [body]
        try:
            parsed = json.loads(body)
        except (ValueError, TypeError, RecursionError):
            return [body]
        if not isinstance(parsed, list):
            return [body]
        return [str(value) for value in parsed if value not in (None, "")]

    @property
    def values(self):
        """Return the answer's values.

        A missing or empty body gives ``[None]`` or ``[""]``, so exporters and
        cardinality code still count it as a blank answer. Otherwise the body
        is decoded according to the question's type (see ``decode_body``).
        """
        if self.body is None or self.body == "":
            return [self.body]
        return Answer.decode_body(self.body, self.question.type)

    def check_answer_body(self, question, body):
        if question.type in [
            Question.RADIO,
            Question.SELECT,
            Question.SELECT_MULTIPLE,
            Question.LIKERT_5,
            Question.INTEGER_SCALE,
        ]:
            choices = question.get_clean_choices()
            self.check_answer_for_select(choices, body, question.type)
        if question.type == Question.INTEGER and body and body != "":
            try:
                body = int(body)
            except ValueError as e:
                msg = "Answer is not an integer"
                raise ValidationError(msg) from e
        if question.type == Question.FLOAT and body and body != "":
            try:
                body = float(body)
            except ValueError as e:
                msg = "Answer is not a number"
                raise ValidationError(msg) from e

    def check_answer_for_select(self, choices, body, question_type):
        """Raise ValidationError if a body holds a value outside the choices.

        Args:
            choices (list[str]): The question's clean choice labels.
            body (str): The answer body to check.
            question_type (str): The question's type, used to decode the body.

        Raises:
            ValidationError: A value is not one of the choices' values.
        """
        answers = Answer.decode_body(body, question_type) if body else []
        choice_values = [Question.choice_value(choice) for choice in choices]
        for answer in answers:
            if answer not in choice_values:
                msg = f"Impossible answer '{body}'"
                msg += f" should be in {choices} "
                raise ValidationError(msg)

    def __str__(self):
        return f"{self.__class__.__name__} to '{self.question}' : '{self.body}'"
