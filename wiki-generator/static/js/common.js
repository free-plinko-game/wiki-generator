// Common utilities for Wiki Generator

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - Type of toast: 'success', 'error', 'info'
 * @param {number} duration - How long to show the toast (ms)
 */
function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

/**
 * Format time elapsed
 * @param {number} seconds - Number of seconds
 * @returns {string} Formatted time string (M:SS)
 */
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Debounce function
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in ms
 * @returns {Function} Debounced function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Make an API request with error handling
 * @param {string} url - The URL to fetch
 * @param {Object} options - Fetch options
 * @returns {Promise} Response data
 */
async function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
    };

    const mergedOptions = {
        ...defaultOptions,
        ...options,
        headers: {
            ...defaultOptions.headers,
            ...options.headers,
        },
    };

    try {
        const response = await fetch(url, mergedOptions);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Request failed');
        }

        return data;
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

/**
 * Convert string to URL-safe filename
 * @param {string} str - String to convert
 * @returns {string} Safe filename
 */
function toFilename(str) {
    return str.replace(/\s+/g, '_').replace(/[^a-zA-Z0-9_-]/g, '');
}

/**
 * Escape HTML to prevent XSS
 * @param {string} str - String to escape
 * @returns {string} Escaped string
 */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Add loading state to submit buttons after a valid submit is triggered.
document.addEventListener('submit', function(e) {
    const form = e.target;
    if (!form || !form.checkValidity()) {
        return;
    }

    const submitter = e.submitter;
    if (submitter && submitter.matches('button[type="submit"]')) {
        submitter.classList.add('btn-loading');
        submitter.disabled = true;
    }
});
