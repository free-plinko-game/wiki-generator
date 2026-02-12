function formatNumber(value) {
    return new Intl.NumberFormat().format(value || 0);
}

function formatPercent(value) {
    const percent = (value || 0) * 100;
    return `${percent.toFixed(2)}%`;
}

function formatPosition(value) {
    return (value || 0).toFixed(2);
}

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('gsc-query-form');
    if (!form) return;

    const statusEl = document.getElementById('gsc-status');
    const tableBody = document.getElementById('gsc-table-body');
    const summary = document.getElementById('gsc-summary');
    const fetchBtn = document.getElementById('gsc-fetch-btn');
    const exportBtn = document.getElementById('gsc-export-btn');

    const totalClicks = document.getElementById('gsc-total-clicks');
    const totalImpressions = document.getElementById('gsc-total-impressions');
    const totalCtr = document.getElementById('gsc-total-ctr');
    const totalPosition = document.getElementById('gsc-total-position');

    function setStatus(message, isError = false) {
        statusEl.textContent = message;
        statusEl.style.color = isError ? 'var(--color-error)' : '';
    }

    function renderEmpty(message) {
        tableBody.innerHTML = `<tr><td colspan="5" class="table-empty">${message}</td></tr>`;
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const startDate = document.getElementById('start_date').value;
        const endDate = document.getElementById('end_date').value;
        const rowLimit = document.getElementById('row_limit').value;

        setStatus('Fetching data...', false);
        fetchBtn.disabled = true;
        fetchBtn.classList.add('btn-loading');

        try {
            const data = await apiRequest(gscDataUrl, {
                method: 'POST',
                body: JSON.stringify({
                    start_date: startDate,
                    end_date: endDate,
                    row_limit: rowLimit
                })
            });

            const rows = data.rows || [];
            const totals = data.totals || {};

            if (!rows.length) {
                renderEmpty('No data found for this range.');
                summary.style.display = 'none';
                setStatus('No data returned.', false);
                return;
            }

            summary.style.display = 'grid';
            totalClicks.textContent = formatNumber(totals.clicks);
            totalImpressions.textContent = formatNumber(totals.impressions);
            totalCtr.textContent = formatPercent(totals.ctr);
            totalPosition.textContent = formatPosition(totals.position);

            tableBody.innerHTML = rows.map((row) => `
                <tr>
                    <td>${escapeHtml(row.query || '')}</td>
                    <td>${formatNumber(row.clicks)}</td>
                    <td>${formatNumber(row.impressions)}</td>
                    <td>${formatPercent(row.ctr)}</td>
                    <td>${formatPosition(row.position)}</td>
                </tr>
            `).join('');

            setStatus(`Loaded ${rows.length} queries.`, false);
        } catch (error) {
            summary.style.display = 'none';
            renderEmpty('Failed to load data.');
            setStatus(error.message || 'Failed to load data.', true);
        } finally {
            fetchBtn.disabled = false;
            fetchBtn.classList.remove('btn-loading');
        }
    });

    if (exportBtn) {
        exportBtn.addEventListener('click', (event) => {
            event.preventDefault();
            const startDate = document.getElementById('start_date').value;
            const endDate = document.getElementById('end_date').value;
            const rowLimit = document.getElementById('row_limit').value;

            if (!startDate || !endDate) {
                setStatus('Start and end dates are required for export.', true);
                return;
            }

            const params = new URLSearchParams({
                start_date: startDate,
                end_date: endDate,
                row_limit: rowLimit
            });

            window.location.href = `${gscExportUrl}?${params.toString()}`;
        });
    }
});
