document.addEventListener("DOMContentLoaded", function () {
  // Import History Form handling
  const importForm = document.getElementById("importHistoryForm");
  if (importForm) {
    importForm.addEventListener("submit", function (event) {
      event.preventDefault();

      var form = event.target;
      var files = form.querySelector('input[type="file"]').files;
      var totalFiles = files.length;
      var completedFiles = 0;
      var redirectUrl = form.getAttribute("data-redirect-url");

      // Reset the loading message text
      document.getElementById("loadingMessage").innerHTML = `
                <p>Loading... Please wait.</p>
                <div class="progress">
                    <div id="progressBar" class="progress-bar bg-spotify-green" role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                </div>
            `;
      document.getElementById("loadingMessage").style.display = "block";

      function updateProgress() {
        completedFiles++;
        var percentComplete = (completedFiles / totalFiles) * 100;
        document.getElementById("progressBar").style.width =
          percentComplete + "%";
        document
          .getElementById("progressBar")
          .setAttribute("aria-valuenow", percentComplete);

        if (completedFiles === totalFiles) {
          document.getElementById("loadingMessage").innerHTML = `
                        <p style="color: green;">Upload Completed.</p>
                        <div class="progress">
                            <div id="progressBar" class="progress-bar bg-success" role="progressbar" style="width: 100%;" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100"></div>
                        </div>
                    `;
          setTimeout(function () {
            var modal = bootstrap.Modal.getInstance(
              document.getElementById("importHistoryModal")
            );
            modal.hide();
            window.location.href = redirectUrl;
          }, 2000);
        }
      }

      function uploadFile(file) {
        var formData = new FormData();
        formData.append("history_files", file);

        var xhr = new XMLHttpRequest();
        xhr.open("POST", form.action, true);
        xhr.setRequestHeader(
          "X-CSRFToken",
          form.querySelector("[name=csrfmiddlewaretoken]").value
        );

        xhr.addEventListener("load", function () {
          if (xhr.status === 200) {
            updateProgress();
          } else {
            document.getElementById("loadingMessage").innerHTML = `
                            <p style="color: red;">Upload Failed. Error: ${xhr.responseText}</p>
                            <div class="progress">
                                <div id="progressBar" class="progress-bar bg-danger" role="progressbar" style="width: 0%;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                            </div>
                        `;
          }
        });

        xhr.send(formData);
      }

      for (var i = 0; i < totalFiles; i++) {
        uploadFile(files[i]);
      }
    });
  }

  // Delete History Form handling
  const deleteForm = document.getElementById("deleteHistoryForm");
  if (deleteForm) {
    deleteForm.addEventListener("submit", function (event) {
      event.preventDefault();

      var form = event.target;
      var formData = new FormData(form);
      var xhr = new XMLHttpRequest();

      xhr.open("POST", form.action, true);
      xhr.setRequestHeader(
        "X-CSRFToken",
        form.querySelector("[name=csrfmiddlewaretoken]").value
      );

      xhr.addEventListener("load", function () {
        if (xhr.status === 200) {
          alert("All listening history has been deleted.");
          window.location.reload();
        } else {
          alert(
            "Failed to delete listening history. Error: " + xhr.responseText
          );
        }
      });

      xhr.addEventListener("error", function () {
        alert("An error occurred while deleting the listening history.");
      });

      xhr.send(formData);
    });
  }
});
