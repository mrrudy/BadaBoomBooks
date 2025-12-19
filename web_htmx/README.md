# BadaBoomBooks Web Interface - HTMX Edition

Modern web-based UI for BadaBoomBooks audiobook organization, built with **Flask + HTMX + DaisyUI**.

## Features

- **Mobile-responsive design** with DaisyUI components
- **Real-time progress tracking** via HTMX polling
- **Parallel processing** using existing QueueManager and Huey workers
- **File browser** with Windows drive detection and audiobook folder identification
- **LLM-powered candidate selection** with 5-minute connection caching
- **Task management** with failed task retry and completed task history
- **No JavaScript frameworks** - simple HTMX-based interactivity

## Architecture

This web interface integrates with the existing BadaBoomBooks parallel processing system:

- **QueueManager** (`src/queue_manager.py`) - Database-backed job/task management
- **Huey workers** - Parallel audiobook processing (4 workers by default)
- **SQLite database** (`badaboombooksqueue.db`) - Persistent task queue
- **HTMX polling** - Real-time UI updates every 2 seconds

### Key Components

```
web_htmx/
├── app.py                     # Flask application
├── requirements.txt           # Python dependencies
├── routes/
│   ├── browse.py             # File browser endpoints
│   ├── scan.py               # Scan planning & job creation
│   ├── tasks.py              # Task management endpoints
│   └── llm.py                # LLM connection testing
├── state/
│   └── cache.py              # LLM connection cache (5min TTL)
├── templates/
│   ├── base.html             # Base layout with HTMX + DaisyUI
│   ├── index.html            # Main page
│   └── partials/             # HTMX partial templates
└── static/
    └── css/custom.css        # Custom styles
```

## Installation

### Prerequisites

1. Python 3.8+
2. BadaBoomBooks core dependencies installed
3. Chrome/Chromium (for Selenium scraping)

### Setup

1. **Navigate to web_htmx directory:**
```bash
cd web_htmx
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure environment (optional):**

Create `.env` file in project root for LLM support:
```
LLM_API_KEY=your_key_here
LLM_MODEL=gpt-4
OPENAI_BASE_URL=https://api.openai.com/v1  # Optional for local models
```

4. **Run the application:**
```bash
python app.py
```

5. **Open browser:**
```
http://localhost:5000
```

## Usage

### Section 1: Scan Planning

1. **Select Folders:**
   - Click "Browse & Select Folders"
   - Navigate through drives/folders
   - Click on audiobook folders (marked with 🎧) to select
   - Close modal when done

2. **Configure Actions:**
   - Enable "Dry Run" to preview without changes
   - Check actions: Flatten, Rename, OPF, ID3 Tags, etc.
   - Choose operation mode: In-place, Copy, or Move
   - Set output directory if copying/moving

3. **Search Options:**
   - Auto-search is always enabled
   - Enable "Use LLM" for intelligent candidate selection
   - Adjust search limits and worker count
   - Test LLM connection before using

4. **Start Processing:**
   - Click "Start Processing"
   - Form validates before submission
   - Job created and workers started automatically

### Section 3: Task Management

#### Current Tasks
- Shows running and pending tasks
- Auto-updates every 2 seconds
- Displays progress bar and worker info
- Cancel button to stop job

#### Failed Tasks (Expandable)
- Lists tasks that failed with error messages
- "Retry" button populates form with failed folder
- Review settings and resubmit

#### Completed Tasks (Expandable)
- Paginated history of successful tasks
- Shows completion time and duration

## Configuration

### Always Enforced Flags

These are automatically set in web mode:
- `--auto-search` - Always enabled
- `--yolo` - Auto-accepts prompts
- `--no-resume` - Always starts fresh

### Default Settings

- `--from-opf` - Checked by default (user can uncheck)
- Workers: 4 parallel workers
- Search limit: 5 results
- Download limit: 3 pages
- Search delay: 2.0 seconds

### Form Validation

- At least one folder must be selected
- `--force-refresh` requires `--opf` and `--from-opf`
- `--llm-select` requires LLM connection available
- Numeric inputs validated (search limit, workers, etc.)

## Technical Details

### Database Integration

The web interface uses the existing `badaboombooksqueue.db` database:

**Jobs Table:**
- One row per form submission
- Tracks status: pending → planning → processing → completed/failed
- Stores serialized ProcessingArgs

**Tasks Table:**
- One row per audiobook folder
- Status: pending → running → completed/failed
- Tracks worker assignment and retry count

### State Management

**Database as Source of Truth:**
- No in-memory state (except LLM cache)
- All progress tracked in SQLite
- Supports multiple concurrent users via `user_id`
- Web UI polls database for updates

**LLM Connection Cache:**
- Singleton cache with 5-minute TTL
- Thread-safe for concurrent requests
- Manual bypass via "Test LLM Connection" button

### Real-Time Updates

**HTMX Polling Strategy:**
```html
<div hx-get="/tasks/current?job_id={{job_id}}"
     hx-trigger="load, every 2s"
     hx-swap="innerHTML">
