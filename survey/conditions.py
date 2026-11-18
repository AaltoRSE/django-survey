from survey.models import Answer, Question, QuestionCondition


def _as_value_list(raw_value, question_type):
    """Normalize a raw parent answer value into a list of choice values.

    Each value goes through ``Question.choice_value`` so it compares equal to
    the condition's labels.

    Args:
        raw_value (list | tuple | str | None): The parent's value: a list
            (select-multiple submitted data) or a single string, such as a
            stored ``Answer.body`` (a JSON list for select-multiple).
        question_type (str): The parent question's type, used to decode a
            string value with ``Answer.decode_body``.

    Returns:
        list[str]: The choice values.
    """
    if raw_value is None:
        return []
    if isinstance(raw_value, (list, tuple)):
        return [Question.choice_value(v) for v in raw_value if v not in (None, "")]
    return [Question.choice_value(v) for v in Answer.decode_body(str(raw_value), question_type)]


def evaluate(condition, raw_value):
    """Evaluate a QuestionCondition against the raw value of its parent answer.

    A missing/empty parent answer always evaluates to False (the child stays
    hidden until the parent is answered).
    """
    if condition.operator == QuestionCondition.OP_IN:
        values = set(_as_value_list(raw_value, condition.depends_on.type))
        if not values:
            return False
        condition_values = {Question.choice_value(label) for label in condition._clean_choice_labels()}
        return bool(values & condition_values)

    if raw_value in (None, ""):
        return False
    try:
        number = float(raw_value)
    except (TypeError, ValueError):
        return False

    if condition.number is None:
        return False

    if condition.operator == QuestionCondition.OP_EQ:
        return number == condition.number
    if condition.operator == QuestionCondition.OP_NE:
        return number != condition.number
    if condition.operator == QuestionCondition.OP_LT:
        return number < condition.number
    if condition.operator == QuestionCondition.OP_LE:
        return number <= condition.number
    if condition.operator == QuestionCondition.OP_GT:
        return number > condition.number
    if condition.operator == QuestionCondition.OP_GE:
        return number >= condition.number
    return False
