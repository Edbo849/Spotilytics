/**
 * Search Results page functionality
 * Handles smooth scrolling between sections and highlights active navigation items
 */
document.addEventListener("DOMContentLoaded", () => {
  const navItems = document.querySelectorAll(".section-nav-item");
  const sections = document.querySelectorAll(".search-section");
  const scrollOffset = 100; // Offset for highlighting sections

  /**
   * Updates the active navigation item based on scroll position
   */
  const updateActiveNavItem = () => {
    // Default to empty if we're above all sections
    let currentSectionId = "";

    // Find the topmost visible section
    sections.forEach((section) => {
      const sectionTop = section.offsetTop;
      if (window.scrollY >= sectionTop - scrollOffset) {
        currentSectionId = section.id;
      }
    });

    // Update navigation items' active state
    navItems.forEach((item) => {
      // Get the target section ID from the href attribute
      const targetSectionId = item.getAttribute("href").substring(1);

      // Toggle active class based on whether this item points to the current section
      item.classList.toggle("active", targetSectionId === currentSectionId);
    });
  };

  /**
   * Smoothly scrolls to the target section when a navigation item is clicked
   * @param {Event} e - Click event object
   */
  const handleNavItemClick = (e) => {
    e.preventDefault();

    const targetSelector = e.currentTarget.getAttribute("href");
    const targetSection = document.querySelector(targetSelector);

    if (targetSection) {
      targetSection.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  };

  // Add click event listeners to navigation items
  navItems.forEach((item) => {
    item.addEventListener("click", handleNavItemClick);
  });

  // Add scroll event listener to update active navigation item
  window.addEventListener("scroll", updateActiveNavItem);

  // Set initial active state on page load
  updateActiveNavItem();
});
