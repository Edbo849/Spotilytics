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
});
