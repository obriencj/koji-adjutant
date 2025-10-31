// Global state for dashboard auto-refresh
let autoRefresh = true;
let refreshInterval = 5000;
let timerId = null;

// Initialize dashboard on page load
function initDashboard() {
    // Initial load
    refreshAll();

    // Set up auto-refresh
    startAutoRefresh();

    // Set up controls (if they exist on this page)
    const toggle = document.getElementById('auto-refresh-toggle');
    const intervalSelect = document.getElementById('refresh-interval');

    if (toggle) {
        toggle.addEventListener('change', (e) => {
            autoRefresh = e.target.checked;
            startAutoRefresh();
        });
    }

    if (intervalSelect) {
        intervalSelect.addEventListener('change', (e) => {
            refreshInterval = parseInt(e.target.value);
            startAutoRefresh();
        });
    }
}

// Refresh all data
function refreshAll() {
    fetchStatus();
    fetchTasks();
    fetchContainers();
}

// Fetch status from API
async function fetchStatus() {
    try {
        const response = await fetch('/api/v1/status');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        updateStatus(data);
    } catch (err) {
        console.error('Failed to fetch status:', err);
        showError('status-section', 'Failed to load status');
    }
}

// Update status display
function updateStatus(data) {
    const workerIdEl = document.getElementById('worker-id');
    if (workerIdEl) {
        workerIdEl.textContent = `Worker: ${data.worker_id}`;
    }

    const badge = document.getElementById('status-badge');
    if (badge) {
        badge.textContent = data.status;
        badge.className = `status-badge status-${data.status}`;
    }

    const uptimeEl = document.getElementById('uptime');
    if (uptimeEl) {
        uptimeEl.textContent = formatDuration(data.uptime_seconds);
    }

    const activeTasksEl = document.getElementById('active-tasks');
    if (activeTasksEl) {
        activeTasksEl.textContent = `${data.active_tasks} / ${data.capacity}`;
    }

    const activeContainersEl = document.getElementById('active-containers');
    if (activeContainersEl) {
        activeContainersEl.textContent = data.containers_active;
    }

    const completedTodayEl = document.getElementById('completed-today');
    if (completedTodayEl) {
        completedTodayEl.textContent = data.tasks_completed_today;
    }

    const lastTaskTimeEl = document.getElementById('last-task-time');
    if (lastTaskTimeEl) {
        lastTaskTimeEl.textContent = data.last_task_time
            ? formatRelativeTime(data.last_task_time)
            : 'Never';
    }

    // Update Podman health status
    if (data.podman) {
        updatePodmanHealth(data.podman);
    }
}

// Update Podman health display
function updatePodmanHealth(podman) {
    const statusBadge = document.getElementById('podman-status-badge');
    const message = document.getElementById('podman-message');
    const details = document.getElementById('podman-details');
    const errorDiv = document.getElementById('podman-error');
    const errorMessage = document.getElementById('podman-error-message');

    if (!statusBadge || !message) return;

    // Update status badge
    statusBadge.textContent = podman.status;
    statusBadge.className = `status-badge status-${podman.status}`;

    // Update message
    message.textContent = podman.message;

    // Show/hide details or error
    if (podman.status === 'healthy') {
        if (details) {
            details.style.display = 'block';
            document.getElementById('podman-socket').textContent = podman.socket || '-';
            document.getElementById('podman-version').textContent = podman.version || '-';
            document.getElementById('podman-api-version').textContent = podman.api_version || '-';
        }
        if (errorDiv) {
            errorDiv.style.display = 'none';
        }
    } else {
        if (details) {
            details.style.display = 'none';
        }
        if (errorDiv && errorMessage && podman.error) {
            errorDiv.style.display = 'block';
            errorMessage.textContent = podman.error;
        }
    }
}

