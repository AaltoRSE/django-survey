/*
 * Client-side show/hide of a radio question's "other" text: the text line is
 * shown only while the question's "other" option is selected. This is UX
 * only; no-JS users see the text field all the time.
 *
 * Loaded after conditional.js so that a line conditional.js shows is hidden
 * again here when its "other" option is not selected.
 */

(function () {
    "use strict";

    function optionSelected(name, value) {
        var inputs = document.getElementsByName(name);
        for (var i = 0; i < inputs.length; i++) {
            if (inputs[i].checked && inputs[i].value === value) {
                return true;
            }
        }
        return false;
    }

    function setRowHidden(input, hidden) {
        var row = input.closest("tr");
        if (!row) {
            return;
        }
        row.hidden = hidden;
        if (hidden) {
            input.value = "";
        }
    }

    function updateOtherFields() {
        var inputs = document.querySelectorAll("[data-other-choice]");
        for (var i = 0; i < inputs.length; i++) {
            var input = inputs[i];
            var name = input.getAttribute("data-other-for");
            var value = input.getAttribute("data-other-choice");
            if (!optionSelected(name, value)) {
                setRowHidden(input, true);
            } else if (!input.hasAttribute("data-depends-on")) {
                // A conditional question's line is shown by conditional.js.
                setRowHidden(input, false);
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        updateOtherFields();
        document.addEventListener("change", updateOtherFields);
        document.addEventListener("input", updateOtherFields);
    });
})();
