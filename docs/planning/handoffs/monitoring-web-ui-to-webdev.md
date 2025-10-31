# Handoff: Monitoring Web UI Implementation

**From**: Strategic Planner
**To**: Web Developer
**Date**: 2025-10-31
**Priority**: Medium
**Estimated Effort**: 1-2 days

---

## Executive Summary

Implement a web-based dashboard for the koji-adjutant monitoring API. The dashboard will display real-time worker status, active tasks, containers, and logs. Use minimal JavaScript, Jinja2 templates, and Flask integration.

## Context

The koji-adjutant monitoring server currently provides a REST API at `/api/v1/*` with comprehensive operational data. However, operators must use curl or API clients to view this data. We need a web UI that makes monitoring intuitive and accessible.

**Current State:**
- ✅ REST API fully implemented (`koji_adjutant/monitoring/server.py`)
- ✅ Endpoints for status, tasks, containers, and logs
- ✅ JSON responses with structured data
- ✅ Health check endpoint at `/api/v1/status`
- ❌ No web UI (operators use curl)

**Desired State:**
- ✅ Web dashboard at `http://localhost:8080/`
- ✅ Real-time updates via JavaScript polling
- ✅ Clean, responsive design
- ✅ Task and container detail pages
- ✅ Log viewer for active tasks

## Problem Statement

Operators need to monitor koji-adjutant workers but currently have no visual interface. Checking worker status requires:

```bash
# Current workflow (manual)
curl http://localhost:8080/api/v1/status | jq
curl http://localhost:8080/api/v1/tasks | jq
curl http://localhost:8080/api/v1/containers | jq
```

This is cumbersome for operational monitoring, especially when tracking multiple workers or debugging build issues.

## Requirements

### Functional Requirements

1. **Dashboard Page** (`/`)
   - Worker status overview (ID, uptime, health)
   - Capacity meter (active_tasks / capacity)
   - Metrics cards (active tasks, containers, completed today)
   - Active tasks table with auto-refresh
   - Active containers table with auto-refresh
   - Auto-refresh toggle and interval control

2. **Task Details Page** (`/tasks/<task_id>`)
   - Full task information
   - Associated container details
   - Real-time log tail (last 100 lines)
   - Progress messages
   - Auto-refresh while task is running

3. **Container Details Page** (`/containers/<container_id>`)
   - Container spec (command, workdir, user)
   - Resource limits (memory, CPUs)
   - Mounts information
   - Link to associated task

### Non-Functional Requirements

1. **Performance**
   - Page load < 1 second
   - Dashboard auto-refresh every 5 seconds
   - Log viewer auto-refresh every 2 seconds
   - Minimal bandwidth (fetch only JSON, no large assets)

2. **Usability**
   - Responsive design (mobile, tablet, desktop)
   - Clear status indicators (color-coded badges)
   - Relative time displays ("5m ago" vs ISO timestamps)
   - Keyboard navigation support

3. **Technology**
   - Vanilla JavaScript (no frameworks)
   - Flask + Jinja2 (server-side rendering)
   - Single CSS file (~300-500 lines)
   - Single JS file (~200-400 lines)
   - No build step or npm dependencies

## API Reference

All endpoints are already implemented in `koji_adjutant/monitoring/server.py`.

### GET /api/v1/status

**Response:**
```json
{
  "worker_id": "build-worker-1",
  "uptime_seconds": 3600,
  "status": "healthy",
  "capacity": 4,
  "active_tasks": 2,
  "containers_active": 2,
  "tasks_completed_today": 15,
  "last_task_time": "2025-10-31T12:34:56Z"
}
```

### GET /api/v1/tasks

**Response:**
```json
{
  "tasks": [
    {
      "task_id": 12345,
      "type": "buildArch",
      "status": "running",
      "arch": "x86_64",
      "tag": "f39-build",
      "started_at": "2025-10-31T12:30:00Z",
      "container_id": "abc123..."
    }
  ],
  "total": 1
}
```

