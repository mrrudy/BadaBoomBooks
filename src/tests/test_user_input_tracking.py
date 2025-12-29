"""
Tests for user input task tracking system.

Validates that tasks requiring user input are properly marked and trackable
in the queue database.
"""

import pytest
from pathlib import Path
from src.queue_manager import QueueManager
from src.models import ProcessingArgs


@pytest.fixture
def test_queue_manager(tmp_path):
    """Create a test queue manager with isolated database."""
    db_path = tmp_path / "test_user_input.db"
    queue_manager = QueueManager(db_path=db_path)
    yield queue_manager
    queue_manager.close()


def test_mark_task_waiting_for_user(test_queue_manager):
    """Test marking a task as waiting for user input."""
    # Create a test job and task
    args = ProcessingArgs(
        output=Path("C:/test"),
        book_root=Path("C:/test"),
        auto_search=True
    )

    job_id = test_queue_manager.create_job(args)
    task_id = test_queue_manager.create_task(
        job_id=job_id,
        folder_path=Path("C:/test/book1"),
        url=None  # No URL yet - needs user input
    )

    # Mark task as waiting for user input
    test_queue_manager.set_task_waiting_for_user(
        task_id=task_id,
        input_type='manual_selection',
        prompt='Select [1-3], 0 to skip, or enter URL: ',
        options=[
            {'number': 1, 'title': 'Book Option 1', 'url': 'https://example.com/1'},
            {'number': 2, 'title': 'Book Option 2', 'url': 'https://example.com/2'},
            {'number': 3, 'title': 'Book Option 3', 'url': 'https://example.com/3'},
            {'number': 0, 'action': 'skip', 'label': 'Skip this book'}
        ],
        context={
            'search_term': 'test book',
            'book_info': {'title': 'Test Book', 'author': 'Test Author'},
            'folder_path': 'book1'
        }
    )

    # Verify task is marked correctly
    task = test_queue_manager.get_task(task_id)
    assert task['status'] == 'waiting_for_user'
    assert task['user_input_type'] == 'manual_selection'
    assert task['user_input_prompt'] == 'Select [1-3], 0 to skip, or enter URL: '
    assert task['user_input_options'] is not None
    assert task['user_input_context'] is not None


def test_get_tasks_waiting_for_user(test_queue_manager):
    """Test retrieving tasks waiting for user input."""
    # Create multiple tasks
    args = ProcessingArgs(
        output=Path("C:/test"),
        book_root=Path("C:/test"),
        auto_search=True
    )

    job_id = test_queue_manager.create_job(args)

    # Create 3 tasks - 2 waiting for user, 1 regular
    task1_id = test_queue_manager.create_task(job_id, Path("C:/test/book1"), None)
    task2_id = test_queue_manager.create_task(job_id, Path("C:/test/book2"), None)
    task3_id = test_queue_manager.create_task(job_id, Path("C:/test/book3"), "https://example.com/book3")

    # Mark first two as waiting for user
    for task_id in [task1_id, task2_id]:
        test_queue_manager.set_task_waiting_for_user(
            task_id=task_id,
            input_type='manual_selection',
            prompt='Select: ',
            options=['Option 1', 'Option 2'],
            context={'test': 'context'}
        )

    # Get waiting tasks
    waiting_tasks = test_queue_manager.get_tasks_waiting_for_user(job_id)

    assert len(waiting_tasks) == 2
    assert all(task['status'] == 'waiting_for_user' for task in waiting_tasks)

    # Verify JSON fields are parsed
    for task in waiting_tasks:
        assert isinstance(task['user_input_options'], list)
        assert isinstance(task['user_input_context'], dict)


def test_resume_task_from_user_input(test_queue_manager):
    """Test resuming a task after receiving user input."""
    args = ProcessingArgs(
        output=Path("C:/test"),
        book_root=Path("C:/test"),
        auto_search=True
    )

    job_id = test_queue_manager.create_job(args)
    task_id = test_queue_manager.create_task(job_id, Path("C:/test/book1"), None)

    # Mark as waiting for user
    test_queue_manager.set_task_waiting_for_user(
        task_id=task_id,
        input_type='manual_selection',
        prompt='Select: ',
        options=['Option 1', 'Option 2'],
        context={'test': 'context'}
    )

    # Verify waiting state
    task = test_queue_manager.get_task(task_id)
    assert task['status'] == 'waiting_for_user'
    assert task['url'] is None

    # Resume with user response (URL)
    user_url = 'https://example.com/selected-book'
    test_queue_manager.resume_task_from_user_input(
        task_id=task_id,
        user_response=user_url,
        clear_input_fields=True
    )

    # Verify resumed state
    task = test_queue_manager.get_task(task_id)
    assert task['status'] == 'pending'
    assert task['url'] == user_url
    assert task['user_input_type'] is None  # Cleared
    assert task['user_input_prompt'] is None  # Cleared
    assert task['user_input_options'] is None  # Cleared
    assert task['user_input_context'] is None  # Cleared


