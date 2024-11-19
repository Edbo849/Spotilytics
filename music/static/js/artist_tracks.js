
document.addEventListener('DOMContentLoaded', () => {
    const getCellValue = (tr, idx) => {
        const cell = tr.children[idx];
        return cell.innerText || cell.textContent;
    };

    const comparer = (idx, asc) => (a, b) => {
        const v1 = getCellValue(a, idx);
        const v2 = getCellValue(b, idx);
        
        const dataType = a.closest('table').querySelectorAll('th')[idx].getAttribute('data-sort');
        
        if (dataType === 'number') {
            const num1 = parseFloat(v1) || 0;
            const num2 = parseFloat(v2) || 0;
            return (num1 - num2) * (asc ? 1 : -1);
        } else {
            return v1.toString().localeCompare(v2) * (asc ? 1 : -1);
        }
    };

    document.querySelectorAll('th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const table = th.closest('table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const index = Array.from(th.parentNode.children).indexOf(th);
            const ascending = !th.classList.contains('asc');
            
            th.parentNode.querySelectorAll('th').forEach(header => {
                header.classList.remove('asc', 'desc');
            });
            th.classList.toggle('asc', ascending);
            th.classList.toggle('desc', !ascending);
            
            rows.sort(comparer(index, ascending));
            rows.forEach(row => tbody.appendChild(row));
        });
    });
});