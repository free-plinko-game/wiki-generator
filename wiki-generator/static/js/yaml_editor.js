// YAML Editor for Wiki Generator

let pages = [];
let pageIndex = 0;

function initYamlEditor(existingConfig, projectId, saveUrl, generateUrl, importUrl) {
    // Load existing config if available
    if (existingConfig && existingConfig.pages) {
        applyConfigToEditor(existingConfig);
    }

    // Event listeners
    document.getElementById('add-page').addEventListener('click', addPage);
    document.getElementById('download-yaml').addEventListener('click', downloadYaml);
    document.getElementById('save-structure').addEventListener('click', () => saveStructure(saveUrl));
    document.getElementById('continue-btn').addEventListener('click', () => continueToGenerate(saveUrl, generateUrl));
    setupYamlImport(importUrl);

    // Update YAML preview on input changes
    document.addEventListener('input', debounce(updateYamlPreview, 300));

    updateYamlPreview();
}

function applyConfigToEditor(config) {
    pages = config.pages || [];
    pageIndex = 0;

    document.getElementById('wiki_name').value = config.wiki_name || '';
    document.getElementById('default_category').value = config.default_category || 'General';

    renderPages();
}

function setupYamlImport(importUrl) {
    const input = document.getElementById('yaml-import-input');
    const applyBtn = document.getElementById('apply-yaml-import');
    const clearBtn = document.getElementById('clear-yaml-import');

    if (!input || !applyBtn || !clearBtn || !importUrl) {
        return;
    }

    clearBtn.addEventListener('click', () => {
        input.value = '';
        showToast('YAML input cleared', 'info');
    });

    applyBtn.addEventListener('click', async () => {
        const yamlText = input.value.trim();
        if (!yamlText) {
            showToast('Paste YAML before applying', 'error');
            return;
        }

        applyBtn.disabled = true;
        applyBtn.classList.add('btn-loading');

        try {
            const response = await fetch(importUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ yaml: yamlText })
            });
            const data = await response.json();
            if (!data.success) {
                showToast(data.error || 'Failed to import YAML', 'error');
                return;
            }

            applyConfigToEditor(data.config || {});
            showToast('YAML imported', 'success');
        } catch (error) {
            showToast('Import error: ' + error.message, 'error');
        } finally {
            applyBtn.disabled = false;
            applyBtn.classList.remove('btn-loading');
        }
    });
}
function addPage() {
    const template = document.getElementById('page-template');
    const clone = template.content.cloneNode(true);
    const pageItem = clone.querySelector('.page-item');

    pageItem.dataset.pageIndex = pageIndex++;

    // Add event listeners
    setupPageEventListeners(pageItem);

    document.getElementById('pages-container').appendChild(clone);

    // Add to pages array
    pages.push({
        title: '',
        category: document.getElementById('default_category').value || 'General',
        description: '',
        key_points: [],
        related_pages: []
    });

    // Expand the new page
    pageItem.classList.add('expanded');

    updateYamlPreview();
}

function setupPageEventListeners(pageItem) {
    const index = parseInt(pageItem.dataset.pageIndex);

    // Toggle expand/collapse
    pageItem.querySelector('.page-item-header').addEventListener('click', function(e) {
        if (e.target.closest('.page-item-actions')) return;
        pageItem.classList.toggle('expanded');
    });

    // Title input
    pageItem.querySelector('.page-title-input').addEventListener('input', function() {
        const titleText = pageItem.querySelector('.page-title-text');
        titleText.textContent = this.value || 'New Page';
        updatePageData(pageItem);
    });

    // Other inputs
    pageItem.querySelector('.page-category-input').addEventListener('input', () => updatePageData(pageItem));
    pageItem.querySelector('.page-description-input').addEventListener('input', () => updatePageData(pageItem));
    pageItem.querySelector('.page-related-input').addEventListener('input', () => updatePageData(pageItem));

    // Add key point
    pageItem.querySelector('.add-key-point').addEventListener('click', function() {
        addKeyPoint(pageItem);
    });

    // Delete page
    pageItem.querySelector('.delete-page').addEventListener('click', function() {
        deletePage(pageItem);
    });

    // Move up/down
    pageItem.querySelector('.move-up').addEventListener('click', function() {
        movePage(pageItem, -1);
    });

    pageItem.querySelector('.move-down').addEventListener('click', function() {
        movePage(pageItem, 1);
    });
}

function addKeyPoint(pageItem) {
    const template = document.getElementById('key-point-template');
    const clone = template.content.cloneNode(true);
    const keyPointItem = clone.querySelector('.key-point-item');

    keyPointItem.querySelector('.key-point-input').addEventListener('input', () => updatePageData(pageItem));
    keyPointItem.querySelector('.remove-key-point').addEventListener('click', function() {
        keyPointItem.remove();
        updatePageData(pageItem);
    });

    pageItem.querySelector('.key-points-list').appendChild(clone);
}

