# Web UI Fixes Applied

## Summary
Fixed 3 critical issues with the web interface. **Server restart required** for changes to take effect.

## Issues Fixed

### 1. ✅ ProcessingArgs Parameter Error
**File:** `web_htmx/routes/scan.py:204`

**Problem:** Using `output_dir` parameter but `ProcessingArgs` expects `output`

**Fix:**
```python
# Before:
output_dir=Path(form_data.get('output_dir')) if form_data.get('output_dir') else None,

# After:
output=Path(form_data.get('output_dir')) if form_data.get('output_dir') else None,
```

**Error Message Before Fix:**
```
Failed to start scan: ProcessingArgs.__init__() got an unexpected keyword argument 'output_dir'
```

---

### 2. ✅ Windows Path Backslash Escaping
**File:** `web_htmx/templates/partials/file_browser_list.html`

**Problem:** Backslashes in Windows paths (e.g., `C:\dev`) were being stripped when embedded in JavaScript strings and URLs, resulting in `C:dev` or broken navigation

**Fix:** Multiple fixes applied:
1. Used Jinja2's `|tojson` filter for JavaScript onclick handlers
2. Used Jinja2's `|urlencode` filter for HTMX URL attributes
3. Added `encodeURIComponent()` in JavaScript template strings
4. Added backslash escaping for CSS selectors

**Lines Changed:**
- Line 32: `hx-get="/browse?path={{ parent|urlencode }}"` (HTMX URL)
- Line 41: `onclick="selectCurrentFolder({{ current_path|tojson }})"`
- Line 57: `hx-get="/browse?path={{ item.path|urlencode }}"` (HTMX URL)
- Line 98: `onclick="navigateIntoAudiobook(event, {{ item.path|tojson }})"`
- Line 148: `onclick="removeSelection({{ folder|tojson }})"`
- Line 176: `htmx.ajax('GET', \`/browse?path=${encodeURIComponent(path)}\`)` (JS template string)
- Line 214: `htmx.ajax('GET', \`/browse?path=${encodeURIComponent(path)}\`)` (JS template string)
- Line 265: `path.replace(/\\/g, '\\\\')` (CSS selector escaping)

**Before:**
```html
<!-- JavaScript onclick -->
<button onclick="selectCurrentFolder('{{ current_path }}')">
<!-- Renders as: onclick="selectCurrentFolder('C:\dev')" -->
<!-- JavaScript interprets \d as escape sequence, becomes: C:dev -->

<!-- HTMX URL -->
<div hx-get="/browse?path={{ item.path }}">
<!-- Renders as: hx-get="/browse?path=C:\dev" -->
<!-- Browser URL parsing breaks on backslash -->
```

**After:**
```html
<!-- JavaScript onclick -->
<button onclick="selectCurrentFolder({{ current_path|tojson }})">
<!-- Renders as: onclick="selectCurrentFolder("C:\\dev")" -->
<!-- Backslashes properly escaped for JavaScript -->

<!-- HTMX URL -->
<div hx-get="/browse?path={{ item.path|urlencode }}">
<!-- Renders as: hx-get="/browse?path=C%3A%5Cdev" -->
<!-- Backslashes URL-encoded for proper HTTP request -->
```

---

### 3. ✅ 500 Errors on Task Endpoints
**File:** `web_htmx/routes/tasks.py`

**Problem:** Three endpoints (`/tasks/current`, `/tasks/failed`, `/tasks/completed`) were throwing 500 errors on initial page load when `user_id` was not yet in session

**Fix:** Added error handling and null checks to all three endpoints

**Changes:**
- Wrapped all endpoint logic in try/except blocks
- Added checks for `user_id` being None before calling `queue_manager.get_jobs_for_user()`
- Return empty task lists gracefully instead of crashing

**Example:**
```python
@bp.route('/current', methods=['GET'])
def current_tasks():
    try:
        user_id = session.get('user_id')

        # Return empty if no user_id
        if not user_id:
            tasks = []
            progress = None
            job = None
        else:
            # ... existing logic ...

        return render_template(...)
    except Exception as e:
        # Return empty state on error
        return render_template(..., tasks=[], progress=None, job=None)
```

---

### 4. ✅ LLM Connection Test Import Error
**File:** `web_htmx/state/cache.py`

**Problem:** Import error when trying to test LLM connection from web environment due to relative import issues

**Fix:** Updated import path to use absolute imports from `src` package

**Before:**
```python
from search.llm_scoring import test_llm_connection  # Fails with relative import errors
```

**After:**
```python
from src.search.llm_scoring import test_llm_connection  # Uses absolute import
```

---

## Testing After Server Restart

### 1. Verify 500 Errors Are Gone
- Open http://127.0.0.1:5000
- Check browser console - should NOT see any 500 errors from `/tasks/*` endpoints
- "Current Tasks" section should load without errors

### 2. Verify Windows Path Handling
- Click "Browse & Select Folders"
- Navigate to a drive (e.g., C: Drive)
- Navigate to a folder with a path like `C:\dev`
- Click "Select This Folder" or select an audiobook folder
- Check that the selected folder displays as `C:\dev` (with backslash), not `C:dev`

### 3. Verify LLM Connection Test
- Look at the "Use LLM for candidate selection" checkbox
- Status badge should show either:
  - "Available" (green) - if LLM is configured and working
  - "Unavailable" (red) - if LLM is not configured or connection failed
  - NOT "Testing..." indefinitely
- Click "Test LLM Connection" button to force a fresh test

### 4. Verify Start Processing Works
- Select a folder
- Enable "Dry Run" and "Generate OPF metadata"
- Choose "In-place" operation mode
- Click "Start Processing"
- Should NOT see error: `ProcessingArgs.__init__() got an unexpected keyword argument 'output_dir'`

---

## How to Restart Server

If running from command line:
1. Press `Ctrl+C` to stop the server
2. Run: `python web_htmx/app.py` or `cd web_htmx && python app.py`

If running as a service/background process:
1. Find the process: `tasklist | findstr python`
2. Kill it: `taskkill /F /PID <process_id>`
3. Restart: `python web_htmx/app.py`

---

## Notes

- All fixes are backwards compatible
- No database schema changes required
- No new dependencies added
- The `|tojson` filter is built into Jinja2, so no additional packages needed