// Fetch tasks from API
async function fetchTasks() {
    try {
        const response = await fetch('/api/v1/tasks');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        updateTasksTable(data.tasks || []);
    } catch (err) {
        console.error('Failed to fetch tasks:', err);
        showError('tasks-tbody', 'Failed to load tasks');
    }
}

// Update tasks table
function updateTasksTable(tasks) {
    const tbody = document.getElementById('tasks-tbody');
    if (!tbody) return;

    if (tasks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6">No active tasks</td></tr>';
        return;
    }

    tbody.innerHTML = tasks
        .map(
            (task) => `
        <tr>
            <td><a href="/tasks/${task.task_id}">${task.task_id}</a></td>
            <td>${escapeHtml(task.type || '-')}</td>
            <td>${escapeHtml(task.arch || '-')}</td>
            <td>${escapeHtml(task.tag || '-')}</td>
            <td><span class="status-badge status-${task.status || 'unknown'}">${escapeHtml(
                task.status || 'unknown'
            )}</span></td>
            <td>${formatRelativeTime(task.started_at)}</td>
        </tr>
    `
        )
        .join('');
}

// Fetch containers from API
async function fetchContainers() {
    try {
        const response = await fetch('/api/v1/containers');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        updateContainersTable(data.containers || []);
    } catch (err) {
        console.error('Failed to fetch containers:', err);
        showError('containers-tbody', 'Failed to load containers');
    }
}

// Update containers table
function updateContainersTable(containers) {
    const tbody = document.getElementById('containers-tbody');
    if (!tbody) return;

    if (containers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5">No active containers</td></tr>';
        return;
    }

    tbody.innerHTML = containers
        .map(
            (container) => `
        <tr>
            <td><a href="/containers/${container.container_id}">${shortenId(
                container.container_id
            )}</a></td>
            <td>${
                container.task_id
                    ? `<a href="/tasks/${container.task_id}">${container.task_id}</a>`
                    : '-'
            }</td>
            <td>${escapeHtml(container.image || '-')}</td>
            <td><span class="status-badge status-${container.status || 'unknown'}">${escapeHtml(
                container.status || 'unknown'
            )}</span></td>
            <td>${formatRelativeTime(container.started_at || container.created_at)}</td>
        </tr>
    `
        )
        .join('');
}

// Format relative time (e.g., "5m ago")
function formatRelativeTime(isoString) {
    if (!isoString) return '-';
    try {
        const then = new Date(isoString);
        const now = new Date();
        const seconds = Math.floor((now - then) / 1000);

        if (seconds < 0) return 'just now';
        if (seconds < 60) return `${seconds}s ago`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        return `${Math.floor(seconds / 86400)}d ago`;
    } catch (err) {
        return isoString;
    }
}

// Format duration (e.g., "2h 30m")
function formatDuration(seconds) {
    if (seconds < 0) return '0s';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
        if (minutes > 0) {
            return `${hours}h ${minutes}m`;
        }
        return `${hours}h`;
    }
    if (minutes > 0) {
        if (secs > 0) {
            return `${minutes}m ${secs}s`;
        }
        return `${minutes}m`;
    }
    return `${secs}s`;
}

// Shorten container ID for display
function shortenId(id) {
    if (!id) return '-';
    return id.length > 12 ? id.substring(0, 12) + '...' : id;
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Show error message
function showError(elementId, message) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `<tr><td colspan="999" style="color: #dc2626; text-align: center;">${escapeHtml(
            message
        )}</td></tr>`;
    }
}

// Auto-refresh management
function startAutoRefresh() {
    if (timerId) {
        clearInterval(timerId);
        timerId = null;
    }
    if (autoRefresh) {
        timerId = setInterval(refreshAll, refreshInterval);
    }
}

// Stop auto-refresh
function stopAutoRefresh() {
    if (timerId) {
        clearInterval(timerId);
        timerId = null;
    }
}

// Auto-initialize if on dashboard page
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDashboard);
} else {
    initDashboard();
}
