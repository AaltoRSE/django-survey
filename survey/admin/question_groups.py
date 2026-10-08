"""Validate the grouping of questions saved together in the survey admin."""

# Answer-defining fields every question of a group must share; the group's
# lead question is authoritative for them. Choices are deliberately absent:
# they stay per-question while the lead shows the answer labels, and are
# enforced separately in propagate_lead_settings() when it hides them.
GROUP_UNIFORM_FIELDS = (
    "type",
    "scale_min",
    "scale_max",
    "other_option",
    "other_label",
    "will_not_answer_option",
    "will_not_answer_label",
    "hide_answer_labels",
)


def propagate_lead_settings(survey):
    """Copy each group lead's answer-defining fields onto the followers of its
    group, so a group stays uniform no matter what was submitted (the admin
    hides these fields on followers). Choices are the exception: when the lead
    shows the answer labels, a follower keeps its own choices (a blank
    follower still inherits the lead's); when the lead hides them, the
    columns must line up, so the lead's choices are enforced. Group
    membership follows question order, per category, like the front end's
    group_leads().

    :param Survey survey: The survey whose questions to walk.
    :rtype: list of the follower questions that were changed."""
    changed = []
    lead_by_category = {}
    for question in survey.questions.order_by("order", "id"):
        lead = lead_by_category.get(question.category_id)
        if question.group_with_previous and lead is not None:
            updates = [
                field for field in GROUP_UNIFORM_FIELDS if getattr(question, field) != getattr(lead, field)
            ]
            for field in updates:
                setattr(question, field, getattr(lead, field))
            own_choices = (question.choices or "").strip()
            if (lead.hide_answer_labels or not own_choices) and question.choices != lead.choices:
                question.choices = lead.choices
                updates.append("choices")
            if question.group_header:
                # A follower cannot be a group header: forced off, not copied
                # from the lead, so group_header stays out of GROUP_UNIFORM_FIELDS.
                question.group_header = False
                updates.append("group_header")
            if updates:
                question.save(update_fields=updates)
                changed.append(question)
        else:
            lead_by_category[question.category_id] = question
    return changed


def sort_key(order, pk):
    """Display position of a question row; new rows (pk None) sort after
    existing rows with the same order number."""
    return (order, pk is None, pk or 0)


def grouped_rows_without_predecessor(rows):
    """Return the rows grouped with the preceding question that have no
    preceding question in their category.

    :param list rows: dicts with "order", "pk", "category_id" and
        "group_with_previous" keys, one per question being saved.
    :rtype: list of the offending row dicts.
    """
    ordered = sorted(rows, key=lambda row: sort_key(row["order"], row["pk"]))
    seen_categories = set()
    missing = []
    for row in ordered:
        if row["group_with_previous"] and row["category_id"] not in seen_categories:
            missing.append(row)
        seen_categories.add(row["category_id"])
    return missing
