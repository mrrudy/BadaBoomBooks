# User Input Task System

## Overview

The BadaBoomBooks queue system supports tracking tasks that require user input. This allows workers to distinguish between tasks they can process autonomously and tasks that need human interaction.

## Task Status: `waiting_for_user`

Tasks can be marked with status `waiting_for_user` when they need user input to proceed. This status ensures:

1. **Non-interactive workers skip these tasks** - Automated batch workers (running with `--yolo` flag) won't pick up tasks requiring user input
2. **Interactive workers can identify them** - Workers capable of user interaction (CLI with prompts, web interface) can filter for these tasks
3. **Proper queueing** - Tasks wait in the queue until user responds, then resume normal processing

## User Input Types

The system tracks three types of user input scenarios:

### 1. LLM Confirmation (`llm_confirmation`)

**When:** LLM has selected a candidate using AI scoring, waiting for user to confirm

**Location:** [src/search/auto_search.py:290](src/search/auto_search.py#L290)

**Prompt:** `"Accept this selection? [Y/n]: "`

**Override:** `--yolo` flag auto-accepts

**Context includes:**
- Selected candidate with LLM score
- All candidates with scores (for comparison)
- Book information (title, author from folder/OPF/ID3)
- Scraper weights applied

**User Options:**
- `Y/yes/Enter` - Accept AI selection
- `n/no` - Reject and show all candidates for manual selection

**Example:**
```
LLM-based candidate selection (top match):

[lubimyczytac] ⭐ 0.95 (weighted: 1.05) - Wszystkie wskaźniki czerwone
   URL: https://lubimyczytac.pl/ksiazka/5068091/wszystkie-wskazniki-czerwone-sztuczny-stan
   Martha Wells | Murderbot [1-2] | 2024

Other candidates (scores):
   [goodreads] 0.42 - Different Book Title
   [audible] 0.38 - Wrong Author Name

Accept this selection? [Y/n]:
```

### 2. Manual Candidate Selection (`manual_selection`)

**When:** Multiple candidates found in auto-search, user must choose

**Location:** [src/search/auto_search.py:317](src/search/auto_search.py#L317)

**Prompt:** `"Select [1-{len(candidates)}], 0 to skip, or enter URL: "`

**Override:** `--yolo` (without `--llm-select`) auto-selects first candidate

**Context includes:**
- List of all candidates found
- Book information from folder/OPF/ID3
- Search term used

**User Options:**
- `1-N` - Select specific candidate by number
- `0` - Skip this book entirely
- Custom URL - Enter any supported site URL (validated against `SCRAPER_REGISTRY`)

**Example:**
```
Book: Martha Wells - Wszystkie wskaźniki czerwone (from folder name)

Candidate pages:
[1] [lubimyczytac] Wszystkie wskaźniki czerwone. Sztuczny stan
    Martha Wells | Murderbot [1-2] | 2024
    https://lubimyczytac.pl/ksiazka/5068091/wszystkie-wskazniki-czerwone-sztuczny-stan

[2] [goodreads] All Systems Red (The Murderbot Diaries, #1)
    Martha Wells | 2017
    https://www.goodreads.com/book/show/32758901

[0] Skip this book

Or enter a custom URL from a supported site (audible.com, goodreads.com, lubimyczytac.pl)

Select [1-2], 0 to skip, or enter URL:
```

### 3. Manual URL Entry (`manual_url`)

**When:** Manual search mode (no `--auto-search`), user must provide URL

**Location:** [src/search/manual_search.py:234](src/search/manual_search.py#L234)

**Prompt:** `"> "`

**Override:** None - manual mode always requires user input

**Context includes:**
- Folder name being processed
- Available scraper sites

**User Options:**
- Valid URL from supported sites
- `skip` - Skip this book

**Example:**
```
Enter URL for 'Martha Wells - Murderbot 01-02' (or 'skip' to skip):
> https://lubimyczytac.pl/ksiazka/5068091/wszystkie-wskazniki-czerwone-sztuczny-stan
```

## Database Schema

### New Task Status

```sql
CONSTRAINT valid_task_status CHECK (status IN (
    'pending',
    'running',
    'completed',
    'failed',
    'skipped',
    'waiting_for_user'  -- NEW
))
```

### New Task Columns

```sql
ALTER TABLE tasks ADD COLUMN user_input_type TEXT;
-- Values: 'llm_confirmation', 'manual_selection', 'manual_url'

ALTER TABLE tasks ADD COLUMN user_input_prompt TEXT;
-- The exact prompt shown to user

ALTER TABLE tasks ADD COLUMN user_input_options TEXT;
-- JSON array of available options/candidates

ALTER TABLE tasks ADD COLUMN user_input_context TEXT;
-- JSON object with book info, candidates, scores, etc.
```

## QueueManager API

### Mark Task Waiting for User

```python
queue_manager.set_task_waiting_for_user(
    task_id='abc-123-...',
    input_type='manual_selection',
    prompt='Select [1-3], 0 to skip, or enter URL: ',
    options=['Candidate 1', 'Candidate 2', 'Candidate 3'],
    context={
        'book_info': {'title': '...', 'author': '...'},
        'search_term': '...',
        'candidates': [...]
    }
)
```

### Get Tasks Waiting for User

```python
# Get all waiting tasks for a specific job
waiting_tasks = queue_manager.get_tasks_waiting_for_user(job_id='xyz-789-...')

# Get all waiting tasks across all jobs
all_waiting = queue_manager.get_tasks_waiting_for_user()

# Each task dict includes:
# - task['user_input_type']
# - task['user_input_prompt']
# - task['user_input_options'] (parsed JSON list)
# - task['user_input_context'] (parsed JSON dict)
# - task['folder_path']
# - task['id']
# - etc.
```

### Resume Task After User Input

```python
# Resume with user's response (URL, selection, etc.)
queue_manager.resume_task_from_user_input(
    task_id='abc-123-...',
    user_response='https://lubimyczytac.pl/ksiazka/5068091/...',
    clear_input_fields=True  # Clear user_input_* columns (default)
)

# Task status changes: waiting_for_user -> pending
# Task is now ready for workers to pick up
```

## Worker Implementation

### Non-Interactive Worker (Batch Processing)

```python
# Worker with --yolo flag should skip waiting_for_user tasks
tasks = queue_manager.get_tasks_by_job(
    job_id=job_id,
    status=['pending']  # ONLY pending, NOT waiting_for_user
)
```

### Interactive Worker (CLI/Web)

```python
# Worker capable of user interaction
tasks = queue_manager.get_tasks_by_job(
    job_id=job_id,
    status=['pending', 'waiting_for_user']  # Can handle both
)

for task in tasks:
    if task['status'] == 'waiting_for_user':
        # Show prompt to user
        user_response = show_prompt(
            prompt=task['user_input_prompt'],
            options=task['user_input_options'],
            context=task['user_input_context']
        )

        # Resume task with response
        queue_manager.resume_task_from_user_input(
            task_id=task['id'],
            user_response=user_response
        )
```

## Web Interface Integration

The web interface already has `awaiting_selection` state in `WebState` class ([web/app.py:57](web/app.py#L57)). This should be integrated with the database-backed `waiting_for_user` status:

```python
# In web worker thread
def process_job_with_queue(job_id):
    queue_manager = QueueManager()

    while True:
        # Check for tasks waiting for user
        waiting = queue_manager.get_tasks_waiting_for_user(job_id=job_id)

        if waiting:
            task = waiting[0]  # Process one at a time

            # Emit to web interface
            socketio.emit('awaiting_selection', {
                'job_id': job_id,
                'task_id': task['id'],
                'input_type': task['user_input_type'],
                'prompt': task['user_input_prompt'],
                'options': task['user_input_options'],
                'context': task['user_input_context']
            })

            # Wait for user response (handled by web route)
            # Route will call queue_manager.resume_task_from_user_input()
            time.sleep(1)
            continue

        # Process normal pending tasks
        tasks = queue_manager.get_tasks_by_job(job_id, status=['pending'])
        # ... process tasks
```

## Migration Notes

### Existing Databases

The schema migrations in `QueueManager._initialize_database()` automatically add new columns to existing databases:

1. `user_input_type` TEXT
2. `user_input_prompt` TEXT
3. `user_input_options` TEXT
4. `user_input_context` TEXT

These are nullable, so existing tasks are unaffected.

### Constraint Updates

The `valid_task_status` constraint is only enforced on new tables. For existing databases:

```python
# Existing constraint remains (old schema)
# CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped'))

# New code can still use 'waiting_for_user' status
# SQLite allows values outside CHECK constraint if constraint was added after table creation
# Constraint is enforced on new tables only
```

To enforce new constraint on existing databases, you would need to:
1. Create new table with updated constraint
2. Copy data
3. Drop old table
4. Rename new table

This is NOT required for the system to work - the new status is usable regardless.

## Testing

### Unit Tests

```python
def test_user_input_task_tracking():
    queue_manager = QueueManager(db_path=tmp_path / 'test.db')

    # Create task
    job_id = queue_manager.create_job(args)
    task_id = queue_manager.create_task(job_id, folder_path, url)

    # Mark waiting for user
    queue_manager.set_task_waiting_for_user(
        task_id=task_id,
        input_type='manual_selection',
        prompt='Select [1-3]:',
        options=['Opt1', 'Opt2', 'Opt3'],
        context={'book': 'Test Book'}
    )

    # Verify status
    task = queue_manager.get_task(task_id)
    assert task['status'] == 'waiting_for_user'
    assert task['user_input_type'] == 'manual_selection'

    # Get waiting tasks
    waiting = queue_manager.get_tasks_waiting_for_user(job_id)
    assert len(waiting) == 1
    assert waiting[0]['user_input_options'] == ['Opt1', 'Opt2', 'Opt3']

    # Resume task
    queue_manager.resume_task_from_user_input(
        task_id=task_id,
        user_response='https://example.com/book'
    )

    # Verify resumed
    task = queue_manager.get_task(task_id)
    assert task['status'] == 'pending'
    assert task['url'] == 'https://example.com/book'
    assert task['user_input_type'] is None  # Cleared
```

### Integration Tests

Test the three user input scenarios:
1. LLM confirmation flow
2. Manual candidate selection flow
3. Manual URL entry flow

Each should properly set `waiting_for_user` status and track context.

## Benefits

1. **Clear Separation** - Workers can filter tasks by capability (user input vs. autonomous)
2. **Audit Trail** - Database tracks what input was requested and when
3. **Resume Capability** - Jobs can pause for user input and resume seamlessly
4. **Web Interface Ready** - Database state makes it easy to build web UI for user prompts
5. **Parallel Processing** - Non-interactive tasks can continue while waiting for user input on others
6. **Debugging** - Can inspect tasks stuck on user input, replay prompts, etc.

## Future Enhancements

1. **Timeout Handling** - Auto-skip tasks waiting too long for user input
2. **Batch User Input** - Collect multiple prompts, show all at once to user
3. **User Input History** - Track all user selections for analytics/ML training
4. **Smart Defaults** - Learn from user selections to improve auto-selection
5. **Multi-User Support** - Different users can handle different waiting tasks
6. **Priority System** - Mark some user inputs as higher priority than others
