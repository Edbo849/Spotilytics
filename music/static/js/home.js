document.addEventListener("DOMContentLoaded", function () {});

$(function () {
  $('input[name="daterange"]').daterangepicker(
    {
      opens: "left",
      locale: {
        format: "YYYY-MM-DD",
      },
    },
    function (start, end, label) {
      $("#start_date").val(start.format("YYYY-MM-DD"));
      $("#end_date").val(end.format("YYYY-MM-DD"));
    }
  );
});

$(document).ready(function () {
  // Toggle the visibility of custom date inputs when the Custom button is clicked
  $("#customRangeBtn").click(function () {
    $(".custom-date-inputs").toggle();
  });

  // Hide custom date inputs when any predefined time range button is clicked
  $(".time-range-row.main-row .btn")
    .not("#customRangeBtn")
    .click(function () {
      $(".custom-date-inputs").hide();
    });
});
