#!/usr/bin/env python3
"""
Wiki Generator - Flask Web Application

A web interface for generating and publishing wiki content using AI.
"""

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path

import yaml
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash

from config import config
from adapters.mediawiki import MediaWikiAdapter

app = Flask(__name__)
app.config.from_object(config['default'])

# Store for generation/upload progress (in production, use Redis or similar)
progress_store = {}


def get_projects_dir():
    """Get the projects directory path."""
    return Path(app.config['PROJECTS_DIR'])


def get_project_path(project_id):
    """Get path to a specific project directory."""
    return get_projects_dir() / project_id


def load_project(project_id):
    """Load project configuration."""
    config_path = get_project_path(project_id) / 'config.json'
    if not config_path.exists():
        return None
    with open(config_path, 'r') as f:
        project = json.load(f)
        project['id'] = project_id
        return project


def save_project(project_id, data):
    """Save project configuration."""
    project_dir = get_project_path(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    config_path = project_dir / 'config.json'
    with open(config_path, 'w') as f:
        json.dump(data, f, indent=2)


def load_pages_config(project_id):
    """Load pages.yaml for a project."""
    yaml_path = get_project_path(project_id) / 'pages.yaml'
    if not yaml_path.exists():
        return None
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def save_pages_config(project_id, config):
    """Save pages.yaml for a project."""
    project_dir = get_project_path(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = project_dir / 'pages.yaml'
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def get_recent_projects(limit=5):
    """Get list of recent projects."""
    projects_dir = get_projects_dir()
    if not projects_dir.exists():
        return []

    projects = []
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            project = load_project(project_dir.name)
            if project:
                projects.append(project)

    # Sort by created_at, newest first
    projects.sort(key=lambda p: p.get('created_at', ''), reverse=True)
    return projects[:limit]


# =============================================================================
# Routes
# =============================================================================

@app.route('/')
def index():
    """Landing page."""
    recent_projects = get_recent_projects()
    return render_template('index.html', recent_projects=recent_projects)


@app.route('/project/new', methods=['GET', 'POST'])
def new_project():
    """Create new project page."""
    if request.method == 'POST':
        # Validate and create project
        name = request.form.get('name', '').strip()
        wiki_domain = request.form.get('wiki_domain', '').strip()
        bot_username = request.form.get('bot_username', '').strip()
        bot_password = request.form.get('bot_password', '')

        if not all([name, wiki_domain, bot_username, bot_password]):
            flash('All fields are required', 'error')
            return render_template('new_project.html')

        # Create project
        project_id = str(uuid.uuid4())[:8]
        project_data = {
            'name': name,
            'platform': 'miraheze',
            'wiki_domain': wiki_domain,
            'bot_username': bot_username,
            'bot_password': bot_password,  # In production, encrypt this
            'api_path': '/w/api.php',
            'created_at': datetime.now().isoformat()
        }

        save_project(project_id, project_data)

        flash('Project created successfully', 'success')
        return redirect(url_for('project_structure', project_id=project_id))

    return render_template('new_project.html')


@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    """Test wiki connection via AJAX."""
    data = request.get_json()

    wiki_domain = data.get('wiki_domain', '').strip()
    bot_username = data.get('bot_username', '').strip()
    bot_password = data.get('bot_password', '')

    if not all([wiki_domain, bot_username, bot_password]):
        return jsonify({'success': False, 'error': 'All fields are required'})

    # Test connection using adapter
    try:
        adapter = MediaWikiAdapter({
            'wiki_domain': wiki_domain,
            'bot_username': bot_username,
            'bot_password': bot_password,
            'api_path': '/w/api.php'
        })

        result = adapter.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/project/<project_id>/structure', methods=['GET'])
def project_structure(project_id):
    """Wiki structure editor page."""
    project = load_project(project_id)
    if not project:
        flash('Project not found', 'error')
        return redirect(url_for('index'))

    pages_config = load_pages_config(project_id)

    return render_template('yaml_editor.html',
                           project=project,
                           pages_config=pages_config)


@app.route('/project/<project_id>/structure/save', methods=['POST'])
def save_structure(project_id):
    """Save wiki structure (AJAX)."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'})

    try:
        config = request.get_json()
        save_pages_config(project_id, config)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/project/<project_id>/generate', methods=['GET'])
def project_generate(project_id):
    """Content generation page."""
    project = load_project(project_id)
    if not project:
        flash('Project not found', 'error')
        return redirect(url_for('index'))

    pages_config = load_pages_config(project_id)
    if not pages_config or not pages_config.get('pages'):
        flash('Please add pages to your wiki structure first', 'warning')
        return redirect(url_for('project_structure', project_id=project_id))

    pages = pages_config.get('pages', [])

    return render_template('generate.html',
                           project=project,
                           pages=pages)


@app.route('/project/<project_id>/generate/start', methods=['POST'])
def start_generation(project_id):
    """Start content generation (AJAX)."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'})

    data = request.get_json()
    api_key = data.get('api_key')
    selected_pages = data.get('pages', [])

    if not api_key:
        return jsonify({'success': False, 'error': 'API key is required'})

    if not selected_pages:
        return jsonify({'success': False, 'error': 'No pages selected'})

    # Initialize progress tracking
    progress_store[project_id] = {
        'status': 'starting',
        'total': len(selected_pages),
        'completed': 0,
        'current_page': '',
        'percent': 0,
        'success': [],
        'failed': []
    }

    # Start generation in background thread
    thread = threading.Thread(
        target=run_generation,
        args=(project_id, api_key, selected_pages)
    )
    thread.daemon = True
    thread.start()

    return jsonify({'success': True})


def run_generation(project_id, api_key, selected_pages):
    """Run content generation in background."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent / 'existing_scripts'))
    from generate_content import WikiContentGenerator

    project_dir = get_project_path(project_id)
    yaml_path = project_dir / 'pages.yaml'
    output_dir = project_dir / 'generated'
    output_dir.mkdir(exist_ok=True)

    progress = progress_store[project_id]

    try:
        generator = WikiContentGenerator(str(yaml_path), api_key)

        for i, title in enumerate(selected_pages):
            progress['current_page'] = title
            progress['status'] = 'generating'

            page = generator.get_page_by_title(title)
            if not page:
                progress['failed'].append(title)
                continue

            try:
                content = generator.generate_page(page)

                # Save to file
                filename = title.replace(' ', '_').replace('/', '_') + '.wiki'
                filepath = output_dir / filename
                filepath.write_text(content, encoding='utf-8')

                progress['success'].append(title)
            except Exception as e:
                progress['failed'].append(title)
                print(f"Error generating {title}: {e}")

            progress['completed'] = i + 1
            progress['percent'] = int(((i + 1) / len(selected_pages)) * 100)

        progress['status'] = 'complete'
        progress['current_page'] = ''

    except Exception as e:
        progress['status'] = 'error'
        progress['error'] = str(e)


@app.route('/project/<project_id>/generate/progress', methods=['GET'])
def get_progress(project_id):
    """Get generation progress (AJAX)."""
    if project_id not in progress_store:
        return jsonify({
            'status': 'unknown',
            'total': 0,
            'completed': 0,
            'percent': 0,
            'current_page': '',
            'success': [],
            'failed': []
        })

    return jsonify(progress_store[project_id])


@app.route('/project/<project_id>/review', methods=['GET'])
def project_review(project_id):
    """Review generated content page."""
    project = load_project(project_id)
    if not project:
        flash('Project not found', 'error')
        return redirect(url_for('index'))

    generated_dir = get_project_path(project_id) / 'generated'

    generated_pages = []
    if generated_dir.exists():
        for wiki_file in generated_dir.glob('*.wiki'):
            stat = wiki_file.stat()
            generated_pages.append({
                'filename': wiki_file.name,
                'title': wiki_file.stem.replace('_', ' '),
                'size': f"{stat.st_size / 1024:.1f} KB"
            })

    if not generated_pages:
        flash('No generated content found. Please generate content first.', 'warning')
        return redirect(url_for('project_generate', project_id=project_id))

    return render_template('review.html',
                           project=project,
                           generated_pages=generated_pages)


@app.route('/project/<project_id>/page/<filename>', methods=['GET'])
def get_page_content(project_id, filename):
    """Get content of a generated page (AJAX)."""
    filepath = get_project_path(project_id) / 'generated' / filename

    if not filepath.exists():
        return jsonify({'error': 'Page not found'}), 404

    content = filepath.read_text(encoding='utf-8')
    return jsonify({'content': content})


@app.route('/project/<project_id>/upload', methods=['POST'])
def upload_pages(project_id):
    """Start uploading pages to wiki (AJAX)."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'})

    data = request.get_json()
    selected_pages = data.get('pages', [])

    if not selected_pages:
        return jsonify({'success': False, 'error': 'No pages selected'})

    # Initialize upload progress
    upload_key = f"{project_id}_upload"
    progress_store[upload_key] = {
        'status': 'uploading',
        'total': len(selected_pages),
        'completed': [],
        'failed': [],
        'current_page': '',
        'percent': 0
    }

    # Start upload in background
    thread = threading.Thread(
        target=run_upload,
        args=(project_id, project, selected_pages)
    )
    thread.daemon = True
    thread.start()

    return jsonify({'success': True})


def run_upload(project_id, project, selected_pages):
    """Run wiki upload in background."""
    upload_key = f"{project_id}_upload"
    progress = progress_store[upload_key]

    generated_dir = get_project_path(project_id) / 'generated'

    try:
        adapter = MediaWikiAdapter({
            'wiki_domain': project['wiki_domain'],
            'bot_username': project['bot_username'],
            'bot_password': project['bot_password'],
            'api_path': project.get('api_path', '/w/api.php')
        })

        if not adapter.login():
            progress['status'] = 'error'
            progress['error'] = 'Failed to login to wiki'
            return

        for i, filename in enumerate(selected_pages):
            progress['current_page'] = filename.replace('.wiki', '').replace('_', ' ')

            filepath = generated_dir / filename
            if not filepath.exists():
                progress['failed'].append(filename)
                continue

            content = filepath.read_text(encoding='utf-8')
            title = filepath.stem.replace('_', ' ')

            if adapter.upload_page(title, content):
                progress['completed'].append(filename)
            else:
                progress['failed'].append(filename)

            progress['percent'] = int(((i + 1) / len(selected_pages)) * 100)

        progress['status'] = 'complete'
        progress['current_page'] = ''

        # Store upload results for complete page
        progress_store[f"{project_id}_upload_results"] = {
            'success': len(progress['completed']),
            'failed': len(progress['failed']),
            'total': len(selected_pages),
            'pages': [f.replace('.wiki', '').replace('_', ' ') for f in progress['completed']]
        }

    except Exception as e:
        progress['status'] = 'error'
        progress['error'] = str(e)


@app.route('/project/<project_id>/upload/progress', methods=['GET'])
def get_upload_progress(project_id):
    """Get upload progress (AJAX)."""
    upload_key = f"{project_id}_upload"

    if upload_key not in progress_store:
        return jsonify({
            'status': 'unknown',
            'total': 0,
            'completed': [],
            'failed': [],
            'percent': 0,
            'current_page': ''
        })

    return jsonify(progress_store[upload_key])


@app.route('/project/<project_id>/complete', methods=['GET'])
def project_complete(project_id):
    """Upload complete page."""
    project = load_project(project_id)
    if not project:
        flash('Project not found', 'error')
        return redirect(url_for('index'))

    # Get upload results
    results_key = f"{project_id}_upload_results"
    stats = progress_store.get(results_key, {
        'success': 0,
        'failed': 0,
        'total': 0,
        'pages': []
    })

    return render_template('complete.html',
                           project=project,
                           stats=stats,
                           uploaded_pages=stats.get('pages', []))


# =============================================================================
# Error Handlers
# =============================================================================

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    flash('Page not found', 'error')
    return redirect(url_for('index'))


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    flash('An error occurred. Please try again.', 'error')
    return redirect(url_for('index'))


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    # Ensure projects directory exists
    get_projects_dir().mkdir(exist_ok=True)

    app.run(debug=True, port=5000)
