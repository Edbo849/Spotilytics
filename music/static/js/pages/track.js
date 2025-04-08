/**
 * Track page functionality
 * Handles loading audio previews for similar tracks
 */
document.addEventListener("DOMContentLoaded", () => {
  const showPreviewsBtn = document.getElementById("showPreviewsBtn");

  if (showPreviewsBtn) {
    showPreviewsBtn.addEventListener("click", async () => {
      // Update button state to loading
      showPreviewsBtn.disabled = true;
      showPreviewsBtn.textContent = "Loading...";

      await loadTrackPreviews(showPreviewsBtn);
    });
  }

  /**
   * Loads track previews from the API and updates the UI
   * @param {HTMLElement} button - The button that triggered the loading
   */
  const loadTrackPreviews = async (button) => {
    try {
      // Select all similar track cards
      const trackCards = document.querySelectorAll(".track-card");

      // Extract track IDs from the data attributes
      const trackIds = Array.from(trackCards).map(
        (card) => card.dataset.trackId
      );

      // Fetch preview URLs from backend
      const response = await fetch(
        `/preview-urls/?track_ids=${trackIds.join(",")}`
      );

      if (!response.ok) {
        throw new Error(`Network response was not ok: ${response.status}`);
      }

      const data = await response.json();

      // Update the UI with preview players
      updateTrackPreviews(trackCards, data);

      // Update button state to success
      button.textContent = "Previews Loaded";
    } catch (error) {
      console.error("Error fetching previews:", error);

      // Update button state to error
      button.textContent = "Error Loading Previews";
      button.disabled = false;
    }
  };

  /**
   * Updates the DOM with audio players for each track preview
   * @param {NodeList} trackCards - Collection of track card elements
   * @param {Object} previewData - Object containing preview URLs keyed by track ID
   */
  const updateTrackPreviews = (trackCards, previewData) => {
    trackCards.forEach((card) => {
      const trackId = card.dataset.trackId;
      const placeholder = card.querySelector(".preview-placeholder");

      if (previewData[trackId]) {
        // Preview URL exists, create audio player
        placeholder.innerHTML = `
          <audio controls>
            <source src="${previewData[trackId]}" type="audio/mpeg">
            Your browser does not support the audio element.
          </audio>`;
      } else {
        // No preview available
        placeholder.innerHTML =
          '<p class="text-muted">No preview available</p>';
      }
    });
  };
});
