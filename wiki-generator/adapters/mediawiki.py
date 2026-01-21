"""MediaWiki/Miraheze adapter."""
import time
from pathlib import Path
from typing import Optional, Callable

import requests

from .base import BaseAdapter


class MediaWikiAdapter(BaseAdapter):
    """Adapter for MediaWiki-based platforms (Miraheze, Wikipedia, etc.)."""

    def __init__(self, config: dict):
        """
        Initialize MediaWiki adapter.

        Args:
            config: dict with keys:
                - wiki_domain: e.g., 'example.miraheze.org'
                - bot_username: Bot username
                - bot_password: Bot password
                - api_path: Optional, defaults to '/w/api.php'
                - rate_limit_delay: Optional, defaults to 1.0
                - max_retries: Optional, defaults to 3
        """
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'WikiGeneratorBot/1.0 (Flask wiki generator)'
        })

        self.api_url = f"https://{config['wiki_domain']}{config.get('api_path', '/w/api.php')}"
        self.rate_limit_delay = config.get('rate_limit_delay', 1.0)
        self.max_retries = config.get('max_retries', 3)
        self._csrf_token: Optional[str] = None

    def test_connection(self) -> dict:
        """Test connection to the MediaWiki API."""
        result = {
            'success': False,
            'api_accessible': False,
            'login_success': False,
            'edit_permission': False,
            'site_name': None,
            'error': None
        }

        # Test API accessibility
        try:
            params = {'action': 'query', 'meta': 'siteinfo', 'format': 'json'}
            response = self.session.get(self.api_url, params=params, timeout=10)
            data = response.json()

            if 'query' in data:
                result['api_accessible'] = True
                result['site_name'] = data['query']['general'].get('sitename', 'Unknown')
            else:
                result['error'] = 'Unexpected API response'
                return result
        except requests.exceptions.Timeout:
            result['error'] = 'Connection timed out'
            return result
        except requests.exceptions.ConnectionError:
            result['error'] = 'Could not connect to wiki'
            return result
        except Exception as e:
            result['error'] = f'Connection error: {str(e)}'
            return result

        # Test authentication
        if self.login():
            result['login_success'] = True

            # Test edit permissions
            try:
                token = self._get_csrf_token()
                if token and token != '+\\':
                    result['edit_permission'] = True
                    result['success'] = True
            except Exception:
                result['edit_permission'] = False
                result['success'] = True
        else:
            result['error'] = 'Authentication failed - check username and password'

        return result

    def login(self) -> bool:
        """Login to MediaWiki using bot credentials."""
        # Step 1: Get login token
        params = {
            'action': 'query',
            'meta': 'tokens',
            'type': 'login',
            'format': 'json'
        }

        try:
            response = self.session.get(self.api_url, params=params, timeout=10)
            data = response.json()
        except Exception:
            return False

        if 'query' not in data or 'tokens' not in data['query']:
            return False

        login_token = data['query']['tokens']['logintoken']

        # Step 2: Login with bot password
        login_params = {
            'action': 'login',
            'lgname': self.config['bot_username'],
            'lgpassword': self.config['bot_password'],
            'lgtoken': login_token,
            'format': 'json'
        }

        try:
            response = self.session.post(self.api_url, data=login_params, timeout=10)
            data = response.json()
        except Exception:
            return False

        return data.get('login', {}).get('result') == 'Success'

    def _get_csrf_token(self) -> str:
        """Get CSRF token for editing."""
        if self._csrf_token:
            return self._csrf_token

        params = {
            'action': 'query',
            'meta': 'tokens',
            'format': 'json'
        }
        response = self.session.get(self.api_url, params=params, timeout=10)
        data = response.json()
        self._csrf_token = data['query']['tokens']['csrftoken']
        return self._csrf_token

    def upload_page(self, title: str, content: str, summary: str = "Bot: Automated content update") -> bool:
        """Upload a single page to MediaWiki."""
        csrf_token = self._get_csrf_token()

        edit_params = {
            'action': 'edit',
            'title': title,
            'text': content,
            'summary': summary,
            'token': csrf_token,
            'format': 'json',
            'bot': True
        }

        for attempt in range(self.max_retries):
            try:
                response = self.session.post(self.api_url, data=edit_params, timeout=30)
                data = response.json()

                if 'edit' in data and data['edit'].get('result') == 'Success':
                    return True
                elif 'error' in data:
                    error_code = data['error'].get('code', 'unknown')

                    if error_code == 'ratelimited':
                        wait_time = (attempt + 1) * 5
                        time.sleep(wait_time)
                        continue
                    elif error_code == 'badtoken':
                        self._csrf_token = None
                        csrf_token = self._get_csrf_token()
                        edit_params['token'] = csrf_token
                        continue
                    else:
                        return False
                else:
                    return False

            except requests.exceptions.RequestException:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return False

        return False

    def upload_directory(
        self,
        content_dir: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> dict:
        """Upload all .wiki files from a directory."""
        content_path = Path(content_dir)
        results = {'success': [], 'failed': []}

        if not content_path.exists():
            return results

        wiki_files = list(content_path.glob('**/*.wiki'))
        total = len(wiki_files)

        for i, wiki_file in enumerate(wiki_files, 1):
            title = wiki_file.stem.replace('_', ' ')
            content = wiki_file.read_text(encoding='utf-8')

            if progress_callback:
                progress_callback(i, total, title)

            if self.upload_page(title, content):
                results['success'].append(title)
            else:
                results['failed'].append(title)

            if i < total:
                time.sleep(self.rate_limit_delay)

        return results

    def get_page(self, title: str) -> Optional[str]:
        """Get content of a wiki page."""
        params = {
            'action': 'query',
            'titles': title,
            'prop': 'revisions',
            'rvprop': 'content',
            'rvslots': 'main',
            'format': 'json'
        }

        try:
            response = self.session.get(self.api_url, params=params, timeout=10)
            data = response.json()
        except Exception:
            return None

        pages = data.get('query', {}).get('pages', {})
        for page_id, page_data in pages.items():
            if page_id == '-1':
                return None
            revisions = page_data.get('revisions', [])
            if revisions:
                return revisions[0].get('slots', {}).get('main', {}).get('*')
        return None

    def list_pages(self, namespace: int = 0, limit: int = 500) -> list:
        """List all pages in a namespace."""
        pages = []
        params = {
            'action': 'query',
            'list': 'allpages',
            'apnamespace': namespace,
            'aplimit': min(limit, 500),
            'format': 'json'
        }

        while True:
            try:
                response = self.session.get(self.api_url, params=params, timeout=10)
                data = response.json()
            except Exception:
                break

            for page in data.get('query', {}).get('allpages', []):
                pages.append(page['title'])

            if 'continue' in data and len(pages) < limit:
                params['apcontinue'] = data['continue']['apcontinue']
            else:
                break

        return pages[:limit]

    @staticmethod
    def get_content_extension() -> str:
        return '.wiki'

    @staticmethod
    def get_platform_name() -> str:
        return 'Miraheze (MediaWiki)'
