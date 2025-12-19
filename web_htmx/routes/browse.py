"""
File Browser Routes

Provides endpoints for browsing the filesystem and selecting audiobook folders.
Handles Windows drive detection, audiobook folder identification, and folder selection.
"""

import os
import string
from pathlib import Path

from flask import Blueprint, request, jsonify, render_template, session

bp = Blueprint('browse', __name__, url_prefix='/browse')


@bp.route('/drives', methods=['GET'])
def list_drives():
    """
    List available drives on Windows or root on Unix.

    Returns:
        HTML partial with drive/root listing
    """
    drives = []

    if os.name == 'nt':  # Windows
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                try:
                    # Test if drive is accessible
                    os.listdir(drive_path)
                    drives.append({
                        'name': f"{letter}: Drive",
                        'path': drive_path,
                        'type': 'drive',
                        'accessible': True,
                        'audio_count': 0
                    })
                except (OSError, PermissionError):
                    # Drive exists but not accessible
                    drives.append({
                        'name': f"{letter}: Drive (No Access)",
                        'path': drive_path,
                        'type': 'drive',
                        'accessible': False,
                        'audio_count': 0
                    })
    else:
        # Unix-like systems
        drives.append({
            'name': '/ (Root)',
            'path': '/',
            'type': 'drive',
            'accessible': True,
            'audio_count': 0
        })

    return render_template('partials/file_browser_list.html',
                          current_path='Computer',
                          parent=None,
                          items=drives,
                          is_drives=True)


@bp.route('/', methods=['GET'])
def browse_path():
    """
    Browse a specific filesystem path.

    Query params:
        path: Directory path to browse

    Returns:
        HTML partial with folder listing
    """
    path_param = request.args.get('path', '')

    try:
        # Handle drives listing
        if not path_param or path_param == 'drives':
            return list_drives()

        # Clean up the path for Windows
        if os.name == 'nt' and path_param.endswith('\\') and len(path_param) == 3:
            # Windows drive path like "C:\\"
            current_path = Path(path_param)
        else:
            current_path = Path(path_param).resolve()

        # Verify path exists
        if not current_path.exists() or not current_path.is_dir():
            return render_template('partials/file_browser_list.html',
                                  error=f'Path does not exist or is not a directory: {path_param}'), 404

        # Determine parent path
        if os.name == 'nt' and str(current_path).endswith(':\\'):
            # Windows drive root - parent should be drives list
            parent_path = 'drives'
        else:
            parent = current_path.parent if current_path != current_path.parent else None
            parent_path = str(parent) if parent else None

        # List directory items
        items = []
        try:
            for item in sorted(current_path.iterdir()):
                if item.is_dir():
                    # Check if it might be an audiobook folder
                    audio_count, is_audiobook = count_audio_files(item)

                    items.append({
                        'name': item.name,
                        'path': str(item),
                        'type': 'audiobook' if is_audiobook else 'folder',
                        'accessible': True,
                        'audio_count': audio_count
                    })
        except (PermissionError, OSError) as e:
            return render_template('partials/file_browser_list.html',
                                  error=f'Access denied: {e}'), 403

        return render_template('partials/file_browser_list.html',
                              current_path=str(current_path),
                              parent=parent_path,
                              items=items,
                              is_drives=False)

    except Exception as e:
        return render_template('partials/file_browser_list.html',
                              error=f'Failed to browse path: {e}'), 400


@bp.route('/select', methods=['POST'])
def select_folder():
    """
    Add or remove a folder from the selection.

    JSON body:
        path: Folder path
        action: "add" or "remove"

    Returns:
        JSON with selected folders and count
    """
    data = request.json
    path = data.get('path')
    action = data.get('action', 'add')

    if not path:
        return jsonify({'error': 'Path required'}), 400

    # Initialize session if needed
    if 'selected_folders' not in session:
        session['selected_folders'] = []

    selected_folders = session['selected_folders']

    if action == 'add':
        if path not in selected_folders:
            selected_folders.append(path)
    elif action == 'remove':
        if path in selected_folders:
            selected_folders.remove(path)

    session['selected_folders'] = selected_folders
    session.modified = True

    return jsonify({
        'selected_folders': selected_folders,
        'count': len(selected_folders)
    })


@bp.route('/selected', methods=['GET'])
def get_selected():
    """
    Get list of selected folders.

    Returns:
        JSON with selected folders
    """
    selected_folders = session.get('selected_folders', [])
    return jsonify({
        'selected_folders': selected_folders,
        'count': len(selected_folders)
    })


@bp.route('/clear', methods=['POST'])
def clear_selection():
    """
    Clear all selected folders.

    Returns:
        JSON confirmation
    """
    session['selected_folders'] = []
    session.modified = True

    return jsonify({
        'selected_folders': [],
        'count': 0
    })


def count_audio_files(folder_path: Path) -> tuple:
    """
    Count audio files in a folder to determine if it's an audiobook.

    Args:
        folder_path: Path to folder

    Returns:
        Tuple of (count, is_audiobook)
    """
    audio_extensions = ['.mp3', '.m4a', '.m4b', '.flac', '.ogg', '.wma']
    audio_files = []

    try:
        for ext in audio_extensions:
            audio_files.extend(list(folder_path.glob(f'*{ext}')))
            if len(audio_files) > 0:
                # Stop checking if we found audio files
                break
    except (PermissionError, OSError):
        pass

    count = len(audio_files)
    is_audiobook = count > 0

    return count, is_audiobook
