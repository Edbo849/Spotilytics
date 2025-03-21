document.addEventListener("DOMContentLoaded", function () {
  const customRangeBtn = document.getElementById("customRangeBtn");
  const customDateInputs = document.querySelector(".custom-date-inputs");

  if (customRangeBtn && customDateInputs) {
    customRangeBtn.addEventListener("click", function () {
      customDateInputs.style.display =
        customDateInputs.style.display === "none" ? "block" : "none";
    });
  }

  const timeRangeButtons = document.querySelectorAll(
    ".time-range-row.main-row .btn:not(#customRangeBtn)"
  );
  timeRangeButtons.forEach((button) => {
    button.addEventListener("click", function () {
      if (customDateInputs) {
        customDateInputs.style.display = "none";
      }
    });
  });

  // Streaming Trend Chart
  const ctx = document.getElementById("streamingTrendChart");
  if (ctx) {
    try {
      let chartData = JSON.parse(
        document.getElementById("trends_data").textContent.trim()
      );
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
                grid: {
                  color: "rgba(255,255,255,0.1)",
                },
                ticks: {
                  color: "#9e9e9e",
                },
              },
              y: {
                grid: {
                  color: "rgba(255,255,255,0.1)",
                },
                ticks: {
                  color: "#9e9e9e",
                },
              },
            },
            plugins: {
              datalabels: {
                display: false,
              },
            },
          },
        });
      }
    } catch (error) {
      console.error("Error creating streaming trend chart:", error);
    }
  }

  // Radar Chart
  const radarCtx = document.getElementById("statsRadarChart");
  if (radarCtx) {
    const data = document.getElementById("radar_chart");
    if (data) {
      try {
        const chartData = JSON.parse(data.textContent);
        new Chart(radarCtx, {
          ...chartData,
          options: {
            ...chartData.options,
            plugins: {
              ...chartData.options.plugins,
              datalabels: { display: false },
            },
          },
        });
      } catch (error) {
        console.error("Error creating radar chart:", error);
      }
    }
  }

  // Doughnut Chart
  const doughnutCtx = document.getElementById("statsDoughnutChart");
  if (doughnutCtx) {
    const data = document.getElementById("doughnut_chart");
    if (data) {
      try {
        const chartData = JSON.parse(data.textContent);
        new Chart(doughnutCtx, {
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
              ...chartData.options.plugins,
              datalabels: {
                color: "#ffffff",
                font: { size: 9, weight: "bold" },
                formatter: (value, ctx) => {
                  const label = ctx.chart.data.labels[ctx.dataIndex];
                  return value > 0.5 ? `${label}\n${value.toFixed(1)}%` : "";
                },
                rotation: (ctx) =>
                  ctx.dataset.data[ctx.dataIndex] > 5 ? 0 : 45,
                align: "center",
                anchor: "center",
              },
            },
          },
        });
      } catch (error) {
        console.error("Error creating doughnut chart:", error);
      }
    }
  }

  // Polar Area Chart
  const polarCtx = document.getElementById("statsHourlyChart");
  if (polarCtx) {
    const data = document.getElementById("polar_area_chart");
    if (data) {
      try {
        const chartData = JSON.parse(data.textContent);
        new Chart(polarCtx, chartData);
      } catch (error) {
        console.error("Error creating polar area chart:", error);
      }
    }
  }

  // Bubble Chart
  const bubbleCtx = document.getElementById("statsBubbleChart");
  if (bubbleCtx) {
    const data = document.getElementById("bubble_chart");
    if (data) {
      try {
        const chartData = JSON.parse(data.textContent);
        new Chart(bubbleCtx, chartData);
      } catch (error) {
        console.error("Error creating bubble chart:", error);
      }
    }
  }

  // Discovery Timeline Chart
  const discoveryCtx = document.getElementById("discoveryTimelineChart");
  if (discoveryCtx) {
    const data = document.getElementById("discovery_chart");
    if (data) {
      try {
        const chartData = JSON.parse(data.textContent);
        new Chart(discoveryCtx, {
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
    }
  }

  // Stacked Bar Chart
  const stackedCtx = document.getElementById("stackedBarChart");
  if (stackedCtx) {
    const data = document.getElementById("stacked_chart");
    if (data) {
      try {
        const chartData = JSON.parse(data.textContent);
        new Chart(stackedCtx, chartData);
      } catch (error) {
        console.error("Error creating stacked bar chart:", error);
      }
    }
  }

  // Bar Chart
  const barCtx = document.getElementById("statsBarChart");
  if (barCtx) {
    const data = document.getElementById("bar_chart");
    if (data) {
      try {
        const chartData = JSON.parse(data.textContent);
        new Chart(barCtx, chartData);
      } catch (error) {
        console.error("Error creating bar chart:", error);
      }
    }
  }
  const toggleViewBtn = document.querySelector(".toggle-view");

  if (toggleViewBtn) {
    const podiumView = document.querySelector(".podium-view");
    const listView = document.querySelector(".list-view");
    const spinner = listView.querySelector(".loading-spinner");
    const table = listView.querySelector("table");

    // Track if data has been loaded
    let dataLoaded = false;

    // Find the toggleViewBtn click handler in your stats_template.js file
    toggleViewBtn.addEventListener("click", function (e) {
      e.preventDefault();
      const currentView = this.getAttribute("data-view");
      let itemType = this.getAttribute("data-type");

      // Get time range from active button
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

      console.log("Toggle button data:", {
        view: this.getAttribute("data-view"),
        type: itemType,
        timeRange: timeRange,
      });

      if (currentView === "podium") {
        // Switch to list view
        podiumView.style.display = "none";
        listView.style.display = "block";
        this.setAttribute("data-view", "list");
        this.innerHTML =
          'Show Podium <i class="tim-icons icon-minimal-right"></i>';

        // Only fetch data if not already loaded
        if (!dataLoaded) {
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

              // Get the list element
              const listGroup = listView.querySelector(".card-list-group");
              if (!listGroup) {
                throw new Error("List group element not found");
              }

              listGroup.innerHTML = "";

              data.items.forEach((item, index) => {
                // Create list item
                const listItem = document.createElement("li");
                listItem.className = "list-group-item";

                // Determine URL and name based on item type
                let url = "#";
                let name = "";
                let imageUrl = null;
                let artistId = null;
                let artistName = null;
                let innerHtml = "";

                if (itemType === "artists") {
                  url = `/artist/${item.artist_id}`;
                  name = item.artist_name;
                  imageUrl = item.image?.[0]?.url;

                  innerHtml = `
                    <div class="d-flex align-items-center">
                      <span class="mr-2 text-muted">${index + 1}.</span>
                      ${
                        imageUrl
                          ? `<img src="${imageUrl}" alt="${name}" class="album-cover">`
                          : ""
                      }
                      <div class="item-details">
                        <a href="${url}" class="item-title">${name}</a>
                      </div>
                    </div>
                    <span class="item-minutes">${Math.round(
                      item.total_minutes
                    ).toLocaleString()} min</span>
                  `;
                } else if (itemType === "tracks") {
                  url = `/track/${item.track_id}`;
                  name = item.track_name;
                  imageUrl = item.album_image;
                  artistName = item.artist_name;
                  artistId = item.artist_id;

                  innerHtml = `
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
                } else if (itemType === "albums") {
                  url = `/album/${item.album_id}`;
                  name = item.album_name;
                  imageUrl = item.image?.[0]?.url;
                  artistName = item.artist_name;
                  artistId = item.artist_id;

                  innerHtml = `
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
                } else if (itemType === "genres") {
                  url = `/genre/${encodeURIComponent(item.genre)}`;
                  name = item.genre;

                  innerHtml = `
                    <div class="d-flex align-items-center">
                      <span class="mr-2 text-muted">${index + 1}.</span>
                      <div class="item-details">
                        <a href="${url}" class="item-title">${name}</a>
                      </div>
                    </div>
                    <span class="item-minutes">${Math.round(
                      item.total_minutes
                    ).toLocaleString()} min</span>
                  `;
                }

                listItem.innerHTML = innerHtml;
                listGroup.appendChild(listItem);
              });

              // Hide spinner, show list
              if (spinner) spinner.style.display = "none";
              if (listGroup) listGroup.style.display = "block";
              dataLoaded = true;
            })
            .catch((error) => {
              console.error("Error loading data:", error);
              if (spinner) {
                spinner.innerHTML = `<p class="text-danger">Error loading data: ${error.message}</p>`;
              }
            });
        }
      } else {
        // Switch to podium view
        podiumView.style.display = "block";
        listView.style.display = "none";
        this.setAttribute("data-view", "podium");
        this.innerHTML =
          'Show All <i class="tim-icons icon-minimal-right"></i>';
      }
    });
  }
});
