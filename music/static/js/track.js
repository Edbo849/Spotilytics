document.addEventListener("DOMContentLoaded", function () {
  const showPreviewsBtn = document.getElementById("showPreviewsBtn");
  if (showPreviewsBtn) {
    showPreviewsBtn.addEventListener("click", async function () {
      this.disabled = true;
      this.textContent = "Loading...";

      // Only get similar track IDs, not the main track
      const trackCards = document.querySelectorAll(".track-card");
      const trackIds = Array.from(trackCards).map(
        (card) => card.dataset.trackId
      );

      try {
        const response = await fetch(
          `/preview-urls/?track_ids=${trackIds.join(",")}`
        );
        if (!response.ok) {
          throw new Error("Network response was not ok");
        }
        const data = await response.json();

        // Update similar tracks previews
        trackCards.forEach((card) => {
          const trackId = card.dataset.trackId;
          const placeholder = card.querySelector(".preview-placeholder");
          if (data[trackId]) {
            placeholder.innerHTML = `
              <audio controls>
                <source src="${data[trackId]}" type="audio/mpeg">
                Your browser does not support the audio element.
              </audio>`;
          } else {
            placeholder.innerHTML =
              '<p class="text-muted">No preview available</p>';
          }
        });

        this.textContent = "Previews Loaded";
      } catch (error) {
        console.error("Error fetching previews:", error);
        this.textContent = "Error Loading Previews";
        this.disabled = false;
      }
    });
  }
});
