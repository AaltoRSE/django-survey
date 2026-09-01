/* Integer scale presets in the Question admin.

   Picking a preset fills the minimum/maximum fields, which stay editable and
   are what actually gets saved; editing either one puts the dropdown back on
   "Custom". Listeners are delegated from the document because the Survey page
   adds question inlines dynamically. */
(function () {
    "use strict";

    function rowInput(preset, name) {
        // Inline rows prefix field names ("questions-0-scale_min"), so derive the
        // sibling's name from the preset select's own name.
        var inputName = preset.name.replace(/scale_preset$/, name);
        return document.querySelector('[name="' + inputName + '"]');
    }

    function applyPreset(preset) {
        if (!preset.value) {
            return;
        }
        var limits = preset.value.split(":");
        var min = rowInput(preset, "scale_min");
        var max = rowInput(preset, "scale_max");
        if (min) {
            min.value = limits[0];
        }
        if (max) {
            max.value = limits[1];
        }
    }

    function resetPreset(input) {
        var presetName = input.name.replace(/scale_(min|max)$/, "scale_preset");
        var preset = document.querySelector('[name="' + presetName + '"]');
        if (preset) {
            preset.value = "";
        }
    }

    document.addEventListener("change", function (event) {
        var target = event.target;
        if (!target.name) {
            return;
        }
        if (/scale_preset$/.test(target.name)) {
            applyPreset(target);
        } else if (/scale_(min|max)$/.test(target.name)) {
            resetPreset(target);
        }
    });
})();
