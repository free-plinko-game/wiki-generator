# Usage Guide

A step-by-step guide to using Wiki Generator. The app follows a 5-step workflow: **Setup > Structure > Generate > Review > Complete**.

## Table of Contents

- [Step 1: Create a Project](#step-1-create-a-project)
- [Step 2: Build Wiki Structure](#step-2-build-wiki-structure)
- [Step 3: Generate Content](#step-3-generate-content)
- [Step 4: Review & Upload](#step-4-review--upload)
- [Step 5: Complete](#step-5-complete)
- [Managing Project Settings](#managing-project-settings)
- [Link Banks](#link-banks)
- [CSV Import Format](#csv-import-format)
- [Generation Modes Explained](#generation-modes-explained)
- [Working with Live Wiki Pages](#working-with-live-wiki-pages)
- [Tips & Troubleshooting](#tips--troubleshooting)

---

## Step 1: Create a Project

1. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) and click **New Project**
2. Enter a **Project Name** (e.g. "Australian Gambling Wiki")
3. Select your **Platform**:

### Miraheze (MediaWiki)

| Field | Example | Where to find it |
|-------|---------|-------------------|
| Wiki Domain | `yourwiki.miraheze.org` | Your wiki's URL |
| Bot Username | `Username@BotName` | `Special:BotPasswords` on your wiki |
| Bot Password | `abc123...` | Generated when creating the bot password |

### Confluence Cloud

| Field | Example | Where to find it |
|-------|---------|-------------------|
| Base URL | `https://your-domain.atlassian.net/wiki` | Your Confluence URL |
| Space Key | `DOCS` | Space settings in Confluence |
| User Email | `you@company.com` | Your Atlassian account email |
| API Token | `ATATT3x...` | [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) |

4. Click **Test Connection** to verify your credentials work
5. Once the test passes, click **Save & Continue**

---

## Step 2: Build Wiki Structure

This is where you define what pages the AI will generate.

### Adding Pages

- Click **Add Page** to create a new page entry
- Fill in the **Title**, **Category**, **Description**, and **Key Points**
- Key points guide the AI on what to cover in each article
- Add **Related Pages** (comma-separated) to create "See Also" links between articles

### YAML Import/Export

If you have an existing structure, you can paste YAML directly:

1. Scroll to the **YAML Preview** panel on the right
2. Paste your YAML into the **Import YAML** textarea
3. Click **Apply YAML**

You can also click **Download** to export your current structure as a YAML file.

### Operator Link Bank

Below the pages editor, you'll find the **Link Bank** card. These are commercial/operator links that the AI will weave into generated articles.

- Click **Add Link** to add a link manually
- Enter the **URL**, **Anchor Text** variations (comma-separated), and a **Count** (target number of pages to place it on, 0 = unlimited)
- Or click **Upload CSV** to bulk import (see [CSV Import Format](#csv-import-format))

### Masking Link Bank

Below the operator link bank is the **Masking Link Bank**. These are non-commercial reference links (e.g. Wikipedia) that make content look more natural.

- Same interface as the operator link bank, but without a count field
- The AI will randomly select 2-3 masking links per article and include 1-2 where they fit naturally

### Saving

- **Save Draft** — saves your structure and links without leaving the page
- **Continue to Generate** — saves everything and moves to Step 3

---

## Step 3: Generate Content

### Select Generation Mode

Choose how you want the AI to process your pages:

| Mode | When to use it |
|------|---------------|
| **Full Generation** | First time generating, or when you want completely fresh content with all links |
| **Add Masking Links** | You already have content with operator links and want to add masking links without changing anything else |
| **Add Operator Links** | You already have content with masking links and want to add operator links without changing anything else |

### Enter API Key

Enter your **OpenAI API key** (`sk-...`). This is used for the current session only and is not stored.

### Select Pages

- Check/uncheck individual pages from the **Pages to Generate** list
- Use **Select All** to toggle all pages
- If you selected live wiki pages on the structure page, they'll appear in a separate **Live Wiki Pages** section (edit passes only)

### Start Generation

Click **Generate Content**. You'll see:
- A progress bar showing completion percentage
- The current page being generated
- Elapsed time
- Success/failure counts

Generation typically takes 10-30 seconds per page depending on article length.

---

## Step 4: Review & Upload

After generation, you're taken to the review page.

### Reviewing Content

- The page list shows all generated/edited pages with file sizes
- Click any page to **preview** its content
- The **External Link Summary** table shows which operator links were placed and on which pages:
  - Green count = target met
  - Yellow = partially placed
  - Red = not placed on any page

### Filtering

If you only generated/edited a subset of pages, the review page defaults to showing **only those pages**. Click **Show all X pages** to see everything, or **Show last run only** to go back to the filtered view.

### Uploading

1. Check the pages you want to publish
2. Click **Upload Selected (N)**
3. Pages are uploaded to your wiki via the API
4. You'll see upload progress and then be redirected to the completion page

---

## Step 5: Complete

The completion page shows:
- A link to your wiki
- Links to the first few uploaded pages
- Upload statistics (success/failed/total)

From here you can click **Add More Pages** to go back to the structure editor, or **Back to Home**.

---

## Managing Project Settings

To update your wiki credentials (e.g. if a bot password expires):

1. Go to the **Structure** page for your project
2. Click the **Settings** button in the top-right corner
3. Update the fields you need to change
4. Password/token fields can be left blank to keep the current value
5. Click **Test Connection** to verify, then **Save Settings**

---

## Link Banks

### Operator Links

Operator links are commercial external links distributed across your generated articles.

- **URL**: The full URL to link to
- **Anchors**: Comma-separated anchor text variations (e.g. `best casino, top casino site`)
- **Count**: How many articles this link should appear in (0 = unlimited)
- The AI tracks usage across articles — once a link hits its target count, it stops being offered to the AI for subsequent pages

### Masking Links

Masking links are non-commercial reference links that make articles look natural rather than like link farms.

- **URL**: Reference URL (e.g. Wikipedia, government sites)
- **Anchors**: Comma-separated anchor text variations
- No count field — these are lightweight
- For each article, 2-3 random masking links are selected from the bank
- The AI is instructed to include only 1-2, and only if they fit naturally
- They are labelled as "secondary" in the prompt so they never overshadow operator links

### How Links Interact

- **Full Generation**: Both operator and masking links are included in the prompt
- **Add Masking Links mode**: Masking links are added; the prompt explicitly tells the AI not to touch existing operator links
- **Add Operator Links mode**: Operator links are added; the prompt explicitly tells the AI not to touch existing masking/reference links

---

## CSV Import Format

Both link banks support CSV upload.

### Operator Links CSV

```
url, anchor1, anchor2, ..., count
https://example.com/page, best example, top example, 5
https://example.com/other, example site, 0
```

- First column: URL
- Middle columns: Anchor text variations
- Last column: If the last value is a number, it's treated as the target count

### Masking Links CSV

```
url, anchor1, anchor2, ...
https://en.wikipedia.org/wiki/Example, example topic, read more about example
https://www.gov.au/page, official information
```

- First column: URL
- Remaining columns: Anchor text variations
- No count column

---

## Working with Live Wiki Pages

The **Live Wiki Pages** section on the structure page lets you interact with pages already published on your wiki.

### Browsing

- Click **Refresh** to fetch the current page list from your wiki
- Click on any page title to load its content into the editor on the right
- You can edit the wiki markup directly and click **Save to Wiki** to publish changes

### Selecting for Edit Passes

- Each live page has a **checkbox** — tick the pages you want to process
- Use **Select All** to select all live pages
- When you click **Continue to Generate**, your selections are carried over
- On the generate page, selected live pages appear in a separate **Live Wiki Pages** section
- Choose **Add Masking Links** or **Add Operator Links** mode to run edit passes on them
- The app fetches each page's content from the wiki, sends it to the AI with the links, and saves the result

> **Note**: Live pages are only available for edit passes (Add Masking/Operator Links), not for Full Generation. Full Generation requires page definitions from the structure editor.

---

## Tips & Troubleshooting

### "Connection failed" on project setup
- **Miraheze**: Verify your bot password at `Special:BotPasswords` on your wiki. Bot passwords can expire.
- **Confluence**: Check that your API token is still valid at [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens).

### Links not appearing in generated content
- The AI only includes links that are contextually relevant to the page topic
- Try adding more anchor text variations that relate to your page topics
- Check the **External Link Summary** on the review page to see placement stats

### Masking links appearing too much/too little
- The system selects 2-3 random masking links per article and instructs the AI to use 1-2
- Add more masking links to the bank for greater variety across articles
- The AI may skip masking links if they don't fit the page topic naturally

### Generation seems slow
- Each page takes 10-30 seconds depending on length and complexity
- Edit passes (Add Masking/Operator Links) are typically faster than full generation
- The progress bar updates in real-time

### Review page shows too many pages
- After an edit pass on a subset of pages, the review page defaults to showing only those pages
- Click **Show all** to see everything if needed

### Bot password setup on Miraheze
1. Log in to your wiki
2. Go to `Special:BotPasswords`
3. Create a new bot with a name (e.g. "WikiGenerator")
4. Grant it **High-volume editing** and **Edit existing pages** permissions
5. Copy the generated password — it looks like `abc1def2ghi3jkl4mno5pqr6stu7vwx8`
6. Your bot username format is `YourUsername@BotName`
