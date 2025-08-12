/**
 * Home page functionality
 * Handles date range selection, chart rendering, and loading recently played tracks
 */

// Global initialization when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  initializeCharts();
  loadRecentlyPlayed();
  initializeCustomDateRange();

  // Note: The jQuery date range picker is initialized separately below
});

/**
 * Initialize custom date range functionality
 */
const initializeCustomDateRange = () => {
  const customRangeBtn = document.getElementById("customRangeBtn");
  const customDateInputs = document.querySelector(".custom-date-inputs");

  if (customRangeBtn && customDateInputs) {
    // Check if we should show it initially (if 'custom' is the active time range)
    if (customRangeBtn.classList.contains("active")) {
      customDateInputs.style.display = "block";
    } else {
      customDateInputs.style.display = "none";
    }

    // Toggle visibility when clicking on the custom button
    customRangeBtn.addEventListener("click", () => {
      customDateInputs.style.display =
        customDateInputs.style.display === "none" ||
        customDateInputs.style.display === ""
          ? "block"
          : "none";
    });

    // Hide custom inputs when other time range buttons are clicked
    const otherTimeRangeButtons = document.querySelectorAll(
      '.btn-simple[name="time_range"]:not(#customRangeBtn)'
    );

    otherTimeRangeButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        customDateInputs.style.display = "none";
      });
    });

    // Add validation for custom date range form
    const customDateForm = customDateInputs.closest("form");
    if (customDateForm) {
      customDateForm.addEventListener("submit", (e) => {
        const startDateInput = customDateForm.querySelector("#start_date");
        const endDateInput = customDateForm.querySelector("#end_date");
        const errorContainer = document.createElement("div");
        errorContainer.className = "alert alert-danger mt-2";
        errorContainer.style.display = "none";

        // Remove any existing error messages
        const existingError = customDateInputs.querySelector(".alert-danger");
        if (existingError) existingError.remove();

        customDateInputs.appendChild(errorContainer);

        // Validation checks
        if (!startDateInput.value || !endDateInput.value) {
          e.preventDefault();
          errorContainer.textContent =
            "Both start date and end date are required.";
          errorContainer.style.display = "block";
          return;
        }

        const startDate = new Date(startDateInput.value);
        const endDate = new Date(endDateInput.value);
        const today = new Date();

        // Check for valid dates
        if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
          e.preventDefault();
          errorContainer.textContent =
            "Please enter valid dates in YYYY-MM-DD format.";
          errorContainer.style.display = "block";
          return;
        }

        // Check for future dates
        if (startDate > today || endDate > today) {
          e.preventDefault();
          errorContainer.textContent = "Dates cannot be in the future.";
          errorContainer.style.display = "block";
          return;
        }

        // Check start date is before end date
        if (startDate > endDate) {
          e.preventDefault();
          errorContainer.textContent = "Start date must be before end date.";
          errorContainer.style.display = "block";
          return;
        }

        // If all validation passes, save the scroll position
        sessionStorage.setItem("scrollPosition", window.scrollY.toString());
      });
    }

    // Add event handler for the Apply button specifically
    const applyButton = customDateInputs.querySelector('button[type="submit"]');
    if (applyButton && customDateForm) {
      applyButton.addEventListener("click", (e) => {
        // The submit event handler above will handle validation
        // This is just a backup for the scroll position
        if (customDateForm.checkValidity()) {
          sessionStorage.setItem("scrollPosition", window.scrollY.toString());
        }
      });
    }
  }
};
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
  $(".btn-simple[name='time_range']")
    .not("#customRangeBtn")
    .on("click", () => {
      $(".custom-date-inputs").hide();
    });
});