</div>
```

- Current tasks: Poll every 2 seconds
- Failed tasks: Poll every 5 seconds
- Completed tasks: Load once (expandable)
- No WebSockets or SSE needed

### Background Processing

When user clicks "Start Processing":

1. Form data converted to `ProcessingArgs`
2. Job created in database via `QueueManager.create_job()`
3. Tasks created (one per folder) via `QueueManager.create_task()`
4. Background thread started with N workers
5. Workers process tasks in parallel using Huey
6. Database updated by workers as tasks complete
7. Web UI polls database to show progress

## Mobile Responsiveness

### Breakpoints (Tailwind/DaisyUI)

- **Desktop (lg):** 3-column grid (Section 1 left, Section 3 right)
- **Tablet (md):** 2-column grid
- **Mobile (sm):** 1-column stack

### Touch Targets

All interactive elements meet 48x48px minimum:
- Buttons: 48px height
- Checkboxes: 24x24px with padding
- File items: 56px height

### Modal Behavior

- File browser modal: Full-screen on mobile
- DaisyUI modals auto-adapt to viewport
- Scrollable containers with custom scrollbars

## Troubleshooting

### LLM Connection Issues

1. Check `.env` file configuration
2. Test connection: Click "Test LLM Connection"
3. Cache expires after 5 minutes
4. Disable LLM select if unavailable

### Workers Not Starting

1. Check database file permissions
2. Verify `QueueManager` imports correctly
3. Check `debug.log` for errors
4. Ensure Huey is installed: `pip install huey`

### File Browser Issues

**Windows:**
- Inaccessible drives shown with lock icon
- Requires permission for network drives
- Trailing backslash handled correctly

**Unix:**
- Starts from root `/`
- Permission errors shown inline

### Database Isolation

Tests use isolated databases:
- Set `BADABOOMBOOKS_DB_PATH` environment variable
- Production database never touched by tests
- Tests can run while app is running

## Development

### Adding New Routes

1. Create blueprint in `routes/new_feature.py`
2. Register in `app.py`: `app.register_blueprint(new_feature.bp)`
3. Create partial template in `templates/partials/`
4. Add HTMX attributes for dynamic loading

### Custom Styling

Edit `static/css/custom.css`:
- Dry-run visual feedback (opacity/saturation)
- Status badge colors
- Scrollable containers
- Touch target sizes

### Testing

**Manual testing checklist:**
- [ ] File browser: Windows drives, navigation, selection
- [ ] Form validation: All dependency rules enforced
- [ ] LLM testing: Connection test, cache, badge updates
- [ ] Job submission: Creates job/tasks, starts workers
- [ ] Task display: Progress updates, polling works
- [ ] Failed retry: Populates form correctly
- [ ] Mobile: Responsive layout, touch targets, modals

**Running automated tests:**
```bash
# From project root
python -m pytest src/tests/ -v
```

## Comparison: Old vs New Web Interface

| Feature | Old (web/) | New (web_htmx/) |
|---------|-----------|-----------------|
| Framework | Flask-SocketIO | Flask + HTMX |
| Real-time | WebSocket | Polling (2s) |
| State | In-memory | Database |
| CSS | Bootstrap | DaisyUI |
| JS | Vanilla classes | Minimal HTMX |
| Mobile | Basic responsive | Fully optimized |
| Workers | Custom system | Existing QueueManager |
| Resume | Complex logic | Disabled (--no-resume) |

## Performance

- **Polling overhead:** 2-second interval, lightweight queries
- **Database:** SQLite handles concurrent reads/writes
- **Workers:** 4 default (adjustable 1-16)
- **LLM cache:** Reduces API calls by 99% (5min TTL)
- **HTMX:** ~14KB gzipped, no build step needed

## Security

- **Secret key:** Auto-generated per session (or set via env)
- **Session cookies:** HttpOnly, secure in production
- **File browser:** Permission checks on all path access
- **SQL injection:** Protected by parameterized queries
- **CSRF:** Not implemented (add Flask-WTF for production)

## Production Deployment

### Gunicorn (Linux)

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Waitress (Windows)

```bash
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name badaboomboks.example.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## License

Same as BadaBoomBooks parent project.

## Support

For issues or questions:
- File an issue on GitHub
- Check main project README
- Review CLAUDE.md for development guidelines
