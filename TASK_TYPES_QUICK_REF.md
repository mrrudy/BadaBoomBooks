# Task Types Quick Reference

## Regular Tasks vs User Input Tasks

### Regular Tasks (Autonomous Processing)

**Status:** `pending` → `running` → `completed`/`failed`/`skipped`

**Can be processed by:**
- ✅ Interactive workers (CLI with prompts)
- ✅ Non-interactive workers (`--yolo` batch processing)
- ✅ Web interface workers

**Examples:**
- Scraping metadata from URL
- Organizing files into folders
- Writing OPF files
- Tagging MP3 files
- Downloading cover images

**Database columns used:**
- `id`, `job_id`, `folder_path`, `url`, `status`
- `worker_id`, `retry_count`, `error`, `result_json`
- Standard workflow columns

---

### User Input Tasks (Interactive Only)

**Status:** `pending` → `running` → `waiting_for_user` → `pending` → `completed`

**Can be processed by:**
- ✅ Interactive workers (CLI with prompts)
- ✅ Web interface workers
- ❌ Non-interactive workers (`--yolo` - these skip waiting_for_user tasks)

**Examples:**
- LLM candidate confirmation
- Manual candidate selection
- Manual URL entry

**Database columns used:**
- All regular columns PLUS:
- `user_input_type` - Type of input needed
- `user_input_prompt` - Prompt text shown to user
- `user_input_options` - JSON array of options
- `user_input_context` - JSON object with book info, candidates, etc.

---

## Filtering Tasks by Worker Type

### Non-Interactive Worker (Batch Mode)

```python
# Only get tasks that can be processed autonomously
tasks = queue_manager.get_tasks_by_job(
    job_id=job_id,
    status=['pending']  # Excludes 'waiting_for_user'
)

# Process each task without user interaction
for task in tasks:
    process_task(task)  # No prompts, fully automated
```

**Command line:**
```bash
# These workers should filter for status=['pending'] only
python BadaBoomBooks.py --yolo --auto-search --opf -O "C:\Output" -R "C:\Input"
```

---

### Interactive Worker (CLI/Web)

```python
# Get both autonomous and user-input tasks
tasks = queue_manager.get_tasks_by_job(
    job_id=job_id,
    status=['pending', 'waiting_for_user']
)

for task in tasks:
    if task['status'] == 'waiting_for_user':
        # Handle user input
        response = prompt_user(task['user_input_prompt'])
        queue_manager.resume_task_from_user_input(
            task_id=task['id'],
            user_response=response
        )
    else:
        # Process normally
        process_task(task)
```

**Command line:**
```bash
# These workers can handle both task types
python BadaBoomBooks.py --auto-search --opf -O "C:\Output" -R "C:\Input"  # No --yolo
```

---

## Three Types of User Input

