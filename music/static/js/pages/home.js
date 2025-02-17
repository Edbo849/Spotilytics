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
  // Listening Stats Chart
  const listeningCtx = document.getElementById("listeningStatsChart");
  if (listeningCtx) {
    const chartData = document.getElementById("chart_data");
    if (chartData) {
      try {
        // Parse the JSON data once
        const data = JSON.parse(chartData.textContent);

        // Create chart with parsed data
        new Chart(listeningCtx, {
          type: "line",
          data: data,
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              x: {
                grid: { color: "rgba(255,255,255,0.1)" },
                ticks: { color: "#9e9e9e" },
              },
              y: {
                grid: { color: "rgba(255,255,255,0.1)" },
                ticks: { color: "#9e9e9e" },
              },
            },
            plugins: {
              datalabels: { display: false },
            },
          },
        });
      } catch (error) {
        console.error("Error creating listening stats chart:", error);
      }
    }
  }

  // Genre Chart
  const genreCtx = document.getElementById("genreChart");
  if (genreCtx) {
    const genreData = document.getElementById("genre_data");
    if (genreData) {
      try {
        // Parse the JSON data once
        const data = JSON.parse(genreData.textContent);

        // Create chart with parsed data directly
        new Chart(genreCtx, data);
      } catch (error) {
        console.error("Error creating genre chart:", error);
      }
    }
  }
});

document.addEventListener("DOMContentLoaded", function () {
  loadRecentlyPlayed();
});

function loadRecentlyPlayed() {
  const container = document.getElementById("recently-played-container");
  if (!container) return;

  container.innerHTML =
    '<div class="loading-spinner"><i class="tim-icons icon-refresh-02 spinner"></i></div>';

  fetch("/recently-played/", { credentials: "include" })
    .then((response) => response.text())
    .then((html) => {
      container.innerHTML = html;
    })
    .catch((error) => {
      console.error("Error loading recently played:", error);
      container.innerHTML =
        '<p class="text-warning">Error loading recently played tracks</p>';
    });
}