function updatePageData(pageItem) {
    const idx = getPageArrayIndex(pageItem);
    if (idx === -1) return;

    pages[idx] = {
        title: pageItem.querySelector('.page-title-input').value,
        category: pageItem.querySelector('.page-category-input').value || document.getElementById('default_category').value,
        description: pageItem.querySelector('.page-description-input').value,
        key_points: Array.from(pageItem.querySelectorAll('.key-point-input'))
            .map(input => input.value)
            .filter(v => v.trim()),
        related_pages: pageItem.querySelector('.page-related-input').value
            .split(',')
            .map(s => s.trim())
            .filter(s => s)
    };

    updateYamlPreview();
}

function deletePage(pageItem) {
    const idx = getPageArrayIndex(pageItem);
    if (idx !== -1) {
        pages.splice(idx, 1);
    }
    pageItem.remove();
    updateYamlPreview();
}

function movePage(pageItem, direction) {
    const container = document.getElementById('pages-container');
    const items = Array.from(container.querySelectorAll('.page-item'));
    const currentIdx = items.indexOf(pageItem);
    const newIdx = currentIdx + direction;

    if (newIdx < 0 || newIdx >= items.length) return;

    // Move in DOM
    if (direction === -1) {
        container.insertBefore(pageItem, items[newIdx]);
    } else {
        container.insertBefore(pageItem, items[newIdx].nextSibling);
    }

    // Move in array
    const arrayIdx = getPageArrayIndex(pageItem);
    const newArrayIdx = arrayIdx + direction;
    if (newArrayIdx >= 0 && newArrayIdx < pages.length) {
        const temp = pages[arrayIdx];
        pages[arrayIdx] = pages[newArrayIdx];
        pages[newArrayIdx] = temp;
    }

    updateYamlPreview();
}

function getPageArrayIndex(pageItem) {
    const container = document.getElementById('pages-container');
    const items = Array.from(container.querySelectorAll('.page-item'));
    return items.indexOf(pageItem);
}

function renderPages() {
    const container = document.getElementById('pages-container');
    container.innerHTML = '';

    pages.forEach((page, idx) => {
        const template = document.getElementById('page-template');
        const clone = template.content.cloneNode(true);
        const pageItem = clone.querySelector('.page-item');

        pageItem.dataset.pageIndex = pageIndex++;

        // Fill in data
        pageItem.querySelector('.page-title-input').value = page.title || '';
        pageItem.querySelector('.page-title-text').textContent = page.title || 'New Page';
        pageItem.querySelector('.page-category-input').value = page.category || '';
        pageItem.querySelector('.page-description-input').value = page.description || '';
        pageItem.querySelector('.page-related-input').value = (page.related_pages || []).join(', ');

        // Add key points
        const keyPointsList = pageItem.querySelector('.key-points-list');
        (page.key_points || []).forEach(kp => {
            const kpTemplate = document.getElementById('key-point-template');
            const kpClone = kpTemplate.content.cloneNode(true);
            kpClone.querySelector('.key-point-input').value = kp;
            keyPointsList.appendChild(kpClone);
        });

        setupPageEventListeners(pageItem);
        container.appendChild(clone);
    });

    // Re-setup key point event listeners
    document.querySelectorAll('.key-point-item').forEach(kpItem => {
        const pageItem = kpItem.closest('.page-item');
        kpItem.querySelector('.key-point-input').addEventListener('input', () => updatePageData(pageItem));
        kpItem.querySelector('.remove-key-point').addEventListener('click', function() {
            kpItem.remove();
            updatePageData(pageItem);
        });
    });

    updateYamlPreview();
}

function buildYamlConfig() {
    return {
        wiki_name: document.getElementById('wiki_name').value || 'My Wiki',
        default_category: document.getElementById('default_category').value || 'General',
        style: {
            tone: 'encyclopaedic, neutral',
            include: [
                'Tables for structured information',
                'Internal links to related pages',
                'External links to official sources',
                'Categories at the end'
            ],
            avoid: [
                'Marketing language',
                'First person pronouns',
                'Speculation or unverified claims'
            ]
        },
        pages: pages.filter(p => p.title.trim())
    };
}

