/**
 * Statistics Template Component
 * Handles chart initialization, date range selection, and toggle between view modes
 */

// Store chart instances for potential cleanup
const chartInstances = {};

document.addEventListener("DOMContentLoaded", () => {
  // =========================================================
  // Date range handling
  // =========================================================
  initializeDateRangeControls();

  // =========================================================
  // Chart initialization
  // =========================================================
  initializeCharts();

  // =========================================================
  // Toggle between podium and list views
  // =========================================================
  initializeViewToggle();
});

/**
 * Initialize date range buttons and custom date controls
 */
const initializeDateRangeControls = () => {
  const customRangeBtn = document.getElementById("customRangeBtn");
  const customDateInputs =
    document.querySelector(".custom-date-inputs") ||
    document.querySelector('[class*="custom-date-inputs"]');

  // Toggle custom date inputs when custom range button is clicked
  if (customRangeBtn && customDateInputs) {
    customRangeBtn.addEventListener("click", () => {
      customDateInputs.style.display =
        customDateInputs.style.display === "none" ? "block" : "none";
    });
  }

  // Hide custom date inputs when any other time range button is clicked
  const timeRangeButtons = document.querySelectorAll(
    ".btn-simple[name='time_range'], .time-range-row .btn:not(#customRangeBtn)"
  );

  timeRangeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (customDateInputs) {
        customDateInputs.style.display = "none";
      }
    });
  });
};

/**
 * Initialize all chart types based on available data elements
 */
const initializeCharts = () => {
  // Map of chart initializers - each function handles a specific chart type
  const chartInitializers = {
    streamingTrend: initializeStreamingTrendChart,
    radar: initializeRadarChart,
    doughnut: initializeDoughnutChart,
    polar: initializePolarAreaChart,
    bubble: initializeBubbleChart,
    discovery: initializeDiscoveryTimelineChart,
    stacked: initializeStackedBarChart,
    bar: initializeBarChart,
  };

  // Call each initializer function
  Object.values(chartInitializers).forEach((initializer) => initializer());
};

/**
 * Initialize streaming trend line chart
 */
const initializeStreamingTrendChart = () => {
  const ctx = document.getElementById("streamingTrendChart");
  if (!ctx) return;

  try {
    const dataElement = document.getElementById("trends_data");
    if (!dataElement) return;

    const chartData = JSON.parse(dataElement.textContent.trim());

    if (
      typeof chartData === "object" &&
      chartData.datasets &&
      chartData.labels
    ) {
      chartInstances.streamingTrend = new Chart(ctx, {
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
              grid: { color: "rgba(255,255,255,0.1)" },
              ticks: { color: "#9e9e9e" },
            },
          },
          plugins: {
            datalabels: { display: false },
          },
        },
      });
    }
  } catch (error) {
    console.error("Error creating streaming trend chart:", error);
  }
};

/**
 * Initialize radar chart for stats visualization
 */
const initializeRadarChart = () => {
  const ctx = document.getElementById("statsRadarChart");
  if (!ctx) return;

  const dataElement = document.getElementById("radar_chart");
  if (!dataElement) return;

  try {
    const chartData = JSON.parse(dataElement.textContent);
    chartInstances.radar = new Chart(ctx, {
      ...chartData,
      options: {
        ...chartData.options,
        plugins: {
          ...chartData.options?.plugins,
          datalabels: { display: false },
        },
      },
    });
  } catch (error) {
    console.error("Error creating radar chart:", error);
  }
};

/**
 * Initialize doughnut chart with custom styling and labels
 */
const initializeDoughnutChart = () => {
  const ctx = document.getElementById("statsDoughnutChart");
  if (!ctx) return;

  const dataElement = document.getElementById("doughnut_chart");
  if (!dataElement) return;

  try {
    const chartData = JSON.parse(dataElement.textContent);
    chartInstances.doughnut = new Chart(ctx, {
      type: chartData.type,
      data: {
        ...chartData.data,
        datasets: [
          {
            ...chartData.data.datasets[0],
            borderColor: "#1e1e2f",
            borderWidth: 2,
          },
        ],
      },
      options: {
        ...chartData.options,
        plugins: {
          ...chartData.options?.plugins,
          datalabels: {
            color: "#ffffff",
            font: { size: 9, weight: "bold" },
            formatter: (value, ctx) => {
              const label = ctx.chart.data.labels[ctx.dataIndex];
              return value > 0.5 ? `${label}\n${value.toFixed(1)}%` : "";
            },
            rotation: (ctx) => (ctx.dataset.data[ctx.dataIndex] > 5 ? 0 : 45),
            align: "center",
            anchor: "center",
          },
        },
      },
    });
  } catch (error) {
    console.error("Error creating doughnut chart:", error);
  }
};

