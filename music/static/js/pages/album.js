/**
 * Album page functionality
 * Handles sortable tables in the album view
 */
document.addEventListener("DOMContentLoaded", () => {
  // Extract cell value from table row at specified index
  const getCellValue = (tr, idx) => {
    return tr.children[idx].innerText || tr.children[idx].textContent;
  };

  /**
   * Create comparison function for table sorting
   * @param {number} idx - Column index to sort by
   * @param {boolean} asc - Whether to sort ascending (true) or descending (false)
   * @returns {Function} Comparison function for Array.sort()
   */
  const createComparer = (idx, asc) => {
    return (rowA, rowB) => {
      // Get the values to compare based on sort direction
      const valueA = getCellValue(asc ? rowA : rowB, idx);
      const valueB = getCellValue(asc ? rowB : rowA, idx);

      // Try numeric comparison if both values are numbers
      const numA = parseFloat(valueA);
      const numB = parseFloat(valueB);

      if (valueA && valueB && !isNaN(numA) && !isNaN(numB)) {
        return numA - numB;
      }

      // Fall back to string comparison
      return String(valueA).localeCompare(String(valueB));
    };
  };

  // Add click handlers to all sortable table headers
  const sortableHeaders = document.querySelectorAll("th[data-sort]");

  sortableHeaders.forEach((header) => {
    // Track sort state for each header
    let isAscending = false;

    header.addEventListener("click", () => {
      // Toggle sort direction
      isAscending = !isAscending;

      // Find table and its body
      const table = header.closest("table");
      const tbody = table.querySelector("tbody");

      // Get column index
      const columnIndex = Array.from(header.parentNode.children).indexOf(
        header
      );

      // Sort rows and update DOM
      const rows = Array.from(tbody.querySelectorAll("tr"));
      const sortedRows = rows.sort(createComparer(columnIndex, isAscending));

      // Re-append rows in sorted order
      sortedRows.forEach((row) => tbody.appendChild(row));
    });
  });
});
