# Koji-Adjutant Monitoring Web UI

## Overview

The koji-adjutant monitoring web UI provides a visual dashboard for monitoring worker status, active tasks, and containers in real-time. It is accessible at `http://localhost:8080/` when the monitoring server is running.

## Architecture

### Components

1. **Flask Application** (`koji_adjutant/web/`)
   - Web routes and template rendering
   - Integrated with existing monitoring HTTP server
   - Serves static assets (CSS, JavaScript)

2. **Templates** (`koji_adjutant/web/templates/`)
   - `base.html` - Base template with header/footer
   - `dashboard.html` - Main dashboard page
   - `task_details.html` - Task detail view with logs
   - `container_details.html` - Container detail view

3. **Static Assets** (`koji_adjutant/web/static/`)
   - `css/style.css` - Responsive stylesheet (~483 lines)
   - `js/dashboard.js` - JavaScript for API polling and DOM updates (~300 lines)

4. **Server Integration** (`koji_adjutant/monitoring/server.py`)
   - Routes API requests (`/api/v1/*`) to existing handlers
   - Routes web requests (non-API) to Flask WSGI application
   - Single HTTP server on port 8080

## Features

### Dashboard Page (`/`)

- **Worker Status Section**
  - Worker ID and status badge
  - Uptime display
  - Capacity indicator (active tasks / capacity)

- **Podman Health Section**
  - Podman connectivity status (healthy/unhealthy/unknown)
  - Socket path used for connection
  - Podman version and API version (when healthy)
  - Error details (when unhealthy)
  - Auto-refreshes with dashboard

- **Metrics Cards**
  - Active Tasks (with capacity ratio)
  - Active Containers count
  - Tasks Completed Today
  - Last Task Time (relative time)

- **Active Tasks Table**
  - Task ID, Type, Arch, Tag, Status, Started time
  - Clickable task IDs link to detail pages
  - Auto-refresh every 5 seconds (configurable)

- **Active Containers Table**
  - Container ID (shortened), Task ID, Image, Status, Started time
  - Clickable container IDs link to detail pages
  - Auto-refresh every 5 seconds (configurable)

- **Auto-refresh Controls**
  - Toggle auto-refresh on/off
  - Interval selector (2s, 5s, 10s, 30s)
  - Default: 5 seconds

### Task Details Page (`/tasks/<task_id>`)

- **Task Information**
  - Type, Status, Arch, Tag, SRPM
  - Started and Finished timestamps
  - Progress messages
  - Associated container information

- **Log Viewer**
  - Displays last 100 lines of build log
  - Auto-refresh every 2 seconds for running tasks
  - Manual refresh button
  - Scrollable pre-formatted log display

- **Navigation**
  - Back link to dashboard
  - Link to associated container details

### Container Details Page (`/containers/<container_id>`)

- **Container Spec**
  - Image, Status, Command, Workdir, User
  - Created, Started, Finished timestamps

- **Resources**
  - Memory limit (formatted: GB/MB/KB)
  - CPU limit

- **Mounts Table**
  - Source path, Target path, Read-only flag

- **Navigation**
  - Back link to dashboard
  - Link to associated task details

## API Integration

The web UI consumes the existing REST API endpoints:

- `GET /api/v1/status` - Worker status and metrics
  - Includes `podman` object with connectivity health:
    - `status`: "healthy", "unhealthy", or "unknown"
    - `message`: Status description
    - `socket`: Socket path used
    - `version`: Podman version (if healthy)
    - `api_version`: Podman API version (if healthy)
    - `error`: Error details (if unhealthy)
- `GET /api/v1/tasks` - List active tasks
- `GET /api/v1/tasks/<id>` - Task details
- `GET /api/v1/tasks/<id>/logs?tail=100` - Task logs (text/plain)
- `GET /api/v1/containers` - List active containers
- `GET /api/v1/containers/<id>` - Container details

All API calls use vanilla JavaScript `fetch()` with error handling.

## Technical Details

### Technology Stack

- **Backend**: Flask 3.0+ (Python 3.11+)
- **Templates**: Jinja2 (built into Flask)
- **Frontend**: Vanilla JavaScript (no frameworks)
- **Styling**: CSS3 with Grid/Flexbox
- **Server**: Integrated with existing ThreadingHTTPServer

### Dependencies

- Flask >= 3.0.0 (added to `setup.cfg`)
- Python 3.11+ (project standard)

### No Build Step

The web UI uses no build tools:
- No npm/node_modules
- No Webpack/bundlers
- No TypeScript compilation
- Direct serving of static files

### Responsive Design

- **Mobile**: 375px width, single-column layout
- **Tablet**: 768px width, 2-column grid
- **Desktop**: 1024px+ width, multi-column layout

