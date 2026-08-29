/* UNIT3D-compatible BBCode helpers for the description editor. */
(function () {
  'use strict';

  const escapeHtml = value => (typeof esc === 'function' ? esc(String(value ?? '')) : String(value ?? ''));

  function safeExternalUrl(value) {
    const url = String(value || '').trim();
    return /^(https?|ftp|irc|sftp|magnet):\/\/[^\s<>"']+$/i.test(url) ? url : '';
  }

  function renderUnit3dBbcode(value, jobId, images) {
    let html = escapeHtml(value || '');
    const prepared = Array.isArray(images) ? images : [];

    const imageAt = index => {
      const image = prepared[index];
      if (!image) return `<span class="bbcode-missing">[upimg${index}]</span>`;
      return `<figure class="bbcode-image"><img src="/api/jobs/${Number(jobId)}/image/${Number(image.id)}" alt="${escapeHtml(image.file_name || 'Prepared image')}" title="Click to enlarge"><figcaption>${escapeHtml(image.file_name || 'Prepared image')} · click image to enlarge</figcaption></figure>`;
    };

    html = html.replace(/\[upimg(\d*)\]/gi, (_, index) => imageAt(index === '' ? 0 : Number(index)));
    html = html.replace(/\[img\s+width=(\d+)\]([\s\S]*?)\[\/img\]/gi, (_, width, source) => {
      const url = safeExternalUrl(source.replace(/&amp;/g, '&'));
      return url ? `<figure class="bbcode-image"><img src="${escapeHtml(url)}" width="${Math.min(2000, Number(width))}" alt="Description image"></figure>` : '<span class="bbcode-missing">[img] invalid image URL [/img]</span>';
    });
    html = html.replace(/\[img=(\d+)(?:x\d+)?\]([\s\S]*?)\[\/img\]/gi, (_, width, source) => {
      const url = safeExternalUrl(source.replace(/&amp;/g, '&'));
      return url ? `<figure class="bbcode-image"><img src="${escapeHtml(url)}" width="${Math.min(2000, Number(width))}" alt="Description image"></figure>` : '<span class="bbcode-missing">[img] invalid image URL [/img]</span>';
    });
    html = html.replace(/\[img\]([\s\S]*?)\[\/img\]/gi, (_, source) => {
      const url = safeExternalUrl(source.replace(/&amp;/g, '&'));
      return url ? `<figure class="bbcode-image"><img src="${escapeHtml(url)}" alt="Description image"></figure>` : '<span class="bbcode-missing">[img] invalid image URL [/img]</span>';
    });
    html = html.replace(/\[comparison=([^\]]+)\]([\s\S]*?)\[\/comparison\]/gi, (_, labels, sources) => {
      const names = String(labels).split(',').map(label => label.trim());
      const urls = String(sources).trim().split(/\s+/);
      const items = names.map((name, index) => {
        const url = safeExternalUrl((urls[index] || '').replace(/&amp;/g, '&'));
        return url ? `<figure><figcaption>${escapeHtml(name)}</figcaption><img src="${escapeHtml(url)}" alt="${escapeHtml(name)}"></figure>` : '';
      }).join('');
      return items ? `<div class="bbcode-comparison">${items}</div>` : '<span class="bbcode-missing">[comparison] invalid image URLs [/comparison]</span>';
    });
    html = html.replace(/\[youtube\]([a-z0-9_-]{11})\[\/youtube\]/gi, (_, id) => `<div class="bbcode-embed"><iframe width="560" height="315" src="https://www.youtube-nocookie.com/embed/${escapeHtml(id)}?rel=0" title="YouTube video" allow="autoplay; encrypted-media" allowfullscreen></iframe></div>`);
    html = html.replace(/\[video\]([a-z0-9_-]{11})\[\/video\]/gi, (_, id) => `<div class="bbcode-embed"><iframe width="560" height="315" src="https://www.youtube-nocookie.com/embed/${escapeHtml(id)}?rel=0" title="YouTube video" allow="autoplay; encrypted-media" allowfullscreen></iframe></div>`);
    html = html.replace(/\[url=(https?:\/\/[^\]\s]+)\]([\s\S]*?)\[\/url\]/gi, (_, url, text) => `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${text}</a>`);
    html = html.replace(/\[url\]([^\[]+?)\[\/url\]/gi, (_, url) => {
      const safe = safeExternalUrl(url.replace(/&amp;/g, '&'));
      return safe ? `<a href="${escapeHtml(safe)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a>` : escapeHtml(url);
    });
    html = html.replace(/\[hr\]/gi, '<hr>');
    html = html.replace(/\[\*\]/g, '<li>');
    html = html.replace(/\[h([1-6])\]([\s\S]*?)\[\/h\1\]/gi, (_, level, body) => `<h${level}>${body}</h${level}>`);
    html = html.replace(/\[b\]([\s\S]*?)\[\/b\]/gi, '<strong>$1</strong>');
    html = html.replace(/\[i\]([\s\S]*?)\[\/i\]/gi, '<em>$1</em>');
    html = html.replace(/\[u\]([\s\S]*?)\[\/u\]/gi, '<u>$1</u>');
    html = html.replace(/\[s\]([\s\S]*?)\[\/s\]/gi, '<s>$1</s>');
    html = html.replace(/\[size=(\d+)\]([\s\S]*?)\[\/size\]/gi, (_, size, body) => `<span style="font-size:${Math.min(100, Math.max(10, Number(size)))}px">${body}</span>`);
    html = html.replace(/\[font=([a-z0-9 ]+)\]([\s\S]*?)\[\/font\]/gi, (_, font, body) => `<span style="font-family:${escapeHtml(font)}">${body}</span>`);
    html = html.replace(/\[color=(#[a-f0-9]{3,8}|[a-z]+)\]([\s\S]*?)\[\/color\]/gi, (_, color, body) => `<span style="color:${escapeHtml(color)}">${body}</span>`);
    html = html.replace(/\[center\]([\s\S]*?)\[\/center\]/gi, '<div class="bbcode-center">$1</div>');
    html = html.replace(/\[left\]([\s\S]*?)\[\/left\]/gi, '<div class="bbcode-left">$1</div>');
    html = html.replace(/\[right\]([\s\S]*?)\[\/right\]/gi, '<div class="bbcode-right">$1</div>');
    html = html.replace(/\[quote=(.*?)\]([\s\S]*?)\[\/quote\]/gi, '<blockquote><cite>Quoting $1:</cite><div>$2</div></blockquote>');
    html = html.replace(/\[quote\]([\s\S]*?)\[\/quote\]/gi, '<blockquote>$1</blockquote>');
    html = html.replace(/\[list=1\]([\s\S]*?)\[\/list\]/gi, '<ol>$1</ol>');
    html = html.replace(/\[list=a\]([\s\S]*?)\[\/list\]/gi, '<ol type="a">$1</ol>');
    html = html.replace(/\[list\]([\s\S]*?)\[\/list\]/gi, '<ul>$1</ul>');
    html = html.replace(/\[code\]([\s\S]*?)\[\/code\]/gi, '<pre class="bbcode-code"><code>$1</code></pre>');
    html = html.replace(/\[pre\]([\s\S]*?)\[\/pre\]/gi, '<code class="bbcode-pre">$1</code>');
    html = html.replace(/\[alert\]([\s\S]*?)\[\/alert\]/gi, '<div class="bbcode-alert">$1</div>');
    html = html.replace(/\[note\]([\s\S]*?)\[\/note\]/gi, '<div class="bbcode-note">$1</div>');
    html = html.replace(/\[sub\]([\s\S]*?)\[\/sub\]/gi, '<sub>$1</sub>');
    html = html.replace(/\[sup\]([\s\S]*?)\[\/sup\]/gi, '<sup>$1</sup>');
    html = html.replace(/\[small\]([\s\S]*?)\[\/small\]/gi, '<small>$1</small>');
    html = html.replace(/\[spoiler=(.*?)\]([\s\S]*?)\[\/spoiler\]/gi, '<details><summary>$1</summary><div>$2</div></details>');
    html = html.replace(/\[spoiler\]([\s\S]*?)\[\/spoiler\]/gi, '<details><summary>Spoiler</summary><div>$1</div></details>');
    html = html.replace(/\[table\]([\s\S]*?)\[\/table\]/gi, '<table>$1</table>');
    html = html.replace(/\[tr\]([\s\S]*?)\[\/tr\]/gi, '<tr>$1</tr>');
    html = html.replace(/\[th\]([\s\S]*?)\[\/th\]/gi, '<th>$1</th>');
    html = html.replace(/\[td\]([\s\S]*?)\[\/td\]/gi, '<td>$1</td>');
    return html.replace(/\r?\n/g, '<br>');
  }

  // Use the same renderer for every live preview update, including previews
  // triggered by the existing prepared-image and description wrappers.
  window.renderBbcode = renderUnit3dBbcode;

  const toolGroups = [
    {
      label: 'Text',
      buttons: [
        ['B', '[b]', '[/b]', 'Bold'], ['I', '[i]', '[/i]', 'Italic'], ['U', '[u]', '[/u]', 'Underline'], ['S', '[s]', '[/s]', 'Strikethrough'],
        ['Sub', '[sub]', '[/sub]', 'Subscript'], ['Sup', '[sup]', '[/sup]', 'Superscript'], ['Small', '[small]', '[/small]', 'Small text']
      ]
    },
    {
      label: 'Layout',
      buttons: [
        ['Center', '[center]', '[/center]', 'Center'], ['Left', '[left]', '[/left]', 'Left align'], ['Right', '[right]', '[/right]', 'Right align'],
        ['Quote', '[quote]', '[/quote]', 'Quote'], ['Code', '[code]', '[/code]', 'Code block'], ['Alert', '[alert]', '[/alert]', 'Alert box'], ['Note', '[note]', '[/note]', 'Note box'], ['Spoiler', '[spoiler]', '[/spoiler]', 'Spoiler']
      ]
    }
  ];

  const selectOptions = [
    ['Heading 1', '[h1]', '[/h1]'], ['Heading 2', '[h2]', '[/h2]'], ['Heading 3', '[h3]', '[/h3]'], ['Heading 4', '[h4]', '[/h4]'], ['Heading 5', '[h5]', '[/h5]'], ['Heading 6', '[h6]', '[/h6]'],
    ['Size 20', '[size=20]', '[/size]'], ['Color red', '[color=red]', '[/color]'], ['Font Arial', '[font=Arial]', '[/font]'], ['Link', '[url=https://example.com]', '[/url]'], ['Image', '[img]', '[/img]'], ['Image 600px', '[img width=600]', '[/img]'], ['Named quote', '[quote=Username]', '[/quote]'], ['Named spoiler', '[spoiler=Title]', '[/spoiler]'],
    ['Numbered list', '[list=1]\n[*]', '\n[/list]'], ['Lettered list', '[list=a]\n[*]', '\n[/list]'], ['Bullet list', '[list]\n[*]', '\n[/list]'],
    ['Table', '[table]\n[tr]\n[th]', '[/th]\n[/tr]\n[tr]\n[td][/td]\n[/tr]\n[/table]'], ['Comparison', '[comparison=Label 1,Label 2]\nhttps://image-1.example/image.jpg https://image-2.example/image.jpg', '\n[/comparison]'], ['Horizontal rule', '[hr]', ''], ['YouTube', '[youtube]', '[/youtube]'], ['Video', '[video]', '[/video]']
  ];

  function insertAtSelection(area, opening, closing) {
    const start = area.selectionStart ?? area.value.length;
    const end = area.selectionEnd ?? start;
    const selected = area.value.slice(start, end) || 'text';
    const insertion = `${opening}${selected}${closing}`;
    area.setRangeText(insertion, start, end, 'select');
    area.setSelectionRange(start + opening.length, start + opening.length + selected.length);
    area.focus();
    area.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function insertTextAtSelection(area, text) {
    const start = area.selectionStart ?? area.value.length;
    const end = area.selectionEnd ?? start;
    area.setRangeText(text, start, end, 'end');
    area.focus();
    area.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function addToolbar(area) {
    if (!area || area.parentElement.querySelector('.bbcode-toolbar')) return;
    const toolbar = document.createElement('div');
    toolbar.className = 'bbcode-toolbar';
    toolbar.setAttribute('aria-label', 'UNIT3D BBCode tools');
    toolbar.innerHTML = toolGroups.map(group => `<div class="bbcode-toolbar-group"><span>${group.label}</span>${group.buttons.map(([label, opening, closing, title]) => `<button type="button" class="bbcode-tool" data-open="${escapeHtml(opening)}" data-close="${escapeHtml(closing)}" title="${title}">${label}</button>`).join('')}</div>`).join('') + `<div class="bbcode-toolbar-group"><span>Insert</span><select class="bbcode-tool-select" aria-label="Insert UNIT3D BBCode"><option value="">Choose a tag...</option>${selectOptions.map(([label, opening, closing]) => `<option value="${escapeHtml(JSON.stringify([opening, closing]))}">${label}</option>`).join('')}</select></div><small class="bbcode-toolbar-note">UNIT3D-compatible tags · select text first for best results</small>`;
    area.parentElement.insertBefore(toolbar, area);
    toolbar.addEventListener('click', event => {
      const button = event.target.closest('[data-open]');
      if (button) insertAtSelection(area, button.dataset.open, button.dataset.close || '');
    });
    toolbar.querySelector('select')?.addEventListener('change', event => {
      if (!event.target.value) return;
      const [opening, closing] = JSON.parse(event.target.value);
      insertAtSelection(area, opening, closing);
      event.target.value = '';
    });

    // The original editor used to append prepared-image tags at the very
    // end of the description. Replace those buttons so each image is added
    // at the cursor as a separate centered block, preserving the description
    // layout on UNIT3D and in the live preview.
    document.querySelectorAll('#description-editor [data-insert]').forEach(button => {
      const replacement = button.cloneNode(true);
      button.replaceWith(replacement);
      replacement.addEventListener('click', () => {
        const tag = replacement.dataset.insert || '';
        insertTextAtSelection(area, `\n[center]${tag}[/center]\n`);
      });
    });
  }

  const originalOpenDescription = window.openDescription;
  window.openDescription = async function (id) {
    await originalOpenDescription(id);
    const area = document.querySelector('#d-description');
    if (area && typeof api === 'function') {
      const job = await api(`/api/jobs/${id}`);
      const coverIndex = (job.images || []).findIndex(image => image.image_type === 'cover');
      // Older generated drafts used image index 0 for the first preview. For
      // generated MediaInfo descriptions, keep the main block tied to the
      // cover image so it is always centerlongest, even in existing jobs.
      if (coverIndex >= 0 && area.value.includes('[b]MediaInfo[/b]') && /\[center\]\[upimg0\]\[\/center\]/i.test(area.value)) {
        area.value = area.value.replace(/\[center\]\[upimg0\]\[\/center\]/i, `[center][upimg${coverIndex}][/center]`);
        area.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }
    addToolbar(area);
  };
})();
