/**
 * Item Statistics Component
 * Manages chart rendering, stats loading, and time range selection
 * for different item types (artists, albums, tracks)
 */

// Store chart references globally so we can destroy them when needed
const chartInstances = {};

document.addEventListener("DOMContentLoaded", () => {
  // =========================================================
  // Stats loading functionality
  // =========================================================
  const timeRangeBtns = document.querySelectorAll(".time-range-btn");
  const statsSection = document.querySelector(".stats-section");

  if (statsSection) {
    const itemId = statsSection.dataset.itemId;
    const itemType = statsSection.dataset.itemType;

    /**
     * Load stats for a specific time range via AJAX
     * @param {string} timeRange - Time range identifier (e.g., "last_4_weeks")
     */
    const loadStats = async (timeRange) => {
      try {
        if (!itemType || !itemId) {
          console.error("Missing itemType or itemId");
          return;
        }

        const response = await fetch(
          `/item-stats/${itemType}/${itemId}?time_range=${timeRange}`,
          { credentials: "include" }
        );

        if (!response.ok) {
          throw new Error(`Network response was not ok: ${response.status}`);
        }

        const data = await response.json();

        // Update stats in the DOM
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
    };

    // Add event listeners to time range buttons
    if (timeRangeBtns.length) {
      timeRangeBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
          // Update active state
          timeRangeBtns.forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");

          // Load stats for selected time range
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
    customRangeBtn.addEventListener("click", () => {
      // Toggle visibility of custom date inputs
      customDateInputs.style.display =
        customDateInputs.style.display === "none" ? "block" : "none";
    });
  }

  // =========================================================
  // Helper function to create or update charts
  // =========================================================
  /**
   * Creates or updates a chart on a specific canvas element
   * @param {string} canvasId - ID of the canvas element
   * @param {string} dataId - ID of the element containing chart data
   * @param {Function} chartCreator - Function to create the chart instance
   */
  const createOrUpdateChart = (canvasId, dataId, chartCreator) => {
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
  };

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
              beginAtZero: true,
              grid: { color: "rgba(255,255,255,0.1)" },
              ticks: { color: "#9e9e9e" },
              min: 0,
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
      // Process tooltip callback functions from string to function
      if (chartData.options?.plugins?.tooltip?.callbacks) {
        const { afterLabel } = chartData.options.plugins.tooltip.callbacks;

        if (
          typeof afterLabel === "string" &&
          afterLabel.startsWith("function")
        ) {
          chartData.options.plugins.tooltip.callbacks.afterLabel = Function(
            "return " + afterLabel
          )();
        }
      }

      // Process datalabels formatter from string to function
      if (chartData.options?.plugins?.datalabels?.formatter) {
        const { formatter } = chartData.options.plugins.datalabels;

        if (typeof formatter === "string" && formatter.startsWith("function")) {
          chartData.options.plugins.datalabels.formatter = Function(
            "return " + formatter
          )();
        }
      }

      return new Chart(ctx, chartData);
    }
  );

  // Initialize various chart types
  const standardCharts = [
    ["hourlyDistributionChart", "hourly_distribution_chart"],
    ["durationComparisonChart", "duration_comparison_chart"],
    ["artistTracksChart", "artist_tracks_chart"],
    ["genreDistributionChart", "genre_distribution_chart"],
    ["albumTracksChart", "album_tracks_chart"],
    ["albumCoverageChart", "album_coverage_chart"],
  ];

  // Create all standard charts with default renderer
  standardCharts.forEach(([canvasId, dataId]) => {
    createOrUpdateChart(
      canvasId,
      dataId,
      (ctx, chartData) => new Chart(ctx, chartData)
    );
  });

  // Discography Coverage Chart (special case with gauge plugin)
  createOrUpdateChart(
    "discographyCoverageChart",
    "discography_coverage_chart",
    (ctx, chartData) => {
      // Try using the gauge plugin
      if (window.ChartGauge || Chart.registry.controllers.gauge) {
        return new Chart(ctx, chartData);
      } else {
        // Use fallback from backend
        console.log(
          "Gauge chart type not available, using fallback from backend."
        );
        return new Chart(ctx, chartData);
      }
    }
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
      // Add click handlers to time range buttons
      timeRangeButtons.forEach((button) => {
        button.addEventListener("click", (e) => {
          e.preventDefault();

          // Save current scroll position to sessionStorage
          sessionStorage.setItem("scrollPosition", window.scrollY);

          // Navigate to the new URL with selected time range
          const timeRange = button.value;
          window.location.href = `/${itemType}/${itemId}?time_range=${timeRange}`;
        });
      });

      // Restore scroll position after page load if it exists
      const savedPosition = sessionStorage.getItem("scrollPosition");
      if (savedPosition) {
        window.scrollTo(0, parseInt(savedPosition));
        sessionStorage.removeItem("scrollPosition"); // Clean up
      }
    }
  }
});
