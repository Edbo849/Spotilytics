document.addEventListener("DOMContentLoaded", function () {
  const timeRangeBtns = document.querySelectorAll(".time-range-btn");
  const itemId = document.querySelector(".stats-section").dataset.itemId;
  const itemType = document.querySelector(".stats-section").dataset.itemType;

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
      console.log(data);

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

  timeRangeBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      timeRangeBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      loadStats(btn.dataset.range);
    });
  });

  // Load initial stats
  loadStats("last_4_weeks");
});

document.addEventListener("DOMContentLoaded", function () {
  const customRangeBtn = document.getElementById("customRangeBtn");
  const customDateInputs = document.querySelector(".custom-date-inputs");

  if (customRangeBtn) {
    customRangeBtn.addEventListener("click", function () {
      customDateInputs.style.display =
        customDateInputs.style.display === "none" ? "block" : "none";
    });
  }
});
