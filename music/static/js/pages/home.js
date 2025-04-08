/**
 * Home page functionality
 * Handles date range selection, chart rendering, and loading recently played tracks
 */

// Global initialization when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  initializeCharts();
  loadRecentlyPlayed();

  // Note: The jQuery date range picker is initialized separately below
});

/**
 * Initialize and render charts on the page
 */
const initializeCharts = () => {
  // Initialize listening stats chart
  initializeListeningStatsChart();

  // Initialize genre distribution chart
  initializeGenreChart();
};

/**
 * Initialize the listening stats line chart
 */
const initializeListeningStatsChart = () => {
  const listeningCtx = document.getElementById("listeningStatsChart");
  const chartData = document.getElementById("chart_data");

  if (!listeningCtx || !chartData) return;

  try {
    // Parse the JSON data once
    const data = JSON.parse(chartData.textContent);

    // Create chart with parsed data
    new Chart(listeningCtx, {
      type: "line",
      data,
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
};

/**
 * Initialize the genre distribution chart
 */
const initializeGenreChart = () => {
  const genreCtx = document.getElementById("genreChart");
  const genreData = document.getElementById("genre_data");

  if (!genreCtx || !genreData) return;

  try {
    // Parse the JSON data once
    const data = JSON.parse(genreData.textContent);

    // Create chart with parsed data directly
    new Chart(genreCtx, data);
  } catch (error) {
    console.error("Error creating genre chart:", error);
  }
};

/**
 * Load recently played tracks via AJAX
 */
const loadRecentlyPlayed = () => {
  const container = document.getElementById("recently-played-container");
  if (!container) return;

  // Show loading spinner
  container.innerHTML = `
    <div class="loading-spinner">
      <i class="tim-icons icon-refresh-02 spinner"></i>
    </div>
  `;

  // Fetch recently played tracks
  fetch("/recently-played/", { credentials: "include" })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }
      return response.text();
    })
    .then((html) => {
      container.innerHTML = html;
    })
    .catch((error) => {
      console.error("Error loading recently played:", error);
      container.innerHTML =
        '<p class="text-warning">Error loading recently played tracks</p>';
    });
};

/**
 * Initialize date range picker (jQuery implementation)
 * This is kept as jQuery since daterangepicker is a jQuery plugin
 */
$(() => {
  // Initialize daterangepicker
  $('input[name="daterange"]').daterangepicker(
    {
      opens: "left",
      locale: {
        format: "YYYY-MM-DD",
      },
    },
    (start, end) => {
      // Update hidden inputs with selected dates
      $("#start_date").val(start.format("YYYY-MM-DD"));
      $("#end_date").val(end.format("YYYY-MM-DD"));
    }
  );

  // Toggle custom date inputs when the Custom button is clicked
  $("#customRangeBtn").on("click", () => {
    $(".custom-date-inputs").toggle();
  });

  // Hide custom date inputs when any other time range button is clicked
  $(".time-range-row.main-row .btn")
    .not("#customRangeBtn")
    .on("click", () => {
      $(".custom-date-inputs").hide();
    });
});
