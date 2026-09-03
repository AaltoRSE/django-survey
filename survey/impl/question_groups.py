"""Pure helpers computing which questions share a group and where group boundaries fall."""

def group_leads(questions):
    """Map each question's pk to the question that opens its group.

    Walks `questions` in the given (display) order. A standalone question
    leads its own group. A group question joins the current lead's group; if it
    has no preceding question in the list (or its predecessor's group was
    never opened), it leads itself instead.

    :param list[Question] questions: questions in display order.
    :rtype: dict[int, Question]
    """
    leads = {}
    current_lead = None
    for question in questions:
        if question.group_with_previous and current_lead is not None:
            leads[question.pk] = current_lead
        else:
            current_lead = question
            leads[question.pk] = question
    return leads


def mark_group_boundaries(fields):
    """Set `starts_group`/`ends_group` on each form field based on `group_id`.

    Walks `fields` (a mapping of field name -> field, e.g. `form.fields`) in
    insertion order, grouping consecutive fields that share the same
    `group_id`. A field opens a group when its `group_id` differs from the
    previous field's, and closes a group when the next field's `group_id`
    differs (or there is no next field). Fields with no `group_id` attribute
    are treated as their own single-field group.

    :param dict fields: form fields, in insertion order.
    """
    field_list = list(fields.values())
    for field in field_list:
        field.starts_group = False
        field.ends_group = False
    previous_group_id = object()
    for index, field in enumerate(field_list):
        group_id = getattr(field, "group_id", None)
        if group_id is None:
            group_id = object()
        next_group_id = None
        if index + 1 < len(field_list):
            next_group_id = getattr(field_list[index + 1], "group_id", None)
        if group_id != previous_group_id:
            field.starts_group = True
        if index + 1 >= len(field_list) or group_id != next_group_id or next_group_id is None:
            field.ends_group = True
        previous_group_id = group_id


def export_name(question, lead):
    """Return the CSV/export column name for `question`, given its group lead.

    :param Question question: the question being exported.
    :param Question lead: the question returned by `group_leads` for it.
    :rtype: str
    """
    if question.label:
        return f"{lead.text} - {question.label}"
    return lead.text
