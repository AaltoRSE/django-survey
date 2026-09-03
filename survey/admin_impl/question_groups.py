"""Validate the grouping of questions saved together in the survey admin."""


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
