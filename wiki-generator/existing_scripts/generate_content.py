#!/usr/bin/env python3
"""
Wiki Content Generator using OpenAI API.

Generates MediaWiki-formatted pages based on YAML configuration.

Usage:
    python scripts/generate_content.py ./content
    python scripts/generate_content.py ./content --pages "BetStop,ACMA"
    python scripts/generate_content.py --list
    python scripts/generate_content.py ./content --config custom_pages.yaml
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

import yaml
from openai import OpenAI


def load_config(config_path: str) -> dict:
    """Load page configuration from YAML file."""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def build_system_prompt(config: dict, content_format: str) -> str:
    """Build the system prompt for content generation."""
    style = config.get('style', {})

    if content_format == 'confluence':
        prompt = f"""You are an expert wiki content writer creating pages for the "{config.get('wiki_name', 'Wiki')}".

Your task is to generate high-quality Confluence Storage Format content (XHTML-compatible).

## Writing Style
- Tone: {style.get('tone', 'encyclopaedic, neutral')}
- Format: Confluence Storage Format (NOT Markdown)

## Required Elements
"""
    else:
        prompt = f"""You are an expert wiki content writer creating pages for the "{config.get('wiki_name', 'Wiki')}".

Your task is to generate high-quality MediaWiki-formatted content.

## Writing Style
- Tone: {style.get('tone', 'encyclopaedic, neutral')}
- Format: MediaWiki markup (NOT Markdown)

## Required Elements
"""

    for item in style.get('include', []):
        prompt += f"- {item}\n"

    prompt += "\n## Avoid\n"
    for item in style.get('avoid', []):
        prompt += f"- {item}\n"

    if content_format == 'confluence':
        prompt += """
## Confluence Storage Format Reference
- Headings: <h1>, <h2>, <h3>
- Bold: <strong>text</strong>
- Italic: <em>text</em>
- Links: <a href="https://url.com">Link Text</a>
- Bullet list: <ul><li>item</li></ul>
- Numbered list: <ol><li>item</li></ol>
- Tables: <table><tbody><tr><th>...</th></tr>...</tbody></table>

## Important
- Use ONLY Confluence storage format (XHTML-compatible), never Markdown
- Include a table for structured data where appropriate
- Be factual and cite official sources where possible
- For Australian gambling content, reference official government sources
"""
    else:
        prompt += """