| Type | Where | When | Override | Worker Compatibility |
|------|-------|------|----------|---------------------|
| **llm_confirmation** | [auto_search.py:290](src/search/auto_search.py#L290) | LLM selected candidate, awaiting confirmation | `--yolo` | Interactive workers only |
| **manual_selection** | [auto_search.py:317](src/search/auto_search.py#L317) | Multiple candidates found, user must choose | `--yolo` (picks first) | Interactive workers only |
| **manual_url** | [manual_search.py:234](src/search/manual_search.py#L234) | Manual search mode requires URL | None | Interactive workers only |

---

## Task Lifecycle Examples

### Example 1: Fully Automated Task (No User Input)

```
1. Task created: status='pending', url='https://lubimyczytac.pl/...'
2. Worker picks up: status='running'
3. Scraping completes successfully
4. Files organized, metadata written
5. Task finishes: status='completed'
```

**Worker types that can handle:** All (interactive + non-interactive)

---

### Example 2: Task Requiring User Input

```
1. Task created: status='pending', url=None (no URL yet)
2. Worker picks up: status='running'
3. Auto-search finds 3 candidates
4. Worker marks waiting: status='waiting_for_user'
   - user_input_type='manual_selection'
   - user_input_prompt='Select [1-3], 0 to skip, or enter URL: '
   - user_input_options=['Candidate 1', 'Candidate 2', 'Candidate 3']
   - user_input_context={'book_info': {...}, 'candidates': [...]}
5. [TASK PAUSES - waiting in queue]
6. Interactive worker detects waiting task
7. Shows prompt to user, gets response: '1'
8. Worker resumes task: status='pending', url='https://...'
   - user_input_* fields cleared
9. Worker picks up again: status='running'
10. Scraping completes with selected URL
11. Task finishes: status='completed'
```

**Worker types that can handle:** Interactive only (CLI without --yolo, web interface)

**Worker types that skip:** Non-interactive (--yolo mode)

---

## How to Identify Task Type in Database

### Query for Autonomous Tasks Only

```sql
SELECT * FROM tasks
WHERE job_id = 'xyz-789'
  AND status = 'pending'
  AND user_input_type IS NULL
ORDER BY created_at;
```

### Query for Tasks Waiting for User

```sql
SELECT * FROM tasks
WHERE job_id = 'xyz-789'
  AND status = 'waiting_for_user'
ORDER BY created_at;
```

### Query for All Interactive Tasks (Current + Past)

```sql
SELECT * FROM tasks
WHERE job_id = 'xyz-789'
  AND (
    status = 'waiting_for_user'
    OR user_input_type IS NOT NULL
  )
ORDER BY created_at;
```

---

## Key Distinguishing Features

| Feature | Regular Task | User Input Task |
|---------|--------------|-----------------|
| **Status** | `pending`/`running`/`completed` | `waiting_for_user` (then resumes to `pending`) |
| **user_input_type** | `NULL` | `'llm_confirmation'`/`'manual_selection'`/`'manual_url'` |
| **user_input_prompt** | `NULL` | `'Select [1-3]:'` etc. |
| **user_input_options** | `NULL` | JSON array of choices |
| **user_input_context** | `NULL` | JSON object with book info |
| **Worker compatibility** | All workers | Interactive workers only |
| **URL field** | Set initially | Set after user responds |
| **Lifecycle** | Linear progression | Pauses for user, then resumes |

---

## Best Practices for Worker Developers

### ✅ DO

1. **Filter by status** when querying tasks
   - Non-interactive: `status=['pending']`
   - Interactive: `status=['pending', 'waiting_for_user']`

2. **Check status before processing**
   ```python
   if task['status'] == 'waiting_for_user':
       handle_user_input(task)
   else:
       process_normally(task)
   ```

3. **Use QueueManager methods**
   ```python
   # Mark waiting
   queue_manager.set_task_waiting_for_user(...)

   # Get waiting tasks
   waiting = queue_manager.get_tasks_waiting_for_user(job_id)

   # Resume after input
   queue_manager.resume_task_from_user_input(...)
   ```

4. **Clear user_input fields after processing** (default behavior)
   - Keeps database clean
   - Prevents confusion on retries

### ❌ DON'T

1. **Don't process waiting_for_user tasks in non-interactive workers**
   - They will fail (no way to get user input)

2. **Don't forget to resume tasks after getting input**
   - Tasks will remain stuck in `waiting_for_user` status

3. **Don't modify user_input fields directly**
   - Use `set_task_waiting_for_user()` and `resume_task_from_user_input()`

4. **Don't assume all tasks have URLs initially**
   - Some tasks get URLs from user input mid-processing

---

## Summary

**The key distinction:** Regular tasks flow autonomously from start to finish. User input tasks pause mid-processing to collect information, then resume.

**For developers:** Check `status == 'waiting_for_user'` to distinguish tasks needing interaction. Non-interactive workers should skip these entirely.

**For database queries:** Filter by `status` to separate task types. Check `user_input_type` to understand what input is needed.
