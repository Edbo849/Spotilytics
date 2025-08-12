/**
 * Artist Tracks page functionality
 * Handles sortable tables with different data types (numbers, strings, dates)
 */
document.addEventListener("DOMContentLoaded", () => {
  /**
   * Extracts text content from a table cell
   * @param {HTMLElement} tr - Table row element
   * @param {number} idx - Column index
   * @returns {string} Cell content
   */
  const getCellValue = (tr, idx) => {
    const cell = tr.children[idx];
    return cell.innerText || cell.textContent;
  };

  /**
   * Creates a comparison function for table sorting
   * @param {number} idx - Column index to sort by
   * @param {boolean} asc - Whether to sort ascending (true) or descending (false)
   * @returns {Function} Comparison function for Array.sort()
   */
  const createComparer = (idx, asc) => (rowA, rowB) => {
    // Get cell values to compare
    const valueA = getCellValue(rowA, idx);
    const valueB = getCellValue(rowB, idx);

    // Determine sort direction multiplier
    const directionMultiplier = asc ? 1 : -1;

    // Get data type from table header
    const dataType = rowA
      .closest("table")
      .querySelectorAll("th")
      [idx].getAttribute("data-sort");

    // Compare based on data type
    switch (dataType) {
      case "number":
        const num1 = parseFloat(valueA) || 0;
        const num2 = parseFloat(valueB) || 0;
        return (num1 - num2) * directionMultiplier;

      case "string":
        return (
          String(valueA).localeCompare(String(valueB)) * directionMultiplier
        );

      case "date":
        const date1 = new Date(valueA);
        const date2 = new Date(valueB);
        return (date1 - date2) * directionMultiplier;

      default:
        // Fallback to string comparison if type not specified
        return (
          String(valueA).localeCompare(String(valueB)) * directionMultiplier
        );
    }
  };

  // Add click handlers to all sortable table headers
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      // Get table elements
      const table = th.closest("table");
      const tbody = table.querySelector("tbody");

      // Get column index
      const columnIndex = Array.from(th.parentNode.children).indexOf(th);

      // Toggle sort direction
      const isAscending = !th.classList.contains("asc");

      // Update UI to show sort direction
      const allHeaders = th.parentNode.querySelectorAll("th");
      allHeaders.forEach((header) => {
        header.classList.remove("asc", "desc");
      });
      th.classList.toggle("asc", isAscending);
      th.classList.toggle("desc", !isAscending);

      // Sort rows and update DOM
      const rows = Array.from(tbody.querySelectorAll("tr"));
      rows
        .sort(createComparer(columnIndex, isAscending))
        .forEach((row) => tbody.appendChild(row));
    });
  });
});
