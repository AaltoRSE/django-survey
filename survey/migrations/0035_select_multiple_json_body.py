"""Convert select-multiple answer bodies to JSON lists.

Select-multiple answers used to be stored as Python's ``str(list)``, e.g.
``"['a', 'b']"`` (legacy rows: ``"[u'a', u'b']"``). They are now stored as
JSON lists, e.g. ``'["a", "b"]'``. The logic is copied here instead of
imported from app code, so the migration keeps working as the app changes.
"""

import ast
import json

from django.db import migrations

SELECT_MULTIPLE = "select-multiple"
# Literal value of SurveyForm.WILL_NOT_ANSWER_SENTINEL in survey/forms.py.
WILL_NOT_ANSWER_SENTINEL = "__will-not-answer__"


def _is_json_list(body):
    """Return whether a body is a valid JSON list."""
    try:
        return isinstance(json.loads(body), list)
    except (ValueError, TypeError, RecursionError):
        return False


def to_json_body(body):
    """Convert a legacy ``str(list)`` body to a JSON list body.

    Args:
        body (str | None): A stored select-multiple answer body.

    Returns:
        str | None: The JSON list body, or ``body`` unchanged when it is
        empty, the will-not-answer sentinel, already a JSON list, or not a
        parsable Python list/tuple literal.
    """
    if not body or body == WILL_NOT_ANSWER_SENTINEL or _is_json_list(body):
        return body
    try:
        parsed = ast.literal_eval(body.strip())
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return body
    if not isinstance(parsed, (list, tuple)):
        return body
    return json.dumps([str(value) for value in parsed], ensure_ascii=False)


def to_legacy_body(body):
    """Convert a JSON list body back to Python's ``str(list)`` form.

    Args:
        body (str | None): A stored select-multiple answer body.

    Returns:
        str | None: ``str(list_of_str)`` for a JSON list body, otherwise
        ``body`` unchanged.
    """
    if not body or not _is_json_list(body):
        return body
    return str([str(value) for value in json.loads(body)])


def _convert(apps, convert):
    """Apply ``convert`` to every select-multiple answer body, saving changed rows.

    Args:
        apps: The migration's app registry (or ``django.apps.apps``).
        convert (Callable[[str | None], str | None]): The body conversion.
    """
    answer_model = apps.get_model("survey", "Answer")
    for answer in answer_model.objects.filter(question__type=SELECT_MULTIPLE).iterator():
        new_body = convert(answer.body)
        if new_body != answer.body:
            answer.body = new_body
            answer.save(update_fields=["body"])


def forwards(apps, schema_editor):
    """Convert select-multiple bodies to JSON lists."""
    _convert(apps, to_json_body)


def backwards(apps, schema_editor):
    """Convert select-multiple JSON list bodies back to ``str(list)``."""
    _convert(apps, to_legacy_body)


class Migration(migrations.Migration):

    dependencies = [
        ("survey", "0034_answer_other_text"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
