document.addEventListener("DOMContentLoaded", function () {
  const customRangeBtn = document.getElementById("customRangeBtn");
  const customDateInputs = document.querySelector(".custom-date-inputs");

  if (customRangeBtn && customDateInputs) {
    customRangeBtn.addEventListener("click", function () {
      customDateInputs.style.display =
        customDateInputs.style.display === "none" ? "block" : "none";
    });
  }

  // Hide custom date inputs when predefined time range buttons clicked
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

  const ctx = document.getElementById("streamingTrendChart");
  if (ctx) {
    const chartDataElement = document.getElementById("trends-chart");
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
                  display: false, // Disable datalabels for line chart
                },
              },
            },
          });
        }
      } catch (error) {
        console.error("Error creating streaming trend chart:", error);
      }
    }
  }

  // Radar chart initialization
  const radarCtx = document.getElementById("statsRadarChart");
  if (radarCtx) {
    const radarDataElement = document.getElementById("radar-chart");
    if (radarDataElement) {
      try {
        let radarData = JSON.parse(radarDataElement.textContent.trim());
        if (typeof radarData === "string") {
          radarData = JSON.parse(radarData);
        }
        if (typeof radarData === "object") {
          const config = {
            ...radarData,
            options: {
              ...radarData.options,
              plugins: {
                ...radarData.options.plugins,
                datalabels: {
                  display: false, // Disable datalabels for radar chart
                },
              },
            },
          };
          new Chart(radarCtx, config);
        }
      } catch (error) {
        console.error("Error creating radar chart:", error);
      }
    }
  }

  const doughnutCtx = document.getElementById("statsDoughnutChart");
  if (doughnutCtx) {
    const doughnutDataElement = document.getElementById("doughnut-chart");
    if (doughnutDataElement) {
      try {
        let doughnutData = JSON.parse(doughnutDataElement.textContent.trim());
        if (typeof doughnutData === "string") {
          doughnutData = JSON.parse(doughnutData);
        }
        if (typeof doughnutData === "object") {
          console.log("Chart data:", doughnutData);

          Chart.register(ChartDataLabels);

          new Chart(doughnutCtx, {
            type: doughnutData.type,
            data: {
              ...doughnutData.data,
              datasets: [
                {
                  ...doughnutData.data.datasets[0],
                  borderColor: "#1e1e2f",
                  borderWidth: 2,
                },
              ],
            },
            options: {
              ...doughnutData.options,
              plugins: {
                ...doughnutData.options.plugins,
                datalabels: {
                  color: "#ffffff",
                  font: {
                    size: 9,
                    weight: "bold",
                  },
                  formatter: function (value, context) {
                    const label = context.chart.data.labels[context.dataIndex];
                    return value > 0.5 ? `${label}\n${value.toFixed(1)}%` : "";
                  },
                  display: true,
                  rotation: function (context) {
                    const value = context.dataset.data[context.dataIndex];
                    return value > 5 ? 0 : 45;
                  },
                  align: "center",
                  anchor: "center",
                  offset: 0,
                },
              },
            },
          });
        }
      } catch (error) {
        console.error("Error creating doughnut chart:", error);
      }
    }
  }
});
