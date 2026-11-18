"""
These type-specific answer models use a text field to allow for flexible
field sizes depending on the actual question this answer corresponds to any
"required" attribute will be enforced by the form.
"""

import ast
import logging

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .question import Question
from .response import Response

LOGGER = logging.getLogger(__name__)
# Bodies longer than this are not given to ast.literal_eval: parsing a huge or
# deeply nested literal costs memory and time, and no real select-multiple
# answer (a list of choice values) comes anywhere near this size.
MAX_LIST_BODY_LENGTH = 100_000


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
    def parse_body(body):
        """Parse a stored answer body into its list of values.

        Select-multiple answers are stored as Python's ``str(list)``, e.g.
        ``"['a', 'b']"`` (legacy rows: ``"[u'a', u'b']"``); every other
        question type stores a plain string. A body starting with ``[`` is
        parsed with ``ast.literal_eval``, which is safe because it only
        accepts Python literals and never executes code. Bodies longer than
        ``MAX_LIST_BODY_LENGTH`` skip that parsing, since evaluating a huge or
        deeply nested literal can exhaust memory or the recursion limit.

        Args:
            body (str | None): The stored answer body.

        Returns:
            list[str]: The values; ``[]`` for ``None`` or ``""``, the whole
            body as the single value when it is not a parsable list.
        """
        if body is None or body == "":
            return []
        body = str(body)
        if body.strip().startswith("[") and len(body) <= MAX_LIST_BODY_LENGTH:
            try:
                parsed = ast.literal_eval(body.strip())
            except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
                parsed = None
            if isinstance(parsed, (list, tuple)):
                return [str(value) for value in parsed if value not in (None, "")]
        return [body]

    @property
    def values(self):
        """Return the answer's values.

        A missing or empty body gives ``[None]`` or ``[""]``, so exporters and
        cardinality code still count it as a blank answer.
        """
        if self.body is None or self.body == "":
            return [self.body]
        return Answer.parse_body(self.body)

    def check_answer_body(self, question, body):
        if question.type in [
            Question.RADIO,
            Question.SELECT,
            Question.SELECT_MULTIPLE,
            Question.LIKERT_5,
            Question.INTEGER_SCALE,
        ]:
            choices = question.get_clean_choices()
            self.check_answer_for_select(choices, body)
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

    def check_answer_for_select(self, choices, body):
        answers = Answer.parse_body(body) if body else []
        choice_values = [Question.choice_value(choice) for choice in choices]
        for answer in answers:
            if answer not in choice_values:
                msg = f"Impossible answer '{body}'"
                msg += f" should be in {choices} "
                raise ValidationError(msg)

    def __str__(self):
        return f"{self.__class__.__name__} to '{self.question}' : '{self.body}'"
