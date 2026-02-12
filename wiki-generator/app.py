#!/usr/bin/env python3
"""
Wiki Generator - Flask Web Application

A web interface for generating and publishing wiki content using AI.
"""

import csv
import io
import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from urllib.parse import unquote
from pathlib import Path
from typing import Optional

import yaml
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, Response

from config import config
from adapters.mediawiki import MediaWikiAdapter
from adapters.confluence import ConfluenceAdapter

app = Flask(__name__)
app.config.from_object(config['default'])

# Store for generation/upload progress (in production, use Redis or similar)
progress_store = {}
SETTINGS_PATH = Path(app.config['PROJECTS_DIR']).parent / 'settings.json'
SECRETS_PATH = Path(app.config['PROJECTS_DIR']).parent / 'secrets.json'

# Allow HTTP OAuth redirect for local development only.
if app.config.get('DEBUG'):
    os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')


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


def load_settings():
    """Load app settings from disk."""
    if not SETTINGS_PATH.exists():
        return {}
    with open(SETTINGS_PATH, 'r') as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def save_settings(data):
    """Save app settings to disk."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(data, f, indent=2)


def load_secrets():
    """Load secrets from disk."""
    if not SECRETS_PATH.exists():
        return {}
    with open(SECRETS_PATH, 'r') as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def save_secrets(data):
    """Save secrets to disk."""
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SECRETS_PATH, 'w') as f:
        json.dump(data, f, indent=2)


def get_gsc_entry(project_id):
    """Get stored GSC entry for a project."""
    secrets = load_secrets()
    return (secrets.get('gsc') or {}).get(project_id, {})


def save_gsc_entry(project_id, entry):
    """Save GSC entry for a project."""
    secrets = load_secrets()
    secrets.setdefault('gsc', {})
    secrets['gsc'][project_id] = entry
    save_secrets(secrets)


def remove_gsc_entry(project_id):
    """Remove GSC entry for a project."""
    secrets = load_secrets()
    if 'gsc' in secrets and project_id in secrets['gsc']:
        secrets['gsc'].pop(project_id, None)
        save_secrets(secrets)


def build_gsc_flow(settings, state):
    """Build Google OAuth flow for Search Console."""
    from google_auth_oauthlib.flow import Flow

    client_id = settings.get('google_oauth_client_id')
    client_secret = settings.get('google_oauth_client_secret')
    redirect_uri = settings.get('google_oauth_redirect_uri')
    scopes = settings.get('google_oauth_scopes') or [
        'https://www.googleapis.com/auth/webmasters.readonly'
    ]

    if not all([client_id, client_secret, redirect_uri]):
        raise ValueError('Google OAuth settings are incomplete')

    client_config = {
        'web': {
            'client_id': client_id,
            'client_secret': client_secret,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token'
        }
    }

    flow = Flow.from_client_config(client_config, scopes=scopes, state=state)
    flow.redirect_uri = redirect_uri
    return flow


def get_gsc_service(project_id):
    """Create an authenticated Search Console service client."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    entry = get_gsc_entry(project_id)
    token_info = entry.get('token')
    if not token_info:
        return None

    credentials = Credentials(
        token=token_info.get('token'),
        refresh_token=token_info.get('refresh_token'),
        token_uri=token_info.get('token_uri'),
        client_id=token_info.get('client_id'),
        client_secret=token_info.get('client_secret'),
        scopes=token_info.get('scopes')
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_info = json.loads(credentials.to_json())
        entry['token'] = token_info
        save_gsc_entry(project_id, entry)

    return build('searchconsole', 'v1', credentials=credentials)


def list_gsc_properties(project_id):
    """List Search Console properties for a project."""
    service = get_gsc_service(project_id)
    if not service:
        return []

    response = service.sites().list().execute()
    entries = response.get('siteEntry', [])
    return sorted({entry.get('siteUrl') for entry in entries if entry.get('siteUrl')})


def get_adapter(project: dict):
    """Return the appropriate adapter for a project."""
    platform = project.get('platform', 'miraheze')
    if platform == 'confluence':
        return ConfluenceAdapter({
            'base_url': project['base_url'],
            'space_key': project['space_key'],
            'user_email': project['user_email'],
            'api_token': project['api_token']
        })

    return MediaWikiAdapter({
        'wiki_domain': project['wiki_domain'],
        'bot_username': project['bot_username'],
        'bot_password': project['bot_password'],
        'api_path': project.get('api_path', '/w/api.php')
    })


def rewrite_confluence_internal_links(content: str, space_key: str) -> str:
    """Convert internal Confluence href links into storage <ac:link> tags."""
    import re

    if not content:
        return content

    if not space_key:
        return content

    link_pattern = re.compile(
        r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL
    )
    display_pattern = re.compile(rf'/display/{re.escape(space_key)}/([^#?]+)', re.IGNORECASE)
    pages_pattern = re.compile(rf'/wiki/spaces/{re.escape(space_key)}/pages/\d+/([^#?]+)', re.IGNORECASE)

    def extract_title_from_href(href: str) -> Optional[str]:
        match = display_pattern.search(href) or pages_pattern.search(href)
        if not match:
            return None
        raw_title = match.group(1)
        return unquote(raw_title.replace('+', ' ')).strip() or None

    def strip_tags(text: str) -> str:
        return re.sub(r'<[^>]+>', '', text).strip()

    def replace_link(match: re.Match) -> str:
        href = match.group(1)
        inner_html = match.group(2)
        title = extract_title_from_href(href)
        if not title:
            return match.group(0)

        label = strip_tags(inner_html)
        if label and label != title:
            return (
                f'<ac:link><ri:page ri:space-key="{space_key}" '
                f'ri:content-title="{title}"/><ac:link-body>{label}'
                f'</ac:link-body></ac:link>'
            )
        return f'<ac:link><ri:page ri:space-key="{space_key}" ri:content-title="{title}"/></ac:link>'

    return link_pattern.sub(replace_link, content)


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
        return {'links': []}
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or 'links' not in data:
        return {'links': []}
    return data


def save_links_config(project_id, config):
    """Save links.yaml for a project."""
    project_dir = get_project_path(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = project_dir / 'links.yaml'
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def load_masking_links_config(project_id):
    """Load masking_links.yaml for a project."""
    yaml_path = get_project_path(project_id) / 'masking_links.yaml'
    if not yaml_path.exists():
        return {'masking_links': []}
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or 'masking_links' not in data:
        return {'masking_links': []}
    return data


def save_masking_links_config(project_id, config):
    """Save masking_links.yaml for a project."""
    project_dir = get_project_path(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = project_dir / 'masking_links.yaml'
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


@app.route('/projects', methods=['GET'])
def all_projects():
    """All projects page."""
    projects = get_all_projects()
    return render_template('projects.html', projects=projects)


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Application settings page."""
    settings_data = load_settings()

    if request.method == 'POST':
        scopes_raw = request.form.get('google_oauth_scopes', '')
        settings_data = {
            'google_oauth_client_id': request.form.get('google_oauth_client_id', '').strip(),
            'google_oauth_client_secret': request.form.get('google_oauth_client_secret', '').strip(),
            'google_oauth_redirect_uri': request.form.get('google_oauth_redirect_uri', '').strip(),
            'google_oauth_scopes': [s.strip() for s in scopes_raw.split(',') if s.strip()],
            'notes': request.form.get('notes', '').strip()
        }

        save_settings(settings_data)
        flash('Settings saved', 'success')
        return redirect(url_for('settings'))

    return render_template('settings.html', settings=settings_data)


@app.route('/project/<project_id>/gsc', methods=['GET'])
def project_gsc(project_id):
    """Google Search Console settings and data."""
    project = load_project(project_id)
    if not project:
        flash('Project not found', 'error')
        return redirect(url_for('index'))

    settings_data = load_settings()
    entry = get_gsc_entry(project_id)
    connected = bool(entry.get('token'))
    property_url = entry.get('property')
    properties = []
    load_error = None

    if connected and not property_url:
        try:
            properties = list_gsc_properties(project_id)
        except Exception as e:
            load_error = str(e)

    end_date = datetime.utcnow().date() - timedelta(days=3)
    start_date = end_date - timedelta(days=27)

    return render_template(
        'gsc.html',
        project=project,
        settings=settings_data,
        connected=connected,
        property_url=property_url,
        properties=properties,
        gsc_error=load_error,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat()
    )


@app.route('/project/<project_id>/gsc/connect', methods=['GET'])
def gsc_connect(project_id):
    """Start OAuth flow for GSC."""
    project = load_project(project_id)
    if not project:
        flash('Project not found', 'error')
        return redirect(url_for('index'))

    settings_data = load_settings()
    state = str(uuid.uuid4())

    try:
        flow = build_gsc_flow(settings_data, state)
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
    except Exception as e:
        flash(f'Failed to start OAuth: {e}', 'error')
        return redirect(url_for('project_gsc', project_id=project_id))

    session['gsc_oauth_state'] = state
    session['gsc_oauth_project'] = project_id

    return redirect(authorization_url)


@app.route('/oauth/google/callback', methods=['GET'])
def gsc_oauth_callback():
    """OAuth callback for Google Search Console."""
    state = request.args.get('state')
    expected_state = session.get('gsc_oauth_state')
    project_id = session.get('gsc_oauth_project')

    if not state or state != expected_state or not project_id:
        flash('OAuth state mismatch. Please try connecting again.', 'error')
        return redirect(url_for('index'))

    settings_data = load_settings()

    try:
        flow = build_gsc_flow(settings_data, state)
        flow.fetch_token(authorization_response=request.url)
        token_info = json.loads(flow.credentials.to_json())
    except Exception as e:
        flash(f'Failed to complete OAuth: {e}', 'error')
        return redirect(url_for('project_gsc', project_id=project_id))

    entry = get_gsc_entry(project_id)
    entry['token'] = token_info
    save_gsc_entry(project_id, entry)

    flash('Google Search Console connected. Select a property to continue.', 'success')
    return redirect(url_for('project_gsc', project_id=project_id))


@app.route('/project/<project_id>/gsc/property', methods=['POST'])
def gsc_set_property(project_id):
    """Save the selected GSC property for a project."""
    project = load_project(project_id)
    if not project:
        flash('Project not found', 'error')
        return redirect(url_for('index'))

    property_url = request.form.get('property_url', '').strip()
    if not property_url:
        flash('Please select a property.', 'error')
        return redirect(url_for('project_gsc', project_id=project_id))

    entry = get_gsc_entry(project_id)
    entry['property'] = property_url
    save_gsc_entry(project_id, entry)

    flash('Property saved.', 'success')
    return redirect(url_for('project_gsc', project_id=project_id))


@app.route('/project/<project_id>/gsc/disconnect', methods=['POST'])
def gsc_disconnect(project_id):
    """Disconnect GSC for a project."""
    project = load_project(project_id)
    if not project:
        flash('Project not found', 'error')
        return redirect(url_for('index'))

    remove_gsc_entry(project_id)
    flash('GSC disconnected.', 'success')
    return redirect(url_for('project_gsc', project_id=project_id))


@app.route('/project/<project_id>/gsc/data', methods=['POST'])
def gsc_data(project_id):
    """Fetch GSC query data."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    entry = get_gsc_entry(project_id)
    property_url = entry.get('property')
    if not property_url:
        return jsonify({'success': False, 'error': 'No GSC property selected'}), 400

    data = request.get_json() or {}
    start_date = (data.get('start_date') or '').strip()
    end_date = (data.get('end_date') or '').strip()
    row_limit = data.get('row_limit') or 100

    try:
        row_limit = max(1, min(250, int(row_limit)))
    except ValueError:
        row_limit = 100

    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'Start and end dates are required'}), 400

    try:
        datetime.fromisoformat(start_date)
        datetime.fromisoformat(end_date)
    except ValueError:
        return jsonify({'success': False, 'error': 'Dates must be in YYYY-MM-DD format'}), 400

    try:
        service = get_gsc_service(project_id)
        if not service:
            return jsonify({'success': False, 'error': 'GSC not connected'}), 401

        request_body = {
            'startDate': start_date,
            'endDate': end_date,
            'dimensions': ['query'],
            'rowLimit': row_limit
        }

        response = service.searchanalytics().query(siteUrl=property_url, body=request_body).execute()
        rows = response.get('rows', [])

        items = []
        totals = {'clicks': 0, 'impressions': 0, 'ctr': 0, 'position': 0}

        for row in rows:
            query = (row.get('keys') or [''])[0]
            clicks = row.get('clicks', 0)
            impressions = row.get('impressions', 0)
            ctr = row.get('ctr', 0)
            position = row.get('position', 0)

            totals['clicks'] += clicks
            totals['impressions'] += impressions
            totals['position'] += position

            items.append({
                'query': query,
                'clicks': clicks,
                'impressions': impressions,
                'ctr': ctr,
                'position': position
            })

        if items:
            totals['ctr'] = (totals['clicks'] / totals['impressions']) if totals['impressions'] else 0
            totals['position'] = totals['position'] / len(items)

        return jsonify({'success': True, 'rows': items, 'totals': totals})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/project/<project_id>/gsc/export', methods=['GET'])
def gsc_export(project_id):
    """Export GSC query data as CSV."""
    project = load_project(project_id)
    if not project:
        flash('Project not found', 'error')
        return redirect(url_for('index'))

    entry = get_gsc_entry(project_id)
    property_url = entry.get('property')
    if not property_url:
        flash('No GSC property selected', 'error')
        return redirect(url_for('project_gsc', project_id=project_id))

    start_date = (request.args.get('start_date') or '').strip()
    end_date = (request.args.get('end_date') or '').strip()
    row_limit = request.args.get('row_limit') or '100'

    try:
        row_limit = max(1, min(250, int(row_limit)))
    except ValueError:
        row_limit = 100

    if not start_date or not end_date:
        flash('Start and end dates are required', 'error')
        return redirect(url_for('project_gsc', project_id=project_id))

    try:
        datetime.fromisoformat(start_date)
        datetime.fromisoformat(end_date)
    except ValueError:
        flash('Dates must be in YYYY-MM-DD format', 'error')
        return redirect(url_for('project_gsc', project_id=project_id))

    try:
        service = get_gsc_service(project_id)
        if not service:
            flash('GSC not connected', 'error')
            return redirect(url_for('project_gsc', project_id=project_id))

        request_body = {
            'startDate': start_date,
            'endDate': end_date,
            'dimensions': ['query'],
            'rowLimit': row_limit
        }

        response = service.searchanalytics().query(siteUrl=property_url, body=request_body).execute()
        rows = response.get('rows', [])

        def generate():
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['query', 'clicks', 'impressions', 'ctr', 'position'])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

            for row in rows:
                query = (row.get('keys') or [''])[0]
                writer.writerow([
                    query,
                    row.get('clicks', 0),
                    row.get('impressions', 0),
                    row.get('ctr', 0),
                    row.get('position', 0)
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

        filename = f"gsc_{project_id}_{start_date}_to_{end_date}.csv"
        return Response(
            generate(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        flash(f'Failed to export CSV: {e}', 'error')
        return redirect(url_for('project_gsc', project_id=project_id))


@app.route('/project/new', methods=['GET', 'POST'])
def new_project():
    """Create new project page."""
    if request.method == 'POST':
        # Validate and create project
        name = request.form.get('name', '').strip()
        platform = request.form.get('platform', 'miraheze').strip()

        if platform == 'confluence':
            base_url = request.form.get('base_url', '').strip()
            space_key = request.form.get('space_key', '').strip()
            user_email = request.form.get('user_email', '').strip()
            api_token = request.form.get('api_token', '')

            if not all([name, base_url, space_key, user_email, api_token]):
                flash('All fields are required', 'error')
                return render_template('new_project.html')
        else:
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
            'platform': platform,
            'created_at': datetime.now().isoformat()
        }

        if platform == 'confluence':
            project_data.update({
                'base_url': base_url,
                'space_key': space_key,
                'user_email': user_email,
                'api_token': api_token  # In production, encrypt this
            })
        else:
            project_data.update({
                'wiki_domain': wiki_domain,
                'bot_username': bot_username,
                'bot_password': bot_password,  # In production, encrypt this
                'api_path': '/w/api.php'
            })

        save_project(project_id, project_data)

        flash('Project created successfully', 'success')
        return redirect(url_for('project_structure', project_id=project_id))

    return render_template('new_project.html')


@app.route('/project/<project_id>/settings', methods=['GET', 'POST'])
def project_settings(project_id):
    """Edit project settings (credentials, name, etc.)."""
    project = load_project(project_id)
    if not project:
        flash('Project not found', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        platform = project.get('platform', 'miraheze')

        if platform == 'confluence':
            project['name'] = name or project['name']
            project['base_url'] = request.form.get('base_url', '').strip() or project.get('base_url', '')
            project['space_key'] = request.form.get('space_key', '').strip() or project.get('space_key', '')
            project['user_email'] = request.form.get('user_email', '').strip() or project.get('user_email', '')
            api_token = request.form.get('api_token', '')
            if api_token:
                project['api_token'] = api_token
        else:
            project['name'] = name or project['name']
            project['wiki_domain'] = request.form.get('wiki_domain', '').strip() or project.get('wiki_domain', '')
            project['bot_username'] = request.form.get('bot_username', '').strip() or project.get('bot_username', '')
            bot_password = request.form.get('bot_password', '')
            if bot_password:
                project['bot_password'] = bot_password

        save_project(project_id, project)
        flash('Project settings updated', 'success')
        return redirect(url_for('project_settings', project_id=project_id))

    return render_template('project_settings.html', project=project, project_id=project_id)


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
    else:
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
    links_config = load_links_config(project_id)
    masking_links_config = load_masking_links_config(project_id)

    return render_template('yaml_editor.html',
                           project=project,
                           pages_config=pages_config,
                           links_config=links_config,
                           masking_links_config=masking_links_config)


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
    """Get link bank JSON (AJAX)."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    config = load_links_config(project_id)
    return jsonify({'success': True, 'links': config.get('links', [])})


@app.route('/project/<project_id>/links/save', methods=['POST'])
def save_links(project_id):
    """Save link bank JSON (AJAX)."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    try:
        data = request.get_json()
        links = data.get('links', [])
        save_links_config(project_id, {'links': links})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/project/<project_id>/masking-links', methods=['GET'])
def get_masking_links(project_id):
    """Return masking links JSON."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    config = load_masking_links_config(project_id)
    return jsonify({'success': True, 'masking_links': config.get('masking_links', [])})


@app.route('/project/<project_id>/masking-links/save', methods=['POST'])
def save_masking_links(project_id):
    """Save masking link bank JSON (AJAX)."""
    project = load_project(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    try:
        data = request.get_json()
        masking_links = data.get('masking_links', [])
        save_masking_links_config(project_id, {'masking_links': masking_links})
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
    live_pages = data.get('live_pages', [])
    mode = data.get('mode', 'full')

    if not api_key:
        return jsonify({'success': False, 'error': 'API key is required'})

    if not selected_pages and not live_pages:
        return jsonify({'success': False, 'error': 'No pages selected'})

    if mode not in ('full', 'add_masking', 'add_operator'):
        mode = 'full'

    total_pages = len(selected_pages) + (len(live_pages) if mode != 'full' else 0)

    # Initialize progress tracking
    progress_store[project_id] = {
        'status': 'starting',
        'total': total_pages,
        'completed': 0,
        'current_page': '',
        'percent': 0,
        'success': [],
        'failed': []
    }

    # Start generation in background thread
    thread = threading.Thread(
        target=run_generation,
        args=(project_id, api_key, selected_pages, mode, live_pages)
    )
    thread.daemon = True
    thread.start()

    return jsonify({'success': True})


def run_generation(project_id, api_key, selected_pages, mode='full', live_pages=None):
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
        generator = WikiContentGenerator(
            str(yaml_path),
            api_key,
            content_format=project.get('platform', 'miraheze'),
            space_key=project.get('space_key')
        )

        # Load global links and pass to generator
        links_config = load_links_config(project_id)
        links = links_config.get('links', [])
        print(f"[Generation] Project {project_id}: loaded {len(links)} links from links.yaml")
        if not links:
            print(f"[Generation] WARNING: No links found in link bank for project {project_id}")
        generator.set_global_links(links)

        # Load masking links and pass to generator
        masking_config = load_masking_links_config(project_id)
        masking_links = masking_config.get('masking_links', [])
        print(f"[Generation] Project {project_id}: loaded {len(masking_links)} masking links")
        generator.set_masking_links(masking_links)

        for i, title in enumerate(selected_pages):
            progress['current_page'] = title
            progress['status'] = 'generating'

            page = generator.get_page_by_title(title)
            if not page:
                progress['failed'].append(title)
                continue

            try:
                if generator.content_format == 'confluence':
                    extension = '.html'
                else:
                    extension = '.wiki'
                filename = title.replace(' ', '_').replace('/', '_') + extension
                filepath = output_dir / filename

                if mode in ('add_masking', 'add_operator'):
                    # Edit pass: read existing content and add links
                    if not filepath.exists():
                        print(f"[Generation] Skipping '{title}': no existing content for edit pass")
                        progress['failed'].append(title)
                        progress['completed'] = i + 1
                        progress['percent'] = int(((i + 1) / len(selected_pages)) * 100)
                        continue
                    existing_content = filepath.read_text(encoding='utf-8')
                    content = generator.add_links_to_existing(existing_content, page, mode)
                else:
                    content = generator.generate_page(page)

                # Save to file
                if generator.content_format == 'confluence':
                    content = rewrite_confluence_internal_links(content, project.get('space_key', ''))
                filepath.write_text(content, encoding='utf-8')

                progress['success'].append(title)
            except Exception as e:
                progress['failed'].append(title)
                print(f"Error generating {title}: {e}")

            progress['completed'] = i + 1
            progress['percent'] = int(((i + 1) / progress['total']) * 100)

        # Process live wiki pages (edit passes only)
        if live_pages and mode in ('add_masking', 'add_operator'):
            adapter = get_adapter(project)
            logged_in = adapter.login()
            if not logged_in:
                print(f"[Generation] WARNING: Failed to login to wiki for live page fetching")

            base_idx = len(selected_pages)
            for j, title in enumerate(live_pages):
                progress['current_page'] = title
                progress['status'] = 'generating'

                try:
                    if not logged_in:
                        print(f"[Generation] Skipping live page '{title}': not logged in")
                        progress['failed'].append(title)
                        continue

                    existing_content = adapter.get_page(title)
                    if not existing_content:
                        print(f"[Generation] Skipping live page '{title}': no content found on wiki")
                        progress['failed'].append(title)
                        continue

                    page = {'title': title}
                    content = generator.add_links_to_existing(existing_content, page, mode)

                    # Save to file
                    if generator.content_format == 'confluence':
                        content = rewrite_confluence_internal_links(content, project.get('space_key', ''))
                        extension = '.html'
                    else:
                        extension = '.wiki'
                    filename = title.replace(' ', '_').replace('/', '_') + extension
                    filepath = output_dir / filename
                    filepath.write_text(content, encoding='utf-8')

                    progress['success'].append(title)
                except Exception as e:
                    progress['failed'].append(title)
                    print(f"Error processing live page {title}: {e}")

                progress['completed'] = base_idx + j + 1
                progress['percent'] = int(((base_idx + j + 1) / progress['total']) * 100)

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

    # Filter to last run if available
    total_page_count = len(generated_pages)
    last_run = progress_store.get(project_id, {})
    last_run_titles = last_run.get('success', []) + last_run.get('failed', [])
    show_all = request.args.get('all') == '1'
    has_filter = bool(last_run_titles) and len(last_run_titles) < total_page_count

    if has_filter and not show_all:
        last_run_set = {t.replace(' ', '_') for t in last_run_titles}
        generated_pages = [p for p in generated_pages if p['filename'].rsplit('.', 1)[0] in last_run_set]
        if not generated_pages:
            generated_pages = [p for p in generated_pages] if not generated_pages else generated_pages
            has_filter = False

    # Build external link summary from link bank
    links_config = load_links_config(project_id)
    bank_links = links_config.get('links', [])
    link_summary = []

    if bank_links and generated_dir.exists():
        # Scan each generated file for link bank URLs
        for link in bank_links:
            url = link.get('url', '')
            if not url:
                continue
            anchors = link.get('anchors', [])
            target_count = link.get('count', 0)
            placed_on = []

            for ext in ('*.wiki', '*.html'):
                for wiki_file in generated_dir.glob(ext):
                    content = wiki_file.read_text(encoding='utf-8')
                    if url in content:
                        placed_on.append(wiki_file.stem.replace('_', ' '))

            link_summary.append({
                'url': url,
                'anchors': anchors,
                'target_count': target_count,
                'actual_count': len(placed_on),
                'pages': placed_on
            })

    return render_template('review.html',
                           project=project,
                           generated_pages=generated_pages,
                           link_summary=link_summary,
                           show_all=show_all,
                           has_filter=has_filter,
                           total_page_count=total_page_count)


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

    app.run(debug=True, port=5000)
