
    const API = '/api/xpost-blog';
    const SOURCE_VISIBLE_KEY = 'xpostBlog.sourceVisible';
    const SORT_ORDER_KEY = 'xpostBlog.sortOrder';
    const NOTE_DRAFT_STORAGE_KEY = 'xpostBlog.noteDraftUrls';
    const ICONS = {
      refresh: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6v5h-5"/><path d="M4 18v-5h5"/><path d="M18.5 9A7 7 0 0 0 6.2 6.2L4 8.5"/><path d="M5.5 15A7 7 0 0 0 17.8 17.8L20 15.5"/></svg>',
      copy: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11"/><path d="M5 15H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v1"/></svg>',
      link: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 1 0-7.1-7.1l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.1 0l-2 2a5 5 0 0 0 7.1 7.1l1.1-1.1"/></svg>',
      x: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.901 2H21l-6.873 7.855L22.5 22h-6.556l-5.135-7.341L4.385 22H2.284l7.351-8.401L1.5 2h6.722l4.642 6.636L18.901 2Z" fill="currentColor" stroke="none"/></svg>',
      discord: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 8.5c3.2-1.4 6.8-1.4 10 0"/><path d="M7.5 16.5c2.8 1.3 6.2 1.3 9 0"/><path d="M8 18c-2.4-.6-3.8-1.8-4.6-3.4.5-3.3 1.4-6.1 3.3-8.1 1.3.1 2.2.4 3.2 1"/><path d="M16 7.5c1-.6 1.9-.9 3.2-1 1.9 2 2.8 4.8 3.3 8.1-.8 1.6-2.2 2.8-4.6 3.4"/><path d="M9.5 13h.01"/><path d="M14.5 13h.01"/></svg>',
      onedrive: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8.4 18h9.1a4 4 0 0 0 .7-7.94A6.1 6.1 0 0 0 6.8 8.4 4.8 4.8 0 0 0 8.4 18Z"/></svg>',
      ogp: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6v5h-5"/><path d="M4 18v-5h5"/><path d="M18.5 9A7 7 0 0 0 6.2 6.2L4 8.5"/><path d="M5.5 15A7 7 0 0 0 17.8 17.8L20 15.5"/></svg>'
    };

    const state = {
      articles: [],
      selectedArticle: null,
      frontmatterContent: '',
      editorContent: '',
      sourceContent: '',
      sourceMeta: null,
      sourceVisible: localStorage.getItem(SOURCE_VISIBLE_KEY) !== '0',
      sortOrder: localStorage.getItem(SORT_ORDER_KEY) === 'asc' ? 'asc' : 'desc',
      dirty: false,
      selectMode: false,
      selectedArticleIds: new Set(),
      contextArticleId: '',
      affiliateMemos: { memo1: '' },
      activeAffiliateKey: 'memo1',
      affiliateDirty: false,
      noteDraftUrls: (() => {
        try {
          return JSON.parse(localStorage.getItem(NOTE_DRAFT_STORAGE_KEY) || '{}');
        } catch {
          return {};
        }
      })(),
      ogpCache: Object.create(null),
      ogpRunId: 0,
    };

    const els = {
      mainPanels: document.getElementById('mainPanels'),
      statusChip: document.getElementById('statusChip'),
      articleList: document.getElementById('articleList'),
      sortToggle: document.getElementById('sortToggle'),
      sourceToggle: document.getElementById('sourceToggle'),
      sourceBody: document.getElementById('sourceBody'),
      sourceLinks: document.getElementById('sourceLinks'),
      editor: document.getElementById('editor'),
      editorTitle: document.getElementById('editorTitle'),
      editorLinks: document.getElementById('editorLinks'),
      editorFooter: document.getElementById('editorFooter'),
      dirtyState: document.getElementById('dirtyState'),
      charCount: document.getElementById('charCount'),
      preview: document.getElementById('preview'),
      previewFooter: document.getElementById('previewFooter'),
      saveButton: document.getElementById('saveButton'),
      noteDraftButton: document.getElementById('noteDraftButton'),
      queueButton: document.getElementById('queueButton'),
      pipelineButton: document.getElementById('pipelineButton'),
      refreshButton: document.getElementById('refreshButton'),
      refreshOgpButton: document.getElementById('refreshOgpButton'),
      copyEditorButton: document.getElementById('copyEditorButton'),
      copyPreviewButton: document.getElementById('copyPreviewButton'),
      insertAffiliateButton: document.getElementById('insertAffiliateButton'),
      sidebar: document.getElementById('sidebar'),
      sourcePanel: document.getElementById('sourcePanel'),
      editorPanel: document.getElementById('editorPanel'),
      sidebarHandle: document.getElementById('sidebarHandle'),
      sourceHandle: document.getElementById('sourceHandle'),
      editorHandle: document.getElementById('editorHandle'),
      affiliateLauncher: document.getElementById('affiliateLauncher'),
      affiliateModalBackdrop: document.getElementById('affiliateModalBackdrop'),
      closeAffiliateButton: document.getElementById('closeAffiliateButton'),
      reloadAffiliateButton: document.getElementById('reloadAffiliateButton'),
      saveAffiliateButton: document.getElementById('saveAffiliateButton'),
      addMemoButton: document.getElementById('addMemoButton'),
      memoTabs: document.getElementById('memoTabs'),
      affiliateEditor: document.getElementById('affiliateEditor'),
      affiliateStatus: document.getElementById('affiliateStatus'),
      insertAffiliateFromModalButton: document.getElementById('insertAffiliateFromModalButton'),
      articleContextMenu: document.getElementById('articleContextMenu'),
      contextSelectButton: document.getElementById('contextSelectButton'),
      contextDuplicateButton: document.getElementById('contextDuplicateButton'),
      contextDeleteButton: document.getElementById('contextDeleteButton'),
      contextOpenOneDriveButton: document.getElementById('contextOpenOneDriveButton'),
      contextOpenExplorerButton: document.getElementById('contextOpenExplorerButton'),
    };

    function initIcons() {
      els.refreshButton.innerHTML = ICONS.refresh;
      els.refreshOgpButton.innerHTML = ICONS.ogp;
      els.insertAffiliateButton.innerHTML = ICONS.link;
      els.copyEditorButton.innerHTML = ICONS.copy;
      els.copyPreviewButton.innerHTML = ICONS.copy;
    }

    function setStatus(message, isError = false) {
      els.statusChip.textContent = message;
      els.statusChip.title = message;
      els.statusChip.style.color = isError ? 'var(--danger)' : 'var(--text-soft)';
    }

    function setAffiliateStatus(message, isError = false) {
      els.affiliateStatus.textContent = message;
      els.affiliateStatus.style.color = isError ? 'var(--danger)' : 'var(--text-soft)';
    }

    function persistNoteDraftUrls() {
      try {
        localStorage.setItem(NOTE_DRAFT_STORAGE_KEY, JSON.stringify(state.noteDraftUrls));
      } catch {
        // localStorage 鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貅ｷ譯√・・ｽ繝ｻ・｡驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｻ鬩包ｽｶ闔ｨ竏壹・郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬯ｮ・｢繝ｻ・ｻ郢晢ｽｻ繝ｻ・ｸ鬯ｮ・ｯ雋・･繝ｻ驛｢譎｢・ｽ・ｻ鬩搾ｽｵ繝ｻ・ｲ髯懶ｽ｣繝ｻ・､郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｯ鬯ｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・｡鬯ｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・｢鬯ｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｪ鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陟托ｽｱ郢晢ｽｻ髣費｣ｰ隲橸ｽｺ邵ｺ蜉ｱ繝ｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮｣豈費ｽｼ螟ｲ・ｽ・ｽ繝ｻ・｣鬩搾ｽｵ繝ｻ・ｲ髯晢ｽｶ隴擾ｽｴ繝ｻ・ｰ鬮ｯ讓奇ｽｺ・ｷ繝ｻ・･郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・｡鬮ｯ貅ｷ萓帙・・ｨ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ
      }
    }

    function escapeHtml(text) {
      return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function apiUrl(resource, params = {}) {
      const url = new URL(API, window.location.origin);
      url.searchParams.set('resource', resource);
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          url.searchParams.set(key, value);
        }
      });
      return url.toString();
    }
    function renderMarkdown(text) {
      if (!text || !String(text).trim()) {
        return '<div class="empty">鬯ｯ・ｮ繝ｻ・ｯ郢晢ｽｻ繝ｻ・ｦ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｨ鬯ｯ・ｩ驕ｨ繧托ｽｽ・ｼ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ繝ｻ・ｷ郢晢ｽｻ繝ｻ・ｶ驛｢譎｢・ｽ・ｻ鬩阪・謌滂ｾつ陷･謫ｾ・ｽ・ｹ隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｮ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｹ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貅ｷ萓帙・・ｨ繝ｻ・ｯ髫ｴ魃会ｽｽ・ｺ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬯ｩ諤憺●繝ｻ・ｽ繝ｻ・ｫ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ譎｢・ｽ・ｶ髯ｷ・ｻ繝ｻ・ｻ郢晢ｽｻ繝ｻ・ｽ驛｢譎｢・ｽ・ｻ/div>';
      }
      if (window.marked?.parse) {
        return marked.parse(text, { breaks: true, gfm: true });
      }
      return `<pre>${escapeHtml(text)}</pre>`;
    }

    function composeMarkdownDocument(frontmatter, body) {
      const normalizedBody = String(body || '').trim();
      const normalizedFrontmatter = String(frontmatter || '').trim();
      if (!normalizedFrontmatter) return normalizedBody;
      return normalizedBody ? `${normalizedFrontmatter}\n\n${normalizedBody}\n` : `${normalizedFrontmatter}\n`;
    }

    function articleTitle(article) {
      return article?.h1Title || String(article?.name || '').replace(/\.md$/i, '') || '鬯ｮ・ｴ陷ｿ蜴・ｽｽ・ｻ郢ｧ謇假ｽｽ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・｡鬯ｯ・ｯ繝ｻ・ｯ髯区ｻゑｽｽ・･驛｢譎｢・ｽ・ｻ;
    }

    function formatDate(value) {
      if (!value) return '';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return '';
      return new Intl.DateTimeFormat('ja-JP', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      }).format(date);
    }

    function formatDiscordDate(value) {
      if (!value) return '';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return '';
      return new Intl.DateTimeFormat('ja-JP', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      }).format(date);
    }

    function formatPostedLabel(value) {
      const formatted = formatDiscordDate(value);
      return formatted ? `${formatted} 鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｨ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ` : '-';
    }

    function articleSortTimestamp(article) {
      const value = article?.discordPostedAt || article?.sourcePublishedAt || article?.sortPublishedAt || article?.lastModified || '';
      const date = new Date(value);
      const time = date.getTime();
      return Number.isNaN(time) ? 0 : time;
    }

    function sortedArticles() {
      const direction = state.sortOrder === 'asc' ? 1 : -1;
      return [...state.articles].sort((a, b) => {
        const diff = articleSortTimestamp(a) - articleSortTimestamp(b);
        if (diff !== 0) return diff * direction;
        return String(a.name || '').localeCompare(String(b.name || ''), 'ja-JP') * direction;
      });
    }

    function updateSortButton() {
      const isAsc = state.sortOrder === 'asc';
      els.sortToggle.textContent = isAsc ? '鬯ｩ蟷｢・ｽ・｢髫ｴ蠑ｱ繝ｻ繝ｻ・ｽ繝ｻ・ｼ髫ｴ竏ｫ・ｵ・ｶ髫伜､懶ｽｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｫ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ: 鬯ｮ・ｫ繝ｻ・ｴ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｰ鬯ｯ・ｨ繝ｻ・ｾ郢晢ｽｻ繝ｻ・ｹ郢晢ｽｻ邵ｺ・､・つ鬯ｩ蛹・ｽｽ・ｶ鬩怜遜・ｽ・ｫ驛｢譎｢・ｽ・ｻ : '鬯ｩ蟷｢・ｽ・｢髫ｴ蠑ｱ繝ｻ繝ｻ・ｽ繝ｻ・ｼ髫ｴ竏ｫ・ｵ・ｶ髫伜､懶ｽｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｫ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ: 鬯ｮ・ｫ繝ｻ・ｴ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｰ鬯ｯ・ｨ繝ｻ・ｾ郢晢ｽｻ繝ｻ・ｹ郢晢ｽｻ邵ｺ・､・つ鬯ｩ蛹・ｽｽ・ｶ鬩怜遜・ｽ・ｫ驛｢譎｢・ｽ・ｻ;
      els.sortToggle.title = isAsc ? '鬯ｮ・ｫ繝ｻ・ｴ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｰ鬯ｯ・ｨ繝ｻ・ｾ郢晢ｽｻ繝ｻ・ｹ郢晢ｽｻ邵ｺ・､・つ鬯ｯ・ｯ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ髯橸ｽｳ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｭ髣包ｽｳ驗呻ｽｫ郢晢ｽｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬩搾ｽｵ繝ｻ・ｲ髯晢ｽｶ隴主臆・ｷ譎会ｽｹ譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｨ鬯ｯ・ｩ驕ｨ繧托ｽｽ・ｼ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｲ鬩幢ｽ｢繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｪ鬯ｩ蟷｢・ｽ・｢髫ｴ謫ｾ・ｽ・ｴ驛｢譎｢・ｽ・ｻ鬩搾ｽｵ繝ｻ・ｺ鬯ｩ・｢隰ｳ・ｾ繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｧ鬯ｯ・ｯ繝ｻ・ｮ郢晢ｽｻ繝ｻ・ｯ鬮ｯ諞ｺ螻ｮ繝ｻ・ｽ繝ｻ・ｼ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬩包ｽｶ鬯・汚・ｽ・･繝ｻ・｢髯晢｣ｰ隲ｷ蛹・ｽｽ・ｹ隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ驛｢譎｢・ｽ・ｻ鬯ｯ莨懌・繝ｻ・ｽ繝ｻ・ｭ髯ｷ・ｴ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｿ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ : '鬯ｮ・ｫ繝ｻ・ｴ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｰ鬯ｯ・ｨ繝ｻ・ｾ郢晢ｽｻ繝ｻ・ｹ郢晢ｽｻ邵ｺ・､・つ鬯ｯ・ｯ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ髯晢ｽｶ隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｯ鬮ｯ諞ｺ螻ｮ繝ｻ・ｽ繝ｻ・ｼ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬩搾ｽｵ繝ｻ・ｲ髯晢ｽｶ隴主臆・ｷ譎会ｽｹ譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｨ鬯ｯ・ｩ驕ｨ繧托ｽｽ・ｼ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｲ鬩幢ｽ｢繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｪ鬯ｩ蟷｢・ｽ・｢髫ｴ謫ｾ・ｽ・ｴ驛｢譎｢・ｽ・ｻ鬩搾ｽｵ繝ｻ・ｺ鬯ｩ・｢隰ｳ・ｾ繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｧ鬯ｮ・ｫ繝ｻ・ｴ髣包ｽｳ驗呻ｽｫ郢晢ｽｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬩包ｽｶ鬯・汚・ｽ・･繝ｻ・｢髯晢｣ｰ隲ｷ蛹・ｽｽ・ｹ隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ驛｢譎｢・ｽ・ｻ鬯ｯ莨懌・繝ｻ・ｽ繝ｻ・ｭ髯ｷ・ｴ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｿ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ;
      els.sortToggle.setAttribute('aria-label', els.sortToggle.title);
    }

    function iconLink(href, label, iconName) {
      const safeLabel = escapeHtml(label);
      const icon = ICONS[iconName] || '';
      if (!href) {
        return `<a class="icon-link" aria-disabled="true" aria-label="${safeLabel}" title="${safeLabel}">${icon}</a>`;
      }
      return `<a class="icon-link" href="${escapeHtml(href)}" target="_blank" rel="noreferrer" aria-label="${safeLabel}" title="${safeLabel}">${icon}</a>`;
    }

    function setSourceVisible(visible) {
      state.sourceVisible = Boolean(visible);
      localStorage.setItem(SOURCE_VISIBLE_KEY, state.sourceVisible ? '1' : '0');
      els.mainPanels.classList.toggle('source-hidden', !state.sourceVisible);
      els.sourceToggle.setAttribute('aria-pressed', state.sourceVisible ? 'true' : 'false');
    }

    function renderArticleList() {
      els.articleList.classList.toggle('selecting', state.selectMode);
      if (!state.articles.length) {
        els.articleList.innerHTML = '<div class="empty">鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｵ髫ｴ謫ｾ・ｽ・ｶ繝ｻ縺､ﾂ郢晢ｽｻ繝ｻ・ｲ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ鬯ｯ蛟ｩ・ｲ・ｻ繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ譎｢・ｽ・ｶ髯ｷ・ｻ繝ｻ・ｻ郢晢ｽｻ繝ｻ・ｽ驛｢譎｢・ｽ・ｻ/div>';
        return;
      }

      els.articleList.innerHTML = sortedArticles().map((article) => {
        const isActive = state.selectedArticle?.id === article.id;
        const isSelected = state.selectedArticleIds.has(article.id);
        const articlePath = [article.path || '', article.name || ''].filter(Boolean).join('/');
        const fallbackDate = formatDate(article.lastModified);
        const discordDate = formatDiscordDate(article.discordPostedAt);
        const sourceDate = formatDiscordDate(article.sourcePublishedAt);
        const timeLabel = discordDate
          ? `${discordDate} 鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｨ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ`
          : sourceDate
            ? `${sourceDate} 鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｨ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ`
            : `鬯ｮ・ｫ繝ｻ・ｴ髯ｷ・ｴ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｴ鬯ｮ・ｫ繝ｻ・ｴ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｰ: ${fallbackDate || '-'}`;
        return `
          <button type="button" class="article-row ${isActive ? 'active' : ''} ${isSelected ? 'selected' : ''}" data-article-id="${escapeHtml(article.id)}">
            <span class="article-check" aria-hidden="true">${isSelected ? '<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>' : ''}</span>
            <span class="article-row-main">
              <span class="article-title">${escapeHtml(articleTitle(article))}</span>
              <span class="article-meta article-time">${escapeHtml(timeLabel)}</span>
            </span>
          </button>
        `;
      }).join('');

      els.articleList.querySelectorAll('[data-article-id]').forEach((button) => {
        button.addEventListener('click', () => {
          const article = state.articles.find((item) => item.id === button.dataset.articleId);
          if (!article) return;
          if (state.selectMode) {
            toggleArticleSelection(article.id);
            return;
          }
          selectArticle(article).catch((error) => setStatus(error.message, true));
        });
        button.addEventListener('contextmenu', (event) => {
          const article = state.articles.find((item) => item.id === button.dataset.articleId);
          if (article) openArticleContextMenu(event, article);
        });
      });
    }

    function setSelectionStatus() {
      const count = state.selectedArticleIds.size;
      setStatus(count ? `${count}鬯ｮ・｣雎郁ｲｻ・ｽ・ｼ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｶ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬮ｯ譎｢・ｽ・ｶ髫ｴ謫ｾ・ｽ・ｶ驛｢譎｢・ｽ・ｻ鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｨ鬮ｮ蜈ｷ・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ` : '鬯ｯ・ｯ繝ｻ・ｩ髯具ｽｹ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｧ郢晢ｽｻ繝ｻ・ｭ郢晢ｽｻ陞ｳ莠･謫郢晢ｽｻ繝ｻ・ｹ髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｼ鬯ｩ蟷｢・ｽ・｢髫ｴ蜿門ｾ励・・ｽ繝ｻ・ｳ郢晢ｽｻ繝ｻ・ｨ鬩搾ｽｵ繝ｻ・ｲ髯懶ｽ｣繝ｻ・､郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ);
    }

    function enterSelectMode(article) {
      state.selectMode = true;
      state.selectedArticleIds = new Set([article.id]);
      closeArticleContextMenu();
      renderArticleList();
      setSelectionStatus();
    }

    function clearSelectMode() {
      state.selectMode = false;
      state.selectedArticleIds.clear();
      renderArticleList();
      setStatus('鬯ｯ・ｯ繝ｻ・ｩ髯具ｽｹ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｧ郢晢ｽｻ繝ｻ・ｭ驛｢譎｢・ｽ・ｻ髯晢ｽｶ隴惹ｸ橸ｽｰ閧ｲ・ｹ譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｣鬯ｯ・ｯ繝ｻ・ｮ郢晢ｽｻ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・､鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
    }

    function toggleArticleSelection(articleId) {
      if (state.selectedArticleIds.has(articleId)) {
        state.selectedArticleIds.delete(articleId);
      } else {
        state.selectedArticleIds.add(articleId);
      }
      renderArticleList();
      setSelectionStatus();
    }

    function contextArticle() {
      return state.articles.find((article) => article.id === state.contextArticleId) || null;
    }

    function closeArticleContextMenu() {
      els.articleContextMenu.hidden = true;
      state.contextArticleId = '';
    }

    function openArticleContextMenu(event, article) {
      event.preventDefault();
      event.stopPropagation();

      const menuWidth = 220;
      const menuHeight = 252;
      const x = Math.max(8, Math.min(event.clientX, window.innerWidth - menuWidth - 8));
      const y = Math.max(8, Math.min(event.clientY, window.innerHeight - menuHeight - 8));

      state.contextArticleId = article.id;
      els.contextOpenOneDriveButton.disabled = !article.webUrl;
      els.contextOpenExplorerButton.disabled = !article.name;
      els.articleContextMenu.style.left = `${x}px`;
      els.articleContextMenu.style.top = `${y}px`;
      els.articleContextMenu.hidden = false;
    }

    function clearArticlePanels() {
      state.selectedArticle = null;
      state.frontmatterContent = '';
      state.editorContent = '';
      state.sourceContent = '';
      state.sourceMeta = null;
      state.dirty = false;
      els.editor.value = '';
      els.editorTitle.textContent = '鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｨ鬯ｩ蟷｢・ｽ・｢髫ｴ謫ｾ・ｽ・ｴ驛｢譎｢・ｽ・ｻ鬩搾ｽｵ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｹ郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｼ';
      els.sourceLinks.innerHTML = '';
      els.sourceBody.innerHTML = '<div class="empty">鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｵ髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ髯晢ｽｶ隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｩ髯具ｽｹ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｧ郢晢ｽｻ繝ｻ・ｭ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｦ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｳ髯晢ｽｯ繝ｻ・ｩ髯ｷ・ｻ繝ｻ・ｳ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬯ｮ・ｴ鬩帙・・ｽ・ｲ繝ｻ・ｻ郢晢ｽｻ繝ｻ・ｼ驛｢譎｢・ｽ・ｻ/div>';
      els.preview.innerHTML = '<div class="empty">鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｵ髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ髯晢ｽｶ隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｩ髯具ｽｹ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｧ郢晢ｽｻ繝ｻ・ｭ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｦ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｳ髯晢ｽｯ繝ｻ・ｩ髯ｷ・ｻ繝ｻ・ｳ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬯ｮ・ｴ鬩帙・・ｽ・ｲ繝ｻ・ｻ郢晢ｽｻ繝ｻ・ｼ驛｢譎｢・ｽ・ｻ/div>';
      updateEditorMeta();
      renderEditorLinks();
    }

    function duplicateName(name) {
      return `鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｳ鬯ｩ蟷｢・ｽ・｢髫ｴ蠑ｱ繝ｻ繝ｻ・ｱ陜｣・､繝ｻ・ｹ隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ_${name || '鬯ｮ・ｴ陷ｿ蜴・ｽｽ・ｻ郢ｧ謇假ｽｽ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・｡鬯ｯ・ｯ繝ｻ・ｯ髯区ｻゑｽｽ・･驛｢譎｢・ｽ・ｻmd'}`;
    }

    async function duplicateArticle(article) {
      if (!article) return;
      closeArticleContextMenu();
      setStatus('鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｵ髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ髯晢ｽｶ隴惹ｸ樊･憺ｩ幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｣驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ');
      const newName = duplicateName(article.name);
      const response = await fetch(apiUrl('articles'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fileId: article.id,
          newName,
          folderPath: article.path || '',
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || '鬯ｯ・ｮ繝ｻ・ｫ鬯ｮ・ｦ繝ｻ・ｪ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｣驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｫ鬯ｮ・ｯ隶灘･・ｽｽ・ｻ郢ｧ謇假ｽｽ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｱ鬯ｮ・ｫ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｨ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);

      state.articles = [
        {
          ...article,
          id: payload.id || '',
          name: payload.name || newName,
          webUrl: payload.webUrl || '',
          lastModified: payload.lastModified || new Date().toISOString(),
          size: payload.size || article.size || 0,
        },
        ...state.articles,
      ];
      renderArticleList();
      setStatus('鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｵ髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ髯晢ｽｶ隴惹ｸ樊･憺ｩ幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｣驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
    }

    async function deleteArticle(article) {
      if (!article) return;
      closeArticleContextMenu();
      const label = articleTitle(article);
      if (!window.confirm(`鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｲ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ{label}鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｲ鬯ｯ・ｮ繝ｻ・ｦ郢晢ｽｻ繝ｻ・ｪ驛｢譎｢・ｽ・ｻ髯橸ｽｳ陞｢・ｽ遶包ｽｧ鬮｣雋ｻ・ｽ・ｨ驕ｶ荵怜・繝ｻ・ｱ郢ｧ荵晢ｼ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ繝ｻ・ｷ郢晢ｽｻ繝ｻ・ｶ郢晢ｽｻ邵ｺ・､・つ鬩幢ｽ｢繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｼ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｮ鬯ｮ・ｫ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｫ鬮ｯ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ鬮ｫ・ｲ陝ｶ・ｷ繝ｻ・ｿ繝ｻ・ｫ驛｢譎｢・ｽ・ｻ鬯ｮ・ｯ繝ｻ・ｷ郢晢ｽｻ繝ｻ・ｿ鬮ｫ・ｰ髮具ｽｻ繝ｻ・ｽ繝ｻ・ｶ驛｢譎｢・ｽ・ｻ鬯ｯ莨懌・繝ｻ・ｽ繝ｻ・ｱ郢晢ｽｻ繝ｻ・ｸ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｻ鬮ｫ・ｨ繝ｻ・ｳ髴托ｽ｢隴会ｽｦ繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ譎｢・ｽ・ｶ髯ｷ・ｻ繝ｻ・ｻ郢晢ｽｻ繝ｻ・ｽ鬯ｪ・ｰ陷茨ｽｷ繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｲ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｡)) return;

      setStatus('鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｵ髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ髯橸ｽｳ陞｢・ｽ遶包ｽｧ鬮｣雋ｻ・ｽ・ｨ驕ｶ荵怜・繝ｻ・ｱ郢ｧ邇也ｵ｡郢晢ｽｻ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ');
      const response = await fetch(apiUrl('articles'), {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fileId: article.id }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || '鬯ｮ・ｯ繝ｻ・ｷ髯ｷ・ｿ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｼ驕ｶ荵怜・繝ｻ・ｱ郢ｧ荵晢ｼ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｫ鬯ｮ・ｯ隶灘･・ｽｽ・ｻ郢ｧ謇假ｽｽ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｱ鬯ｮ・ｫ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｨ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);

      const wasSelected = state.selectedArticle?.id === article.id;
      state.articles = state.articles.filter((item) => item.id !== article.id);
      state.selectedArticleIds.delete(article.id);

      if (state.selectedArticleIds.size === 0) state.selectMode = false;
      renderArticleList();

      if (wasSelected) {
        const nextArticle = sortedArticles()[0] || null;
        if (nextArticle) {
          await selectArticle(nextArticle);
        } else {
          clearArticlePanels();
        }
      }

      setStatus('鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｵ髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ髯橸ｽｳ陞｢・ｽ遶包ｽｧ鬮｣雋ｻ・ｽ・ｨ驕ｶ荵怜・繝ｻ・ｱ郢ｧ荵晢ｼ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
    }

    function openOneDriveArticle(article) {
      if (!article?.webUrl) return;
      window.open(article.webUrl, '_blank', 'noopener,noreferrer');
      closeArticleContextMenu();
    }

    function openExplorerArticle(article) {
      if (!article) return;
      const localPath = ['X鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｨ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ', article.path || ''].filter(Boolean).join('/');
      if (article.webUrl) {
        window.open(article.webUrl, '_blank', 'noopener,noreferrer');
      }
      closeArticleContextMenu();
      setStatus('鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｨ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｯ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｹ鬯ｩ蟷｢・ｽ・｢髫ｴ諠ｹ・ｸ讖ｸ・ｽ・ｹ繝ｻ・ｲ郢晢ｽｻ陷ｿ蜴・ｽｽ・ｺ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｹ髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｼ鬯ｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｩ鬯ｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｼ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｧ鬯ｯ・ｮ繝ｻ・ｯ郢晢ｽｻ繝ｻ・ｦ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｨ鬯ｯ・ｩ驕ｨ繧托ｽｽ・ｼ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ);
    }
    function renderSourcePanel() {
      const item = state.sourceMeta;
      if (!item) {
        els.sourceLinks.innerHTML = '';
        els.sourceBody.innerHTML = '<div class="empty">陷医・蜈憺◇・ｿ邵ｺ蠕娯旺郢ｧ鄙ｫ竏ｪ邵ｺ蟶呻ｽ・/div>';
        return;
      }

      const stats = [
        ['隰壽・・ｨ・ｿ髢繝ｻ, item.authorName || item.authorUsername || '-'],
        ['Discord隰暦ｽｲ髴医・, formatPostedLabel(item.observedAt || item.discordPostedAt)],
        ['邵ｺ繝ｻ・樒ｸｺ・ｭ', item.favoriteCount ?? item.likeCount ?? 0],
        ['郢晢ｽｪ郢晄亢縺帷ｹ昴・, item.repostCount ?? item.retweetCount ?? 0],
        ['霑･・ｶ隲ｷ繝ｻ, item.articleStatus || item.status || '-'],
      ];

      els.sourceLinks.innerHTML = [
        `<button type="button" class="icon-button" id="sourceInlineCopyButton" aria-label="隴幢ｽｬ隴√・縺慕ｹ晄鱒繝ｻ" title="隴幢ｽｬ隴√・縺慕ｹ晄鱒繝ｻ">${ICONS.copy}</button>`,
        iconLink(item.postUrl || item.xUrl || item.url, 'X郢ｧ蟶晏ｹ慕ｸｺ繝ｻ, 'x'),
        iconLink(item.discordJumpUrl || item.discordUrl, 'Discord郢ｧ蟶晏ｹ慕ｸｺ繝ｻ, 'discord'),
      ].join('');

      const sourceInlineCopyButton = document.getElementById('sourceInlineCopyButton');
      if (sourceInlineCopyButton) {
        sourceInlineCopyButton.addEventListener('click', () => copyText(state.sourceContent, '陷医・蜈憺◇・ｿ郢ｧ蛛ｵ縺慕ｹ晄鱒繝ｻ邵ｺ蜉ｱ竏ｪ邵ｺ蜉ｱ笳・).catch((error) => setStatus(error.message, true)));
      }

      els.sourceBody.innerHTML = `
        <div class="meta-grid">
          ${stats.map(([label, value]) => `
            <div class="meta-cell">
              <strong>${escapeHtml(label)}</strong>
              <span>${escapeHtml(String(value))}</span>
            </div>
          `).join('')}
        </div>
        <div class="markdown">${renderMarkdown(state.sourceContent)}</div>
      `;
    }

    function renderEditorLinks() {
      const articleUrl = state.sourceMeta?.articleWebUrl || state.selectedArticle?.webUrl || '';
      els.editorLinks.innerHTML = iconLink(articleUrl, 'OneDrive髫ｪ蛟・ｽｺ繝ｻ, 'onedrive');
    }

    function updateEditorMeta() {
      const count = els.editor.value.length;
      els.charCount.textContent = `${count.toLocaleString('ja-JP')}鬯ｮ・ｯ隴擾ｽｴ郢晢ｽｻ郢晢ｽｻ繝ｻ・ｼ郢晢ｽｻ繝ｻ・ｿ;
      els.dirtyState.textContent = state.dirty ? '鬯ｮ・ｫ繝ｻ・ｴ髯晢ｽｷ繝ｻ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｪ鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陷ｿ髢・ｾ蜉ｱ繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｭ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ : '鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陷ｿ髢・ｾ蜉ｱ繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｭ鬮｣蜴・ｽｽ・ｫ郢晢ｽｻ繝ｻ・ｶ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｻ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｩ';
      els.editorFooter.textContent = 'Ctrl+S / Command+S 鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｧ鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陷ｿ髢・ｾ蜉ｱ繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｭ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ;
    }

    function renderPreview(forceOgp = false) {
      state.editorContent = els.editor.value;
      els.preview.innerHTML = renderMarkdown(state.editorContent);
      updateEditorMeta();
      queueOgpCards(forceOgp);
    }
    async function fetchArticles(forceReload = false) {
      setStatus(forceReload ? 'OneDrive鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬯ｮ・ｮ陋ｹ・ｺ繝ｻ・ｧ繝ｻ・ｭ驛｢譎｢・ｽ・ｻ鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｯ・ｮ繝ｻ・ｴ鬮ｮ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｼ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ' : '鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮ｯ蛹ｺ・ｻ繧托ｽｽ・ｽ繝ｻ・ｶ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ邵ｺ・､・つ鬯ｯ・ｮ繝ｻ・ｫ髯具ｽｹ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｧ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬯ｮ・ｮ陋ｹ・ｺ繝ｻ・ｧ繝ｻ・ｫ髯溷供・ｮ・｣髴趣ｽｧ髯ｷ閧ｴ・ｻ繧托ｽｽ・ｽ繝ｻ・ｶ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ');
      const previousId = state.selectedArticle?.id;
      const response = await fetch(apiUrl('articles', { refresh: Date.now() }), { cache: 'no-store' });
      if (!response.ok) throw new Error('鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮ｯ蛹ｺ・ｻ繧托ｽｽ・ｽ繝ｻ・ｶ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ邵ｺ・､・つ鬯ｯ・ｮ繝ｻ・ｫ髯具ｽｹ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｧ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｮ鬯ｮ・ｯ繝ｻ・ｷ郢晢ｽｻ繝ｻ・ｿ鬯ｯ・ｮ繝ｻ・｢繝ｻ縺､ﾂ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ鬯・汚・ｽ・･繝ｻ・｢髫ｴ・ｽ隴∬・繝ｻ郢晢ｽｻ繝ｻ・ｱ鬯ｮ・ｫ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｨ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
      const data = await response.json();
      state.articles = data.articles || [];
      state.selectedArticle = previousId ? state.articles.find((article) => article.id === previousId) || null : null;
      renderArticleList();
      setStatus(forceReload ? `OneDrive鬯ｮ・ｯ繝ｻ・ｷ繝ｻ縺､ﾂ鬮ｯ譎｢・｣・ｰ鬮ｮ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｪ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｯ・ｮ繝ｻ・ｴ鬮ｮ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｼ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｮ・ｯ隶厄ｽｸ繝ｻ・ｽ繝ｻ・ｳ鬮ｯ貅ｷ譯√・・ｽ繝ｻ・｡驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ${state.articles.length}鬯ｮ・｣雎郁ｲｻ・ｽ・ｼ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｶ` : `鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮ｯ蛹ｺ・ｻ繧托ｽｽ・ｽ繝ｻ・ｶ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ邵ｺ・､・つ鬯ｯ・ｮ繝ｻ・ｫ髯具ｽｹ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｧ ${state.articles.length}鬯ｮ・｣雎郁ｲｻ・ｽ・ｼ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｶ`);
      const firstArticle = sortedArticles()[0];
      if (!state.selectedArticle && firstArticle) {
        await selectArticle(firstArticle);
      } else if (state.selectedArticle) {
        await selectArticle(state.selectedArticle);
      }
    }

    async function selectArticle(article) {
      state.selectedArticle = article;
      state.dirty = false;
      renderArticleList();
      renderEditorLinks();
      els.editorTitle.textContent = articleTitle(article);
      setStatus('鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｫ・ｰ髮具ｽｻ繝ｻ・ｽ繝ｻ・ｽ鬯ｮ・ｫ繝ｻ・ｴ驕ｶ荳橸ｽ｣・ｹ郢晢ｽｻ驛｢譎｢・ｽ・ｻ髯橸ｽｳ陞｢・ｽ隨翫ｋ・ｬ・ｮ繝ｻ・｢繝ｻ縺､ﾂ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬮ｯ貊楢ｪ薙・・ｽ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ');

      const [articleResponse, sourceResponse] = await Promise.all([
        fetch(apiUrl('articles', { id: article.id }), { cache: 'no-store' }),
        fetch(apiUrl('index', { articleId: article.id }), { cache: 'no-store' }),
      ]);

      if (!articleResponse.ok) throw new Error('鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｫ・ｰ髮具ｽｻ繝ｻ・ｽ繝ｻ・ｽ鬯ｮ・ｫ繝ｻ・ｴ驕ｶ荳橸ｽ｣・ｹ郢晢ｽｻ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬯ｮ・ｯ繝ｻ・ｷ郢晢ｽｻ繝ｻ・ｿ鬯ｯ・ｮ繝ｻ・｢繝ｻ縺､ﾂ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ鬯・汚・ｽ・･繝ｻ・｢髫ｴ・ｽ隴∬・繝ｻ郢晢ｽｻ繝ｻ・ｱ鬯ｮ・ｫ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｨ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
      const articleData = await articleResponse.json();
      state.frontmatterContent = articleData.frontmatter || '';
      state.editorContent = articleData.body || articleData.content || '';
      els.editor.value = state.editorContent;

      if (sourceResponse.ok) {
        const sourceData = await sourceResponse.json();
        state.sourceMeta = sourceData.item || null;
        state.sourceContent = sourceData.sourceContent || '';
      } else {
        state.sourceMeta = null;
        state.sourceContent = '';
      }

      renderSourcePanel();
      renderEditorLinks();
      renderPreview(false);
      void fetchNoteDraftUrl(article.id);
      setStatus('鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｵ髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ髯晢ｽｶ隴惹ｹ怜･鈴Δ譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｯ・ｮ繝ｻ・ｴ鬮ｮ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｼ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
    }

    async function saveCurrentArticle() {
      if (!state.selectedArticle) {
        setStatus('鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陷ｿ髢・ｾ蜉ｱ繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｭ鬮｣雋ｻ・ｽ・ｨ髫ｲ蟷｢・ｽ・ｶ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｯ・ｮ繝ｻ・ｮ鬮ｮ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・｡鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｮ鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｵ髫ｴ謫ｾ・ｽ・ｶ繝ｻ縺､ﾂ郢晢ｽｻ繝ｻ・ｲ鬯ｮ・ｫ繝ｻ・ｴ髯晢ｽｷ繝ｻ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｪ鬯ｯ・ｯ繝ｻ・ｩ髯具ｽｹ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｧ郢晢ｽｻ繝ｻ・ｭ鬩搾ｽｵ繝ｻ・ｲ髯懶ｽ｣繝ｻ・､郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ, true);
        return false;
      }

      setStatus('鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陷ｿ髢・ｾ蜉ｱ繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｭ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ');
      const response = await fetch(apiUrl('articles'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: state.selectedArticle.name,
          fileId: state.selectedArticle.id,
          content: composeMarkdownDocument(state.frontmatterContent, els.editor.value),
        }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || '鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陷ｿ髢・ｾ蜉ｱ繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｭ鬮ｯ蛹ｺ・ｻ繧托ｽｽ・ｽ繝ｻ・･鬩包ｽｶ鬯・汚・ｽ・･繝ｻ・｢髫ｴ・ｽ隴∬・繝ｻ郢晢ｽｻ繝ｻ・ｱ鬯ｮ・ｫ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｨ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
      }

      const payload = await response.json();
      state.selectedArticle = {
        ...state.selectedArticle,
        id: payload.id || state.selectedArticle.id,
        name: payload.name || state.selectedArticle.name,
        webUrl: payload.webUrl || state.selectedArticle.webUrl,
        lastModified: payload.lastModified || new Date().toISOString(),
      };
      state.dirty = false;
      updateEditorMeta();
      renderEditorLinks();
      renderArticleList();
      setStatus('鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陷ｿ髢・ｾ蜉ｱ繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｭ鬮ｯ蛹ｺ・ｻ繧托ｽｽ・ｽ繝ｻ・･驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
      return true;
    }

    async function triggerWorkflow(mode, statusMessage, errorMessage) {
      setStatus(statusMessage);
      const response = await fetch(apiUrl('trigger'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, max_items: 0 }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || errorMessage);
      setStatus(payload.message || statusMessage.replace('鬯ｮ・ｯ隶厄ｽｸ繝ｻ・ｽ繝ｻ・ｳ鬮ｮ荵昴・繝ｻ・ｽ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｡鬮ｯ貅ｷ譯√・・ｽ繝ｻ・｡驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ', '鬯ｮ・ｫ闖ｫ・ｶ髫ｱ阮吶・繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｷ鬯ｮ・ｯ繝ｻ・ｷ髯晢｣ｰ髮懶ｽ｣繝ｻ・ｽ繝ｻ・ｼ鬮ｮ蜈ｷ・ｽ・ｻ郢晢ｽｻ繝ｻ・ｼ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ));
    }

    async function triggerQueue() {
      return triggerWorkflow('process_queue', 'QUE鬯ｮ・ｯ繝ｻ・ｷ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｦ鬯ｯ・ｨ繝ｻ・ｾ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ髯橸ｽｳ陞｢・ｽ繝ｻ・･隲帙・・ｽ・ｲ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｡鬮ｯ貅ｷ譯√・・ｽ繝ｻ・｡驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ', 'QUE鬯ｮ・ｯ繝ｻ・ｷ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｦ鬯ｯ・ｨ繝ｻ・ｾ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬯ｮ・ｯ隶厄ｽｸ繝ｻ・ｽ繝ｻ・ｳ鬮ｮ荵昴・繝ｻ・ｽ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｡鬮ｯ貅ｷ萓帙・・ｨ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ鬯ｮ・ｯ隶灘･・ｽｽ・ｻ郢ｧ謇假ｽｽ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｱ鬯ｮ・ｫ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｨ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
    }

    async function triggerPipeline() {
      return triggerWorkflow('full_pipeline', '鬯ｮ・ｫ繝ｻ・ｴ髯晢｣ｰ繝ｻ・｢繝ｻ縺､ﾂ鬯ｮ・ｯ陷茨ｽｷ繝ｻ・ｽ繝ｻ・ｻ鬮ｫ・ｴ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｴ郢晢ｽｻ郢ｧ謇假ｽｽ・ｽ繝ｻ・ｰ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬮ｴ螟ｧ・｣・ｼ鬩墓㈱繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｮ鬮ｮ荵昴・繝ｻ・ｽ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｡鬮ｯ貅ｷ譯√・・ｽ繝ｻ・｡驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ', '鬯ｮ・ｫ繝ｻ・ｴ髯晢｣ｰ繝ｻ・｢繝ｻ縺､ﾂ鬯ｮ・ｯ陷茨ｽｷ繝ｻ・ｽ繝ｻ・ｻ鬮ｫ・ｴ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｴ郢晢ｽｻ郢ｧ謇假ｽｽ・ｽ繝ｻ・ｰ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬮ｴ螟ｧ・｣・ｼ鬩墓㈱繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｮ鬮ｮ荵昴・繝ｻ・ｽ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｡鬮ｯ貅ｷ萓帙・・ｨ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ鬯ｮ・ｯ隶灘･・ｽｽ・ｻ郢ｧ謇假ｽｽ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｱ鬯ｮ・ｫ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｨ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
    }

    async function triggerNoteDraft() {
      const selectedIds = state.selectMode ? Array.from(state.selectedArticleIds) : [];
      const targetIds = selectedIds.length ? selectedIds : (state.selectedArticle ? [state.selectedArticle.id] : []);

      if (!targetIds.length) {
        setStatus('note鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貅ｯ縺悶・・ｪ髮懶ｽ｣繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬮ｫ・ｶ闕ｳ・ｻ繝ｻ・･郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｯ・ｮ繝ｻ・ｮ鬮ｮ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・｡鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｮ鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｵ髫ｴ謫ｾ・ｽ・ｶ繝ｻ縺､ﾂ郢晢ｽｻ繝ｻ・ｲ鬯ｮ・ｫ繝ｻ・ｴ髯晢ｽｷ繝ｻ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｪ鬯ｯ・ｯ繝ｻ・ｩ髯具ｽｹ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｧ郢晢ｽｻ繝ｻ・ｭ鬩搾ｽｵ繝ｻ・ｲ髯懶ｽ｣繝ｻ・､郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ, true);
        return;
      }

      if (state.dirty && state.selectedArticle && targetIds.includes(state.selectedArticle.id)) {
        const saved = await saveCurrentArticle();
        if (!saved) return;
      }

      setStatus('note鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貅ｯ縺悶・・ｪ髮懶ｽ｣繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬯ｯ・ｮ繝ｻ・ｦ郢晢ｽｻ繝ｻ・ｪ驛｢譎｢・ｽ・ｻ髯橸ｽｳ陞滂ｽｲ繝ｻ・ｽ繝ｻ・･髫ｰ・ｳ繝ｻ・ｾ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｷ鬯ｮ・ｯ繝ｻ・ｷ髯ｷ・･繝ｻ・ｲ郢晢ｽｻ繝ｻ・ｩ驛｢・ｧ隰・∞・ｽ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ');
      const response = await fetch('/api/note-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fileIds: targetIds, noTopImage: true }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.success === false) {
        throw new Error(payload.error || payload.message || 'note鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貅ｯ縺悶・・ｪ髮懶ｽ｣繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬯ｯ・ｮ繝ｻ・ｦ郢晢ｽｻ繝ｻ・ｪ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬯ｮ・ｫ闖ｫ・ｶ髫ｱ阮吶・繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｷ鬯ｮ・ｯ繝ｻ・ｷ髯晢｣ｰ髮懶ｽ｣繝ｻ・ｽ繝ｻ・ｼ髫ｰ螟ｲ・ｽ・ｫ驛｢譎｢・ｽ・ｻ鬯ｮ・ｯ隶灘･・ｽｽ・ｻ郢ｧ謇假ｽｽ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｱ鬯ｮ・ｫ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｨ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
      }
      setStatus(`${targetIds.length}鬯ｮ・｣雎郁ｲｻ・ｽ・ｼ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｶ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｮnote鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貅ｯ縺悶・・ｪ髮懶ｽ｣繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬯ｯ・ｮ繝ｻ・ｦ郢晢ｽｻ繝ｻ・ｪ驛｢譎｢・ｽ・ｻ髯橸ｽｳ陞｢・ｽ繝ｻ・･隲帙・・ｽ・ｲ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｡鬮ｯ貅ｷ譯√・・ｽ繝ｻ・｡驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｧ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ繝ｻ・ｷ郢晢ｽｻ繝ｻ・ｶ郢晢ｽｻ邵ｺ・､・つ驛｢譎｢・ｽ・ｻ髣包ｽｵ髢ｾ・ｭ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬮ｯ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・､驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｢驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｺ鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｱ鬯ｯ・ｮ繝ｻ・ｦ郢晢ｽｻ繝ｻ・ｪ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ髣鯉ｽｨ繝ｻ・ｽ繝ｻ・ｪ);
      if (state.selectMode) {
        state.selectMode = false;
        state.selectedArticleIds.clear();
        renderArticleList();
      }
      await pollNoteDraftUrls(targetIds);
    }

    async function fetchNoteDraftUrl(fileId) {
      if (!fileId) return null;
      try {
        const response = await fetch(`/api/note-draft?fileId=${encodeURIComponent(fileId)}`, { cache: 'no-store' });
        if (!response.ok) return null;
        const payload = await response.json().catch(() => ({}));
        const url = payload.url || null;
        if (url) {
          state.noteDraftUrls[fileId] = url;
          persistNoteDraftUrls();
        }
        return url;
      } catch {
        return null;
      }
    }

    async function pollNoteDraftUrl(fileId) {
      for (let attempt = 0; attempt < 24; attempt += 1) {
        const url = await fetchNoteDraftUrl(fileId);
        if (url) {
          setStatus(`note鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貅ｯ縺悶・・ｪ髮懶ｽ｣繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬮ｫ・ｰ繝ｻ・ｾ郢晢ｽｻ繝ｻ・ｻRL: ${url}`);
          window.open(url, '_blank', 'noopener,noreferrer');
          return url;
        }
        await new Promise((resolve) => setTimeout(resolve, 5000));
      }
      setStatus('note鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貅ｯ縺悶・・ｪ髮懶ｽ｣繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬯ｯ・ｮ繝ｻ・ｦ郢晢ｽｻ繝ｻ・ｪ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬯ｮ・ｯ隶厄ｽｸ繝ｻ・ｽ繝ｻ・ｳ鬮ｮ荵昴・繝ｻ・ｽ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｡鬮ｯ貅ｷ譯√・・ｽ繝ｻ・｡驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｧ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ繝ｻ・ｷ郢晢ｽｻ繝ｻ・ｶ郢晢ｽｻ邵ｺ・､・つ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻitHub Actions 鬯ｮ・ｯ隶厄ｽｸ繝ｻ・ｽ繝ｻ・ｳ鬮ｯ貅ｷ譯√・・ｽ繝ｻ・｡驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬮ｯ貅ｷ萓帙・・ｨ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ鬯ｮ・ｯ繝ｻ・ｷ繝ｻ縺､ﾂ鬮ｯ・ｷ繝ｻ・･郢晢ｽｻ繝ｻ・ｲ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｢驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｺ鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｱ鬯ｯ・ｮ繝ｻ・ｦ郢晢ｽｻ繝ｻ・ｪ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｦ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｳ髯晢ｽｯ繝ｻ・ｩ髯ｷ・ｻ繝ｻ・ｳ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬯ｮ・ｴ鬩帙・・ｽ・ｲ繝ｻ・ｻ郢晢ｽｻ繝ｻ・ｼ驛｢譎｢・ｽ・ｻ);
      return null;
    }

    async function pollNoteDraftUrls(fileIds) {
      const ids = Array.isArray(fileIds) ? fileIds : [fileIds];
      if (ids.length === 1) return pollNoteDraftUrl(ids[0]);

      const pending = new Set(ids);
      for (let attempt = 0; attempt < 24 && pending.size > 0; attempt += 1) {
        for (const fileId of [...pending]) {
          const url = await fetchNoteDraftUrl(fileId);
          if (url) pending.delete(fileId);
        }
        setStatus(pending.size ? `note鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貅ｯ縺悶・・ｪ髮懶ｽ｣繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬮ｫ・ｰ繝ｻ・ｾ郢晢ｽｻ繝ｻ・ｻRL鬯ｯ・ｩ陟・瑳繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｱ鬮ｯ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ 鬯ｮ・ｫ繝ｻ・ｹ郢晢ｽｻ繝ｻ・ｿ鬮｣蛹・ｽｽ・ｵ髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ驛｢譎｢・ｽ・ｻ{pending.size}鬯ｮ・｣雎郁ｲｻ・ｽ・ｼ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｶ` : 'note鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貅ｯ縺悶・・ｪ髮懶ｽ｣繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬮ｫ・ｰ繝ｻ・ｾ郢晢ｽｻ繝ｻ・ｻRL鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬯ｮ・ｮ陋ｹ・ｺ繝ｻ・ｧ繝ｻ・ｫ髯溷供・ｮ・｣髴趣ｽｧ髯ｷ閧ｴ・ｺ・ｷ繝ｻ・ｹ繝ｻ・ｲ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
        if (pending.size === 0) return true;
        await new Promise((resolve) => setTimeout(resolve, 5000));
      }
      setStatus('note鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貅ｯ縺悶・・ｪ髮懶ｽ｣繝ｻ・ｽ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬯ｯ・ｮ繝ｻ・ｦ郢晢ｽｻ繝ｻ・ｪ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬯ｮ・ｯ隶厄ｽｸ繝ｻ・ｽ繝ｻ・ｳ鬮ｮ荵昴・繝ｻ・ｽ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｡鬮ｯ貅ｷ譯√・・ｽ繝ｻ・｡驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｧ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ繝ｻ・ｷ郢晢ｽｻ繝ｻ・ｶ郢晢ｽｻ邵ｺ・､・つ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻitHub Actions 鬯ｮ・ｯ隶厄ｽｸ繝ｻ・ｽ繝ｻ・ｳ鬮ｯ貅ｷ譯√・・ｽ繝ｻ・｡驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬮ｯ貅ｷ萓帙・・ｨ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ鬯ｮ・ｯ繝ｻ・ｷ繝ｻ縺､ﾂ鬮ｯ・ｷ繝ｻ・･郢晢ｽｻ繝ｻ・ｲ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｢驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｺ鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｱ鬯ｯ・ｮ繝ｻ・ｦ郢晢ｽｻ繝ｻ・ｪ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｦ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｳ髯晢ｽｯ繝ｻ・ｩ髯ｷ・ｻ繝ｻ・ｳ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬯ｮ・ｴ鬩帙・・ｽ・ｲ繝ｻ・ｻ郢晢ｽｻ繝ｻ・ｼ驛｢譎｢・ｽ・ｻ);
      return false;
    }

    async function copyText(text, doneMessage) {
      await navigator.clipboard.writeText(text);
      setStatus(doneMessage);
    }
    function buildOgpCard(href, title, description, image, domain) {
      const card = document.createElement('a');
      card.className = 'ogp-card';
      card.href = href;
      card.target = '_blank';
      card.rel = 'noopener noreferrer';
      card.innerHTML = [
        '<div class="ogp-card-body">',
        domain ? `<div class="ogp-card-domain">${escapeHtml(domain)}</div>` : '',
        title ? `<div class="ogp-card-title">${escapeHtml(title)}</div>` : '',
        description ? `<div class="ogp-card-desc">${escapeHtml(description)}</div>` : '',
        '</div>',
        image ? `<img class="ogp-card-image" src="${escapeHtml(image)}" alt="" loading="lazy" onerror="this.style.display='none'" />` : '',
      ].join('');
      return card;
    }

    function insertOgpCard(anchor, card) {
      if (!anchor?.isConnected || anchor.classList.contains('ogp-card')) return;
      if (anchor.nextElementSibling?.classList?.contains('ogp-card')) return;
      anchor.insertAdjacentElement('afterend', card);
    }

    function normalizeUrlForOgp(href) {
      try {
        const url = new URL(href);
        if (!/^https?:$/.test(url.protocol)) return '';
        return url.toString();
      } catch {
        return '';
      }
    }

    function queueOgpCards(force = false) {
      const runId = ++state.ogpRunId;
      els.previewFooter.textContent = 'OGP鬯ｮ・ｯ雋・ｽｯ繝ｻ・ｼ隴∬・繝ｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｩ鬮ｮ邇厄ｽｴ蜈ｷ・ｽ・ｼ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ';
      window.requestAnimationFrame(() => applyOgpCards(runId, force));
    }

    async function applyOgpCards(runId, force = false) {
      const links = [...els.preview.querySelectorAll('a[href^="http"]:not(.ogp-card)')]
        .map((anchor) => ({ anchor, href: normalizeUrlForOgp(anchor.href) }))
        .filter((entry) => entry.href);

      if (!links.length) {
        els.previewFooter.textContent = 'OGP鬯ｮ・ｯ隴擾ｽｴ郢晢ｽｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｾ鬯ｯ・ｮ繝ｻ・ｮ鬮ｮ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・｡鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ;
        return;
      }

      if (force) {
        links.forEach(({ anchor }) => anchor.removeAttribute('data-ogp-processed'));
      }

      let processed = 0;
      for (const { anchor, href } of links) {
        if (runId !== state.ogpRunId) return;
        if (!anchor.isConnected || anchor.dataset.ogpProcessed) continue;
        anchor.dataset.ogpProcessed = '1';

        try {
          let ogp = state.ogpCache[href];
          if (!ogp || force) {
            const response = await fetch(`/api/ogp?url=${encodeURIComponent(href)}`, { cache: 'no-store' });
            if (!response.ok) throw new Error(`OGP ${response.status}`);
            ogp = await response.json();
            state.ogpCache[href] = ogp;
          }
          const domain = ogp.domain || new URL(href).hostname;
          insertOgpCard(anchor, buildOgpCard(href, ogp.title || href, ogp.description || '', ogp.image || '', domain));
          processed += 1;
          els.previewFooter.textContent = `OGP ${processed}/${links.length}`;
        } catch {
          anchor.removeAttribute('data-ogp-processed');
          const domain = new URL(href).hostname;
          insertOgpCard(anchor, buildOgpCard(href, domain, '', '', domain));
        }
      }

      els.previewFooter.textContent = processed ? `OGP鬯ｮ・ｯ隶厄ｽｸ繝ｻ・ｽ繝ｻ・ｻ鬮ｫ・ｴ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｮ鬮ｯ譎｢・ｽ・ｷ驛｢譎｢・ｽ・ｻ${processed}鬯ｮ・｣雎郁ｲｻ・ｽ・ｼ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｶ` : 'OGP鬯ｮ・ｯ隴擾ｽｴ郢晢ｽｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｾ鬯ｯ・ｮ繝ｻ・ｮ鬮ｮ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・｡鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ;
    }

    function refreshOgp() {
      els.preview.querySelectorAll('.ogp-card').forEach((card) => card.remove());
      els.preview.querySelectorAll('a[data-ogp-processed]').forEach((anchor) => anchor.removeAttribute('data-ogp-processed'));
      renderPreview(true);
      setStatus('OGP鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬮ｯ・ｷ繝ｻ・ｻ髣費｣ｰ繝ｻ・･郢晢ｽｻ繝ｻ・ｳ郢晢ｽｻ繝ｻ・ｩ鬯ｮ・ｫ繝ｻ・ｴ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ);
    }

    function memoKeys() {
      return Object.keys(state.affiliateMemos)
        .sort((a, b) => Number(a.replace('memo', '')) - Number(b.replace('memo', '')));
    }

    function renderMemoTabs() {
      const keys = memoKeys();
      if (!keys.includes(state.activeAffiliateKey)) state.activeAffiliateKey = keys[0] || 'memo1';
      els.memoTabs.innerHTML = keys.map((key) => `
        <button type="button" class="memo-tab ${key === state.activeAffiliateKey ? 'active' : ''}" data-memo-key="${escapeHtml(key)}">
          ${escapeHtml(key.toUpperCase())}
        </button>
      `).join('');
      els.memoTabs.querySelectorAll('[data-memo-key]').forEach((button) => {
        button.addEventListener('click', () => {
          syncAffiliateEditorToState();
          state.activeAffiliateKey = button.dataset.memoKey;
          els.affiliateEditor.value = state.affiliateMemos[state.activeAffiliateKey] || '';
          renderMemoTabs();
        });
      });
    }

    function syncAffiliateEditorToState() {
      if (!state.activeAffiliateKey) return;
      state.affiliateMemos[state.activeAffiliateKey] = els.affiliateEditor.value;
    }

    async function fetchAffiliateMemos() {
      setAffiliateStatus('鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｯ・ｮ繝ｻ・ｴ鬮ｮ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｼ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｮ・｣陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ');
      const response = await fetch(apiUrl('affiliate'), { cache: 'no-store' });
      if (!response.ok) throw new Error('tech affiliate鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｮ鬯ｮ・ｯ繝ｻ・ｷ郢晢ｽｻ繝ｻ・ｿ鬯ｯ・ｮ繝ｻ・｢繝ｻ縺､ﾂ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ鬯・汚・ｽ・･繝ｻ・｢髫ｴ・ｽ隴∬・繝ｻ郢晢ｽｻ繝ｻ・ｱ鬯ｮ・ｫ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｨ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
      const payload = await response.json();
      state.affiliateMemos = payload.memos || { memo1: '' };
      state.activeAffiliateKey = memoKeys()[0] || 'memo1';
      state.affiliateDirty = false;
      renderMemoTabs();
      els.affiliateEditor.value = state.affiliateMemos[state.activeAffiliateKey] || '';
      setAffiliateStatus('鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｯ・ｮ繝ｻ・ｴ鬮ｮ諛ｶ・ｽ・｣郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｼ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｿ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
    }

    async function saveAffiliateMemos() {
      syncAffiliateEditorToState();
      setAffiliateStatus('鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陷ｿ髢・ｾ蜉ｱ繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｭ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ');
      const response = await fetch(apiUrl('affiliate'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ memos: state.affiliateMemos }),
      });
      if (!response.ok) throw new Error('tech affiliate鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｮ鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陷ｿ髢・ｾ蜉ｱ繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｭ鬮ｯ蛹ｺ・ｻ繧托ｽｽ・ｽ繝ｻ・･鬩包ｽｶ鬯・汚・ｽ・･繝ｻ・｢髫ｴ・ｽ隴∬・繝ｻ郢晢ｽｻ繝ｻ・ｱ鬯ｮ・ｫ繝ｻ・ｰ郢晢ｽｻ繝ｻ・ｨ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
      state.affiliateDirty = false;
      setAffiliateStatus('鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陷ｿ髢・ｾ蜉ｱ繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｭ鬮ｯ蛹ｺ・ｻ繧托ｽｽ・ｽ繝ｻ・･驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
    }

    function openAffiliateModal() {
      els.affiliateModalBackdrop.classList.add('open');
      els.affiliateModalBackdrop.setAttribute('aria-hidden', 'false');
      if (!memoKeys().length || (memoKeys().length === 1 && state.affiliateMemos.memo1 === '')) {
        fetchAffiliateMemos().catch((error) => setAffiliateStatus(error.message, true));
      } else {
        renderMemoTabs();
        els.affiliateEditor.value = state.affiliateMemos[state.activeAffiliateKey] || '';
      }
      els.affiliateEditor.focus();
    }

    function closeAffiliateModal() {
      syncAffiliateEditorToState();
      els.affiliateModalBackdrop.classList.remove('open');
      els.affiliateModalBackdrop.setAttribute('aria-hidden', 'true');
    }

    function addMemo() {
      syncAffiliateEditorToState();
      const nums = memoKeys().map((key) => Number(key.replace('memo', ''))).filter(Boolean);
      const next = `memo${Math.max(0, ...nums) + 1}`;
      state.affiliateMemos[next] = '';
      state.activeAffiliateKey = next;
      state.affiliateDirty = true;
      renderMemoTabs();
      els.affiliateEditor.value = '';
      els.affiliateEditor.focus();
    }

    function activeAffiliateText() {
      syncAffiliateEditorToState();
      return String(state.affiliateMemos[state.activeAffiliateKey] || '').trim();
    }

    function insertAffiliateAtEnd() {
      const text = activeAffiliateText();
      if (!text) {
        setStatus('鬯ｮ・ｫ繝ｻ・ｰ髯ｷ・ｴ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｿ鬯ｮ・ｯ繝ｻ・ｷ鬮｣魃会ｽｽ・ｨ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・･鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ繝ｻ・ｷ郢晢ｽｻ繝ｻ・ｶ驛｢譎｢・ｽ・ｻ髴托ｽ｢隴会ｽｦ繝ｻ・ｽ繝ｻ・ｹ郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・｢鬯ｩ蟷｢・ｽ・｢髫ｴ蠑ｱ繝ｻ繝ｻ・ｽ繝ｻ・ｼ髫ｴ竏ｫ・ｵ・ｶ髫伜､懶ｽｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｪ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｨ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・､鬯ｩ蟷｢・ｽ・｢髫ｴ荳ｻ繝ｻ隶捺ｻ・碑ｭ趣ｽ｢繝ｻ・ｽ繝ｻ・ｦ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｭ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｹ鬯ｩ蟷｢・ｽ・｢髫ｴ荳ｻ繝ｻ隶捺ｻ・・繝ｻ・ｶ郢晢ｽｻ繝ｻ・ｲ鬯ｯ・ｩ陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｨ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｺ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｧ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ, true);
        return;
      }
      if (!state.selectedArticle) {
        setStatus('鬯ｯ・ｮ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｪ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮｣蛹・ｽｽ・ｵ髫ｴ謫ｾ・ｽ・ｶ繝ｻ縺､ﾂ郢晢ｽｻ繝ｻ・ｲ鬯ｮ・ｫ繝ｻ・ｴ髯晢ｽｷ繝ｻ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｪ鬯ｯ・ｯ繝ｻ・ｩ髯具ｽｹ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｸ鬯ｮ・ｫ繝ｻ・ｰ髯橸ｽ｢繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｧ郢晢ｽｻ繝ｻ・ｭ鬩搾ｽｵ繝ｻ・ｲ髯懶ｽ｣繝ｻ・､郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ, true);
        return;
      }
      const current = els.editor.value.trimEnd();
      els.editor.value = current.includes(text) ? current : `${current}\n\n---\n\n${text}\n`;
      state.dirty = true;
      renderPreview(false);
      setStatus(`${state.activeAffiliateKey.toUpperCase()}鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬮ｯ讖ｸ・ｽ・ｳ髯樊ｻゑｽｽ・ｲ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｨ鬮ｯ蛹ｺ・ｺ蛟･繝ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｺ鬮ｯ蜈ｷ・ｽ・ｹ郢晢ｽｻ繝ｻ・ｺ鬮ｯ貊ゑｽｽ・｢郢晢ｽｻ繝ｻ・ｰ鬯ｮ・ｯ隴擾ｽｴ郢晢ｽｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｾ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｸ鬯ｮ・ｫ繝ｻ・ｰ髯ｷ・ｴ郢晢ｽｻ繝ｻ・ｽ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｿ鬯ｮ・ｯ繝ｻ・ｷ鬮｣魃会ｽｽ・ｨ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・･鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
    }
    function applyResizer(handle, target, cssVar, minPx, maxPx) {
      handle.addEventListener('pointerdown', (event) => {
        handle.classList.add('dragging');
        const startX = event.clientX;
        const startWidth = target.getBoundingClientRect().width;

        function onMove(moveEvent) {
          const nextWidth = Math.min(Math.max(startWidth + (moveEvent.clientX - startX), minPx), maxPx);
          document.documentElement.style.setProperty(cssVar, `${nextWidth}px`);
        }

        function onUp() {
          handle.classList.remove('dragging');
          window.removeEventListener('pointermove', onMove);
          window.removeEventListener('pointerup', onUp);
        }

        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
      });
    }

    function applyEditorResizer(handle) {
      handle.addEventListener('pointerdown', (event) => {
        handle.classList.add('dragging');
        const container = handle.parentElement;
        const startX = event.clientX;
        const startWidth = els.editorPanel.getBoundingClientRect().width;
        const totalWidth = container.getBoundingClientRect().width || window.innerWidth;

        function onMove(moveEvent) {
          const nextWidth = Math.min(Math.max(startWidth + (moveEvent.clientX - startX), 420), Math.max(460, totalWidth - 360));
          const percent = (nextWidth / totalWidth) * 100;
          document.documentElement.style.setProperty('--editor-width', `${percent}%`);
        }

        function onUp() {
          handle.classList.remove('dragging');
          window.removeEventListener('pointermove', onMove);
          window.removeEventListener('pointerup', onUp);
        }

        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
      });
    }

    function bindEvents() {
      els.saveButton.addEventListener('click', () => saveCurrentArticle().catch((error) => setStatus(error.message, true)));
      els.noteDraftButton.addEventListener('click', () => triggerNoteDraft().catch((error) => setStatus(error.message, true)));
      els.queueButton.addEventListener('click', () => triggerQueue().catch((error) => setStatus(error.message, true)));
      els.pipelineButton.addEventListener('click', () => triggerPipeline().catch((error) => setStatus(error.message, true)));
      els.refreshButton.addEventListener('click', () => fetchArticles(true).catch((error) => setStatus(error.message, true)));
      els.refreshOgpButton.addEventListener('click', refreshOgp);
      els.copyEditorButton.addEventListener('click', () => copyText(els.editor.value, '鬯ｮ・ｫ繝ｻ・ｴ髯晢ｽｷ繝ｻ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｬ鬯ｮ・ｫ繝ｻ・ｴ驕ｶ荳橸ｽ｣・ｹ郢晢ｽｻ驛｢譎｢・ｽ・ｻ髯懶ｽ｣繝ｻ・､郢晢ｽｻ繝ｻ・ｹ郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｳ鬯ｩ蟷｢・ｽ・｢髫ｴ蠑ｱ繝ｻ繝ｻ・ｱ陜｣・､繝ｻ・ｹ隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ).catch((error) => setStatus(error.message, true)));
      els.copyPreviewButton.addEventListener('click', () => copyText(state.editorContent, '鬯ｩ蟷｢・ｽ・｢髫ｴ蠑ｱ繝ｻ繝ｻ・ｽ繝ｻ・ｧ郢晢ｽｻ繝ｻ・ｭ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｯ鬯ｩ蟷｢・ｽ・｢髫ｰ・ｨ鬲托ｽｴ・つ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｦ鬯ｩ蟷｢・ｽ・｢髫ｴ雜｣・ｽ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｳ鬯ｩ蟷｢・ｽ・｢郢晢ｽｻ繝ｻ・ｧ鬮ｯ蜿･・ｹ・｢繝ｻ・ｽ繝ｻ・ｵ鬩搾ｽｵ繝ｻ・ｺ髫ｲ・ｷ陋ｹ繝ｻ・ｽ・ｽ繝ｻ・ｹ髫ｴ蠑ｱ繝ｻ繝ｻ・ｱ陜｣・､繝ｻ・ｹ隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ).catch((error) => setStatus(error.message, true)));
      els.insertAffiliateButton.addEventListener('click', insertAffiliateAtEnd);
      els.sortToggle.addEventListener('click', () => {
        state.sortOrder = state.sortOrder === 'asc' ? 'desc' : 'asc';
        localStorage.setItem(SORT_ORDER_KEY, state.sortOrder);
        updateSortButton();
        renderArticleList();
        setStatus(state.sortOrder === 'asc' ? '鬯ｮ・ｫ繝ｻ・ｴ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｰ鬯ｯ・ｨ繝ｻ・ｾ郢晢ｽｻ繝ｻ・ｹ郢晢ｽｻ邵ｺ・､・つ鬯ｯ・ｯ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ髯橸ｽｳ陞滂ｽｲ繝ｻ・ｽ繝ｻ・ｭ髣包ｽｳ驗呻ｽｫ郢晢ｽｻ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬩包ｽｶ闔ｨ竏ｬ・ｱ・ｪ郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ : '鬯ｮ・ｫ繝ｻ・ｴ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｰ鬯ｯ・ｨ繝ｻ・ｾ郢晢ｽｻ繝ｻ・ｹ郢晢ｽｻ邵ｺ・､・つ鬯ｯ・ｯ繝ｻ・ｯ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ驛｢譎｢・ｽ・ｻ髯晢ｽｶ隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｫ郢晢ｽｻ繝ｻ・ｯ鬮ｯ諞ｺ螻ｮ繝ｻ・ｽ繝ｻ・ｼ驛｢譎｢・ｽ・ｻ郢晢ｽｻ繝ｻ・ｰ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ鬩包ｽｶ闔ｨ竏ｬ・ｱ・ｪ郢晢ｽｻ繝ｻ・ｸ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬩包ｽｶ隰ｫ・ｾ繝ｻ・ｽ繝ｻ・ｪ鬯ｩ謳ｾ・ｽ・ｵ郢晢ｽｻ繝ｻ・ｺ鬮ｯ・ｷ闔ｨ螟ｲ・ｽ・ｽ繝ｻ・ｱ鬮ｫ・ｨ繝ｻ・ｳ驛｢譎｢・ｽ・ｻ);
      });
      els.sourceToggle.addEventListener('click', () => setSourceVisible(!state.sourceVisible));

      els.editor.addEventListener('input', () => {
        state.dirty = true;
        renderPreview(false);
      });

      window.addEventListener('keydown', (event) => {
        const isSaveShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's';
        if (isSaveShortcut) {
          event.preventDefault();
          saveCurrentArticle().catch((error) => setStatus(error.message, true));
          return;
        }
        if (event.key === 'Escape') {
          if (!els.articleContextMenu.hidden) closeArticleContextMenu();
          else if (state.selectMode) clearSelectMode();
        }
      });

      window.addEventListener('click', (event) => {
        if (!els.articleContextMenu.hidden && !els.articleContextMenu.contains(event.target)) {
          closeArticleContextMenu();
        }
      });
      window.addEventListener('contextmenu', (event) => {
        if (!els.articleContextMenu.hidden && !els.articleContextMenu.contains(event.target)) {
          closeArticleContextMenu();
        }
      });

      els.articleContextMenu.addEventListener('click', (event) => event.stopPropagation());
      els.contextSelectButton.addEventListener('click', () => {
        const article = contextArticle();
        if (article) enterSelectMode(article);
      });
      els.contextDuplicateButton.addEventListener('click', () => {
        duplicateArticle(contextArticle()).catch((error) => setStatus(error.message, true));
      });
      els.contextDeleteButton.addEventListener('click', () => {
        deleteArticle(contextArticle()).catch((error) => setStatus(error.message, true));
      });
      els.contextOpenOneDriveButton.addEventListener('click', () => openOneDriveArticle(contextArticle()));
      els.contextOpenExplorerButton.addEventListener('click', () => openExplorerArticle(contextArticle()));

      els.affiliateLauncher.addEventListener('click', openAffiliateModal);
      els.closeAffiliateButton.addEventListener('click', closeAffiliateModal);
      els.affiliateModalBackdrop.addEventListener('click', (event) => {
        if (event.target === els.affiliateModalBackdrop) closeAffiliateModal();
      });
      els.reloadAffiliateButton.addEventListener('click', () => fetchAffiliateMemos().catch((error) => setAffiliateStatus(error.message, true)));
      els.saveAffiliateButton.addEventListener('click', () => saveAffiliateMemos().catch((error) => setAffiliateStatus(error.message, true)));
      els.addMemoButton.addEventListener('click', addMemo);
      els.insertAffiliateFromModalButton.addEventListener('click', insertAffiliateAtEnd);
      els.affiliateEditor.addEventListener('input', () => {
        state.affiliateDirty = true;
        syncAffiliateEditorToState();
        setAffiliateStatus('鬯ｮ・ｫ繝ｻ・ｴ髯晢ｽｷ繝ｻ・｢郢晢ｽｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｪ鬯ｮ・｣陷ｴ繝ｻ・ｽ・ｽ繝ｻ・ｫ鬮ｫ・ｴ陷ｿ髢・ｾ蜉ｱ繝ｻ繝ｻ・ｽ郢晢ｽｻ繝ｻ・ｭ鬩幢ｽ｢隴趣ｽ｢繝ｻ・ｽ繝ｻ・ｻ);
      });

      applyResizer(els.sidebarHandle, els.sidebar, '--sidebar-width', 240, 520);
      applyResizer(els.sourceHandle, els.sourcePanel, '--source-width', 260, 560);
      applyEditorResizer(els.editorHandle);
    }

    async function init() {
      initIcons();
      bindEvents();
      setSourceVisible(state.sourceVisible);
      updateSortButton();
      updateEditorMeta();
      await Promise.all([
        fetchArticles(),
        fetchAffiliateMemos().catch((error) => setAffiliateStatus(error.message, true)),
      ]);
    }

    init().catch((error) => setStatus(error.message, true));
  
