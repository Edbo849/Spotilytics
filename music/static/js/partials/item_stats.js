// Store chart references globally so we can destroy them when needed
const chartInstances = {};

document.addEventListener("DOMContentLoaded", function () {
  // =========================================================
  // Stats loading functionality
  // =========================================================
  const timeRangeBtns = document.querySelectorAll(".time-range-btn");
  const statsSection = document.querySelector(".stats-section");

  if (statsSection) {
    const itemId = statsSection.dataset.itemId;
    const itemType = statsSection.dataset.itemType;

    async function loadStats(timeRange) {
      try {
        if (!itemType || !itemId) {
          console.error("Missing itemType or itemId");
          return;
        }

        const response = await fetch(
          `/item-stats/${itemType}/${itemId}?time_range=${timeRange}`,
          { credentials: "include" }
        );
        const data = await response.json();

        // Update stats
        document.getElementById("total-plays").textContent = data.total_plays;
        document.getElementById("total-minutes").textContent = Math.round(
          data.total_minutes
        ).toLocaleString();
        document.getElementById(
          "peak-position"
        ).textContent = `#${data.peak_position}`;
        document.getElementById("avg-gap").textContent = `${Math.round(
          data.avg_gap
        )} hours`;
        document.getElementById(
          "longest-streak"
        ).textContent = `${data.longest_streak} days`;
        document.getElementById("peak-day-plays").textContent =
          data.peak_day_plays;
        document.getElementById("prime-time").textContent = data.prime_time;
        document.getElementById(
          "repeat-rate"
        ).textContent = `${data.repeat_rate}%`;
      } catch (error) {
        console.error("Error loading stats:", error);
      }
    }

    if (timeRangeBtns.length) {
      timeRangeBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
          timeRangeBtns.forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          loadStats(btn.dataset.range);
        });
      });

      // Load initial stats
      loadStats("last_4_weeks");
    }
  }

  // =========================================================
  // Custom date range toggle
  // =========================================================
  const customRangeBtn = document.getElementById("customRangeBtn");
  const customDateInputs = document.querySelector(".custom-date-inputs");

  if (customRangeBtn && customDateInputs) {
    customRangeBtn.addEventListener("click", function () {
      customDateInputs.style.display =
        customDateInputs.style.display === "none" ? "block" : "none";
    });
  }

  // =========================================================
  // Helper function to create or update charts
  // =========================================================
  function createOrUpdateChart(canvasId, dataId, chartCreator) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    const data = document.getElementById(dataId);
    if (!data) return;

    try {
      // If there's already a chart for this canvas, destroy it
      if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
      }

      // Create the new chart
      const chartData = JSON.parse(data.textContent);
      chartInstances[canvasId] = chartCreator(ctx, chartData);
    } catch (error) {
      console.error(`Error creating ${canvasId} chart:`, error);
    }
  }

  // =========================================================
  // Initialize all charts
  // =========================================================

  // Streaming Trend Chart
  createOrUpdateChart(
    "streamingTrendChart",
    "trends_data",
    (ctx, chartData) => {
      return new Chart(ctx, {
        type: "line",
        data: chartData,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: {
              grid: { color: "rgba(255,255,255,0.1)" },
              ticks: { color: "#9e9e9e" },
            },
            y: {
              beginAtZero: true, // Add this line to start Y-axis at 0
              grid: { color: "rgba(255,255,255,0.1)" },
              ticks: { color: "#9e9e9e" },
              min: 0, // Add this to ensure y never goes below 0
            },
          },
          plugins: {
            datalabels: { display: false },
          },
        },
      });
    }
  );

  // Listening Context Chart
  createOrUpdateChart(
    "listeningContextChart",
    "context_data",
    (ctx, chartData) => {
      // Process tooltip callback functions
      if (chartData.options?.plugins?.tooltip?.callbacks) {
        if (
          typeof chartData.options.plugins.tooltip.callbacks.afterLabel ===
            "string" &&
          chartData.options.plugins.tooltip.callbacks.afterLabel.startsWith(
            "function"
          )
        ) {
          chartData.options.plugins.tooltip.callbacks.afterLabel = Function(
            "return " + chartData.options.plugins.tooltip.callbacks.afterLabel
          )();
        }
      }

      // Process datalabels formatter
      if (chartData.options?.plugins?.datalabels) {
        if (
          typeof chartData.options.plugins.datalabels.formatter === "string" &&
          chartData.options.plugins.datalabels.formatter.startsWith("function")
        ) {
          chartData.options.plugins.datalabels.formatter = Function(
            "return " + chartData.options.plugins.datalabels.formatter
          )();
        }
      }

      return new Chart(ctx, chartData);
    }
  );

  // Hourly Distribution Chart
  createOrUpdateChart(
    "hourlyDistributionChart",
    "hourly_distribution_chart",
    (ctx, chartData) => new Chart(ctx, chartData)
  );

  // Duration Comparison Chart
  createOrUpdateChart(
    "durationComparisonChart",
    "duration_comparison_chart",
    (ctx, chartData) => new Chart(ctx, chartData)
  );

  // Artist Tracks Chart
  createOrUpdateChart(
    "artistTracksChart",
    "artist_tracks_chart",
    (ctx, chartData) => new Chart(ctx, chartData)
  );

  // Genre Distribution Chart
  createOrUpdateChart(
    "genreDistributionChart",
    "genre_distribution_chart",
    (ctx, chartData) => new Chart(ctx, chartData)
  );

  // Discography Coverage Chart
  createOrUpdateChart(
    "discographyCoverageChart",
    "discography_coverage_chart",
    (ctx, chartData) => {
      // Try using the gauge plugin
      if (window.ChartGauge || Chart.registry.controllers.gauge) {
        return new Chart(ctx, chartData);
      } else {
        // Simply log the error and use the chartData directly - let the backend handle fallback
        console.log(
          "Gauge chart type not available, using fallback from backend."
        );
        return new Chart(ctx, chartData);
      }
    }
  );

  // Album Tracks Chart
  createOrUpdateChart(
    "albumTracksChart",
    "album_tracks_chart",
    (ctx, chartData) => new Chart(ctx, chartData)
  );

  // Album Coverage Chart
  createOrUpdateChart(
    "albumCoverageChart",
    "album_coverage_chart",
    (ctx, chartData) => new Chart(ctx, chartData)
  );
  // =========================================================
  // Item stats time range change handler
  // =========================================================
  const timeRangeButtons = document.querySelectorAll(
    '.btn-simple[name="time_range"]'
  );

  if (statsSection && timeRangeButtons.length > 0) {
    const itemType = statsSection.dataset.itemType;
    const itemId = statsSection.dataset.itemId;

    if (itemType && itemId) {
      timeRangeButtons.forEach((button) => {
        button.addEventListener("click", function (e) {
          e.preventDefault();

          // Save current scroll position to sessionStorage
          sessionStorage.setItem("scrollPosition", window.scrollY);

          // Navigate to the new URL
          const timeRange = this.value;
          window.location.href = `/${itemType}/${itemId}?time_range=${timeRange}`;
        });
      });

      // Restore scroll position after page load if it exists
      if (sessionStorage.getItem("scrollPosition")) {
        window.scrollTo(0, parseInt(sessionStorage.getItem("scrollPosition")));
        sessionStorage.removeItem("scrollPosition"); // Clean up
      }
    }
  }
});
