document.addEventListener("DOMContentLoaded", function () {
  const releasesContainer = document.getElementById("releases-container");
  const latestReleasesContainer = document.getElementById(
    "latest-releases-container"
  );
  const filterButtons = document.querySelectorAll("[data-type]");
  const spinner = document.querySelector(".loading-spinner");
  let currentType = "album";

  filterButtons.forEach((btn) => {
    btn.classList.remove("active");
    if (btn.dataset.type === "album") {
      btn.classList.add("active");
    }
  });

  async function loadReleases(type) {
    if (!releasesContainer) return;

    const artistId = releasesContainer.dataset.artistId;
    spinner.style.display = "block";
    releasesContainer.innerHTML = "";

    try {
      const response = await fetch(`/artist/${artistId}/releases/?type=all`);
      if (!response.ok) throw new Error("Network response was not ok");
      const data = await response.json();

      // Display latest releases
      if (latestReleasesContainer) {
        const sortedReleases = [...data.releases]
          .filter((release) => {
            if (release.album_type === "compilation") {
              return release.artists && release.artists[0].id === artistId;
            }
            return true;
          })
          .sort((a, b) => new Date(b.release_date) - new Date(a.release_date))
          .slice(0, 10);

        const latestReleasesHtml = sortedReleases
          .map(
            (release) => `
            <div class="album-card">
              <a href="/album/${release.id}">
                <img src="${release.images[0].url}" alt="${
              release.name
            }" class="album-img" />
                <div class="album-info">
                  <h5>${release.name}</h5>
                  <p>${release.release_date.slice(0, 4)} • ${
              release.album_type
            }</p>
                </div>
              </a>
            </div>
          `
          )
          .join("");

        latestReleasesContainer.innerHTML = latestReleasesHtml;
      }

      const filteredReleases = data.releases.filter((release) => {
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

      if (!filteredReleases || filteredReleases.length === 0) {
        const typeDisplay = {
          album: "albums",
          single: "singles",
          compilation: "compilations",
        };
        releasesContainer.innerHTML = `
    <div class="text-center w-100">
      <p class="text-muted">This artist has no ${
        typeDisplay[type] || "releases"
      }</p>
    </div>
  `;
        return;
      }

      const releases = filteredReleases
        .map(
          (release) => `
          <div class="album-card">
            <a href="/album/${release.id}">
              <img src="${release.images[0].url}" alt="${
            release.name
          }" class="album-img" />
              <div class="album-info">
                <h5>${release.name}</h5>
                <p>${release.release_date.slice(0, 4)} • ${
            release.album_type
          }</p>
              </div>
            </a>
          </div>
        `
        )
        .join("");

      releasesContainer.innerHTML = releases;
    } catch (error) {
      console.error("Error loading releases:", error);
      releasesContainer.innerHTML =
        '<p class="text-warning">Error loading releases</p>';
    } finally {
      spinner.style.display = "none";
    }
  }

  filterButtons.forEach((button) => {
    button.addEventListener("click", function () {
      const type = this.dataset.type;
      if (type === currentType) return;

      filterButtons.forEach((btn) => btn.classList.remove("active"));
      this.classList.add("active");

      currentType = type;
      loadReleases(type);
    });
  });

  loadReleases("album");
});
