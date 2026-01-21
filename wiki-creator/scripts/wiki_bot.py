#!/usr/bin/env python3
"""
MediaWiki Bot for uploading wiki content to Miraheze.

Usage:
    # Upload all content from directory
    python scripts/wiki_bot.py --config config.json --upload ./content

    # Upload single page
    python scripts/wiki_bot.py --config config.json --page "Page Title" --content ./path/to/file.wiki

    # Test connection
    python scripts/wiki_bot.py --config config.json --test

    # List all pages on wiki
    python scripts/wiki_bot.py --config config.json --list
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests


class WikiBot:
    """MediaWiki API bot for content management."""

    def __init__(self, config_path: str):
        """Initialize bot with configuration file."""
        self.config = self._load_config(config_path)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'WikiCreatorBot/1.0 (https://github.com/free-plinko-game/wiki-creator; wiki content automation)'
        })
        self.api_url = f"https://{self.config['wiki_domain']}{self.config.get('api_path', '/w/api.php')}"
        self.rate_limit_delay = self.config.get('rate_limit_delay', 1.0)
        self.max_retries = self.config.get('max_retries', 3)
        self._csrf_token: Optional[str] = None

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file or environment variables."""
        # First try environment variables (for CI/CD)
        if os.environ.get('WIKI_DOMAIN'):
            return {
                'wiki_domain': os.environ['WIKI_DOMAIN'],
                'bot_username': os.environ['WIKI_BOT_USERNAME'],
                'bot_password': os.environ['WIKI_BOT_PASSWORD'],
                'api_path': os.environ.get('WIKI_API_PATH', '/w/api.php'),
                'rate_limit_delay': float(os.environ.get('WIKI_RATE_LIMIT', '1.0')),
                'max_retries': int(os.environ.get('WIKI_MAX_RETRIES', '3')),
            }

        # Fall back to config file
        with open(config_path, 'r') as f:
            return json.load(f)

    def login(self) -> bool:
        """Login to the wiki using bot credentials."""
        # Step 1: Get login token
        params = {
            'action': 'query',
            'meta': 'tokens',
            'type': 'login',
            'format': 'json'
        }
        response = self.session.get(self.api_url, params=params)
        data = response.json()

        if 'query' not in data or 'tokens' not in data['query']:
            print(f"Error getting login token: {data}")
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
        response = self.session.post(self.api_url, data=login_params)
        data = response.json()

        if data.get('login', {}).get('result') == 'Success':
            print(f"Successfully logged in as {self.config['bot_username']}")
            return True
        else:
            print(f"Login failed: {data}")
            return False

    def _get_csrf_token(self) -> str:
        """Get CSRF token for editing."""
        if self._csrf_token:
            return self._csrf_token

        params = {
            'action': 'query',
            'meta': 'tokens',
            'format': 'json'
        }
        response = self.session.get(self.api_url, params=params)
        data = response.json()
        self._csrf_token = data['query']['tokens']['csrftoken']
        return self._csrf_token

    def edit_page(self, title: str, content: str, summary: str = "Bot: Automated content update") -> bool:
        """Create or edit a wiki page."""
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
                response = self.session.post(self.api_url, data=edit_params)
                data = response.json()

                if 'edit' in data and data['edit'].get('result') == 'Success':
                    print(f"Successfully uploaded: {title}")
                    return True
                elif 'error' in data:
                    error_code = data['error'].get('code', 'unknown')
                    error_info = data['error'].get('info', 'Unknown error')

                    if error_code == 'ratelimited':
                        wait_time = (attempt + 1) * 5
                        print(f"Rate limited, waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    elif error_code == 'badtoken':
                        # Token expired, get new one
                        self._csrf_token = None
                        csrf_token = self._get_csrf_token()
                        edit_params['token'] = csrf_token
                        continue
                    else:
                        print(f"Error uploading {title}: {error_code} - {error_info}")
                        return False
                else:
                    print(f"Unexpected response for {title}: {data}")
                    return False

            except requests.exceptions.RequestException as e:
                print(f"Network error (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return False

        return False

    def get_page(self, title: str) -> Optional[str]:
        """Get the content of a wiki page."""
        params = {
            'action': 'query',
            'titles': title,
            'prop': 'revisions',
            'rvprop': 'content',
            'rvslots': 'main',
            'format': 'json'
        }
        response = self.session.get(self.api_url, params=params)
        data = response.json()

        pages = data.get('query', {}).get('pages', {})
        for page_id, page_data in pages.items():
            if page_id == '-1':
                return None  # Page doesn't exist
            revisions = page_data.get('revisions', [])
            if revisions:
                return revisions[0].get('slots', {}).get('main', {}).get('*')
        return None

    def page_exists(self, title: str) -> bool:
        """Check if a page exists on the wiki."""
        params = {
            'action': 'query',
            'titles': title,
            'format': 'json'
        }
        response = self.session.get(self.api_url, params=params)
        data = response.json()

        pages = data.get('query', {}).get('pages', {})
        return '-1' not in pages

    def list_pages(self, namespace: int = 0, limit: int = 500) -> list[str]:
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
            response = self.session.get(self.api_url, params=params)
            data = response.json()

            for page in data.get('query', {}).get('allpages', []):
                pages.append(page['title'])

            if 'continue' in data and len(pages) < limit:
                params['apcontinue'] = data['continue']['apcontinue']
            else:
                break

        return pages[:limit]

    def delete_page(self, title: str, reason: str = "Bot: Page cleanup") -> bool:
        """Delete a wiki page (requires delete permissions)."""
        csrf_token = self._get_csrf_token()

        delete_params = {
            'action': 'delete',
            'title': title,
            'reason': reason,
            'token': csrf_token,
            'format': 'json'
        }

        response = self.session.post(self.api_url, data=delete_params)
        data = response.json()

        if 'delete' in data:
            print(f"Successfully deleted: {title}")
            return True
        else:
            print(f"Failed to delete {title}: {data}")
            return False

    def upload_directory(self, content_dir: str, dry_run: bool = False) -> dict:
        """Upload all .wiki files from a directory."""
        content_path = Path(content_dir)
        results = {'success': [], 'failed': [], 'skipped': []}

        if not content_path.exists():
            print(f"Error: Directory {content_dir} does not exist")
            return results

        wiki_files = list(content_path.glob('**/*.wiki'))
        total = len(wiki_files)
        print(f"Found {total} wiki files to upload")

        for i, wiki_file in enumerate(wiki_files, 1):
            # Convert filename to page title
            # e.g., "Interactive_Gambling_Act_2001.wiki" -> "Interactive Gambling Act 2001"
            title = wiki_file.stem.replace('_', ' ')

            # Read content
            content = wiki_file.read_text(encoding='utf-8')

            print(f"[{i}/{total}] Processing: {title}")

            if dry_run:
                print(f"  [DRY RUN] Would upload: {title}")
                results['skipped'].append(title)
            else:
                if self.edit_page(title, content):
                    results['success'].append(title)
                else:
                    results['failed'].append(title)

                # Rate limiting
                if i < total:
                    time.sleep(self.rate_limit_delay)

        return results

    def test_connection(self) -> bool:
        """Test the connection and authentication."""
        print(f"Testing connection to {self.api_url}...")

        # Test API accessibility
        try:
            params = {'action': 'query', 'meta': 'siteinfo', 'format': 'json'}
            response = self.session.get(self.api_url, params=params)
            data = response.json()

            if 'query' in data:
                sitename = data['query']['general'].get('sitename', 'Unknown')
                print(f"Connected to wiki: {sitename}")
            else:
                print(f"Unexpected API response: {data}")
                return False
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False

        # Test authentication
        if self.login():
            print("Authentication successful!")

            # Test edit permissions by getting a CSRF token
            try:
                token = self._get_csrf_token()
                if token and token != '+\\':
                    print("Edit permissions confirmed")
                    return True
                else:
                    print("Warning: May not have edit permissions")
                    return True
            except Exception as e:
                print(f"Warning: Could not verify edit permissions: {e}")
                return True
        else:
            print("Authentication failed")
            return False


def main():
    parser = argparse.ArgumentParser(description='MediaWiki Bot for Miraheze')
    parser.add_argument('--config', '-c', default='config.json',
                        help='Path to config file (default: config.json)')
    parser.add_argument('--upload', '-u', metavar='DIR',
                        help='Upload all .wiki files from directory')
    parser.add_argument('--page', '-p', metavar='TITLE',
                        help='Page title for single upload')
    parser.add_argument('--content', '-f', metavar='FILE',
                        help='Content file for single upload')
    parser.add_argument('--test', '-t', action='store_true',
                        help='Test connection and authentication')
    parser.add_argument('--list', '-l', action='store_true',
                        help='List all pages on wiki')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Dry run - don\'t actually upload')
    parser.add_argument('--get', '-g', metavar='TITLE',
                        help='Get content of a page')

    args = parser.parse_args()

    # Initialize bot
    try:
        bot = WikiBot(args.config)
    except FileNotFoundError:
        print(f"Error: Config file '{args.config}' not found")
        print("Create config.json from config.example.json or set environment variables")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)

    # Test connection
    if args.test:
        success = bot.test_connection()
        sys.exit(0 if success else 1)

    # Login for other operations
    if not bot.login():
        print("Failed to login. Check your credentials.")
        sys.exit(1)

    # List pages
    if args.list:
        pages = bot.list_pages()
        print(f"\nFound {len(pages)} pages:")
        for page in pages:
            print(f"  - {page}")
        sys.exit(0)

    # Get page content
    if args.get:
        content = bot.get_page(args.get)
        if content:
            print(content)
        else:
            print(f"Page '{args.get}' not found")
        sys.exit(0)

    # Upload directory
    if args.upload:
        results = bot.upload_directory(args.upload, dry_run=args.dry_run)
        print(f"\nUpload complete:")
        print(f"  Success: {len(results['success'])}")
        print(f"  Failed:  {len(results['failed'])}")
        if args.dry_run:
            print(f"  Skipped: {len(results['skipped'])} (dry run)")
        if results['failed']:
            print(f"\nFailed pages:")
            for page in results['failed']:
                print(f"  - {page}")
            sys.exit(1)
        sys.exit(0)

    # Upload single page
    if args.page and args.content:
        content_path = Path(args.content)
        if not content_path.exists():
            print(f"Error: Content file '{args.content}' not found")
            sys.exit(1)

        content = content_path.read_text(encoding='utf-8')
        if args.dry_run:
            print(f"[DRY RUN] Would upload: {args.page}")
            print(f"Content preview:\n{content[:500]}...")
        else:
            success = bot.edit_page(args.page, content)
            sys.exit(0 if success else 1)
        sys.exit(0)

    # No action specified
    parser.print_help()
    sys.exit(1)


if __name__ == '__main__':
    main()
