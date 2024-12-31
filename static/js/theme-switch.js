document.addEventListener("DOMContentLoaded", function () {
  const themeSwitch = document.querySelector(
    '.theme-switch input[type="checkbox"]'
  );
  const body = document.body;

  function toggleTheme() {
    const body = document.body;
    const currentTheme = localStorage.getItem("theme");

    if (currentTheme === "white-content") {
      body.classList.remove("white-content");
      localStorage.setItem("theme", "dark-content");
    } else {
      body.classList.add("white-content");
      localStorage.setItem("theme", "white-content");
    }
  }

  // Theme switch handler
  themeSwitch.addEventListener("change", function (e) {
    if (e.target.checked) {
      body.classList.add("white-content");
      localStorage.setItem("theme", "white-content");
    } else {
      body.classList.remove("white-content");
      localStorage.setItem("theme", "dark-content");
    }
  });
});