/**
 * Initialize polar area chart for hourly distribution
 */
const initializePolarAreaChart = () => {
  const ctx = document.getElementById("statsHourlyChart");
  if (!ctx) return;

  const dataElement = document.getElementById("polar_area_chart");
  if (!dataElement) return;

  try {
    const chartData = JSON.parse(dataElement.textContent);
    chartInstances.polar = new Chart(ctx, chartData);
  } catch (error) {
    console.error("Error creating polar area chart:", error);
  }
};

/**
 * Initialize bubble chart for multidimensional data visualization
 */
const initializeBubbleChart = () => {
  const ctx = document.getElementById("statsBubbleChart");
  if (!ctx) return;

  const dataElement = document.getElementById("bubble_chart");
  if (!dataElement) return;

  try {
    const chartData = JSON.parse(dataElement.textContent);
    chartInstances.bubble = new Chart(ctx, chartData);
  } catch (error) {
    console.error("Error creating bubble chart:", error);
  }
};

/**
 * Initialize discovery timeline chart for historical data
 */
const initializeDiscoveryTimelineChart = () => {
  const ctx = document.getElementById("discoveryTimelineChart");
  if (!ctx) return;

  const dataElement = document.getElementById("discovery_chart");
  if (!dataElement) return;

  try {
    const chartData = JSON.parse(dataElement.textContent);
    chartInstances.discovery = new Chart(ctx, {
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
          },
        },
        plugins: {
          legend: {
            labels: { color: "#9e9e9e" },
          },
          datalabels: { display: false },
        },
      },
    });
  } catch (error) {
    console.error("Error creating discovery timeline chart:", error);
  }
};

/**
 * Initialize stacked bar chart for comparative data
 */
const initializeStackedBarChart = () => {
  const ctx = document.getElementById("stackedBarChart");
  if (!ctx) return;

  const dataElement = document.getElementById("stacked_chart");
  if (!dataElement) return;

  try {
    const chartData = JSON.parse(dataElement.textContent);
    chartInstances.stacked = new Chart(ctx, chartData);
  } catch (error) {
    console.error("Error creating stacked bar chart:", error);
  }
};

/**
 * Initialize bar chart for item comparisons
 */
const initializeBarChart = () => {
  const ctx = document.getElementById("statsBarChart");
  if (!ctx) return;

  const dataElement = document.getElementById("bar_chart");
  if (!dataElement) return;

  try {
    const chartData = JSON.parse(dataElement.textContent);
    chartInstances.bar = new Chart(ctx, chartData);
  } catch (error) {
    console.error("Error creating bar chart:", error);
  }
};

/**
 * Initialize the toggle between podium view and list view
 */
