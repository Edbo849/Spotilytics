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

  console.log("Starting streaming trend chart initialization");

  const ctx = document.getElementById("streamingTrendChart");
  console.log("Canvas element:", ctx);

  if (ctx) {
    const chartDataElement = document.getElementById("trends-chart");
    console.log("Chart data element:", chartDataElement);

    if (chartDataElement) {
      try {
        console.log("Raw chart data:", chartDataElement.textContent);

        let chartData = JSON.parse(chartDataElement.textContent.trim());
        console.log("Parsed initial chart data:", chartData);

        if (typeof chartData === "string") {
          chartData = JSON.parse(chartData);
          console.log("Parsed nested chart data:", chartData);
        }
        if (typeof chartData === "object") {
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
            },
          });
        }
      } catch (error) {
        console.error("Error creating streaming trend chart:", error);
      }
    }
  }
});
