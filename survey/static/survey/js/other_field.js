/*
 * Client-side show/hide for "other, please specify" free-text fields. This
 * is UX only: the server-side clean() in survey.forms.ResponseForm is the
 * source of truth (no-JS users always see the text field; irrelevant
 * "other" text is discarded server-side).
 */
(function () {
    "use strict";

    function fieldValue(name) {
        var inputs = document.getElementsByName(name);
        if (!inputs.length) {
            // Parent question is not on this page (an earlier step): leave
            // the visibility decision to the server.
            return undefined;
        }
        var values = [];
        for (var i = 0; i < inputs.length; i++) {
            var input = inputs[i];
            var tag = input.tagName.toLowerCase();
            if (tag === "select") {
                for (var j = 0; j < input.options.length; j++) {
                    if (input.options[j].selected) {
                        values.push(input.options[j].value);
                    }
                }
            } else if (input.type === "checkbox" || input.type === "radio") {
                if (input.checked) {
                    values.push(input.value);
                }
            } else {
                values.push(input.value);
            }
        }
        return values;
    }

    function updateOtherFields() {
        var others = document.querySelectorAll("[data-other-for]");
        for (var i = 0; i < others.length; i++) {
            var other = others[i];
            var parentName = other.getAttribute("data-other-for");
            var values = fieldValue(parentName);
            var isOther = values !== undefined && values.indexOf("__other__") !== -1;
            var row = other.closest("tr");
            if (row) {
                row.hidden = !isOther;
            }
            other.disabled = !isOther;
            if (!isOther) {
                other.value = "";
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        updateOtherFields();
        document.addEventListener("change", updateOtherFields);
        document.addEventListener("input", updateOtherFields);
    });
})();