### GET /api/v1/tasks/<task_id>

**Response:**
```json
{
  "task_id": 12345,
  "type": "buildArch",
  "status": "running",
  "arch": "x86_64",
  "tag": "f39-build",
  "srpm": "mypackage-1.0-1.src.rpm",
  "started_at": "2025-10-31T12:30:00Z",
  "finished_at": null,
  "container_id": "abc123...",
  "log_path": "/mnt/koji/work/tasks/12345/build.log",
  "progress": "Building RPM packages..."
}
```

### GET /api/v1/tasks/<task_id>/logs?tail=100

**Response:**
```json
{
  "task_id": 12345,
  "lines": [
    "Building package...",
    "Compiling sources...",
    "Creating RPM..."
  ],
  "tail": 100
}
```

### GET /api/v1/containers

**Response:**
```json
{
  "containers": [
    {
      "container_id": "abc123...",
      "task_id": 12345,
      "image": "docker.io/almalinux/9-minimal",
      "status": "running",
      "created_at": "2025-10-31T12:29:55Z",
      "started_at": "2025-10-31T12:30:00Z"
    }
  ],
  "total": 1
}
```

### GET /api/v1/containers/<container_id>

**Response:**
```json
{
  "container_id": "abc123...",
  "task_id": 12345,
  "image": "docker.io/almalinux/9-minimal",
  "status": "running",
  "spec": {
    "command": ["rpmbuild", "-ba", "package.spec"],
    "workdir": "/builddir",
    "user": "mockbuild"
  },
  "mounts": [
    {
      "source": "/mnt/koji",
      "target": "/mnt/koji",
      "read_only": false
    }
  ],
  "resource_limits": {
    "memory_bytes": 4294967296,
    "cpus": 2.0
  },
  "created_at": "2025-10-31T12:29:55Z",
  "started_at": "2025-10-31T12:30:00Z",
  "finished_at": null
}
```

## Implementation Plan

### Phase 1: Flask Integration (1-2 hours)

**Goal**: Set up Flask alongside existing HTTP server

**Tasks:**
1. Create `koji_adjutant/web/` module structure
2. Create Flask Blueprint for web routes
3. Modify `monitoring/server.py` to serve Flask app
4. Set up template and static directories

**Files to Create:**
- `koji_adjutant/web/__init__.py` - Blueprint definition
- `koji_adjutant/web/routes.py` - Web route handlers
- `koji_adjutant/web/templates/` - Template directory
- `koji_adjutant/web/static/css/` - CSS directory
- `koji_adjutant/web/static/js/` - JavaScript directory

**Files to Modify:**
- `koji_adjutant/monitoring/server.py` - Add Flask app

**Acceptance:**
- Flask app starts on port 8080
- Root route `/` returns "Dashboard coming soon"
- API routes `/api/v1/*` still work

### Phase 2: Base Template (30 minutes)

**Goal**: Create reusable base template with header/footer

**Tasks:**
1. Create `base.html` with document structure
2. Add responsive viewport meta tags
3. Include CSS and JS references
4. Create header with worker ID and nav
5. Create footer with attribution

**File to Create:**
- `koji_adjutant/web/templates/base.html`

