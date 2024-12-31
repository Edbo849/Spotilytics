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

document.addEventListener("DOMContentLoaded", function () {
  // Existing line chart code
  const ctx = document.getElementById("listeningStatsChart");
  if (ctx) {
    const chartDataElement = document.getElementById("chart-data");
    if (chartDataElement) {
      try {
        let chartData = JSON.parse(chartDataElement.textContent.trim());
        if (typeof chartData === "string") {
          chartData = JSON.parse(chartData);
        }
        if (
          typeof chartData === "object" &&
          chartData.datasets &&
          chartData.labels
        ) {
          new Chart(ctx, {
            type: "line",
            data: chartData,
            options: {
              responsive: true,
              maintainAspectRatio: false,
              scales: {
                x: {
                  title: {
                    display: true,
                    text: chartDataElement.dataset.xlabel,
                  },
                  grid: {
                    color: "rgba(255,255,255,0.1)",
                  },
                  ticks: {
                    color: "#9e9e9e",
                  },
                },
                y: {
                  title: {
                    display: true,
                    text: "Number of Songs",
                  },
                  grid: {
                    color: "rgba(255,255,255,0.1)",
                  },
                  ticks: {
                    color: "#9e9e9e",
                  },
                },
              },
            },
          });
        }
      } catch (error) {
        console.error("Error creating line chart:", error);
      }
    }
  }

  // New genre pie chart code
  const genreCtx = document.getElementById("genreChart");
  if (genreCtx) {
    const genreDataElement = document.getElementById("genre-data");
    if (genreDataElement) {
      try {
        let genreData = JSON.parse(genreDataElement.textContent.trim());
        if (typeof genreData === "string") {
          genreData = JSON.parse(genreData);
        }
        if (typeof genreData === "object") {
          new Chart(genreCtx, {
            type: genreData.type,
            data: genreData.data,
            options: genreData.options,
          });
        }
      } catch (error) {
        console.error("Error creating genre chart:", error);
      }
    }
  }
});