def test_filter_tasks_by_worker_type(test_queue_manager):
    """Test that workers can filter tasks by their capability."""
    args = ProcessingArgs(
        output=Path("C:/test"),
        book_root=Path("C:/test"),
        auto_search=True
    )

    job_id = test_queue_manager.create_job(args)

    # Create 5 tasks - 3 regular pending, 2 waiting for user
    regular_task_ids = []
    for i in range(3):
        task_id = test_queue_manager.create_task(
            job_id,
            Path(f"C:/test/regular{i}"),
            f"https://example.com/book{i}"
        )
        regular_task_ids.append(task_id)

    waiting_task_ids = []
    for i in range(2):
        task_id = test_queue_manager.create_task(
            job_id,
            Path(f"C:/test/waiting{i}"),
            None
        )
        test_queue_manager.set_task_waiting_for_user(
            task_id=task_id,
            input_type='manual_selection',
            prompt='Select: ',
            options=['Opt1', 'Opt2']
        )
        waiting_task_ids.append(task_id)

    # Non-interactive worker: Get only pending tasks
    non_interactive_tasks = test_queue_manager.get_tasks_for_job(
        job_id,
        status=['pending']
    )
    assert len(non_interactive_tasks) == 3
    assert all(task['status'] == 'pending' for task in non_interactive_tasks)
    assert all(task['id'] in regular_task_ids for task in non_interactive_tasks)

    # Interactive worker: Get both pending and waiting_for_user
    interactive_tasks = test_queue_manager.get_tasks_for_job(
        job_id,
        status=['pending', 'waiting_for_user']
    )
    assert len(interactive_tasks) == 5

    # Get only waiting tasks
    waiting_only = test_queue_manager.get_tasks_waiting_for_user(job_id)
    assert len(waiting_only) == 2
    assert all(task['id'] in waiting_task_ids for task in waiting_only)


def test_user_input_types(test_queue_manager):
    """Test all three types of user input tracking."""
    args = ProcessingArgs(
        output=Path("C:/test"),
        book_root=Path("C:/test"),
        auto_search=True
    )

    job_id = test_queue_manager.create_job(args)

    # Type 1: LLM confirmation
    task1_id = test_queue_manager.create_task(job_id, Path("C:/test/llm_confirm"), None)
    test_queue_manager.set_task_waiting_for_user(
        task_id=task1_id,
        input_type='llm_confirmation',
        prompt='Accept this selection? [Y/n]: ',
        options=[
            {'site': 'lubimyczytac', 'llm_score': 0.95, 'title': 'Selected Book'}
        ],
        context={'has_llm_scores': True}
    )

    # Type 2: Manual selection
    task2_id = test_queue_manager.create_task(job_id, Path("C:/test/manual_select"), None)
    test_queue_manager.set_task_waiting_for_user(
        task_id=task2_id,
        input_type='manual_selection',
        prompt='Select [1-3], 0 to skip, or enter URL: ',
        options=[
            {'number': 1, 'title': 'Option 1'},
            {'number': 2, 'title': 'Option 2'},
            {'number': 3, 'title': 'Option 3'}
        ]
    )

    # Type 3: Manual URL entry
    task3_id = test_queue_manager.create_task(job_id, Path("C:/test/manual_url"), None)
    test_queue_manager.set_task_waiting_for_user(
        task_id=task3_id,
        input_type='manual_url',
        prompt='> ',
        options=[
            {'action': 'enter_url', 'label': 'Enter URL from supported sites'},
            {'action': 'skip', 'label': "Type 'skip' to skip"}
        ],
        context={'input_mode': 'manual_search'}
    )

    # Verify all types are tracked
    waiting_tasks = test_queue_manager.get_tasks_waiting_for_user(job_id)
    assert len(waiting_tasks) == 3

    input_types = {task['user_input_type'] for task in waiting_tasks}
    assert input_types == {'llm_confirmation', 'manual_selection', 'manual_url'}

    # Verify each type has appropriate fields
    for task in waiting_tasks:
        assert task['user_input_type'] in ['llm_confirmation', 'manual_selection', 'manual_url']
        assert task['user_input_prompt'] is not None
        assert task['user_input_options'] is not None
        assert isinstance(task['user_input_options'], list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