**Template Structure:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Koji Adjutant Monitor{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
    <header>
        <h1>Koji Adjutant Monitor</h1>
        <nav>
            <a href="/">Dashboard</a>
        </nav>
    </header>
    <main>
        {% block content %}{% endblock %}
    </main>
    <script src="{{ url_for('static', filename='js/dashboard.js') }}"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

**Acceptance:**
- Base template renders without errors
- CSS and JS assets load correctly
- Responsive viewport configured

### Phase 3: Dashboard Template (1-2 hours)

**Goal**: Create main dashboard page with metrics and tables

**Tasks:**
1. Create `dashboard.html` extending `base.html`
2. Add status section (worker ID, uptime, health badge)
3. Add metrics cards section (4 cards in grid)
4. Add tasks table with headers and empty body
5. Add containers table with headers and empty body
6. Add auto-refresh controls (toggle, interval selector)
7. Add loading placeholders

**File to Create:**
- `koji_adjutant/web/templates/dashboard.html`

**Template Sections:**
```html
{% extends "base.html" %}

{% block content %}
<!-- Status Section -->
<section class="status-section">
    <h2 id="worker-id">Worker: ...</h2>
    <span id="status-badge" class="status-badge">...</span>
    <p>Uptime: <span id="uptime">...</span></p>
</section>

<!-- Metrics Cards -->
<section class="metrics-grid">
    <div class="metric-card">
        <h3>Active Tasks</h3>
        <p class="metric-value" id="active-tasks">-</p>
    </div>
    <div class="metric-card">
        <h3>Active Containers</h3>
        <p class="metric-value" id="active-containers">-</p>
    </div>
    <div class="metric-card">
        <h3>Completed Today</h3>
        <p class="metric-value" id="completed-today">-</p>
    </div>
    <div class="metric-card">
        <h3>Last Task</h3>
        <p class="metric-value" id="last-task-time">-</p>
    </div>
</section>

<!-- Tasks Table -->
<section class="table-section">
    <h2>Active Tasks</h2>
    <table id="tasks-table">
        <thead>
            <tr>
                <th>Task ID</th>
                <th>Type</th>
                <th>Arch</th>
                <th>Tag</th>
                <th>Status</th>
                <th>Duration</th>
            </tr>
        </thead>
        <tbody id="tasks-tbody">
            <tr><td colspan="6">Loading...</td></tr>
        </tbody>
    </table>
</section>

<!-- Containers Table -->
<section class="table-section">
    <h2>Active Containers</h2>
    <table id="containers-table">
        <thead>
            <tr>
                <th>Container ID</th>
                <th>Task ID</th>
                <th>Image</th>
                <th>Status</th>
                <th>Uptime</th>
            </tr>
        </thead>
        <tbody id="containers-tbody">
            <tr><td colspan="5">Loading...</td></tr>
        </tbody>
    </table>
</section>

<!-- Auto-refresh Controls -->
<section class="controls-section">
    <label>
        <input type="checkbox" id="auto-refresh-toggle" checked>
        Auto-refresh
    </label>
    <label>
        Interval:
        <select id="refresh-interval">
            <option value="2000">2s</option>
            <option value="5000" selected>5s</option>
            <option value="10000">10s</option>
            <option value="30000">30s</option>
        </select>
    </label>
</section>
{% endblock %}

{% block scripts %}
<script>
    // Initialize dashboard auto-refresh
    window.addEventListener('DOMContentLoaded', () => {
        initDashboard();
    });
</script>
{% endblock %}
```

**Acceptance:**
- Dashboard renders with all sections
- Tables show loading state initially
- Controls are visible and functional

### Phase 4: CSS Styling (2-3 hours)

**Goal**: Create responsive, clean stylesheet

**Tasks:**
1. Create `static/css/style.css`
2. Add reset/normalize styles
3. Style header and navigation
4. Style metrics cards grid (responsive)
5. Style tables (hover, striping)
6. Style status badges (color-coded)
7. Add responsive breakpoints
8. Add loading states and transitions

**File to Create:**
- `koji_adjutant/web/static/css/style.css`

**Key Styles:**

```css
/* Reset and base */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    line-height: 1.6;
    color: #1f2937;
    background: #f9fafb;
}

/* Header */
header {
    background: #1f2937;
    color: white;
    padding: 1rem 2rem;
}

/* Metrics Grid */
.metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin: 2rem 0;
}

.metric-card {
    background: white;
    padding: 1.5rem;
    border-radius: 0.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

/* Status Badges */
.status-badge {
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.875rem;
    font-weight: 500;
}

.status-healthy {
    background: #dcfce7;
    color: #15803d;
}

.status-running {
    background: #dbeafe;
    color: #1e40af;
}

.status-completed {
    background: #dcfce7;
    color: #15803d;
}

.status-failed {
    background: #fee2e2;
    color: #991b1b;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    background: white;
    border-radius: 0.5rem;
    overflow: hidden;
}

thead {
    background: #f3f4f6;
}

th, td {
    padding: 0.75rem;
    text-align: left;
}

tbody tr:hover {
    background: #f9fafb;
}

/* Responsive */
@media (max-width: 768px) {
    .metrics-grid {
        grid-template-columns: 1fr;
    }

    table {
        font-size: 0.875rem;
    }
}
```

**Acceptance:**
- Clean, modern appearance
- Responsive on mobile (375px)
- Responsive on tablet (768px)
- Responsive on desktop (1920px)
- Status badges color-coded correctly

### Phase 5: JavaScript Implementation (2-3 hours)

**Goal**: Implement API polling and DOM updates

**Tasks:**
1. Create `static/js/dashboard.js`
2. Implement status fetching and display
3. Implement tasks fetching and table updates
4. Implement containers fetching and table updates
5. Add auto-refresh logic with controls
6. Add relative time formatting
7. Add error handling and retries
8. Add click handlers for links

**File to Create:**
- `koji_adjutant/web/static/js/dashboard.js`

**Key Functions:**

```javascript
// Global state
let autoRefresh = true;
let refreshInterval = 5000;
let timerId = null;

// Initialize dashboard
function initDashboard() {
    // Initial load
    refreshAll();

    // Set up auto-refresh
    startAutoRefresh();

    // Set up controls
    document.getElementById('auto-refresh-toggle').addEventListener('change', (e) => {
        autoRefresh = e.target.checked;
        startAutoRefresh();
    });

    document.getElementById('refresh-interval').addEventListener('change', (e) => {
        refreshInterval = parseInt(e.target.value);
        startAutoRefresh();
    });
}

// Refresh all data
function refreshAll() {
    fetchStatus();
    fetchTasks();
    fetchContainers();
}

// Fetch status
async function fetchStatus() {
    try {
        const response = await fetch('/api/v1/status');
        const data = await response.json();
        updateStatus(data);
    } catch (err) {
        console.error('Failed to fetch status:', err);
    }
}

// Update status display
function updateStatus(data) {
    document.getElementById('worker-id').textContent = `Worker: ${data.worker_id}`;

    const badge = document.getElementById('status-badge');
    badge.textContent = data.status;
    badge.className = `status-badge status-${data.status}`;

    document.getElementById('uptime').textContent = formatDuration(data.uptime_seconds);
    document.getElementById('active-tasks').textContent = `${data.active_tasks} / ${data.capacity}`;
    document.getElementById('active-containers').textContent = data.containers_active;
    document.getElementById('completed-today').textContent = data.tasks_completed_today;
    document.getElementById('last-task-time').textContent =
        data.last_task_time ? formatRelativeTime(data.last_task_time) : 'Never';
}

// Fetch tasks
async function fetchTasks() {
    try {
        const response = await fetch('/api/v1/tasks');
        const data = await response.json();
        updateTasksTable(data.tasks);
    } catch (err) {
        console.error('Failed to fetch tasks:', err);
    }
}

// Update tasks table
function updateTasksTable(tasks) {
    const tbody = document.getElementById('tasks-tbody');

    if (tasks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6">No active tasks</td></tr>';
        return;
    }

    tbody.innerHTML = tasks.map(task => `
        <tr>
            <td><a href="/tasks/${task.task_id}">${task.task_id}</a></td>
            <td>${task.type}</td>
            <td>${task.arch}</td>
            <td>${task.tag}</td>
            <td><span class="status-badge status-${task.status}">${task.status}</span></td>
            <td>${formatRelativeTime(task.started_at)}</td>
        </tr>
    `).join('');
}

// Format relative time
function formatRelativeTime(isoString) {
    const then = new Date(isoString);
    const now = new Date();
    const seconds = Math.floor((now - then) / 1000);

    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

// Format duration
function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) return `${hours}h ${minutes}m`;
    if (minutes > 0) return `${minutes}m ${secs}s`;
    return `${secs}s`;
}

// Auto-refresh management
function startAutoRefresh() {
    if (timerId) clearInterval(timerId);
    if (autoRefresh) {
        timerId = setInterval(refreshAll, refreshInterval);
    }
}
```

**Acceptance:**
- Dashboard loads data on page load
- Data refreshes automatically every 5 seconds
- Auto-refresh toggle works
- Interval selector updates refresh rate
- Relative times display correctly
- Tables update without flicker
- Links to task details work

### Phase 6: Task Details Page (1 hour)

**Goal**: Create task detail view with logs

**Tasks:**
1. Create `task_details.html` template
2. Add route handler in `routes.py`
3. Display task information
4. Display associated container info
5. Add log viewer with tail
6. Add auto-refresh for running tasks

**Files to Create/Modify:**
- `koji_adjutant/web/templates/task_details.html`
- `koji_adjutant/web/routes.py` (add `/tasks/<int:task_id>` route)

**Template Structure:**
```html
{% extends "base.html" %}

{% block content %}
<section>
    <h2>Task #<span id="task-id">{{ task_id }}</span></h2>
    <a href="/">← Back to Dashboard</a>
</section>

<section class="info-grid">
    <div class="info-card">
        <h3>Task Information</h3>
        <dl>
            <dt>Type:</dt><dd id="task-type">-</dd>
            <dt>Status:</dt><dd id="task-status">-</dd>
            <dt>Arch:</dt><dd id="task-arch">-</dd>
            <dt>Tag:</dt><dd id="task-tag">-</dd>
            <dt>SRPM:</dt><dd id="task-srpm">-</dd>
            <dt>Started:</dt><dd id="task-started">-</dd>
            <dt>Finished:</dt><dd id="task-finished">-</dd>
            <dt>Progress:</dt><dd id="task-progress">-</dd>
        </dl>
    </div>

    <div class="info-card">
        <h3>Container</h3>
        <dl>
            <dt>Container ID:</dt><dd id="container-id">-</dd>
            <dt>Image:</dt><dd id="container-image">-</dd>
        </dl>
        <a href="#" id="container-link">View Container Details</a>
    </div>
</section>

<section class="log-viewer">
    <h3>Build Log (last 100 lines)</h3>
    <button onclick="refreshLogs()">Refresh</button>
    <pre id="log-content">Loading logs...</pre>
</section>
{% endblock %}

{% block scripts %}
<script>
const taskId = {{ task_id }};
let logRefreshTimer = null;

async function fetchTaskDetails() {
    try {
        const response = await fetch(`/api/v1/tasks/${taskId}`);
        const data = await response.json();
        updateTaskDetails(data);

        // Auto-refresh logs if running
        if (data.status === 'running' && !logRefreshTimer) {
            logRefreshTimer = setInterval(fetchLogs, 2000);
        } else if (data.status !== 'running' && logRefreshTimer) {
            clearInterval(logRefreshTimer);
        }
    } catch (err) {
        console.error('Failed to fetch task details:', err);
    }
}

async function fetchLogs() {
    try {
        const response = await fetch(`/api/v1/tasks/${taskId}/logs?tail=100`);
        const data = await response.json();
        document.getElementById('log-content').textContent = data.lines.join('\n');
    } catch (err) {
        console.error('Failed to fetch logs:', err);
    }
}

function updateTaskDetails(data) {
    document.getElementById('task-type').textContent = data.type;
    document.getElementById('task-status').innerHTML =
        `<span class="status-badge status-${data.status}">${data.status}</span>`;
    document.getElementById('task-arch').textContent = data.arch || '-';
    document.getElementById('task-tag').textContent = data.tag || '-';
    document.getElementById('task-srpm').textContent = data.srpm || '-';
    document.getElementById('task-started').textContent =
        new Date(data.started_at).toLocaleString();
    document.getElementById('task-finished').textContent =
        data.finished_at ? new Date(data.finished_at).toLocaleString() : 'Running';
    document.getElementById('task-progress').textContent = data.progress || '-';

    if (data.container_id) {
        document.getElementById('container-id').textContent =
            data.container_id.substring(0, 12);
        document.getElementById('container-link').href =
            `/containers/${data.container_id}`;
    }
}

// Initialize
window.addEventListener('DOMContentLoaded', () => {
    fetchTaskDetails();
    fetchLogs();
});
</script>
{% endblock %}
```

**Acceptance:**
- Task details page loads correctly
- Task information displays
- Logs display (last 100 lines)
- Logs auto-refresh every 2 seconds for running tasks
- Link to container details works

### Phase 7: Container Details Page (45 minutes)

**Goal**: Create container detail view

**Tasks:**
1. Create `container_details.html` template
2. Add route handler in `routes.py`
3. Display container spec
4. Display resource limits
5. Display mounts
6. Link to associated task

**Files to Create/Modify:**
- `koji_adjutant/web/templates/container_details.html`
- `koji_adjutant/web/routes.py` (add `/containers/<string:container_id>` route)

**Template Structure:**
```html
{% extends "base.html" %}

{% block content %}
<section>
    <h2>Container: <span id="container-id">{{ container_id }}</span></h2>
    <a href="/">← Back to Dashboard</a>
</section>

<section class="info-grid">
    <div class="info-card">
        <h3>Container Spec</h3>
        <dl>
            <dt>Image:</dt><dd id="container-image">-</dd>
            <dt>Status:</dt><dd id="container-status">-</dd>
            <dt>Command:</dt><dd id="container-command">-</dd>
            <dt>Workdir:</dt><dd id="container-workdir">-</dd>
            <dt>User:</dt><dd id="container-user">-</dd>
            <dt>Created:</dt><dd id="container-created">-</dd>
            <dt>Started:</dt><dd id="container-started">-</dd>
        </dl>
        <a href="#" id="task-link">View Task Details</a>
    </div>

    <div class="info-card">
        <h3>Resources</h3>
        <dl>
            <dt>Memory Limit:</dt><dd id="memory-limit">-</dd>
            <dt>CPU Limit:</dt><dd id="cpu-limit">-</dd>
        </dl>

        <h3>Mounts</h3>
        <table id="mounts-table">
            <thead>
                <tr>
                    <th>Source</th>
                    <th>Target</th>
                    <th>RO</th>
                </tr>
            </thead>
            <tbody id="mounts-tbody">
                <tr><td colspan="3">Loading...</td></tr>
            </tbody>
        </table>
    </div>
</section>
{% endblock %}

{% block scripts %}
<script>
const containerId = "{{ container_id }}";

async function fetchContainerDetails() {
    try {
        const response = await fetch(`/api/v1/containers/${containerId}`);
        const data = await response.json();
        updateContainerDetails(data);
    } catch (err) {
        console.error('Failed to fetch container details:', err);
    }
}

function updateContainerDetails(data) {
    document.getElementById('container-image').textContent = data.image;
    document.getElementById('container-status').innerHTML =
        `<span class="status-badge status-${data.status}">${data.status}</span>`;
    document.getElementById('container-command').textContent =
        data.spec.command ? data.spec.command.join(' ') : '-';
    document.getElementById('container-workdir').textContent = data.spec.workdir || '-';
    document.getElementById('container-user').textContent = data.spec.user || '-';
    document.getElementById('container-created').textContent =
        new Date(data.created_at).toLocaleString();
    document.getElementById('container-started').textContent =
        data.started_at ? new Date(data.started_at).toLocaleString() : '-';

    // Resources
    document.getElementById('memory-limit').textContent =
        data.resource_limits.memory_bytes ?
        formatBytes(data.resource_limits.memory_bytes) : 'Unlimited';
    document.getElementById('cpu-limit').textContent =
        data.resource_limits.cpus || 'Unlimited';

    // Mounts
    const mountsTbody = document.getElementById('mounts-tbody');
    if (data.mounts.length === 0) {
        mountsTbody.innerHTML = '<tr><td colspan="3">No mounts</td></tr>';
    } else {
        mountsTbody.innerHTML = data.mounts.map(mount => `
            <tr>
                <td>${mount.source}</td>
                <td>${mount.target}</td>
                <td>${mount.read_only ? 'Yes' : 'No'}</td>
            </tr>
        `).join('');
    }

    // Task link
    if (data.task_id) {
        document.getElementById('task-link').href = `/tasks/${data.task_id}`;
    }
}

function formatBytes(bytes) {
    const gb = bytes / (1024 ** 3);
    if (gb >= 1) return `${gb.toFixed(2)} GB`;
    const mb = bytes / (1024 ** 2);
    return `${mb.toFixed(2)} MB`;
}

// Initialize
window.addEventListener('DOMContentLoaded', fetchContainerDetails);
</script>
{% endblock %}
```

**Acceptance:**
- Container details page loads correctly
- Container spec displays
- Resource limits show formatted values
- Mounts table populates
- Link to task details works

### Phase 8: Documentation (30 minutes)

**Goal**: Document the web UI

**Tasks:**
1. Create `docs/monitoring/web-ui.md`
2. Document architecture and endpoints
3. Add screenshots placeholders
4. Document configuration
5. Add troubleshooting section

**File to Create:**
- `docs/monitoring/web-ui.md`

**Acceptance:**
- Documentation is clear and complete
- Architecture is explained
- Examples are provided

## Testing Checklist

### Manual Testing

- [ ] **Dashboard loads** - Navigate to `http://localhost:8080/`
- [ ] **Metrics display** - Worker ID, uptime, capacity, etc.
- [ ] **Tasks table** - Shows active tasks with correct data
- [ ] **Containers table** - Shows active containers
- [ ] **Auto-refresh** - Data updates every 5 seconds
- [ ] **Toggle auto-refresh** - Can disable/enable
- [ ] **Change refresh interval** - Interval changes take effect
- [ ] **Task link** - Click task ID navigates to details
- [ ] **Task details** - Task information displays correctly
- [ ] **Task logs** - Logs display and auto-refresh
- [ ] **Container link** - Click container ID navigates to details
- [ ] **Container details** - Container information displays correctly
- [ ] **Back navigation** - Back links return to dashboard
- [ ] **Browser back** - Browser back button works
- [ ] **Responsive mobile** - Layout works on 375px width
- [ ] **Responsive tablet** - Layout works on 768px width
- [ ] **Responsive desktop** - Layout works on 1920px width
- [ ] **Status colors** - Badges show correct colors
- [ ] **Relative times** - Times display as "5m ago" etc.
- [ ] **No console errors** - Browser console is clean
- [ ] **Keyboard navigation** - Tab navigation works
- [ ] **404 handling** - Invalid URLs show errors gracefully

### Integration Testing with Koji-Boxed

1. **Start koji-boxed:**
   ```bash
   cd /home/siege/koji-boxed
   make up
   ```

2. **Open dashboard:**
   ```
   http://localhost:8080/
   ```

3. **Trigger a build:**
   ```bash
   koji build f39-candidate my-package.src.rpm
   ```

4. **Verify:**
   - Task appears in dashboard
   - Container appears in containers table
   - Task details page shows build progress
   - Logs update in real-time
   - Task completes and status updates

### Performance Testing

- [ ] **Page load time** - Dashboard loads in < 1 second
- [ ] **Refresh performance** - No lag during auto-refresh
- [ ] **Log updates** - Logs refresh smoothly
- [ ] **Memory usage** - No memory leaks during long sessions
- [ ] **Network traffic** - Minimal bandwidth usage

## Success Criteria

1. ✅ Dashboard displays real-time worker status
2. ✅ Task list updates automatically
3. ✅ Container list updates automatically
4. ✅ Task details page shows full information and logs
5. ✅ Container details page shows full information
6. ✅ Clean, responsive design works on all screen sizes
7. ✅ No JavaScript errors in console
8. ✅ Graceful handling of API errors
9. ✅ Auto-refresh can be toggled on/off
10. ✅ Minimal dependencies (no build step)
11. ✅ Works with koji-boxed integration

## Deliverables

1. ✅ `koji_adjutant/web/` module with Flask integration
2. ✅ `base.html` - Base template
3. ✅ `dashboard.html` - Main dashboard page
4. ✅ `task_details.html` - Task details page
5. ✅ `container_details.html` - Container details page
6. ✅ `static/css/style.css` - Stylesheet (~300-500 lines)
7. ✅ `static/js/dashboard.js` - JavaScript (~200-400 lines)
8. ✅ Modified `monitoring/server.py` - Flask integration
9. ✅ `docs/monitoring/web-ui.md` - Documentation

## Reference Files

**Review these files before starting:**
- `/home/siege/koji-adjutant/koji_adjutant/monitoring/server.py` - REST API implementation
- `/home/siege/koji-adjutant/koji_adjutant/monitoring/registry.py` - Data structures
- `/home/siege/koji-adjutant/.cursor/rules/006_web_developer.mdc` - Your role definition

**Koji-Boxed integration:**
- `/home/siege/koji-boxed/docker-compose.yml` - Port 8080 exposed
- `/home/siege/koji-boxed/services/koji-worker/` - Worker service
- `/home/siege/koji-boxed/ADJUTANT_INTEGRATION.md` - Integration guide

## Technical Constraints

1. **No external dependencies** - Use only Python standard library + Flask
2. **No build step** - No Webpack, npm, or bundling
3. **Single CSS file** - Keep all styles in one file
4. **Single JS file** - Keep all JavaScript in one file (or split by page if needed)
5. **Server-side rendering** - Templates rendered by Jinja2
6. **Progressive enhancement** - Works with JS disabled (graceful degradation)

## Tips

1. **Start simple** - Get basic routing working first
2. **Test incrementally** - Test each page as you build it
3. **Use browser DevTools** - Monitor network requests and console
4. **Check responsive design** - Use DevTools device emulation
5. **Profile performance** - Check for slow API calls or render issues
6. **Handle errors gracefully** - Show user-friendly messages
7. **Log to console** - Use `console.log()` for debugging
8. **Keep it minimal** - Resist the urge to add complexity

## Questions?

If you encounter issues or need clarification:

1. **API not responding** - Check if monitoring server is running
2. **Flask import errors** - Ensure Flask is installed in koji-adjutant venv
3. **Templates not found** - Verify template paths in Flask config
4. **Static assets 404** - Check static_folder path in Flask app
5. **CORS issues** - API and web UI are same-origin, should not occur
6. **Performance issues** - Reduce refresh intervals or optimize table rendering

---

## Ready to Begin?

You have everything you need:
- ✅ Complete API reference
- ✅ Detailed implementation plan
- ✅ Template examples
- ✅ CSS and JS patterns
- ✅ Testing checklist

**Start with Phase 1: Flask Integration** and work through each phase sequentially. Test each phase before moving to the next.

Good luck, Web Developer! 🚀
