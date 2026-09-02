"""Resolve duplicate question order numbers after saving a survey in the admin."""

from survey.models import Question


def pinned_question_ids(formset):
    """Return ids of questions whose order was set in this save: newly created
    questions and existing ones whose "order" field changed. These keep their
    number; other questions move out of their way."""
    pinned = {question.pk for question in formset.new_objects}
    pinned.update(question.pk for question, changed_fields in formset.changed_objects if "order" in changed_fields)
    return pinned


def resolve_order_collisions(questions, pinned_ids):
    """Return the list of questions whose order was changed to make orders unique.

    Pinned questions claim their chosen numbers first (on a tie the lower id
    wins). The remaining questions are then walked in their previous order,
    pinned losers ahead of unchanged ones at the same number, and each takes the
    lowest free number at or above its old value, skipping over pinned slots, so
    a question whose number was just set displaces the unchanged ones."""
    taken = set()
    unpinned = []
    for question in sorted(questions, key=lambda question: (question.pk not in pinned_ids, question.order, question.pk)):
        if question.pk in pinned_ids and question.order not in taken:
            taken.add(question.order)
        else:
            unpinned.append(question)
    changed = []
    for question in sorted(unpinned, key=lambda question: (question.order, question.pk not in pinned_ids, question.pk)):
        order = question.order
        while order in taken:
            order += 1
        taken.add(order)
        if order != question.order:
            question.order = order
            changed.append(question)
    return changed


def shift_colliding_questions(survey, pinned_ids):
    """Load the survey's questions, resolve order collisions and persist the moved ones."""
    moved = resolve_order_collisions(list(survey.questions.all()), pinned_ids)
    for question in moved:
        question.save(update_fields=["order"])
    return moved
