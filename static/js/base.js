/**
 * Base functionality for Spotilytics
 * Handles common operations like file uploads and history deletion
 */
document.addEventListener("DOMContentLoaded", () => {
  // =========================================================
  // Import History Form handling
  // =========================================================
  const importForm = document.getElementById("importHistoryForm");

  if (importForm) {
    importForm.addEventListener("submit", (event) => {
      event.preventDefault();

      const form = event.target;
      const fileInput = form.querySelector('input[type="file"]');
      const files = fileInput.files;
      const totalFiles = files.length;
      const redirectUrl = form.getAttribute("data-redirect-url");

      if (totalFiles === 0) {
        alert("Please select at least one file to upload.");
        return;
      }

      let completedFiles = 0;
      const loadingMessage = document.getElementById("loadingMessage");

      // Initialize progress UI
      initializeProgressUI(loadingMessage);

      /**
       * Updates the progress bar and handles completion
       */
      const updateProgress = () => {
        completedFiles++;
        const percentComplete = (completedFiles / totalFiles) * 100;

        // Update progress bar
        const progressBar = document.getElementById("progressBar");
        progressBar.style.width = `${percentComplete}%`;
        progressBar.setAttribute("aria-valuenow", percentComplete);

        // Handle completion
        if (completedFiles === totalFiles) {
          showCompletionMessage(loadingMessage);

          // Redirect after a short delay
          setTimeout(() => {
            const modal = bootstrap.Modal.getInstance(
              document.getElementById("importHistoryModal")
            );
            modal.hide();
            window.location.href = redirectUrl;
          }, 2000);
        }
      };

      /**
       * Uploads a single file to the server
       * @param {File} file - The file to upload
       */
      const uploadFile = (file) => {
        const formData = new FormData();
        formData.append("history_files", file);

        // Use fetch API instead of XMLHttpRequest
        fetch(form.action, {
          method: "POST",
          headers: {
            "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]")
              .value,
          },
          body: formData,
        })
          .then((response) => {
            if (response.ok) {
              updateProgress();
            } else {
              return response.text().then((errorText) => {
                throw new Error(errorText);
              });
            }
          })
          .catch((error) => {
            showErrorMessage(loadingMessage, error.message);
          });
      };

      // Upload all selected files
      Array.from(files).forEach((file) => uploadFile(file));
    });
  }

  // =========================================================
  // Delete History Form handling
  // =========================================================
  const deleteForm = document.getElementById("deleteHistoryForm");

  if (deleteForm) {
    deleteForm.addEventListener("submit", (event) => {
      event.preventDefault();

      // Confirm deletion to prevent accidental data loss
      if (
        !confirm(
          "Are you sure you want to delete all your listening history? This action cannot be undone."
        )
      ) {
        return;
      }

      const form = event.target;
      const formData = new FormData(form);
      const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;

      // Use fetch API for better readability
      fetch(form.action, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken,
        },
        body: formData,
      })
        .then((response) => {
          if (response.ok) {
            alert("All listening history has been deleted.");
            window.location.reload();
          } else {
            return response.text().then((errorText) => {
              throw new Error(errorText);
            });
          }
        })
        .catch((error) => {
          alert(`Failed to delete listening history: ${error.message}`);
        });
    });
  }
});

/**
 * Initialize the progress UI
 * @param {HTMLElement} container - Element to show the progress in
 */
const initializeProgressUI = (container) => {
  container.innerHTML = `
    <p>Loading... Please wait.</p>
    <div class="progress">
      <div id="progressBar" class="progress-bar bg-spotify-green" 
           role="progressbar" style="width: 0%;" 
           aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
      </div>
    </div>
  `;
  container.style.display = "block";
};

/**
 * Show completion message in the UI
 * @param {HTMLElement} container - Element to show the message in
 */
const showCompletionMessage = (container) => {
  container.innerHTML = `
    <p style="color: green;">Upload Completed!</p>
    <div class="progress">
      <div id="progressBar" class="progress-bar bg-success" 
           role="progressbar" style="width: 100%;" 
           aria-valuenow="100" aria-valuemin="0" aria-valuemax="100">
      </div>
    </div>
  `;
};

/**
 * Show error message in the UI
 * @param {HTMLElement} container - Element to show the error in
 * @param {string} errorText - Error message to display
 */
const showErrorMessage = (container, errorText) => {
  container.innerHTML = `
    <p style="color: red;">Upload Failed. Error: ${errorText}</p>
    <div class="progress">
      <div id="progressBar" class="progress-bar bg-danger" 
           role="progressbar" style="width: 0%;" 
           aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
      </div>
    </div>
  `;
};