const initializeViewToggle = () => {
  const toggleViewBtn = document.querySelector(".toggle-view");
  if (!toggleViewBtn) return;

  const podiumView = document.querySelector(".podium-view");
  const listView = document.querySelector(".list-view");
  const spinner = listView?.querySelector(".loading-spinner");

  // Track if data has been loaded already
  let dataLoaded = false;

  toggleViewBtn.addEventListener("click", (e) => {
    e.preventDefault();
    const currentView = toggleViewBtn.getAttribute("data-view");
    let itemType = toggleViewBtn.getAttribute("data-type");

    // Get current time range from active button
    const activeTimeButton = document.querySelector(
      '.btn-simple[name="time_range"].active'
    );
    const timeRange = activeTimeButton
      ? activeTimeButton.value
      : "last_4_weeks";

    // Determine item type from URL if not set
    if (!itemType) {
      const path = window.location.pathname;

      if (path.includes("artist-stats")) {
        itemType = "artists";
      } else if (path.includes("album-stats")) {
        itemType = "albums";
      } else if (path.includes("track-stats")) {
        itemType = "tracks";
      } else if (path.includes("genre-stats")) {
        itemType = "genres";
      }
    }

    if (currentView === "podium") {
      // Switch to list view
      podiumView.style.display = "none";
      listView.style.display = "block";
      toggleViewBtn.setAttribute("data-view", "list");
      toggleViewBtn.innerHTML =
        'Show Podium <i class="tim-icons icon-minimal-right"></i>';

      // Only fetch data if not already loaded
      if (!dataLoaded) {
        loadListData(itemType, timeRange, spinner, listView);
      }
    } else {
      // Switch to podium view
      podiumView.style.display = "block";
      listView.style.display = "none";
      toggleViewBtn.setAttribute("data-view", "podium");
      toggleViewBtn.innerHTML =
        'Show All <i class="tim-icons icon-minimal-right"></i>';
    }
  });

  /**
   * Load list data from API
   * @param {string} itemType - Type of items to load (artists, tracks, albums, genres)
   * @param {string} timeRange - Time range for the data
   * @param {HTMLElement} spinner - Loading spinner element
   * @param {HTMLElement} listView - List view container
   */
  const loadListData = (itemType, timeRange, spinner, listView) => {
    if (spinner) spinner.style.display = "block";

    // Make sure we have an itemType
    if (!itemType) {
      console.error("Item type is not defined");
      if (spinner) {
        spinner.innerHTML =
          '<p class="text-danger">Error: Could not determine item type</p>';
      }
      return;
    }

    // Use absolute URL path with leading slash
    fetch(`/api/top-items/?type=${itemType}&time_range=${timeRange}`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            `Server responded with ${response.status}: ${response.statusText}`
          );
        }
        return response.json();
      })
      .then((data) => {
        if (!data || !data.items) {
          throw new Error("Invalid data returned from server");
        }

        renderListItems(data.items, itemType, listView);

        // Hide spinner, show list
        if (spinner) spinner.style.display = "none";

        const listGroup = listView.querySelector(".card-list-group");
        if (listGroup) listGroup.style.display = "block";

        dataLoaded = true;
      })
      .catch((error) => {
        console.error("Error loading data:", error);
        if (spinner) {
          spinner.innerHTML = `<p class="text-danger">Error loading data: ${error.message}</p>`;
        }
      });
  };

  /**
   * Render list items in the list view
   * @param {Array} items - List of items to render
   * @param {string} itemType - Type of items (artists, tracks, albums, genres)
   * @param {HTMLElement} listView - List view container
   */
  const renderListItems = (items, itemType, listView) => {
    const listGroup = listView.querySelector(".card-list-group");
    if (!listGroup) {
      throw new Error("List group element not found");
    }

    listGroup.innerHTML = "";

    items.forEach((item, index) => {
      const listItem = document.createElement("li");
      listItem.className = "list-group-item";

      // Generate HTML based on item type
      listItem.innerHTML = createItemHtml(item, index, itemType);
      listGroup.appendChild(listItem);
    });
  };

  /**
   * Create HTML for a list item based on its type
   * @param {Object} item - Item data
   * @param {number} index - Item index for numbering
   * @param {string} itemType - Type of item (artists, tracks, albums, genres)
   * @returns {string} HTML string for the item
   */
  const createItemHtml = (item, index, itemType) => {
    // Initialize variables
    let url = "#";
    let name = "";
    let imageUrl = null;
    let artistId = null;
    let artistName = null;

    // Set properties based on item type
    switch (itemType) {
      case "artists":
        url = `/artist/${item.artist_id}`;
        name = item.artist_name;
        imageUrl = item.image?.[0]?.url;
        break;

      case "tracks":
        url = `/track/${item.track_id}`;
        name = item.track_name;
        imageUrl = item.album_image;
        artistName = item.artist_name;
        artistId = item.artist_id;
        break;

      case "albums":
        url = `/album/${item.album_id}`;
        name = item.album_name;
        imageUrl = item.image?.[0]?.url;
        artistName = item.artist_name;
        artistId = item.artist_id;
        break;

      case "genres":
        url = `/genre/${encodeURIComponent(item.genre)}`;
        name = item.genre;
        break;
    }

    // Build common HTML structure
    return `
      <div class="d-flex align-items-center">
        <span class="mr-2 text-muted">${index + 1}.</span>
        ${
          imageUrl
            ? `<img src="${imageUrl}" alt="${name}" class="album-cover">`
            : ""
        }
        <div class="item-details">
          <a href="${url}" class="item-title">${name}</a>
          ${
            artistName && artistId
              ? `<a href="/artist/${artistId}" class="item-artist">${artistName}</a>`
              : ""
          }
        </div>
      </div>
      <span class="item-minutes">${Math.round(
        item.total_minutes
      ).toLocaleString()} min</span>
    `;
  };
};