Breakpoints defined in CSS:
- `@media (max-width: 768px)` - Tablet
- `@media (max-width: 480px)` - Mobile

### Auto-refresh Behavior

- **Dashboard**: 5 seconds default (configurable)
- **Task Details (logs)**: 2 seconds (only for running tasks)
- **Task Details (info)**: 5 seconds (only for running tasks)
- Auto-refresh stops when task completes

### Error Handling

- API errors display user-friendly messages
- Failed requests logged to browser console
- Graceful degradation when API unavailable
- Loading states during data fetch

## Usage

### Starting the Monitoring Server

The web UI is automatically available when the monitoring server starts:

```python
from koji_adjutant.monitoring import start_monitoring_server

server = start_monitoring_server(
    bind_address="127.0.0.1",
    port=8080,
    worker_id="build-worker-1"
)
```

### Accessing the Dashboard

1. Start koji-adjutant (monitoring enabled)
2. Open browser: `http://localhost:8080/`
3. Dashboard loads automatically
4. Data refreshes every 5 seconds

### Integration with Koji-Boxed

When running with koji-boxed:

1. Start koji-boxed: `make up`
2. Access dashboard at `http://localhost:8080/`
3. Monitor builds in real-time
4. View task logs during builds

## Configuration

No additional configuration required. The web UI uses the same monitoring server configuration:

- Bind address: `adjutant_monitoring_bind()` from config
- Port: Parsed from bind string (default: 8080)
- Worker ID: Hostname

## Development

### File Structure

```
koji_adjutant/
├── web/
│   ├── __init__.py          # Flask app factory
│   ├── routes.py            # Web route handlers
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── task_details.html
│   │   └── container_details.html
│   └── static/
│       ├── css/
│       │   └── style.css
│       └── js/
│           └── dashboard.js
└── monitoring/
    └── server.py            # HTTP server with Flask integration
```

### Testing

Manual testing checklist:

- [ ] Dashboard loads without errors
- [ ] Metrics cards display correct data
- [ ] Task list shows active tasks
- [ ] Container list shows active containers
- [ ] Auto-refresh updates data correctly
- [ ] Task details page displays full information
- [ ] Log viewer shows task logs
- [ ] Container details page displays full information
- [ ] Responsive layout works on mobile (375px)
- [ ] Responsive layout works on tablet (768px)
- [ ] Responsive layout works on desktop (1920px)
- [ ] Status badges display correct colors
- [ ] Relative times update (e.g., "5 minutes ago")
- [ ] Links between pages work correctly
- [ ] Browser back/forward buttons work
- [ ] No console errors or warnings
- [ ] Keyboard navigation works

### Troubleshooting

**Issue**: Dashboard shows "Loading..." indefinitely
- **Solution**: Check browser console for API errors. Verify monitoring server is running.

**Issue**: Flask import errors
- **Solution**: Install Flask: `pip install Flask>=3.0.0`

**Issue**: Templates not found
- **Solution**: Verify `koji_adjutant/web/templates/` directory exists and contains templates.

**Issue**: Static assets 404
- **Solution**: Verify `koji_adjutant/web/static/` directory exists with css/ and js/ subdirectories.

**Issue**: API requests fail
- **Solution**: Check monitoring server logs. Verify API endpoints return JSON.

**Issue**: Auto-refresh not working
- **Solution**: Check browser console for JavaScript errors. Verify `dashboard.js` is loaded.

## Performance

### Page Load
- Target: < 1 second
- Achieved by server-side rendering and minimal JavaScript

### Auto-refresh
- Dashboard: 5 seconds (configurable)
- Task logs: 2 seconds (running tasks only)
- Minimal bandwidth (JSON responses only)

### Network Usage
- Dashboard refresh: ~5-10 KB per request
- Log refresh: ~50-200 KB (depends on log size)
- Static assets: Loaded once, cached by browser

## Security Considerations

- **XSS Prevention**: All user-generated content is HTML-escaped
- **CSRF**: Not applicable (read-only monitoring)
- **CORS**: API endpoints allow CORS (`Access-Control-Allow-Origin: *`)
- **Authentication**: None (assumes network-level access control)

## Future Enhancements

Potential improvements:

- Charts/graphs for metrics over time
- Task filtering and search
- Export logs to file
- Real-time WebSocket updates (replace polling)
- Dark mode theme
- Task history view
- Container metrics (CPU/memory usage)

## References

- [Handoff Document](../planning/handoffs/monitoring-web-ui-to-webdev.md)
- [Web Developer Rules](../../.cursor/rules/006_web_developer.mdc)
- [Monitoring Server API](server.md)
- [Monitoring Registry](registry.md)
