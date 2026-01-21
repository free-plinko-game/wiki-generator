# Australian Gambling Regulation Wiki

Automated wiki publishing system using **OpenAI** to generate encyclopaedic content about Australian gambling regulation, hosted on Miraheze.

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   pages.yaml    │ --> │  OpenAI GPT-4o  │ --> │  .wiki files    │
│  (definitions)  │     │  (generation)   │     │  (MediaWiki)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        v
                                                ┌─────────────────┐
                                                │  Miraheze Wiki  │
                                                └─────────────────┘
```

1. **Define pages** in `pages.yaml` (title, category, key points)
2. **Generate content** using OpenAI GPT-4o
3. **Upload** to Miraheze wiki via MediaWiki API

## Quick Start

### 1. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 2. Configure

```powershell
copy config.example.json config.json
```

Edit `config.json`:
```json
{
    "wiki_domain": "your-wiki.miraheze.org",
    "bot_username": "YourUsername@BotName",
    "bot_password": "your-wiki-bot-password",
    "openai_api_key": "sk-your-openai-api-key"
}
```

### 3. Generate & Upload

```powershell
# Generate all pages
python scripts\generate_content.py .\content

# Upload to wiki
python scripts\wiki_bot.py --upload .\content
```

## Project Structure

```
wiki-creator/
├── scripts/
│   ├── wiki_bot.py          # MediaWiki API bot
│   └── generate_content.py  # OpenAI content generator
├── content/                  # Generated .wiki files
├── pages.yaml               # Page definitions
├── config.json              # API credentials (gitignored)
├── config.example.json      # Config template
└── requirements.txt         # Python dependencies
```

## Defining Pages

Edit `pages.yaml` to configure what pages to generate:

```yaml
pages:
  - title: "Page Title"
    category: "Legislation"
    description: "Brief description for AI context"
    key_points:
      - "Key fact 1 to include"
      - "Key fact 2 with specific details"
      - "Statistics, dates, numbers"
    related_pages:
      - "Other Page"
    external_links:
      - "https://official-source.gov.au"
```

### Configuration Options

| Field | Required | Description |
|-------|----------|-------------|
| `title` | Yes | Page title |
| `category` | No | Wiki category |
| `description` | Yes | Context for AI |
| `key_points` | Yes | Points to cover |
| `related_pages` | No | "See Also" links |
| `external_links` | No | External sources |

## Commands

### Content Generator

```powershell
# List configured pages
python scripts\generate_content.py --list

# Generate all pages
python scripts\generate_content.py .\content

# Generate specific pages
python scripts\generate_content.py .\content --pages "BetStop,ACMA"
```

### Wiki Bot

```powershell
# Test connection
python scripts\wiki_bot.py --test

# Upload content
python scripts\wiki_bot.py --upload .\content

# Dry run (no upload)
python scripts\wiki_bot.py --upload .\content --dry-run

# List wiki pages
python scripts\wiki_bot.py --list
```

## Setting Up Miraheze

1. **Request wiki** at [meta.miraheze.org/wiki/Special:RequestWiki](https://meta.miraheze.org/wiki/Special:RequestWiki)
2. **Create bot credentials** at `Special:BotPasswords`
3. **Update** `config.json` with credentials

## Included Pages

Default `pages.yaml` includes 13 pages:

| Category | Pages |
|----------|-------|
| Legislation | Interactive Gambling Act 2001, National Consumer Protection Framework |
| Regulatory Bodies | ACMA, State and Territory Regulators |
| Consumer Protection | BetStop, Responsible Gambling Tools |
| Technical Standards | Random Number Generators, Return to Player |
| Consumer Information | Gambling Types, Payment Methods |
| Reference | Glossary, History |

## Cost Estimate

GPT-4o pricing (~$5/1M input, ~$15/1M output):
- 13 pages ≈ **$0.40-0.50 total**

## Troubleshooting

**"OpenAI API key not found"**
- Set `OPENAI_API_KEY` env var, or add to `config.json`

**"Config file not found"**
- Ensure `pages.yaml` exists, or use `--config path/to/file.yaml`

**Rate limited by wiki**
- Increase `rate_limit_delay` in config (default: 1 second)

## License

MIT License
