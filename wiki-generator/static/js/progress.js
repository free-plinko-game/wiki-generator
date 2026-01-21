// Progress tracking for content generation

let startTime;
let timerInterval;

function initGeneratePage(projectId, startGenerateUrl, progressUrl) {
    const form = document.getElementById('generate-form');
    const selectAll = document.getElementById('select-all');

    // Select all checkbox
    selectAll.addEventListener('change', function() {
        document.querySelectorAll('.page-checkbox').forEach(cb => {
            cb.checked = this.checked;
        });
    });

    // Form submission
    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        const apiKey = document.getElementById('api_key').value;
        const selectedPages = Array.from(document.querySelectorAll('.page-checkbox:checked'))
            .map(cb => cb.value);

        if (!apiKey) {
            showToast('Please enter your Anthropic API key', 'error');
            return;
        }

        if (selectedPages.length === 0) {
            showToast('Please select at least one page', 'error');
            return;
        }

        // Show progress section
        document.getElementById('setup-section').style.display = 'none';
        document.getElementById('progress-section').style.display = 'block';
        document.getElementById('pages-total').textContent = selectedPages.length;

        // Start timer
        startTime = Date.now();
        timerInterval = setInterval(updateTimer, 1000);

        // Start generation
        try {
            const response = await fetch(startGenerateUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    api_key: apiKey,
                    pages: selectedPages
                })
            });

            const data = await response.json();

            if (data.success) {
                // Start polling for progress
                pollProgress(progressUrl);
            } else {
                showError(data.error || 'Failed to start generation');
            }
        } catch (error) {
            showError('Network error: ' + error.message);
        }
    });
}

function updateTimer() {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    document.getElementById('time-elapsed').textContent = formatTime(elapsed);
}

async function pollProgress(progressUrl) {
    try {
        const response = await fetch(progressUrl);
        const data = await response.json();

        // Update UI
        document.getElementById('progress-bar').style.width = data.percent + '%';
        document.getElementById('pages-completed').textContent = data.completed;
        document.getElementById('pages-total').textContent = data.total;

        // Update status
        const statusDiv = document.getElementById('progress-status');
        const pageDiv = document.getElementById('progress-page');

        if (data.status === 'generating') {
            statusDiv.textContent = `Generating page ${data.completed + 1} of ${data.total}`;
            pageDiv.textContent = data.current_page || 'Processing...';
        } else if (data.status === 'complete') {
            clearInterval(timerInterval);
            showComplete(data);
            return;
        } else if (data.status === 'error') {
            clearInterval(timerInterval);
            showError(data.error || 'Generation failed');
            return;
        } else {
            statusDiv.textContent = 'Processing...';
            pageDiv.textContent = data.current_page || 'Starting...';
        }

        // Add to log
        if (data.current_page && data.status === 'generating') {
            addLogEntry(`Generating: ${data.current_page}`);
        }

        // Continue polling
        setTimeout(() => pollProgress(progressUrl), 2000);
    } catch (error) {
        console.error('Progress poll error:', error);
        // Retry after longer delay
        setTimeout(() => pollProgress(progressUrl), 5000);
    }
}

function addLogEntry(message) {
    const log = document.getElementById('generation-log');
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.textContent = `[${time}] ${message}`;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function showComplete(data) {
    document.getElementById('progress-section').style.display = 'none';
    document.getElementById('complete-section').style.display = 'block';

    const msg = document.getElementById('complete-message');
    if (data.failed && data.failed.length > 0) {
        msg.textContent = `${data.success.length} pages generated, ${data.failed.length} failed.`;
    } else {
        msg.textContent = `All ${data.success.length} pages have been generated successfully.`;
    }
}

function showError(message) {
    clearInterval(timerInterval);

    document.getElementById('progress-status').textContent = 'Error';
    document.getElementById('progress-page').textContent = message;
    document.getElementById('progress-bar').style.background = 'var(--color-error)';

    addLogEntry(`ERROR: ${message}`);
    showToast(message, 'error', 5000);
}
