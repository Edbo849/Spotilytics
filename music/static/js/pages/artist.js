/**
 * Artist page functionality
 * Handles loading and filtering artist releases by type
 */
document.addEventListener("DOMContentLoaded", () => {
  // DOM elements
  const releasesContainer = document.getElementById("releases-container");
  const latestReleasesContainer = document.getElementById(
    "latest-releases-container"
  );
  const filterButtons = document.querySelectorAll("[data-type]");
  const spinner = document.querySelector(".loading-spinner");

  // Track current filter type
  let currentType = "album";

  // Initialize active button state
  filterButtons.forEach((btn) => {
    btn.classList.remove("active");
    if (btn.dataset.type === "album") {
      btn.classList.add("active");
    }
  });

  /**
   * Load artist releases filtered by type
   * @param {string} type - Release type filter (album, single, compilation, all)
   */
  const loadReleases = async (type) => {
    if (!releasesContainer) return;

    const artistId = releasesContainer.dataset.artistId;
    spinner.style.display = "block";
    releasesContainer.innerHTML = "";

    try {
      // Fetch all releases for the artist
      const response = await fetch(`/artist/${artistId}/releases/?type=all`);
      if (!response.ok) throw new Error("Network response was not ok");
      const data = await response.json();

      // Process and display latest releases (if container exists)
      if (latestReleasesContainer) {
        renderLatestReleases(data.releases, artistId);
      }

      // Filter releases based on selected type
      const filteredReleases = filterReleasesByType(
        data.releases,
        type,
        artistId
      );

      // Display message when no releases match the filter
      if (!filteredReleases.length) {
        renderEmptyState(type, releasesContainer);
        return;
      }

      // Render filtered releases
      renderReleases(filteredReleases, releasesContainer);
    } catch (error) {
      console.error("Error loading releases:", error);
      releasesContainer.innerHTML =
        '<p class="text-warning">Error loading releases</p>';
    } finally {
      spinner.style.display = "none";
    }
  };

  /**
   * Filter releases based on selected type
   * @param {Array} releases - All artist releases
   * @param {string} type - Release type to filter by
   * @param {string} artistId - Current artist ID
   * @returns {Array} Filtered releases
   */
  const filterReleasesByType = (releases, type, artistId) => {
    return releases.filter((release) => {
      if (type === "all") {
        if (release.album_type === "compilation") {
          return release.artists && release.artists[0].id === artistId;
        }
        return release.album_type !== "appears_on";
      }

      if (type === "compilation") {
        return (
          release.album_type === "compilation" &&
          release.artists &&
          release.artists[0].id === artistId
        );
      }

      return release.album_type === type;
    });
  };

  /**
   * Render latest releases in the latest releases container
   * @param {Array} releases - All artist releases
   * @param {string} artistId - Current artist ID
   */
  const renderLatestReleases = (releases, artistId) => {
    const sortedReleases = [...releases]
      .filter((release) => {
        if (release.album_type === "compilation") {
          return release.artists && release.artists[0].id === artistId;
        }
        return true;
      })
      .sort((a, b) => new Date(b.release_date) - new Date(a.release_date))
      .slice(0, 10);

    latestReleasesContainer.innerHTML = sortedReleases
      .map((release) => createReleaseCard(release))
      .join("");
  };

  /**
   * Render releases in the specified container
   * @param {Array} releases - Releases to display
   * @param {HTMLElement} container - Container to render into
   */
  const renderReleases = (releases, container) => {
    container.innerHTML = releases
      .map((release) => createReleaseCard(release))
      .join("");
  };

  /**
   * Create HTML for a release card
   * @param {Object} release - Release data
   * @returns {string} HTML for release card
   */
  const createReleaseCard = (release) => {
    return `
      <div class="album-card">
        <a href="/album/${release.id}">
          <img src="${release.images[0].url}" alt="${
      release.name
    }" class="album-img" />
          <div class="album-info">
            <h5>${release.name}</h5>
            <p>${release.release_date.slice(0, 4)} • ${release.album_type}</p>
          </div>
        </a>
      </div>
    `;
  };

  /**
   * Render empty state message when no releases match filter
   * @param {string} type - Current filter type
   * @param {HTMLElement} container - Container to render into
   */
  const renderEmptyState = (type, container) => {
    const typeDisplay = {
      album: "albums",
      single: "singles",
      compilation: "compilations",
    };

    container.innerHTML = `
      <div class="text-center w-100">
        <p class="text-muted">This artist has no ${
          typeDisplay[type] || "releases"
        }</p>
      </div>
    `;
  };

  // Add click handlers to filter buttons
  filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const type = button.dataset.type;
      if (type === currentType) return;

      // Update active button UI
      filterButtons.forEach((btn) => btn.classList.remove("active"));
      button.classList.add("active");

      // Update current type and load releases
      currentType = type;
      loadReleases(type);
    });
  });

  // Initial load
  loadReleases("album");
});
