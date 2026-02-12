# Wiki Generator

A web-based tool for generating and managing wiki content using AI. Supports **Miraheze (MediaWiki)** and **Confluence Cloud** platforms.

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Visual Editor   │ --> │  OpenAI GPT-4o  │ --> │  Wiki Platform  │
│  (Structure +    │     │   (Content      │     │  (Miraheze or   │
│   Link Banks)    │     │    Generation)  │     │   Confluence)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

1. **Create a project** — connect to your Miraheze wiki or Confluence space
2. **Build structure** — define pages, categories, key points in a visual editor
3. **Manage links** — set up operator and masking link banks with anchor text variations
4. **Generate content** — AI creates wiki-formatted articles with links woven in naturally
5. **Review & upload** — preview generated content and publish to your wiki

## Features

- **Visual Structure Builder** — drag-and-drop page editor with YAML import/export
- **Operator Link Bank** — external links with per-link placement targets, distributed across articles
- **Masking Link Bank** — non-commercial reference links that make content look natural (2-3 random per article)
- **Generation Modes** — full generation, add masking links only, or add operator links only to existing content
- **Live Wiki Pages** — browse, select, and edit pages already published on your wiki
- **Multi-Platform** — supports Miraheze (MediaWiki) and Confluence Cloud
- **One-Click Upload** — batch upload generated content with progress tracking
- **Google Search Console** — optional GSC integration for performance data

For a detailed walkthrough of every feature, see the **[Usage Guide](USAGE.md)**.

## Quick Start

### 1. Install Dependencies

```bash
cd wiki-generator
pip install -r requirements.txt
```

### 2. Run the App

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

### 3. Create a Project

Click **New Project**, enter your wiki credentials, test the connection, and save.

**For Miraheze:** You'll need a bot username and password from `Special:BotPasswords` on your wiki.

**For Confluence:** You'll need your base URL, space key, email, and an API token.

## Project Structure

```
wiki-generator/
├── app.py                    # Flask application (routes, generation logic)
├── config.py                 # App configuration
├── requirements.txt          # Python dependencies
├── adapters/
│   ├── base.py               # Base wiki adapter interface
│   ├── mediawiki.py          # Miraheze/MediaWiki API adapter
│   └── confluence.py         # Confluence Cloud API adapter
├── existing_scripts/
│   ├── generate_content.py   # AI content generation (GPT-4o)
│   └── wiki_bot.py           # Legacy wiki bot utilities
├── static/
│   ├── css/style.css         # Application styles
│   └── js/
│       ├── yaml_editor.js    # Structure editor + link bank UI
│       ├── progress.js       # Generation progress tracking
│       └── gsc.js            # Google Search Console UI
├── templates/                # Jinja2 HTML templates
│   ├── base.html             # Base layout with step indicator
│   ├── index.html            # Homepage
│   ├── new_project.html      # Project creation
│   ├── project_settings.html # Edit project credentials
│   ├── yaml_editor.html      # Structure + link bank editor
│   ├── generate.html         # Generation mode selection + progress
│   ├── review.html           # Content review + upload
│   ├── settings.html         # App-level settings
│   └── gsc.html              # Google Search Console
└── projects/                 # Per-project data (gitignored)
    └── {project_id}/
        ├── config.json       # Project credentials
        ├── pages.yaml        # Wiki structure
        ├── links.yaml        # Operator link bank
        ├── masking_links.yaml # Masking link bank
        └── generated/        # AI-generated .wiki/.html files
```

## Generation Modes

| Mode | Description |
|------|-------------|
| **Full Generation** | Generate articles from scratch with both operator and masking links |
| **Add Masking Links** | Keep existing content, weave in masking links only (protects operator links) |
| **Add Operator Links** | Keep existing content, weave in operator links only (protects masking links) |

## Link Banks

### Operator Links
Commercial links distributed across generated articles. Each link has:
- URL and anchor text variations
- Target count (how many articles to place it in, 0 = unlimited)

### Masking Links
Non-commercial reference links (e.g. Wikipedia) that make content look natural:
- 2-3 random masking links selected per article
- Prompted as "secondary" so AI doesn't overuse them
- No count tracking — simple URL + anchor text

Both support CSV import (`url, anchor1, anchor2, ...`).

## Legacy CLI Tool

The `wiki-creator/` folder contains the original command-line version of this tool. It is no longer maintained — all features are now in the `wiki-generator/` web application.

## Requirements

- Python 3.10+
- An OpenAI API key (for content generation)
- A Miraheze wiki with bot credentials, or a Confluence Cloud space with API token

## License

MIT License
