document.addEventListener("DOMContentLoaded", function () {
  const navItems = document.querySelectorAll(".section-nav-item");

  // Highlight active section on scroll
  window.addEventListener("scroll", () => {
    let current = "";

    document.querySelectorAll(".search-section").forEach((section) => {
      const sectionTop = section.offsetTop;
      if (pageYOffset >= sectionTop - 100) {
        current = section.getAttribute("id");
      }
    });

    navItems.forEach((item) => {
      item.classList.remove("active");
      if (item.getAttribute("href").substring(1) === current) {
        item.classList.add("active");
      }
    });
  });

  // Smooth scroll to section
  navItems.forEach((item) => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      const target = document.querySelector(item.getAttribute("href"));
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
});
