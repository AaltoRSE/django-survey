/* Admin: hide question fields irrelevant to the selected question type or
   to a question grouped with the preceding one.

   Display-only UX; server-side validation in Question.clean() /
   QuestionInlineForm.clean() stays authoritative, and the answer-defining
   fields hidden on grouped questions are overwritten with the group lead's
   values on save (same philosophy as the conditional.js header comment).
   One exception: a grouped question's choices field stays visible while its
   lead shows the answer labels, so each row of a group can carry its own
   labels; the server enforces the lead's choices only when it hides them.
   Listeners are delegated from the document because the Survey page adds
   question inlines dynamically. */
(function () {
    "use strict";

    var TYPE_NAME = /^(questions-(\d+|__prefix__)-)?type$/;
    var GROUP_NAME = /^(questions-(\d+|__prefix__)-)?group_with_previous$/;
    var GROUP_HEADER_NAME = /^(questions-(\d+|__prefix__)-)?group_header$/;
    var HIDE_LABELS_NAME = /^(questions-(\d+|__prefix__)-)?hide_answer_labels$/;
    var CATEGORY_NAME = /^(questions-(\d+|__prefix__)-)?category$/;

    // Fields ignored for a question grouped with the preceding one: the
    // group's title, description and answer-defining settings come from the
    // question that opens the group. The row label is deliberately absent:
    // it is how a follower gets its row text. Choices are listed but shown
    // again when the group's lead keeps the answer labels visible (see
    // updateContainer), so each row can have labels of its own.
    var GROUP_HIDDEN_FIELDS = [
        "text",
        "description",
        "group_header",
        "header_rows",
        "type",
        "choices",
        "scale_preset",
        "scale_min",
        "scale_max",
        "other_option",
        "other_label",
        "will_not_answer_option",
        "will_not_answer_label",
        "hide_answer_labels",
    ];

    // Header-only fields, revealed by the "Group header" checkbox on a
    // question that is not grouped with the preceding one.
    var HEADER_ONLY_FIELDS = ["header_rows", "label", "hide_answer_labels"];

    // Field name -> types that show it. Fields absent from a given page
    // simply resolve to no matching row and are skipped. The "other" and
    // "will not answer" options are available on every question type, so
    // they are not listed here.
    var FIELD_TYPES = {
        choices: ["radio", "select", "select-multiple", "select_image"],
        scale_preset: ["integer-scale"],
        scale_min: ["integer-scale"],
        scale_max: ["integer-scale"],
    };

    function findInput(container, pattern) {
        var inputs = container.querySelectorAll("[name]");
        for (var i = 0; i < inputs.length; i++) {
            if (pattern.test(inputs[i].name)) {
                return inputs[i];
            }
        }
        return null;
    }

    function categoryValue(container) {
        var category = findInput(container, CATEGORY_NAME);
        return category ? category.value : null;
    }

    // The lead of a grouped row: the nearest preceding inline row in the
    // same category that is not itself grouped with its predecessor. Mirrors
    // the per-category walk of propagate_lead_settings() for rows in display
    // order; a mismatch only mis-shows a field the server overwrites anyway.
    function findLead(container) {
        var category = categoryValue(container);
        var row = container.previousElementSibling;
        while (row) {
            if (row.classList && row.classList.contains("inline-related")) {
                if (categoryValue(row) === category) {
                    var groupCheckbox = findInput(row, GROUP_NAME);
                    if (!groupCheckbox || !groupCheckbox.checked) {
                        return row;
                    }
                }
            }
            row = row.previousElementSibling;
        }
        return null;
    }

    // A follower edits its own choices only when its lead keeps the answer
    // labels visible and is of a type that has choices at all.
    function followerShowsChoices(container) {
        var lead = findLead(container);
        if (!lead) {
            return false;
        }
        var hideLabels = findInput(lead, HIDE_LABELS_NAME);
        if (!hideLabels || hideLabels.checked) {
            return false;
        }
        var typeSelect = findInput(lead, TYPE_NAME);
        return Boolean(typeSelect && FIELD_TYPES.choices.indexOf(typeSelect.value) !== -1);
    }

    function updateContainer(container) {
        var typeSelect = findInput(container, TYPE_NAME);
        var groupCheckbox = findInput(container, GROUP_NAME);
        var headerCheckbox = findInput(container, GROUP_HEADER_NAME);
        var grouped = Boolean(groupCheckbox && groupCheckbox.checked);
        // A page without the checkbox shows everything.
        var withHeader = !headerCheckbox || headerCheckbox.checked;
        var names = GROUP_HIDDEN_FIELDS.slice();
        var name;
        for (var i = 0; i < HEADER_ONLY_FIELDS.length; i++) {
            if (names.indexOf(HEADER_ONLY_FIELDS[i]) === -1) {
                names.push(HEADER_ONLY_FIELDS[i]);
            }
        }
        for (name in FIELD_TYPES) {
            if (FIELD_TYPES.hasOwnProperty(name) && names.indexOf(name) === -1) {
                names.push(name);
            }
        }
        for (var j = 0; j < names.length; j++) {
            name = names[j];
            var row = container.querySelector(".form-row.field-" + name);
            if (!row) {
                continue;
            }
            var hidden;
            if (grouped) {
                hidden = GROUP_HIDDEN_FIELDS.indexOf(name) !== -1;
                if (hidden && name === "choices") {
                    hidden = !followerShowsChoices(container);
                }
            } else {
                hidden = !withHeader && HEADER_ONLY_FIELDS.indexOf(name) !== -1;
                if (!hidden && FIELD_TYPES[name] && typeSelect) {
                    hidden = FIELD_TYPES[name].indexOf(typeSelect.value) === -1;
                }
            }
            row.style.display = hidden ? "none" : "";
        }
    }

    function containerOf(input) {
        return input.closest(".inline-related") || input.closest("form");
    }

    function isTrigger(name) {
        return (
            TYPE_NAME.test(name) ||
            GROUP_NAME.test(name) ||
            GROUP_HEADER_NAME.test(name) ||
            HIDE_LABELS_NAME.test(name) ||
            CATEGORY_NAME.test(name)
        );
    }

    function updateAll(root) {
        var inputs = (root || document).querySelectorAll("[name]");
        for (var i = 0; i < inputs.length; i++) {
            if (isTrigger(inputs[i].name)) {
                var container = containerOf(inputs[i]);
                if (container) {
                    updateContainer(container);
                }
            }
        }
    }

    document.addEventListener("change", function (event) {
        var target = event.target;
        if (!target.name || !isTrigger(target.name)) {
            return;
        }
        // A lead's settings decide what its followers show, so one change
        // refreshes every row, not just the changed one.
        updateAll(document);
    });

    document.addEventListener("DOMContentLoaded", function () {
        updateAll(document);
    });

    // New inline rows: native event (Django >= 4.1) plus a jQuery fallback,
    // since pyproject.toml declares django>=2.2 and pre-4.1 fires the event
    // only through django.jQuery (jQuery-triggered events don't reach native
    // listeners).
    document.addEventListener("formset:added", function (event) {
        updateAll(event.target);
    });
    if (typeof django !== "undefined" && django.jQuery) {
        django.jQuery(document).on("formset:added", function (event, row) {
            updateAll(row ? row.get(0) : document);
        });
    }
})();
