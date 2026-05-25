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
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from werkzeug.security import check_password_hash, generate_password_hash

from config import config
from adapters.mediawiki import MediaWikiAdapter
from adapters.confluence import ConfluenceAdapter
from adapters.fandom import FandomAdapter

app = Flask(__name__)
app.config.from_object(config['default'])

# Store for generation/upload progress (in production, use Redis or similar)
progress_store = {}


def get_accounts_path():
    """Get the accounts.json file path."""
    return Path(__file__).parent / 'accounts.json'


def load_accounts():
    """Load all accounts from accounts.json."""
    path = get_accounts_path()
    if not path.exists():
        return []
    with open(path, 'r') as f:
        data = json.load(f)
    return data.get('accounts', [])


def save_accounts(accounts):
    """Save accounts list to accounts.json."""
    with open(get_accounts_path(), 'w') as f:
        json.dump({'accounts': accounts}, f, indent=2)


def get_account_by_id(account_id):
    """Find a single account by its ID."""
    for acct in load_accounts():
        if acct['id'] == account_id:
            return acct
    return None


def get_projects_dir():
    """Get the projects directory path."""
    return Path(app.config['PROJECTS_DIR'])


def get_project_path(project_id):
    """Get path to a specific project directory."""
    return get_projects_dir() / project_id


def load_project(project_id):
    """Load project configuration, enriching with account info for display."""
    config_path = get_project_path(project_id) / 'config.json'
    if not config_path.exists():
        return None
    with open(config_path, 'r') as f:
        project = json.load(f)
        project['id'] = project_id

    # Enrich with account info for display if using account_id
    account_id = project.get('account_id')
    if account_id:
        account = get_account_by_id(account_id)
        if account:
            platform = account.get('platform', 'miraheze')
            wiki_url = normalize_wiki_url(account.get('wiki_url', ''), platform)
            project['account_nickname'] = account.get('nickname', '')
            project.setdefault('wiki_domain', wiki_url)
            project.setdefault('base_url', wiki_url)

    return project


