"""Confluence adapter."""
from __future__ import annotations

import base64
from typing import Optional, Callable

import requests

from .base import BaseAdapter


class ConfluenceAdapter(BaseAdapter):
    """Adapter for Atlassian Confluence (Cloud)."""

    def __init__(self, config: dict):
        """
        Initialize Confluence adapter.

        Args:
            config: dict with keys:
                - base_url: e.g., 'https://your-domain.atlassian.net/wiki'
                - space_key: Confluence space key
                - user_email: Confluence user email
                - api_token: Confluence API token
        """
        self.config = config
        self.base_url = config['base_url'].rstrip('/')
        self.space_key = config['space_key']

        user_email = config['user_email']
        api_token = config['api_token']
        token = base64.b64encode(f"{user_email}:{api_token}".encode('utf-8')).decode('ascii')

        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Basic {token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'WikiGeneratorBot/1.0 (Confluence adapter)'
        })

        self.api_url = f"{self.base_url}/rest/api"
        self.max_retries = int(config.get('max_retries', 3))

    def test_connection(self) -> dict:
        """Test connection to Confluence API and access to the space."""
        result = {
            'success': False,
            'api_accessible': False,
            'login_success': False,
            'edit_permission': False,
            'site_name': None,
            'error': None
        }

        try:
            response = self.session.get(f"{self.api_url}/space", params={'spaceKey': self.space_key}, timeout=10)
            if response.status_code == 401:
                result['error'] = 'Authentication failed - check email and API token'
                return result
            response.raise_for_status()
            data = response.json()
            result['api_accessible'] = True
            if data.get('results'):
                result['site_name'] = data['results'][0].get('name')
                result['login_success'] = True
                result['edit_permission'] = True
                result['success'] = True
            else:
                result['error'] = 'Space not found'
        except requests.exceptions.Timeout:
            result['error'] = 'Connection timed out'
        except requests.exceptions.ConnectionError:
            result['error'] = 'Could not connect to Confluence'
        except Exception as e:
            result['error'] = f'Connection error: {str(e)}'

        return result

    def login(self) -> bool:
        """Authenticate by verifying access to the space."""
        try:
            response = self.session.get(f"{self.api_url}/space", params={'spaceKey': self.space_key}, timeout=10)
            return response.status_code == 200
        except Exception:
            return False

    def _get_page_by_title(self, title: str) -> Optional[dict]:
        """Fetch a page by title within the configured space."""
        try:
            response = self.session.get(
                f"{self.api_url}/content",
                params={
                    'spaceKey': self.space_key,
                    'title': title,
                    'type': 'page',
                    'expand': 'version,body.storage'
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            return None

        results = data.get('results', [])
        return results[0] if results else None

    def upload_page(self, title: str, content: str, summary: str = "Updated via Wiki Generator") -> bool:
        """Create or update a Confluence page."""
        existing = self._get_page_by_title(title)

        payload = {
            'type': 'page',
            'title': title,
            'space': {'key': self.space_key},
            'body': {
                'storage': {
                    'value': content,
                    'representation': 'storage'
                }
            }
        }

        try:
            if existing:
                page_id = existing.get('id')
                version = existing.get('version', {}).get('number', 1)
                payload['version'] = {'number': version + 1, 'message': summary}
                response = self.session.put(f"{self.api_url}/content/{page_id}", json=payload, timeout=15)
            else:
                response = self.session.post(f"{self.api_url}/content", json=payload, timeout=15)

            return response.status_code in (200, 201)
        except Exception:
            return False

    def upload_directory(
        self,
        content_dir: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> dict:
        """Upload all .html files from a directory."""
        from pathlib import Path

        content_path = Path(content_dir)
        results = {'success': [], 'failed': []}

        if not content_path.exists():
            return results

        html_files = list(content_path.glob('**/*.html'))
        total = len(html_files)

        for i, html_file in enumerate(html_files, 1):
            title = html_file.stem.replace('_', ' ')
            content = html_file.read_text(encoding='utf-8')

            if progress_callback:
                progress_callback(i, total, title)

            if self.upload_page(title, content):
                results['success'].append(title)
            else:
                results['failed'].append(title)

        return results

    def get_page(self, title: str) -> Optional[str]:
        """Get page content in storage format."""
        page = self._get_page_by_title(title)
        if not page:
            return None
        return page.get('body', {}).get('storage', {}).get('value')

    def list_pages(self, namespace: int = 0, limit: int = 500) -> list:
        """List all pages in the space."""
        pages = []
        start = 0

        while True:
            try:
                response = self.session.get(
                    f"{self.api_url}/content",
                    params={
                        'spaceKey': self.space_key,
                        'type': 'page',
                        'limit': min(limit - len(pages), 200),
                        'start': start
                    },
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
            except Exception:
                break

            results = data.get('results', [])
            for page in results:
                pages.append(page.get('title', ''))

            if len(pages) >= limit or not data.get('_links', {}).get('next'):
                break

            start += len(results)

        return pages[:limit]

    def parse_page(self, content: str, title: Optional[str] = None) -> str:
        """Storage format is HTML-ish already, return as-is."""
        return content

    @staticmethod
    def get_content_extension() -> str:
        return '.html'

    @staticmethod
    def get_platform_name() -> str:
        return 'Confluence'