## MediaWiki Syntax Reference
- Headings: = H1 =, == H2 ==, === H3 ===
- Bold: '''text'''
- Italic: ''text''
- Internal links: [[Page Name]] or [[Page Name|Display Text]]
- External links: [https://url.com Link Text]
- Bullet list: * item
- Numbered list: # item
- Tables: {| class="wikitable" ... |}
- Categories: [[Category:Name]]
- Definition lists: ; term : definition

## Important
- Use ONLY MediaWiki syntax, never Markdown
- Include a wikitable for structured data where appropriate
- Always end with [[Category:CategoryName]]
- Be factual and cite official sources where possible
- For Australian gambling content, reference official government sources
"""

    return prompt


def build_page_prompt(page: dict, config: dict, content_format: str) -> str:
    """Build the user prompt for a specific page."""
    prompt = f"""Generate a complete MediaWiki page for: "{page['title']}"

## Page Details
- Category: {page.get('category', config.get('default_category', 'General'))}
- Description: {page.get('description', 'No description provided')}

## Key Points to Cover
"""

    for point in page.get('key_points', []):
        prompt += f"- {point}\n"

    if page.get('related_pages'):
        prompt += "\n## Related Pages (for See Also section)\n"
        for related in page['related_pages']:
            prompt += f"- [[{related}]]\n"

    if page.get('external_links'):
        prompt += "\n## External Links to Include\n"
        for link in page['external_links']:
            prompt += f"- {link}\n"

    if page.get('format'):
        prompt += f"\n## Special Format Instructions\n{page['format']}\n"

    if content_format == 'confluence':
        prompt = prompt.replace('MediaWiki page', 'Confluence page')
        prompt += f"""
## Output Requirements
1. Start with a brief lead paragraph (no heading)
2. Use <h2> section headings
3. Include at least one HTML table
4. End with <h2>See Also</h2> and <h2>External Links</h2>
5. Output ONLY the Confluence storage HTML, no explanations or code blocks
"""
    else:
        prompt += f"""
## Output Requirements
1. Start with a brief lead paragraph (no heading)
2. Use == Section Headings ==
3. Include at least one {{| class="wikitable" |}} table
4. End with == See Also ==, == External Links ==, and [[Category:{page.get('category', 'General')}]]
5. Output ONLY the wiki markup, no explanations or code blocks
"""
    return prompt


class WikiContentGenerator:
    """Generate wiki content using OpenAI API."""

    def __init__(self, config_path: str = "pages.yaml", api_key: Optional[str] = None, content_format: Optional[str] = None):
        """Initialize the generator."""
        self.config = load_config(config_path)
        self.client = self._init_openai(api_key)
        self.content_format = (content_format or self.config.get('content_format') or 'mediawiki').lower()
        if self.content_format in ('miraheze', 'mediawiki'):
            self.content_format = 'mediawiki'
        self.system_prompt = build_system_prompt(self.config, self.content_format)

    def _init_openai(self, api_key: Optional[str]) -> OpenAI:
        """Initialize OpenAI client."""
        api_key = api_key or os.environ.get('OPENAI_API_KEY')
        if not api_key:
            # Try loading from config.json
            try:
                with open('config.json', 'r') as f:
                    config = json.load(f)
                    api_key = config.get('openai_api_key')
            except FileNotFoundError:
                pass

        if not api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or add 'openai_api_key' to config.json"
            )

        return OpenAI(api_key=api_key)

    def generate_page(self, page: dict) -> str:
        """Generate content for a single page."""
        user_prompt = build_page_prompt(page, self.config, self.content_format)

        print(f"  Generating content with OpenAI...")

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=4000
        )

        content = response.choices[0].message.content

        # Add generation metadata as HTML comment
        metadata = f"""<!--
    Generated: {datetime.now().isoformat()}
    Page: {page['title']}
    Category: {page.get('category', 'General')}
    Generator: OpenAI GPT-4o
-->
"""
        return metadata + content.strip()

    def _get_output_extension(self) -> str:
        return '.html' if self.content_format == 'confluence' else '.wiki'

    def get_page_by_title(self, title: str) -> Optional[dict]:
        """Find a page config by title."""
        title_lower = title.lower().strip()
        for page in self.config.get('pages', []):
            if page['title'].lower() == title_lower:
                return page
        return None

    def list_pages(self) -> list[dict]:
        """List all configured pages."""
        return self.config.get('pages', [])

    def generate_all(self, output_dir: Path) -> dict:
        """Generate all configured pages."""
        results = {'success': [], 'failed': []}
        output_dir.mkdir(parents=True, exist_ok=True)

        pages = self.list_pages()
        total = len(pages)

        print(f"Generating {total} pages...")

        for i, page in enumerate(pages, 1):
            title = page['title']
            print(f"[{i}/{total}] {title}")

            try:
                content = self.generate_page(page)

                # Save to file
                filename = title.replace(' ', '_').replace('/', '_') + self._get_output_extension()
                filepath = output_dir / filename
                filepath.write_text(content, encoding='utf-8')

                print(f"  Saved: {filepath}")
                results['success'].append(title)

            except Exception as e:
                print(f"  ERROR: {e}")
                results['failed'].append({'title': title, 'error': str(e)})

        return results

    def generate_selected(self, titles: list[str], output_dir: Path) -> dict:
        """Generate selected pages by title."""
        results = {'success': [], 'failed': [], 'not_found': []}
        output_dir.mkdir(parents=True, exist_ok=True)

        for title in titles:
            page = self.get_page_by_title(title)

            if not page:
                print(f"Page not found: {title}")
                results['not_found'].append(title)
                continue

            print(f"Generating: {page['title']}")

            try:
                content = self.generate_page(page)

                filename = page['title'].replace(' ', '_').replace('/', '_') + self._get_output_extension()
                filepath = output_dir / filename
                filepath.write_text(content, encoding='utf-8')

                print(f"  Saved: {filepath}")
                results['success'].append(page['title'])

            except Exception as e:
                print(f"  ERROR: {e}")
                results['failed'].append({'title': page['title'], 'error': str(e)})

        return results


def main():
    parser = argparse.ArgumentParser(
        description='Generate MediaWiki content using OpenAI'
    )
    parser.add_argument('output_dir', nargs='?', default='./content',
                        help='Output directory for .wiki files')
    parser.add_argument('--config', '-c', default='pages.yaml',
                        help='Page configuration YAML file')
    parser.add_argument('--pages', '-p', default='all',
                        help='Pages to generate: "all" or comma-separated titles')
    parser.add_argument('--list', '-l', action='store_true',
                        help='List all configured pages')

    args = parser.parse_args()

    # List pages only
    if args.list:
        try:
            config = load_config(args.config)
            pages = config.get('pages', [])
            print(f"\nConfigured pages in {args.config}:")
            print("-" * 50)
            for page in pages:
                category = page.get('category', 'General')
                print(f"  [{category}] {page['title']}")
            print(f"\nTotal: {len(pages)} pages")
        except FileNotFoundError:
            print(f"Config file not found: {args.config}")
            sys.exit(1)
        return

    # Initialize generator
    try:
        generator = WikiContentGenerator(args.config)
    except FileNotFoundError:
        print(f"Config file not found: {args.config}")
        sys.exit(1)
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    output_path = Path(args.output_dir)

    # Generate pages
    if args.pages.lower() == 'all':
        results = generator.generate_all(output_path)
    else:
        titles = [t.strip() for t in args.pages.split(',')]
        results = generator.generate_selected(titles, output_path)

    # Print summary
    print(f"\nGeneration complete:")
    print(f"  Success: {len(results['success'])}")
    print(f"  Failed:  {len(results['failed'])}")
    if results.get('not_found'):
        print(f"  Not found: {len(results['not_found'])}")

    if results['failed']:
        print("\nFailed pages:")
        for item in results['failed']:
            print(f"  - {item['title']}: {item['error']}")
        sys.exit(1)


if __name__ == '__main__':
    main()
