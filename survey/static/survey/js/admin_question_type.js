/* Admin: hide question fields irrelevant to the selected question type.

   Display-only UX; server-side validation in Question.clean() /
   QuestionInlineForm.clean() stays authoritative (same philosophy as the
   conditional.js header comment). Listeners are delegated from the document
   because the Survey page adds question inlines dynamically. */
(function () {
    "use strict";

    var TYPE_NAME = /^(questions-(\d+|__prefix__)-)?type$/;

    // Field name -> types that show it. Fields absent from a given page
    // (e.g. other_label / will_not_answer_label on the inline) simply
    // resolve to no matching row and are skipped.
    var FIELD_TYPES = {
        choices: ["radio", "select", "select-multiple", "select_image"],
        scale_preset: ["integer-scale"],
        scale_min: ["integer-scale"],
        scale_max: ["integer-scale"],
        other_option: ["radio", "select"],
        other_label: ["radio", "select"],
        will_not_answer_option: ["integer-scale"],
        will_not_answer_label: ["integer-scale"],
    };

    function updateRow(typeSelect) {
        var container = typeSelect.closest(".inline-related") || typeSelect.closest("form");
        if (!container) {
            return;
        }
        var type = typeSelect.value;
        for (var name in FIELD_TYPES) {
            if (!FIELD_TYPES.hasOwnProperty(name)) {
                continue;
            }
            var row = container.querySelector(".form-row.field-" + name);
            if (!row) {
                continue;
            }
            row.style.display = FIELD_TYPES[name].indexOf(type) === -1 ? "none" : "";
        }
    }

    function updateAll(root) {
        var selects = (root || document).querySelectorAll('[name]');
        for (var i = 0; i < selects.length; i++) {
            if (TYPE_NAME.test(selects[i].name)) {
                updateRow(selects[i]);
            }
        }
    }

    document.addEventListener("change", function (event) {
        var target = event.target;
        if (target.name && TYPE_NAME.test(target.name)) {
            updateRow(target);
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
