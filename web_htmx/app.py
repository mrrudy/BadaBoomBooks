#!/usr/bin/env python3
"""
BadaBoomBooks Web Interface - HTMX Edition

Modern web UI using Flask + HTMX + DaisyUI for audiobook organization.
Integrates with existing QueueManager and parallel processing system.
"""

import os
import sys
from pathlib import Path

from flask import Flask, render_template, session
from flask.json.provider import DefaultJSONProvider
import uuid

# Add src directory to Python path
root_dir = Path(__file__).parent.parent
src_dir = root_dir / 'src'
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(root_dir))

# Import QueueManager from existing system
from src.queue_manager import QueueManager
from src.config import __version__

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'badaboombooks-htmx-' + str(uuid.uuid4()))
app.config['SESSION_TYPE'] = 'filesystem'

# Custom JSON provider to handle Path objects
class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, Path):
            return str(obj)
        return super().default(obj)

app.json = CustomJSONProvider(app)

# Initialize QueueManager (singleton)
queue_manager = QueueManager()

# Register route blueprints
from routes import browse, scan, tasks, llm

app.register_blueprint(browse.bp)
app.register_blueprint(scan.bp)
app.register_blueprint(tasks.bp)
app.register_blueprint(llm.bp)


@app.route('/')
def index():
    """Main page - Scan planning + task management."""
    # Initialize session if needed
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

    if 'selected_folders' not in session:
        session['selected_folders'] = []

    return render_template('index.html',
                          version=__version__,
                          user_id=session['user_id'])


@app.route('/health')
def health():
    """Health check endpoint."""
    return {
        'status': 'ok',
        'version': __version__,
        'queue_manager': 'connected'
    }


@app.context_processor
def inject_version():
    """Make version available to all templates."""
    return {'version': __version__}


# Register custom Jinja2 filters
import re

@app.template_filter('regex_replace')
def regex_replace(s, pattern, replacement):
    """Replace text using regex pattern."""
    return re.sub(pattern, replacement, s)


if __name__ == '__main__':
    # Development server
    print(f"BadaBoomBooks Web Interface v{__version__}")
    print("Starting server on http://localhost:5000")
    print("Press Ctrl+C to stop")

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=True
    )
