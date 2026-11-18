from survey.models import Answer, Question, QuestionCondition


def _as_value_list(raw_value):
    """Normalize a raw parent answer value into a list of choice values.

    ``raw_value`` may already be a list (select-multiple submitted data), or a
    single string, or a stringified list stored in ``Answer.body`` such as
    ``"['a', 'b']"`` (parsed with ``Answer.parse_body``). Each value goes through
    ``Question.choice_value`` so it compares equal to the condition's labels.
    """
    if raw_value is None:
        return []
    if isinstance(raw_value, (list, tuple)):
        return [Question.choice_value(v) for v in raw_value if v not in (None, "")]
    return [Question.choice_value(v) for v in Answer.parse_body(str(raw_value))]


def evaluate(condition, raw_value):
    """Evaluate a QuestionCondition against the raw value of its parent answer.

    A missing/empty parent answer always evaluates to False (the child stays
    hidden until the parent is answered).
    """
    if condition.operator == QuestionCondition.OP_IN:
        values = set(_as_value_list(raw_value))
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
