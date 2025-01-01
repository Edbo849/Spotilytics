document.addEventListener("DOMContentLoaded", function () {
  const chatForm = document.getElementById("chatForm");
  const chatMessages = document.getElementById("chatMessages");
  const userInput = document.getElementById("userInput");

  chatForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    const message = userInput.value.trim();
    if (!message) return;

    // Display user's message
    appendMessage("user", message);
    userInput.value = "";

    // Send to backend
    try {
      const response = await fetch(CHAT_API_URL, {
        // Use the global variable
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
        body: JSON.stringify({ message: message }),
      });

      const data = await response.json();

      if (response.ok) {
        appendMessage("bot", data.reply);
      } else {
        appendMessage("bot", data.error || "An error occurred.");
      }
    } catch (error) {
      appendMessage("bot", "An error occurred.");
      console.error("Error:", error);
    }
  });

  function appendMessage(sender, text) {
    const messageDiv = document.createElement("div");
    messageDiv.classList.add("message", sender);
    messageDiv.innerHTML = `<p>${text}</p>`;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function getCSRFToken() {
    let cookieValue = null;
    const name = "csrftoken";
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.startsWith(name + "=")) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
});

$(document).ready(function () {
  $("#sendButton").on("click", function () {
    let userMessage = $("#userInput").val();
    if (userMessage.trim() === "") return;

    // Display user's message
    displayMessage(userMessage, "user");

    // Clear input
    $("#userInput").val("");

    // Show loading indicator
    $("#loadingIndicator").show();

    // Send AJAX request to the server
    $.ajax({
      url: "/path-to-your-chat-api/", // Replace with your actual API endpoint
      method: "POST",
      data: {
        message: userMessage,
      },
      success: function (response) {
        // Hide loading indicator
        $("#loadingIndicator").hide();

        if (response.reply) {
          // Display AI's response
          displayMessage(response.reply, "bot");
        } else if (response.error) {
          displayMessage("Error: " + response.error, "bot");
        }
      },
      error: function () {
        // Hide loading indicator
        $("#loadingIndicator").hide();

        // Display generic error message
        displayMessage(
          "An error occurred while processing your request.",
          "bot"
        );
      },
    });
  });

  function displayMessage(message, sender) {
    let messageClass = sender === "user" ? "message user" : "message bot";
    $("#chat-container").append(
      `<div class="${messageClass}">${message}</div>`
    );
    // Optionally, scroll to the latest message
    $("#chat-container").scrollTop($("#chat-container")[0].scrollHeight);
  }
});