function updateYamlPreview() {
    const config = buildYamlConfig();
    const yamlOutput = document.getElementById('yaml-output');

    // Simple YAML serialization
    let yaml = `wiki_name: "${config.wiki_name}"\n`;
    yaml += `default_category: "${config.default_category}"\n\n`;

    yaml += `style:\n`;
    yaml += `  tone: "${config.style.tone}"\n`;
    yaml += `  include:\n`;
    config.style.include.forEach(item => {
        yaml += `    - "${item}"\n`;
    });
    yaml += `  avoid:\n`;
    config.style.avoid.forEach(item => {
        yaml += `    - "${item}"\n`;
    });

    yaml += `\npages:\n`;
    config.pages.forEach(page => {
        yaml += `  - title: "${page.title}"\n`;
        yaml += `    category: "${page.category}"\n`;
        if (page.description) {
            yaml += `    description: "${page.description}"\n`;
        }
        if (page.key_points && page.key_points.length > 0) {
            yaml += `    key_points:\n`;
            page.key_points.forEach(kp => {
                yaml += `      - "${kp}"\n`;
            });
        }
        if (page.related_pages && page.related_pages.length > 0) {
            yaml += `    related_pages:\n`;
            page.related_pages.forEach(rp => {
                yaml += `      - "${rp}"\n`;
            });
        }
        yaml += `\n`;
    });

    yamlOutput.textContent = yaml;
}

function downloadYaml() {
    const config = buildYamlConfig();
    let yaml = generateYamlString(config);

    const blob = new Blob([yaml], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'pages.yaml';
    a.click();
    URL.revokeObjectURL(url);

    showToast('YAML downloaded', 'success');
}

function generateYamlString(config) {
    // Use the same format as updateYamlPreview
    let yaml = `wiki_name: "${config.wiki_name}"\n`;
    yaml += `default_category: "${config.default_category}"\n\n`;

    yaml += `style:\n`;
    yaml += `  tone: "${config.style.tone}"\n`;
    yaml += `  include:\n`;
    config.style.include.forEach(item => {
        yaml += `    - "${item}"\n`;
    });
    yaml += `  avoid:\n`;
    config.style.avoid.forEach(item => {
        yaml += `    - "${item}"\n`;
    });

    yaml += `\npages:\n`;
    config.pages.forEach(page => {
        yaml += `  - title: "${page.title}"\n`;
        yaml += `    category: "${page.category}"\n`;
        if (page.description) {
            yaml += `    description: "${page.description}"\n`;
        }
        if (page.key_points && page.key_points.length > 0) {
            yaml += `    key_points:\n`;
            page.key_points.forEach(kp => {
                yaml += `      - "${kp}"\n`;
            });
        }
        if (page.related_pages && page.related_pages.length > 0) {
            yaml += `    related_pages:\n`;
            page.related_pages.forEach(rp => {
                yaml += `      - "${rp}"\n`;
            });
        }
        yaml += `\n`;
    });

    return yaml;
}

async function saveStructure(saveUrl) {
    const config = buildYamlConfig();

    if (config.pages.length === 0) {
        showToast('Add at least one page before saving', 'error');
        return;
    }

    try {
        const response = await fetch(saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const data = await response.json();

        if (data.success) {
            showToast('Structure saved', 'success');
        } else {
            showToast(data.error || 'Failed to save', 'error');
        }
    } catch (error) {
        showToast('Error saving: ' + error.message, 'error');
    }
}

async function continueToGenerate(saveUrl, generateUrl) {
    const config = buildYamlConfig();

    if (config.pages.length === 0) {
        showToast('Add at least one page before continuing', 'error');
        return;
    }

    // Save first, then redirect
    try {
        const response = await fetch(saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const data = await response.json();

        if (data.success) {
            window.location.href = generateUrl;
        } else {
            showToast(data.error || 'Failed to save structure', 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

function syncTitleToYaml(previousTitle, nextTitle) {
    const title = (nextTitle || '').trim();
    if (!title) {
        return;
    }

    const container = document.getElementById('pages-container');
    const items = Array.from(container.querySelectorAll('.page-item'));
    const prevLower = (previousTitle || '').trim().toLowerCase();
    const nextLower = title.toLowerCase();

    let targetItem = null;
    if (prevLower) {
        targetItem = items.find(item => {
            const input = item.querySelector('.page-title-input');
            return input && input.value.trim().toLowerCase() === prevLower;
        });
    }

    if (!targetItem) {
        targetItem = items.find(item => {
            const input = item.querySelector('.page-title-input');
            return input && input.value.trim().toLowerCase() === nextLower;
        });
    }

    if (!targetItem) {
        addPage();
        const updatedItems = Array.from(container.querySelectorAll('.page-item'));
        targetItem = updatedItems[updatedItems.length - 1];
    }

    const titleInput = targetItem.querySelector('.page-title-input');
    const titleText = targetItem.querySelector('.page-title-text');
    if (titleInput) {
        titleInput.value = title;
    }
    if (titleText) {
        titleText.textContent = title || 'New Page';
    }

    targetItem.classList.add('expanded');
    updatePageData(targetItem);
}

window.syncTitleToYaml = syncTitleToYaml;
