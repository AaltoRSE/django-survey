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


def parse_header_rows(text, separator):
    """Parse a question's `header_rows` text into a grid of cell strings.

    `text` holds one header row per line, with cells separated by
    `separator`. Blank (or whitespace-only) lines are dropped; each
    remaining line's cells are stripped of surrounding whitespace, but empty
    cells are kept (so short rows can leave leading/trailing gaps).

    :param str text: the raw `Question.header_rows` value, or falsy.
    :param str separator: the cell separator, e.g. `settings.CHOICES_SEPARATOR`.
    :rtype: list[list[str]]
    """
    if not text:
        return []
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        rows.append([cell.strip() for cell in line.split(separator)])
    return rows


def mark_row_parity(fields):
    """Set `row_parity` ("odd"/"even") on each form field, alternating within
    each group.

    Walks `fields` (a mapping of field name -> field, e.g. `form.fields`) in
    insertion order, using the same grouping rule as `mark_group_boundaries`:
    consecutive fields sharing a `group_id` belong to the same group, and
    fields with no `group_id` attribute are their own single-field group.
    Within each group, the first field is "odd", the second "even", the
    third "odd", and so on.

    :param dict fields: form fields, in insertion order.
    """
    previous_group_id = object()
    row_index = 0
    for field in fields.values():
        group_id = getattr(field, "group_id", None)
        if group_id is None:
            group_id = object()
        if group_id != previous_group_id:
            row_index = 0
        field.row_parity = "even" if row_index % 2 else "odd"
        row_index += 1
        previous_group_id = group_id


def mark_label_columns(fields):
    """Set `group_has_row_labels` on each form field: whether its group's
    table needs the row-label column.

    Walks `fields` (a mapping of field name -> field, e.g. `form.fields`) in
    insertion order, using the same grouping rule as `mark_group_boundaries`:
    consecutive fields sharing a `group_id` belong to the same group, and
    fields with no `group_id` attribute are their own single-field group.
    Every field of a group gets True iff any field in the group has a
    non-blank `row_label` (companion fields such as the "other" text input
    have no `row_label` and never make it True, but still get the flag so
    their rows render consistently).

    :param dict fields: form fields, in insertion order.
    """
    field_list = list(fields.values())
    group = []
    previous_group_id = object()
    for field in field_list + [None]:
        group_id = object()
        if field is not None:
            group_id = getattr(field, "group_id", None)
            if group_id is None:
                group_id = object()
        if group and group_id != previous_group_id:
            has_labels = any((getattr(member, "row_label", "") or "").strip() for member in group)
            for member in group:
                member.group_has_row_labels = has_labels
            group = []
        if field is not None:
            group.append(field)
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
