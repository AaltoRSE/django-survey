/* Admin: hide question fields irrelevant to the selected question type or
   to a question grouped with the preceding one.

   Display-only UX; server-side validation in Question.clean() /
   QuestionInlineForm.clean() stays authoritative, and the answer-defining
   fields hidden on grouped questions are overwritten with the group lead's
   values on save (same philosophy as the conditional.js header comment).
   Listeners are delegated from the document because the Survey page adds
   question inlines dynamically. */
(function () {
    "use strict";

    var TYPE_NAME = /^(questions-(\d+|__prefix__)-)?type$/;
    var GROUP_NAME = /^(questions-(\d+|__prefix__)-)?group_with_previous$/;

    // Fields ignored for a question grouped with the preceding one: the
    // group's title, description and answer-defining settings come from the
    // question that opens the group.
    var GROUP_HIDDEN_FIELDS = [
        "text",
        "description",
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
    ];

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

    function updateContainer(container) {
        var typeSelect = findInput(container, TYPE_NAME);
        var groupCheckbox = findInput(container, GROUP_NAME);
        var grouped = Boolean(groupCheckbox && groupCheckbox.checked);
        var names = GROUP_HIDDEN_FIELDS.slice();
        for (var name in FIELD_TYPES) {
            if (FIELD_TYPES.hasOwnProperty(name) && names.indexOf(name) === -1) {
                names.push(name);
            }
        }
        for (var i = 0; i < names.length; i++) {
            var row = container.querySelector(".form-row.field-" + names[i]);
            if (!row) {
                continue;
            }
            var hidden = grouped && GROUP_HIDDEN_FIELDS.indexOf(names[i]) !== -1;
            if (!hidden && FIELD_TYPES[names[i]] && typeSelect) {
                hidden = FIELD_TYPES[names[i]].indexOf(typeSelect.value) === -1;
            }
            row.style.display = hidden ? "none" : "";
        }
    }

    function containerOf(input) {
        return input.closest(".inline-related") || input.closest("form");
    }

    function updateAll(root) {
        var inputs = (root || document).querySelectorAll("[name]");
        for (var i = 0; i < inputs.length; i++) {
            if (TYPE_NAME.test(inputs[i].name) || GROUP_NAME.test(inputs[i].name)) {
                var container = containerOf(inputs[i]);
                if (container) {
                    updateContainer(container);
                }
            }
        }
    }

    document.addEventListener("change", function (event) {
        var target = event.target;
        if (!target.name) {
            return;
        }
        if (TYPE_NAME.test(target.name) || GROUP_NAME.test(target.name)) {
            var container = containerOf(target);
            if (container) {
                updateContainer(container);
            }
        }
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