def save_project(project_id, data):
    """Save project configuration."""
    project_dir = get_project_path(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    config_path = project_dir / 'config.json'
    with open(config_path, 'w') as f:
        json.dump(data, f, indent=2)


def normalize_wiki_url(url: str, platform: str = 'miraheze') -> str:
    """Strip scheme and trailing slashes from wiki URLs.

    MediaWikiAdapter prepends 'https://' itself, so storing
    'https://foo.miraheze.org/' would produce a double-scheme URL.
    Confluence expects a full base_url, so we leave that alone.
    """
    if platform == 'confluence':
        return url.rstrip('/')
    # Strip scheme
    for prefix in ('https://', 'http://'):
        if url.startswith(prefix):
            url = url[len(prefix):]
    return url.strip('/')


def resolve_project_credentials(project: dict) -> dict:
    """Merge account credentials into project dict if account_id is set."""
    account_id = project.get('account_id')
    if not account_id:
        return project

    account = get_account_by_id(account_id)
    if not account:
        return project

    merged = dict(project)
    platform = account.get('platform', 'miraheze')
    merged['platform'] = platform

    wiki_url = normalize_wiki_url(account.get('wiki_url', ''), platform)

    if platform == 'confluence':
        merged['base_url'] = wiki_url
        merged['space_key'] = account.get('space_key', '')
        merged['user_email'] = account.get('bot_username', '')
        merged['api_token'] = account.get('bot_password', '')
    else:
        merged['wiki_domain'] = wiki_url
        merged['bot_username'] = account.get('bot_username', '')
        merged['bot_password'] = account.get('bot_password', '')

    return merged


def get_adapter(project: dict):
    """Return the appropriate adapter for a project."""
    project = resolve_project_credentials(project)
    platform = project.get('platform', 'miraheze')
    if platform == 'confluence':
        return ConfluenceAdapter({
            'base_url': project['base_url'],
            'space_key': project['space_key'],
            'user_email': project['user_email'],
            'api_token': project['api_token']
        })
    elif platform == 'fandom':
        return FandomAdapter({
            'wiki_domain': project['wiki_domain'],
            'bot_username': project['bot_username'],
            'bot_password': project['bot_password']
        })

    if platform == 'wikigg':
        return MediaWikiAdapter({
            'wiki_domain': f"{project['wiki_domain']}.wiki.gg",
            'bot_username': project['bot_username'],
            'bot_password': project['bot_password'],
            'api_path': '/api.php'
        })
    if platform == 'shoutwiki':
        return MediaWikiAdapter({
            'wiki_domain': f"{project['wiki_domain']}.shoutwiki.com",
            'bot_username': project['bot_username'],
            'bot_password': project['bot_password'],
            'api_path': '/w/api.php'
        })
    default_api_path = '/api.php' if platform == 'telepedia' else '/w/api.php'
    return MediaWikiAdapter({
        'wiki_domain': project['wiki_domain'],
        'bot_username': project['bot_username'],
        'bot_password': project['bot_password'],
        'api_path': project.get('api_path', default_api_path)
    })


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


def load_links_config(project_id):
    """Load links.yaml for a project."""
    yaml_path = get_project_path(project_id) / 'links.yaml'
    if not yaml_path.exists():
        return {'link_targets': []}
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {'link_targets': []}


def save_links_config(project_id, config):
    """Save links.yaml for a project."""
    project_dir = get_project_path(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = project_dir / 'links.yaml'
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def get_recent_projects(limit=5):
    """Get list of recent projects."""
    projects_dir = get_projects_dir()
    if not projects_dir.exists():
        return []

    projects = get_all_projects()
    return projects[:limit]


def get_all_projects():
    """Get list of all projects."""
    projects_dir = get_projects_dir()
    if not projects_dir.exists():
        return []

    projects = []
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            project = load_project(project_dir.name)
            if project:
                projects.append(project)

    projects.sort(key=lambda p: p.get('created_at', ''), reverse=True)
    return projects


# =============================================================================
# Auth
# =============================================================================

def _get_credentials():
    username = os.environ.get('APP_USERNAME', 'admin')
    password = os.environ.get('APP_PASSWORD', '')
    return username, password


@app.before_request
def require_login():
    public = {'login', 'logout', 'static'}
    if request.endpoint not in public and not session.get('logged_in'):
        return redirect(url_for('login', next=request.path))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        username, password = _get_credentials()
        if not password:
            error = 'APP_PASSWORD environment variable is not set on the server.'
        elif request.form.get('username') == username and request.form.get('password') == password:
            session.permanent = True
            session['logged_in'] = True
            return redirect(request.args.get('next') or url_for('index'))
        else:
            error = 'Invalid username or password.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# =============================================================================
# Routes
# =============================================================================

@app.route('/')
def index():
    """Landing page."""
    all_projects = get_all_projects()
    recent_projects = all_projects[:5]
    return render_template(
        'index.html',
        recent_projects=recent_projects,
        all_projects=all_projects
    )


@app.route('/accounts')
def accounts_page():
    """Accounts management page."""
    accounts = load_accounts()
    return render_template('accounts.html', accounts=accounts)


@app.route('/api/accounts', methods=['GET'])
def api_list_accounts():
    """List all accounts (passwords masked)."""
    accounts = load_accounts()
    safe = []
    for a in accounts:
        entry = dict(a)
        entry.pop('bot_password', None)
        safe.append(entry)
    return jsonify({'success': True, 'accounts': safe})


@app.route('/api/accounts', methods=['POST'])
def api_create_account():
    """Create a new account."""
    data = request.get_json() or {}
    nickname = (data.get('nickname') or '').strip()
    platform = (data.get('platform') or 'miraheze').strip()
    wiki_url = (data.get('wiki_url') or '').strip()
    bot_username = (data.get('bot_username') or '').strip()
    bot_password = data.get('bot_password') or ''

    if not all([nickname, wiki_url, bot_username, bot_password]):
        return jsonify({'success': False, 'error': 'All fields are required'}), 400

    account = {
        'id': str(uuid.uuid4()),
        'nickname': nickname,
        'platform': platform,
        'wiki_url': wiki_url,
        'bot_username': bot_username,
        'bot_password': bot_password
    }

    if platform == 'confluence':
        account['space_key'] = (data.get('space_key') or '').strip()

    accounts = load_accounts()
    accounts.append(account)
    save_accounts(accounts)

    safe = dict(account)
    safe.pop('bot_password', None)
    return jsonify({'success': True, 'account': safe})


@app.route('/api/accounts/<account_id>', methods=['PUT'])
def api_update_account(account_id):
    """Update an existing account."""
    data = request.get_json() or {}
    accounts = load_accounts()

    target = None
    for acct in accounts:
        if acct['id'] == account_id:
            target = acct
            break

    if not target:
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    if 'nickname' in data:
        target['nickname'] = data['nickname'].strip()
    if 'platform' in data:
        target['platform'] = data['platform'].strip()
    if 'wiki_url' in data:
        target['wiki_url'] = data['wiki_url'].strip()
    if 'bot_username' in data:
        target['bot_username'] = data['bot_username'].strip()
    if 'bot_password' in data and data['bot_password']:
        target['bot_password'] = data['bot_password']
    if 'space_key' in data:
        target['space_key'] = data['space_key'].strip()

    save_accounts(accounts)

    safe = dict(target)
    safe.pop('bot_password', None)
    return jsonify({'success': True, 'account': safe})


@app.route('/api/accounts/<account_id>', methods=['DELETE'])
def api_delete_account(account_id):
    """Delete an account."""
    accounts = load_accounts()
    filtered = [a for a in accounts if a['id'] != account_id]

    if len(filtered) == len(accounts):
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    save_accounts(filtered)
    return jsonify({'success': True})


@app.route('/api/projects/<project_id>', methods=['DELETE'])
def api_delete_project(project_id):
    """Delete a project and all its files."""
    import shutil
    project_path = get_project_path(project_id)
    if not os.path.isdir(project_path):
        return jsonify({'success': False, 'error': 'Project not found'}), 404
    shutil.rmtree(project_path)
    return jsonify({'success': True})


@app.route('/api/accounts/<account_id>/test', methods=['POST'])
def api_test_account(account_id):
    """Test connection for a saved account."""
    account = get_account_by_id(account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    platform = account.get('platform', 'miraheze')
    wiki_url = normalize_wiki_url(account.get('wiki_url', ''), platform)

    try:
        if platform == 'confluence':
            adapter = ConfluenceAdapter({
                'base_url': wiki_url,
                'space_key': account.get('space_key', ''),
                'user_email': account['bot_username'],
                'api_token': account['bot_password']
            })
        elif platform == 'fandom':
            adapter = FandomAdapter({
                'wiki_domain': wiki_url,
                'bot_username': account['bot_username'],
                'bot_password': account['bot_password']
            })
        else:
            if platform == 'wikigg':
                domain = f"{wiki_url}.wiki.gg"
                api_path = '/api.php'
            elif platform == 'shoutwiki':
                domain = f"{wiki_url}.shoutwiki.com"
                api_path = '/w/api.php'
            else:
                domain = wiki_url
                api_path = '/api.php' if platform == 'telepedia' else '/w/api.php'
            adapter = MediaWikiAdapter({
                'wiki_domain': domain,
                'bot_username': account['bot_username'],
                'bot_password': account['bot_password'],
                'api_path': api_path
            })

        result = adapter.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/projects', methods=['GET'])
def all_projects():
    """All projects page."""
    projects = get_all_projects()
    return render_template('projects.html', projects=projects)


@app.route('/project/new', methods=['GET', 'POST'])
def new_project():
    """Create new project page."""
    accounts = load_accounts()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        account_id = request.form.get('account_id', '').strip()

        if not name:
            flash('Project name is required', 'error')
            return render_template('new_project.html', accounts=accounts)

        if not account_id:
            flash('Please select a wiki account', 'error')
            return render_template('new_project.html', accounts=accounts)

        account = get_account_by_id(account_id)
        if not account:
            flash('Selected account not found', 'error')
            return render_template('new_project.html', accounts=accounts)

        project_id = str(uuid.uuid4())[:8]
        project_data = {
            'name': name,
            'account_id': account_id,
            'platform': account.get('platform', 'miraheze'),
            'created_at': datetime.now().isoformat()
        }

        save_project(project_id, project_data)

        flash('Project created successfully', 'success')
        return redirect(url_for('project_structure', project_id=project_id))

    return render_template('new_project.html', accounts=accounts)


@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    """Test wiki connection via AJAX."""
    data = request.get_json()

    platform = data.get('platform', 'miraheze').strip()

    if platform == 'confluence':
        base_url = data.get('base_url', '').strip()
        space_key = data.get('space_key', '').strip()
        user_email = data.get('user_email', '').strip()
        api_token = data.get('api_token', '')

        if not all([base_url, space_key, user_email, api_token]):
            return jsonify({'success': False, 'error': 'All fields are required'})

        try:
            adapter = ConfluenceAdapter({
                'base_url': base_url,
                'space_key': space_key,
                'user_email': user_email,
                'api_token': api_token
            })
            result = adapter.test_connection()
            return jsonify(result)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    elif platform == 'fandom':
        wiki_domain = data.get('wiki_domain', '').strip()
        bot_username = data.get('bot_username', '').strip()
        bot_password = data.get('bot_password', '')

        if not all([wiki_domain, bot_username, bot_password]):
            return jsonify({'success': False, 'error': 'All fields are required'})

        try:
            adapter = FandomAdapter({
                'wiki_domain': wiki_domain,
                'bot_username': bot_username,
                'bot_password': bot_password
            })
            result = adapter.test_connection()
            return jsonify(result)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    else:
        wiki_domain = data.get('wiki_domain', '').strip()
        bot_username = data.get('bot_username', '').strip()
        bot_password = data.get('bot_password', '')

        if not all([wiki_domain, bot_username, bot_password]):
            return jsonify({'success': False, 'error': 'All fields are required'})

        # Test connection using adapter
        try:
            if platform == 'wikigg':
                domain = f"{wiki_domain}.wiki.gg"
                api_path = '/api.php'
            elif platform == 'shoutwiki':
                domain = f"{wiki_domain}.shoutwiki.com"
                api_path = '/w/api.php'
            else:
                domain = wiki_domain
                api_path = '/api.php' if platform == 'telepedia' else '/w/api.php'
            adapter = MediaWikiAdapter({
                'wiki_domain': domain,
                'bot_username': bot_username,
                'bot_password': bot_password,
                'api_path': api_path
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
    links_config = load_links_config(project_id)

    return render_template('yaml_editor.html',
                           project=project,
                           pages_config=pages_config,
                           links_config=links_config)


@app.route('/project/<project_id>/live-pages', methods=['GET'])
def project_live_pages(project_id):
    """List live pages from the project's wiki."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    try:
        adapter = get_adapter(project)

        if not adapter.login():
            return jsonify({'success': False, 'error': 'Failed to login to wiki'}), 401

        raw_limit = request.args.get('limit', '200')
        try:
            limit = max(1, min(500, int(raw_limit)))
        except ValueError:
            limit = 200

        pages = adapter.list_pages(limit=limit)
        return jsonify({'success': True, 'pages': pages, 'count': len(pages)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/project/<project_id>/live-page', methods=['GET'])
def project_live_page_content(project_id):
    """Get wiki page content and HTML preview."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    title = request.args.get('title', '').strip()
    if not title:
        return jsonify({'success': False, 'error': 'Missing title'}), 400

    try:
        adapter = get_adapter(project)

        if not adapter.login():
            return jsonify({'success': False, 'error': 'Failed to login to wiki'}), 401

        content = adapter.get_page(title)
        if content is None:
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        html = adapter.parse_page(content, title=title)

        return jsonify({
            'success': True,
            'title': title,
            'content': content,
            'html': html
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/project/<project_id>/live-page', methods=['POST'])
def project_live_page_save(project_id):
    """Save wiki page content."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    content = data.get('content') or ''
    summary = (data.get('summary') or 'Updated via Wiki Generator').strip()

    if not title:
        return jsonify({'success': False, 'error': 'Missing title'}), 400

    try:
        adapter = get_adapter(project)

        if not adapter.login():
            return jsonify({'success': False, 'error': 'Failed to login to wiki'}), 401

        success = adapter.upload_page(title, content, summary=summary)
        if not success:
            return jsonify({'success': False, 'error': 'Failed to save page'}), 500

        html = adapter.parse_page(content, title=title)

        return jsonify({'success': True, 'title': title, 'html': html})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/project/<project_id>/live-page/preview', methods=['POST'])
def project_live_page_preview(project_id):
    """Render wikitext as HTML without saving."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    content = data.get('content') or ''

    if not content.strip():
        return jsonify({'success': False, 'error': 'Missing content'}), 400

    try:
        adapter = get_adapter(project)

        if not adapter.login():
            return jsonify({'success': False, 'error': 'Failed to login to wiki'}), 401

        html = adapter.parse_page(content, title=title)
        return jsonify({'success': True, 'html': html})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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


@app.route('/project/<project_id>/links', methods=['GET'])
def get_links(project_id):
    """Get link bank for a project (AJAX)."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'})

    links_config = load_links_config(project_id)
    return jsonify({'success': True, 'links': links_config.get('link_targets', [])})


@app.route('/project/<project_id>/links/save', methods=['POST'])
def save_links(project_id):
    """Save link bank for a project (AJAX)."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'})

    try:
        data = request.get_json()
        link_targets = data.get('link_targets', [])
        save_links_config(project_id, {'link_targets': link_targets})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/project/<project_id>/structure/import', methods=['POST'])
def import_structure(project_id):
    """Parse pasted YAML and return normalized config."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    data = request.get_json() or {}
    raw_yaml = (data.get('yaml') or '').strip()
    if not raw_yaml:
        return jsonify({'success': False, 'error': 'YAML input is empty'}), 400

    try:
        parsed = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as e:
        return jsonify({'success': False, 'error': f'YAML parse error: {e}'}), 400

    if not isinstance(parsed, dict):
        return jsonify({'success': False, 'error': 'YAML must define a mapping at the top level'}), 400

    wiki_block = parsed.get('wiki') if isinstance(parsed.get('wiki'), dict) else {}
    pages = parsed.get('pages', [])
    if not pages:
        pages = wiki_block.get('pages', [])
    if pages is None:
        pages = []
    if not isinstance(pages, list):
        return jsonify({'success': False, 'error': 'pages must be a list'}), 400

    normalized_pages = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        title = str(page.get('title', '')).strip()
        if not title:
            continue

        normalized_pages.append({
            'title': title,
            'category': page.get('category', parsed.get('default_category', wiki_block.get('default_category', 'General'))) or 'General',
            'description': page.get('description', '') or '',
            'key_points': page.get('key_points', []) or [],
            'related_pages': page.get('related_pages', []) or []
        })

    config = {
        'wiki_name': parsed.get('wiki_name', wiki_block.get('name', '')),
        'default_category': parsed.get('default_category', wiki_block.get('default_category', 'General')),
        'pages': normalized_pages
    }

    return jsonify({'success': True, 'config': config})


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
    project = load_project(project_id)
    if not project:
        progress['status'] = 'error'
        progress['error'] = 'Project not found'
        return

    try:
        links_config = load_links_config(project_id)
        link_targets = links_config.get('link_targets', [])

        generator = WikiContentGenerator(
            str(yaml_path),
            api_key,
            content_format=project.get('platform', 'miraheze'),
            link_targets=link_targets
        )

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
                extension = '.html' if generator.content_format == 'confluence' else '.wiki'
                filename = title.replace(' ', '_').replace('/', '_') + extension
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
        for ext in ('*.wiki', '*.html'):
            for wiki_file in generated_dir.glob(ext):
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
        adapter = get_adapter(project)

        if not adapter.login():
            progress['status'] = 'error'
            progress['error'] = 'Failed to login to wiki'
            return

        for i, filename in enumerate(selected_pages):
            progress['current_page'] = filename.replace('.wiki', '').replace('.html', '').replace('_', ' ')

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
            'pages': [f.replace('.wiki', '').replace('.html', '').replace('_', ' ') for f in progress['completed']]
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

    port = int(os.environ.get('PORT', 8500))
    app.run(debug=False, host='0.0.0.0', port=port)
