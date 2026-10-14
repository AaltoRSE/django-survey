$(document).ready(function () {
  // Look for an input with date css class and load flatpickr on it, if it exists
  const dateInputFields = $("input.date");
  if (dateInputFields.length > 0) {
    dateInputFields.flatpickr();
  }
  // Time inputs use flatpickr's time-only picker; disableMobile keeps it
  // instead of the phone's native picker.
  const timeInputFields = $("input.time");
  if (timeInputFields.length > 0) {
    timeInputFields.flatpickr({
      enableTime: true,
      noCalendar: true,
      dateFormat: "H:i",
      time_24hr: true,
      disableMobile: true,
    });
  }
  // Date and time inputs work the same way, with the calendar shown.
  const datetimeInputFields = $("input.datetime");
  if (datetimeInputFields.length > 0) {
    datetimeInputFields.flatpickr({
      enableTime: true,
      dateFormat: "Y-m-d H:i",
      time_24hr: true,
      disableMobile: true,
    });
  }
});
