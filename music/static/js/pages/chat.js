/**
 * Chat interface functionality
 * Handles user input, message display, and communication with the backend
 */

// Wait for DOM to be fully loaded before initializing
document.addEventListener("DOMContentLoaded", () => {
  // DOM elements
  const chatForm = document.getElementById("chatForm");
  const chatMessages = document.getElementById("chatMessages");
  const userInput = document.getElementById("userInput");
  const loadingIndicator = document.getElementById("loadingIndicator");

  /**
   * Handle form submission
   * Captures user input and sends to backend API
   */
  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = userInput.value.trim();
    if (!message) return;

    // Display user's message and clear input
    appendMessage("user", message);
    userInput.value = "";

    // Show loading indicator if it exists
    if (loadingIndicator) loadingIndicator.style.display = "block";

    // Send to backend using Fetch API
    try {
      const response = await fetch(CHAT_API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
        body: JSON.stringify({ message }),
      });

      const data = await response.json();

      // Hide loading indicator if it exists
      if (loadingIndicator) loadingIndicator.style.display = "none";

      if (response.ok) {
        appendMessage("bot", data.reply);
      } else {
        appendMessage("bot", data.error || "An error occurred.");
      }
    } catch (error) {
      console.error("Error:", error);
      appendMessage("bot", "An error occurred.");

      // Hide loading indicator if it exists
      if (loadingIndicator) loadingIndicator.style.display = "none";
    }
  });

  /**
   * Append a new message to the chat container
   * @param {string} sender - Message sender ("user" or "bot")
   * @param {string} text - Message text content
   */
  const appendMessage = (sender, text) => {
    const messageDiv = document.createElement("div");
    messageDiv.classList.add("message", sender);
    messageDiv.innerHTML = `<p>${text}</p>`;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  };

  /**
   * Extract CSRF token from cookies for secure form submission
   * @returns {string} CSRF token or null if not found
   */
  const getCSRFToken = () => {
    const name = "csrftoken";
    if (!document.cookie || document.cookie === "") return null;

    const cookies = document.cookie.split(";");
    for (const cookie of cookies) {
      const trimmedCookie = cookie.trim();
      if (trimmedCookie.startsWith(`${name}=`)) {
        return decodeURIComponent(trimmedCookie.substring(name.length + 1));
      }
    }
    return null;
  };
});

/**
 * jQuery implementation for backward compatibility
 * This code is redundant with the native JS implementation above and should be refactored.
 * @deprecated Use the native JS implementation above
 */
$(document).ready(() => {
  $("#sendButton").on("click", () => {
    const userMessage = $("#userInput").val().trim();
    if (!userMessage) return;

    // Display user's message
    displayMessage(userMessage, "user");

    // Clear input
    $("#userInput").val("");

    // Show loading indicator
    $("#loadingIndicator").show();

    // Send AJAX request to the server
    $.ajax({
      url: CHAT_API_URL, // Should use the same API URL as native implementation
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(), // Added CSRF token
      },
      data: {
        message: userMessage,
      },
      success: (response) => {
        // Hide loading indicator
        $("#loadingIndicator").hide();

        if (response.reply) {
          // Display AI's response
          displayMessage(response.reply, "bot");
        } else if (response.error) {
          displayMessage(`Error: ${response.error}`, "bot");
        }
      },
      error: () => {
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

  /**
   * Display a message in the chat container using jQuery
   * @param {string} message - Message text content
   * @param {string} sender - Message sender ("user" or "bot")
   */
  const displayMessage = (message, sender) => {
    const messageClass = sender === "user" ? "message user" : "message bot";
    $("#chat-container").append(
      `<div class="${messageClass}"><p>${message}</p></div>`
    );
    // Scroll to the latest message
    $("#chat-container").scrollTop($("#chat-container")[0].scrollHeight);
  };

  /**
   * Get CSRF token for jQuery implementation
   * @returns {string} CSRF token
   */
  const getCsrfToken = () => {
    return (
      $("[name=csrfmiddlewaretoken]").val() ||
      document.querySelector("[name=csrfmiddlewaretoken]")?.value
    );
  };
});
