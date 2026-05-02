// Google Sheets APIインスタンス
let sheetsAPI = null;
const DEFAULT_SPREADSHEET_URL = 'https://docs.google.com/spreadsheets/d/1ioLnPe9z6vO0tuN3I_qcDi6buS8GCaYowbjq8LTOT94/edit?gid=698344880#gid=698344880';
const DEFAULT_SHEET_NAME = 'ブランド製品名仕訳';

// sheets-api.jsを動的に読み込む
const loadSheetsAPI = () => {
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'sheets-api.js';
        script.onload = () => {
            sheetsAPI = new window.GoogleSheetsAPI();
            resolve();
        };
        script.onerror = reject;
        document.head.appendChild(script);
    });
};

// 初期化時にSheets APIを読み込み
loadSheetsAPI().then(() => {
    console.log('Google Sheets API準備完了');
}).catch(err => {
    console.error('Google Sheets API読み込みエラー:', err);
});

document.addEventListener('DOMContentLoaded', () => {
    // Google Sheets関連の要素
    const sheetsToggleEl = document.getElementById('sheetsToggle');
    const sheetsClientIdEl = document.getElementById('sheetsClientId');
    const sheetsClientSecretEl = document.getElementById('sheetsClientSecret');
    const spreadsheetUrlEl = document.getElementById('spreadsheetUrl');
    const sheetNameEl = document.getElementById('sheetName');
    const authenticateButton = document.getElementById('authenticateButton');
    const authStatusEl = document.getElementById('authStatus');

    // Google Sheets設定の読み込み
    chrome.storage.sync.get([
        'sheetsToggle',
        'sheetsClientId',
        'sheetsClientSecret',
        'spreadsheetUrl',
        'sheetName',
        'sheetsAccessToken',
        'sheetsTokenExpiry'
    ], (result) => {
        if (sheetsToggleEl) sheetsToggleEl.checked = result.sheetsToggle || false;
        if (sheetsClientIdEl) sheetsClientIdEl.value = result.sheetsClientId || '';
        if (sheetsClientSecretEl) sheetsClientSecretEl.value = result.sheetsClientSecret || '';
        if (spreadsheetUrlEl) spreadsheetUrlEl.value = result.spreadsheetUrl || DEFAULT_SPREADSHEET_URL;
        if (sheetNameEl) sheetNameEl.value = result.sheetName || DEFAULT_SHEET_NAME;

        updateAuthStatus(result.sheetsAccessToken, result.sheetsTokenExpiry);
        updateExecuteButtonLabel();
    });

    // 認証状態の表示を更新
    function updateAuthStatus(token, expiry) {
        if (!authStatusEl) return;

        if (token && expiry && Date.now() < expiry) {
            const remainingHours = Math.floor((expiry - Date.now()) / (1000 * 60 * 60));
            authStatusEl.textContent = `✅ 認証済み(残り${remainingHours}時間)`;
            authStatusEl.style.color = '#28a745';
        } else {
            authStatusEl.textContent = '❌ 未認証';
            authStatusEl.style.color = '#dc3545';
        }
    }

    function updateExecuteButtonLabel() {
        const button = document.getElementById('executeJsButton');
        if (!button) return;
        button.textContent = sheetsToggleEl && sheetsToggleEl.checked
            ? '☁️ 実行(Sheets書き込み)'
            : '▶️ 実行';
    }

    // Google Sheets設定の保存
    const saveSheetsConfig = () => {
        return new Promise((resolve) => {
            chrome.storage.sync.set({
                sheetsToggle: sheetsToggleEl ? sheetsToggleEl.checked : false,
                sheetsClientId: sheetsClientIdEl ? sheetsClientIdEl.value.trim() : '',
                sheetsClientSecret: sheetsClientSecretEl ? sheetsClientSecretEl.value.trim() : '',
                spreadsheetUrl: spreadsheetUrlEl ? (spreadsheetUrlEl.value.trim() || DEFAULT_SPREADSHEET_URL) : DEFAULT_SPREADSHEET_URL,
                sheetName: sheetNameEl ? (sheetNameEl.value.trim() || DEFAULT_SHEET_NAME) : DEFAULT_SHEET_NAME
            }, () => {
                updateExecuteButtonLabel();
                resolve();
            });
        });
    };

    // 各入力フィールドの変更を監視
    if (sheetsToggleEl) sheetsToggleEl.addEventListener('change', saveSheetsConfig);
    if (sheetsClientIdEl) sheetsClientIdEl.addEventListener('change', saveSheetsConfig);
    if (sheetsClientSecretEl) sheetsClientSecretEl.addEventListener('change', saveSheetsConfig);
    if (spreadsheetUrlEl) spreadsheetUrlEl.addEventListener('change', saveSheetsConfig);
    if (sheetNameEl) sheetNameEl.addEventListener('change', saveSheetsConfig);
    if (sheetsClientIdEl) sheetsClientIdEl.addEventListener('input', saveSheetsConfig);
    if (sheetsClientSecretEl) sheetsClientSecretEl.addEventListener('input', saveSheetsConfig);
    if (spreadsheetUrlEl) spreadsheetUrlEl.addEventListener('input', saveSheetsConfig);
    if (sheetNameEl) sheetNameEl.addEventListener('input', saveSheetsConfig);

    // Google認証ボタン
    if (authenticateButton) {
        authenticateButton.addEventListener('click', async () => {
            try {
                authenticateButton.disabled = true;
                authenticateButton.textContent = '🔄 認証中...';

                if (!sheetsAPI) {
                    await loadSheetsAPI();
                }

                await sheetsAPI.authenticate();

                const config = await sheetsAPI.getConfig();
                updateAuthStatus(config.sheetsAccessToken, config.sheetsTokenExpiry);

                alert('✅ Google認証が完了しました!');
                authenticateButton.textContent = '🔐 Google認証';
            } catch (error) {
                console.error('認証エラー:', error);
                alert(`❌ 認証に失敗しました:\n${error.message}`);
                authenticateButton.textContent = '🔐 Google認証';
            } finally {
                authenticateButton.disabled = false;
            }
        });
    }

    // UIの他の要素
    const affiliateTagEl = document.getElementById('affiliateTag');
    const itemCountEl = document.getElementById('itemCount');
    const minRatingEl = document.getElementById('minRating');
    const minReviewsEl = document.getElementById('minReviews');
    const sortOrderEl = document.getElementById('sortOrder');
    const executeJsButton = document.getElementById('executeJsButton');
    const statusMessageEl = document.getElementById('statusMessage');
    const statusCategoryEl = document.getElementById('statusCategory');
    const statusCountEl = document.getElementById('statusCount');
    const statusTargetEl = document.getElementById('statusTarget');
    const statusSortEl = document.getElementById('statusSort');
    const statusModeEl = document.getElementById('statusMode');
    const copyAllButton = document.getElementById('copyAllButton');
    const stopButton = document.getElementById('stopButton');
    const settingsButton = document.getElementById('settingsButton');
    const settingsPanel = document.getElementById('settingsPanel');
    const mainPanel = document.getElementById('mainPanel');
    const modeSelectEl = document.getElementById('modeSelect');
    const pageDetailSelectEl = document.getElementById('pageDetailSelect');
    const createArticleButton = document.getElementById('createArticleButton');

    // プロンプト管理関連の要素
    const promptButton = document.getElementById('promptButton');
    const promptPanel = document.getElementById('promptPanel');
    const promptTitleSelect = document.getElementById('promptTitleSelect');
    const promptTitleInput = document.getElementById('promptTitleInput');
    const promptContent = document.getElementById('promptContent');
    const promptSaveButton = document.getElementById('promptSaveButton');
    const promptCopyButton = document.getElementById('promptCopyButton');
    const promptDeleteButton = document.getElementById('promptDeleteButton');

    // アフィリエイトリンク作成ボタンの要素
    const affiliateLinkButton = document.getElementById('affiliateLinkButton');
    const BLOG_API_BASE = 'https://blog-vercel-dun.vercel.app';
    const ACTION_PAYLOAD_MAX_CHARS = 52000;

    function setArticleStatus(message) {
        if (statusMessageEl) {
            statusMessageEl.textContent = message;
        }
    }

    function compactText(value, maxLength = 500) {
        const text = String(value || '').replace(/\s+/g, ' ').trim();
        if (text.length <= maxLength) return text;
        return `${text.slice(0, maxLength - 1)}…`;
    }

    function compactList(values, maxItems = 40, maxLength = 400) {
        if (!Array.isArray(values)) return [];
        const out = [];
        const seen = new Set();
        for (const value of values.flat(Infinity)) {
            const text = compactText(value, maxLength);
            if (!text || seen.has(text)) continue;
            seen.add(text);
            out.push(text);
            if (out.length >= maxItems) break;
        }
        return out;
    }

    function compactMap(value, maxEntries = 40, maxLength = 400) {
        if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
        const out = {};
        for (const [key, itemValue] of Object.entries(value).slice(0, maxEntries)) {
            const cleanKey = compactText(key, 120);
            const cleanValue = compactText(itemValue, maxLength);
            if (cleanKey && cleanValue) out[cleanKey] = cleanValue;
        }
        return out;
    }

    function buildActionsPayload(payload) {
        const compacted = {
            source: payload.source || 'chrome-extension',
            capturedAt: payload.capturedAt || new Date().toISOString(),
            url: payload.url || '',
            canonicalUrl: payload.canonicalUrl || '',
            asin: payload.asin || '',
            title: compactText(payload.title || payload.pageTitle || '', 500),
            pageTitle: compactText(payload.pageTitle || '', 500),
            brand: compactText(payload.brand || '', 300),
            price: compactText(payload.price || '', 120),
            listPrice: compactText(payload.listPrice || '', 120),
            rating: compactText(payload.rating || '', 120),
            reviewCount: compactText(payload.reviewCount || '', 120),
            availability: compactText(payload.availability || '', 300),
            seller: compactText(payload.seller || '', 300),
            categories: compactList(payload.categories, 20, 220),
            featureBullets: compactList(payload.featureBullets, 50, 360),
            description: compactText(payload.description || '', 3000),
            aplusLines: compactList(payload.aplusLines, 90, 360),
            carouselTexts: compactList(payload.carouselTexts, 45, 280),
            imageAlts: compactList(payload.imageAlts, 45, 220),
            ocrTexts: compactList(payload.ocrTexts, 35, 360),
            ocrStatus: compactText(payload.ocrStatus || '', 120),
            productOverview: compactMap(payload.productOverview, 50, 360),
            detailBullets: compactMap(payload.detailBullets, 50, 360),
            importantInformation: compactText(payload.importantInformation || '', 1600),
            highResolutionImages: compactList(payload.highResolutionImages, 20, 900),
            extractionError: compactText(payload.extractionError || '', 500),
        };

        const trimSteps = [
            () => { compacted.imageAlts = compacted.imageAlts.slice(0, 20); },
            () => { compacted.carouselTexts = compacted.carouselTexts.slice(0, 25); },
            () => { compacted.ocrTexts = compacted.ocrTexts.slice(0, 20); },
            () => { compacted.aplusLines = compacted.aplusLines.slice(0, 60); },
            () => { compacted.description = compactText(compacted.description, 1600); },
            () => { compacted.importantInformation = compactText(compacted.importantInformation, 800); },
            () => { compacted.featureBullets = compacted.featureBullets.slice(0, 30); },
            () => { compacted.highResolutionImages = compacted.highResolutionImages.slice(0, 10); },
            () => { compacted.productOverview = compactMap(compacted.productOverview, 25, 240); },
            () => { compacted.detailBullets = compactMap(compacted.detailBullets, 25, 240); },
            () => { compacted.carouselTexts = []; },
            () => { compacted.imageAlts = []; },
            () => { compacted.ocrTexts = []; },
        ];

        for (const trim of trimSteps) {
            if (JSON.stringify([compacted]).length <= ACTION_PAYLOAD_MAX_CHARS) break;
            trim();
        }

        return compacted;
    }

    function formatActionRunStatus(data) {
        if (data?.run?.html_url) {
            const label = data.run.run_number ? `Run #${data.run.run_number}` : `Run ${data.run.id}`;
            return `✅ GitHub Actions起動済み: ${label} (${data.run.status || 'queued'})`;
        }
        if (data?.actions_url) {
            return `✅ GitHub Actions dispatch受付済み: Run作成待ち (${data.request_id || 'request'})`;
        }
        return '✅ GitHub Actions起動リクエストを送信しました';
    }

    // クリップボードへのコピー(堅牢版)
    async function copyToClipboardRobust(text) {
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(text);
                return true;
            }
        } catch (e) {
            // フォールバックへ
        }
        try {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.top = '-1000px';
            textarea.style.left = '-1000px';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            const ok = document.execCommand('copy');
            document.body.removeChild(textarea);
            if (ok) return true;
        } catch (_) { }
        return false;
    }

    const SHEET_HEADERS = [
        'カテゴリ',
        'タイトル',
        'Amazon URL',
        'ASIN',
        'ブランド',
        '製品名',
        '価格',
        '参考価格',
        'レビュー平均',
        'レビュー数',
        '在庫状況',
        '販売元',
        '発送元',
        '状況',
        '記事方針',
        '想定読者',
        '検索キーワード',
        '商品特徴',
        '商品説明',
        'A+コンテンツ',
        'ブランドストーリー',
        '商品概要',
        '技術仕様',
        '詳細情報',
        '重要情報',
        '画像altテキスト',
        'カルーセル内テキスト',
        '画像内OCRテキスト',
        'OCR状態',
        '高解像度画像URL',
        '取得日時',
        '取得元URL',
        '正規URL',
        '抽出エラー',
        '取得メモ'
    ];

    const chromeSyncGet = (keys) => new Promise(resolve => chrome.storage.sync.get(keys, resolve));
    const chromeLocalGet = (keys) => new Promise(resolve => chrome.storage.local.get(keys, resolve));

    async function isSheetsEnabled() {
        const result = await chromeSyncGet(['sheetsToggle']);
        return Boolean(result.sheetsToggle);
    }

    function cleanSheetValue(value) {
        return value == null ? '' : String(value);
    }

    function normalizePrice(value) {
        return cleanSheetValue(value).replace(/[^0-9]/g, '');
    }

    function limitSheetCell(value, limit = 49000) {
        const text = cleanSheetValue(value);
        return text.length > limit ? `${text.slice(0, limit)}\n[文字数上限のため省略]` : text;
    }

    function stringifySheetValue(value) {
        if (Array.isArray(value)) {
            return value
                .flat(Infinity)
                .map(item => stringifySheetValue(item))
                .filter(Boolean)
                .join('\n');
        }
        if (value && typeof value === 'object') {
            return Object.entries(value)
                .filter(([, entryValue]) => cleanSheetValue(entryValue).trim() !== '')
                .map(([key, entryValue]) => `${key}: ${stringifySheetValue(entryValue)}`)
                .join('\n');
        }
        return cleanSheetValue(value);
    }

    function removeMarkupAndCode(value) {
        let text = cleanSheetValue(value);
        for (let i = 0; i < 8; i += 1) {
            const next = text
                .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
                .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
                .replace(/<noscript\b[^>]*>[\s\S]*?<\/noscript>/gi, ' ')
                .replace(/<template\b[^>]*>[\s\S]*?<\/template>/gi, ' ')
                .replace(/<img\b[^>]*>/gi, ' ')
                .replace(/<[^>]+>/g, ' ')
                .replace(/(?:^|\s)(?:\.|#)[\w.#:[\]\-="'\s>*+~,()]+?\s*\{[^{}]*\}/g, ' ')
                .replace(/@media[^{]+\{[^{}]*\}/g, ' ')
                .replace(/\bfunction\s+[A-Za-z0-9_$]*\s*\([^)]*\)\s*\{[^{}]*\}/g, ' ')
                .replace(/\(\s*function\s*\([^)]*\)\s*\{[^{}]*\}\s*\([^)]*\)\s*\)/g, ' ');
            if (next === text) break;
            text = next;
        }
        return text
            .replace(/&nbsp;/gi, ' ')
            .replace(/&amp;/gi, '&')
            .replace(/&lt;/gi, '<')
            .replace(/&gt;/gi, '>')
            .replace(/&quot;/gi, '"')
            .replace(/&#39;/g, "'")
            .replace(/[ \t]+\n/g, '\n')
            .replace(/\n[ \t]+/g, '\n')
            .replace(/[ \t]{2,}/g, ' ')
            .trim();
    }

    function isSheetNoiseLine(line) {
        const value = cleanSheetValue(line).trim();
        if (!value) return true;
        if (/^(?:\.|#|@media\b|function\b|var\b|let\b|const\b|\(function\b|window\.|document\.|P\.when\b|A\.declarative\b)/.test(value)) return true;
        if (/[{}]/.test(value) && /(display|position|padding|margin|width|height|background|font|border|color|float|z-index|text-align|vertical-align|line-height)\s*:/.test(value)) return true;
        if (/(SponsoredProductsViewability|adFeedback|data-adfeedbackdetails|sp_detail|spAddToCart|a-carousel-card-empty|FirebirdSpRendering)/.test(value)) return true;
        if (/^(?:Thumbs up feedback|Thumbs down feedback|Scroll|Icon|Product Image|送信|読み込み中|カスタマー画像)$/.test(value)) return true;
        if (/(?:お寄せいただいたフィードバック|おすすめの管理|商品を読み込めません|前のスライドセット|次のスライドセット|前のページの関連|次のページの関連|この商品をチェックした人|この商品に関連する商品|無料配送になる関連商品)/.test(value)) return true;
        if (/^ページ:\s*\d+\s*\/\s*\d+/.test(value)) return true;
        return false;
    }

    function sanitizeSheetText(value) {
        const stripped = removeMarkupAndCode(value);
        const lines = stripped
            .split(/\n+/)
            .map(line => line.replace(/\s{2,}/g, ' ').trim())
            .filter(line => !isSheetNoiseLine(line));
        const seen = new Set();
        const out = [];
        for (const line of lines) {
            const key = line.replace(/\s+/g, '');
            if (seen.has(key)) continue;
            seen.add(key);
            out.push(line);
        }
        return out.join('\n');
    }

    function sheetCell(value) {
        return limitSheetCell(sanitizeSheetText(stringifySheetValue(value)));
    }

    function extractAsinFromUrl(url) {
        const match = cleanSheetValue(url).match(/\/(?:dp|gp\/product|gp\/aw\/d)\/([A-Z0-9]{10})(?:[/?#]|$)|[?&]asin=([A-Z0-9]{10})/i);
        return match ? (match[1] || match[2] || '').toUpperCase() : '';
    }

    function normalizeBrandName(value) {
        return cleanSheetValue(value)
            .replace(/^ブランド\s*[:：]\s*/i, '')
            .replace(/^Brand\s*[:：]\s*/i, '')
            .replace(/^Visit the\s+(.+?)\s+Store$/i, '$1')
            .replace(/^(.+?)のストア.*$/i, '$1')
            .trim();
    }

    function extractProductNameFromTitle(title, brand) {
        const cleanTitle = cleanSheetValue(title);
        const cleanBrand = normalizeBrandName(brand);
        if (!cleanTitle) return '';
        if (!cleanBrand) return cleanTitle;
        if (cleanTitle.toLowerCase().startsWith(cleanBrand.toLowerCase())) {
            return cleanTitle.slice(cleanBrand.length).replace(/^[\s:：\-|]+/, '').trim() || cleanTitle;
        }
        return cleanTitle;
    }

    function buildBaseSheetRow(values = {}) {
        return [
            sheetCell(values.category),
            sheetCell(values.title),
            sheetCell(values.amazonUrl || values.url),
            sheetCell(values.asin || extractAsinFromUrl(values.amazonUrl || values.url)),
            sheetCell(values.brand),
            sheetCell(values.productName),
            sheetCell(values.price),
            sheetCell(values.referencePrice || values.listPrice),
            sheetCell(values.rating),
            sheetCell(values.reviewCount),
            sheetCell(values.availability),
            sheetCell(values.seller),
            sheetCell(values.fulfilledBy || values.shipsFrom),
            sheetCell(values.status || values.kind)
        ];
    }

    function makeTsv(headers, rows) {
        return [
            headers.join('\t'),
            ...rows.map(row => row.map(cleanSheetValue).join('\t'))
        ].join('\n');
    }

    function sortProducts(products, sortOrder) {
        const sortedList = [...(products || [])];
        if (sortOrder === 'asc') {
            sortedList.sort((a, b) => parseInt(a.reviewCount || 0, 10) - parseInt(b.reviewCount || 0, 10));
        } else if (sortOrder === 'desc') {
            sortedList.sort((a, b) => parseInt(b.reviewCount || 0, 10) - parseInt(a.reviewCount || 0, 10));
        }
        return sortedList;
    }

    function buildListRows(products, category, sortOrder, kind = '') {
        return sortProducts(products, sortOrder).map(p => buildBaseSheetRow({
            category: category || '',
            title: p.name || p.title || '',
            amazonUrl: p.url || p.amazonUrl || p.affiliateUrl || '',
            asin: p.asin || extractAsinFromUrl(p.url || p.amazonUrl || p.affiliateUrl || ''),
            brand: p.brand || '',
            productName: p.productName || '',
            price: normalizePrice(p.price),
            referencePrice: normalizePrice(p.referencePrice),
            rating: p.rating || '',
            reviewCount: p.reviewCount || '',
            availability: p.availability || '',
            seller: p.seller || '',
            status: kind || p.kind || ''
        }));
    }

    function buildProductDetailRow(productData, kind = '個別商品ページ') {
        return buildBaseSheetRow({
            category: productData.category || '',
            title: productData.title || '',
            amazonUrl: productData.amazonUrl || productData.url || '',
            asin: productData.asin || extractAsinFromUrl(productData.amazonUrl || productData.url || ''),
            brand: productData.brand || '',
            productName: productData.productName || extractProductNameFromTitle(productData.title, productData.brand),
            price: normalizePrice(productData.price),
            referencePrice: normalizePrice(productData.referencePrice || productData.listPrice),
            rating: productData.rating || '',
            reviewCount: productData.reviewCount || '',
            availability: productData.availability || '',
            seller: productData.seller || '',
            fulfilledBy: productData.fulfilledBy || productData.shipsFrom || '',
            status: kind
        });
    }

    function buildCurrentPageAIRow(productData) {
        const category = Array.isArray(productData.categories) && productData.categories.length
            ? productData.categories[productData.categories.length - 1]
            : productData.category || '';
        const amazonUrl = productData.amazonUrl || productData.canonicalUrl || productData.url || '';
        const asin = productData.asin || extractAsinFromUrl(amazonUrl);
        const productName = productData.productName || extractProductNameFromTitle(productData.title, productData.brand);

        return [
            sheetCell(category),
            sheetCell(productData.title),
            sheetCell(amazonUrl),
            sheetCell(asin),
            sheetCell(productData.brand),
            sheetCell(productName),
            sheetCell(productData.price),
            sheetCell(productData.referencePrice || productData.listPrice),
            sheetCell(productData.rating),
            sheetCell(productData.reviewCount),
            sheetCell(productData.availability),
            sheetCell(productData.seller),
            sheetCell(productData.fulfilledBy || productData.shipsFrom),
            '単品',
            '',
            '',
            '',
            sheetCell(productData.featureBullets || productData.text1),
            sheetCell(productData.description || productData.text2),
            sheetCell(productData.aplusLines || productData.text3),
            sheetCell(productData.brandStory),
            sheetCell(productData.productOverview),
            sheetCell(productData.technicalSpecifications || productData.productOverview),
            sheetCell(productData.detailBullets),
            sheetCell(productData.importantInformation),
            sheetCell(productData.imageAlts),
            sheetCell(productData.carouselTexts),
            sheetCell(productData.ocrTexts),
            sheetCell(productData.ocrStatus),
            sheetCell(productData.highResolutionImages),
            sheetCell(productData.capturedAt),
            sheetCell(productData.url),
            sheetCell(productData.canonicalUrl),
            sheetCell(productData.extractionError),
            ''
        ];
    }

    async function writeRowsToSheet(rows, successPrefix = 'Sheetsへ書き込みました') {
        const dataRows = (rows || []).filter(row =>
            Array.isArray(row) && row.some(cell => cleanSheetValue(cell).trim() !== '')
        );

        if (dataRows.length === 0) {
            statusMessageEl.textContent = '⚠️ 書き込むデータがありません';
            chrome.storage.local.set({ status: '⚠️ 書き込むデータがありません' });
            setTimeout(() => updateStatus(), 2000);
            return false;
        }

        statusMessageEl.textContent = `☁️ Sheetsに${dataRows.length}件を書き込み中...`;
        chrome.storage.local.set({ status: `☁️ Sheetsに${dataRows.length}件を書き込み中...` });
        await saveSheetsConfig();

        try {
            if (!sheetsAPI) {
                await loadSheetsAPI();
            }

            await sheetsAPI.appendData(dataRows);
            const successMessage = `✅ ${successPrefix} (${dataRows.length}件)`;
            statusMessageEl.textContent = successMessage;
            chrome.storage.local.set({ status: successMessage });
            setTimeout(() => updateStatus(), 3000);
            return true;
        } catch (error) {
            const errorMessage = `❌ Sheets書き込み失敗: ${error.message}`;
            statusMessageEl.textContent = errorMessage;
            chrome.storage.local.set({ status: errorMessage });
            setTimeout(() => updateStatus(), 5000);
            throw error;
        }
    }

    async function outputRows(rows, options = {}) {
        const dataRows = (rows || []).filter(row =>
            Array.isArray(row) && row.some(cell => cleanSheetValue(cell).trim() !== '')
        );

        if (dataRows.length === 0) {
            statusMessageEl.textContent = '⚠️ 取得できたデータがありません';
            chrome.storage.local.set({ status: '⚠️ 取得できたデータがありません' });
            setTimeout(() => updateStatus(), 2000);
            return false;
        }

        if (await isSheetsEnabled()) {
            await writeRowsToSheet(dataRows, options.sheetSuccessPrefix || 'Sheetsへ書き込みました');
            return true;
        }

        const width = Math.max(...dataRows.map(row => row.length));
        const headers = options.headers || SHEET_HEADERS.slice(0, width);
        const text = options.copyText || makeTsv(headers, dataRows);
        const ok = await copyToClipboardRobust(text);
        if (ok) {
            const successMessage = options.copySuccessMessage || `✅ ${dataRows.length}件をコピーしました`;
            statusMessageEl.textContent = successMessage;
            chrome.storage.local.set({ status: successMessage });
        } else {
            statusMessageEl.textContent = '❌ コピーに失敗しました';
            chrome.storage.local.set({ status: '❌ コピーに失敗しました' });
        }
        setTimeout(() => updateStatus(), 2000);
        return ok;
    }

    async function collectAmazonPageTargets(scope) {
        if (scope === 'allTabs') {
            const allTabs = await chrome.tabs.query({ currentWindow: true });
            const seen = new Set();
            return allTabs.filter(tab => {
                const url = tab.url || '';
                if (isSystemUrl(url) || !url.toLowerCase().includes('amazon.') || seen.has(url)) return false;
                seen.add(url);
                return true;
            });
        }

        const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
        return activeTab && activeTab.url && !isSystemUrl(activeTab.url) ? [activeTab] : [];
    }

    async function executeOnTabs(targets, func, argsBuilder, label = 'ページ') {
        const results = [];
        for (let i = 0; i < targets.length; i++) {
            const targetTab = targets[i];
            statusMessageEl.textContent = `🔄 ${label} ${i + 1}/${targets.length} を処理中...`;
            try {
                const args = typeof argsBuilder === 'function' ? argsBuilder(targetTab, i) : (argsBuilder || []);
                const [result] = await chrome.scripting.executeScript({
                    target: { tabId: targetTab.id },
                    func,
                    args
                });
                if (result && result.result) {
                    results.push(result.result);
                }
            } catch (error) {
                console.error(`${label} ${i + 1} の処理に失敗:`, error);
            }
        }
        return results;
    }

    async function waitForLocalScrapeCompletion(timeoutMs = 600000) {
        const startedAt = Date.now();
        while (Date.now() - startedAt < timeoutMs) {
            const result = await chromeLocalGet(['isScraping', 'scrapedProducts', 'currentCategory', 'sortOrder', 'status']);
            if (!result.isScraping && result.status && result.status !== '取得中...') {
                return result;
            }
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
        throw new Error('スクレイピング完了待ちがタイムアウトしました');
    }

    function isSystemUrl(url) {
        return !url ||
            url.startsWith('chrome://') ||
            url.startsWith('chrome-extension://') ||
            url.startsWith('about:') ||
            url.startsWith('edge://');
    }

    function isAmazonProductUrl(url) {
        const text = String(url || '').toLowerCase();
        if (!text) return false;
        if (text.includes('amzn.asia/') || text.includes('amzn.to/')) return true;
        return text.includes('amazon.') && (
            text.includes('/dp/') ||
            text.includes('/gp/product/') ||
            /\/gp\/aw\/d\/[a-z0-9]{10}(?:[/?#]|$)/i.test(text) ||
            /[?&]asin=[a-z0-9]{10}/i.test(text)
        );
    }

    async function collectAmazonDetailTargets(scope) {
        if (scope === 'allTabs') {
            const allTabs = await chrome.tabs.query({ currentWindow: true });
            const seen = new Set();
            return allTabs.filter(tab => {
                const url = tab.url || '';
                if (isSystemUrl(url) || !isAmazonProductUrl(url) || seen.has(url)) return false;
                seen.add(url);
                return true;
            });
        }

        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab || !tab.url || isSystemUrl(tab.url) || !isAmazonProductUrl(tab.url)) {
            return [];
        }
        return [tab];
    }

    async function collectAmazonDetailPayload(tab) {
        try {
            const [result] = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: async () => {
                    const clean = (value) => String(value || '')
                        .replace(/\u200e|\u200f/g, '')
                        .replace(/\s+/g, ' ')
                        .trim();
                    const removeNoiseNodes = (root) => {
                        if (!root || !root.querySelectorAll) return root;
                        root.querySelectorAll([
                            'script',
                            'style',
                            'noscript',
                            'template',
                            'svg',
                            'iframe',
                            '[aria-hidden="true"]',
                            '.aok-hidden',
                            '[id*="sp_detail"]',
                            '[id*="sponsored"]',
                            '[class*="sponsored"]',
                            '[data-adfeedbackdetails]',
                            '[data-ad-placement-metadata]'
                        ].join(',')).forEach(el => el.remove());
                        return root;
                    };
                    const isNoiseLine = (value) => {
                        const line = clean(value);
                        if (!line) return true;
                        if (/^(?:\.|#|@media\b|function\b|var\b|let\b|const\b|\(function\b|window\.|document\.|P\.when\b|A\.declarative\b)/.test(line)) return true;
                        if (/[{}]/.test(line) && /(display|position|padding|margin|width|height|background|font|border|color|float|z-index|text-align|vertical-align|line-height)\s*:/.test(line)) return true;
                        if (/(SponsoredProductsViewability|adFeedback|data-adfeedbackdetails|sp_detail|spAddToCart|a-carousel-card-empty|FirebirdSpRendering)/.test(line)) return true;
                        if (/^(?:Thumbs up feedback|Thumbs down feedback|Scroll|Icon|Product Image|送信|読み込み中|カスタマー画像)$/.test(line)) return true;
                        if (/(?:お寄せいただいたフィードバック|おすすめの管理|商品を読み込めません|前のスライドセット|次のスライドセット|前のページの関連|次のページの関連|この商品をチェックした人|この商品に関連する商品|無料配送になる関連商品)/.test(line)) return true;
                        if (/^ページ:\s*\d+\s*\/\s*\d+/.test(line)) return true;
                        return false;
                    };
                    const cleanNodeText = (node) => {
                        if (!node) return '';
                        const clone = removeNoiseNodes(node.cloneNode(true));
                        return clean(clone.textContent || '');
                    };
                    const text = (selector) => cleanNodeText(document.querySelector(selector));
                    const attr = (selector, name) => clean(document.querySelector(selector)?.getAttribute(name) || '');
                    const uniq = (values, limit = 300) => {
                        const out = [];
                        const seen = new Set();
                        for (const value of values.flat(Infinity)) {
                            const line = clean(value);
                            if (!line || isNoiseLine(line) || seen.has(line)) continue;
                            seen.add(line);
                            out.push(line);
                            if (out.length >= limit) break;
                        }
                        return out;
                    };
                    const texts = (selector, limit = 300, root = document) => uniq([...root.querySelectorAll(selector)].map(el => cleanNodeText(el)), limit);
                    const linesFrom = (root, limit = 300) => {
                        if (!root) return [];
                        const clone = removeNoiseNodes(root.cloneNode(true));
                        const lines = [];
                        const walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT);
                        while (walker.nextNode()) {
                            const line = clean(walker.currentNode.nodeValue);
                            if (line && line.length >= 2 && !isNoiseLine(line)) lines.push(line);
                        }
                        return uniq(lines, limit);
                    };
                    const kvRows = (selector) => {
                        const rows = {};
                        document.querySelectorAll(selector).forEach((row) => {
                            const key = cleanNodeText(row.querySelector('th, .a-span3, .label, .prodDetSectionEntry')).replace(/:$/, '');
                            const value = cleanNodeText(row.querySelector('td, .a-span9, .value, .prodDetAttrValue'));
                            if (key && value) rows[key] = value;
                        });
                        return rows;
                    };
                    const detailBullets = {};
                    document.querySelectorAll('#detailBullets_feature_div li, #detailBulletsWrapper_feature_div li').forEach((li) => {
                        const raw = clean(li.textContent);
                        const parts = raw.split(':');
                        if (parts.length >= 2) {
                            const key = clean(parts.shift()).replace(/^[\u200e\u200f\s]+|[:：]$/g, '');
                            const value = clean(parts.join(':'));
                            if (key && value) detailBullets[key] = value;
                        }
                    });

                    const aplusRoot = document.querySelector('#aplus, #aplus_feature_div, #aplus3p_feature_div, #dpx-aplus-product-description_feature_div');
                    const aplusLines = linesFrom(aplusRoot, 260);
                    const carouselTexts = uniq([
                        aplusRoot ? texts('[role="tab"], button, .a-carousel-card, [class*="carousel"], [class*="module"], h1, h2, h3, h4, p, li', 180, aplusRoot) : [],
                    ], 300);
                    const imageAlts = uniq([...document.querySelectorAll('#aplus img, #imageBlock img, #altImages img')]
                        .flatMap(img => [img.alt, img.title, img.getAttribute('aria-label')]), 300);
                    const productOverviewRows = kvRows('#productOverview_feature_div tr');
                    const technicalSpecificationRows = {
                        ...kvRows('#productDetails_techSpec_section_1 tr'),
                        ...kvRows('#productDetails_detailBullets_sections1 tr'),
                    };

                    const ocrTexts = [];
                    let ocrStatus = 'not_available';
                    if ('TextDetector' in window) {
                        ocrStatus = 'attempted';
                        try {
                            const detector = new window.TextDetector();
                            const images = [...document.querySelectorAll('#aplus img, #imageBlock img, #altImages img')]
                                .filter(img => img.complete && img.naturalWidth > 120 && img.naturalHeight > 80)
                                .slice(0, 24);
                            for (const img of images) {
                                try {
                                    const bitmap = await createImageBitmap(img);
                                    const detected = await detector.detect(bitmap);
                                    bitmap.close?.();
                                    for (const block of detected || []) {
                                        if (block?.rawValue) ocrTexts.push(block.rawValue);
                                    }
                                } catch (_) {
                                    // Cross-origin images may not be OCR-readable from the page context.
                                }
                            }
                        } catch (error) {
                            ocrStatus = `error: ${error.message}`;
                        }
                    }

                    const dynamicImagesRaw = attr('#landingImage', 'data-a-dynamic-image');
                    let images = [];
                    try { images = Object.keys(JSON.parse(dynamicImagesRaw || '{}')); } catch (_) { images = []; }
                    if (!images.length) {
                        images = uniq([
                            attr('#landingImage', 'src'),
                            attr('meta[property="og:image"]', 'content'),
                        ], 20);
                    }

                    const canonicalUrl = attr('link[rel="canonical"]', 'href');
                    const asin = attr('#ASIN', 'value') ||
                        (location.href.match(/\/(?:dp|gp\/product|gp\/aw\/d)\/([A-Z0-9]{10})(?:[/?#]|$)/i) || [])[1] ||
                        (location.search.match(/[?&]asin=([A-Z0-9]{10})/i) || [])[1] || '';

                    return {
                        source: 'chrome-extension',
                        capturedAt: new Date().toISOString(),
                        url: location.href,
                        canonicalUrl,
                        asin,
                        title: text('#productTitle') || attr('meta[property="og:title"]', 'content') || document.title,
                        pageTitle: document.title,
                        brand: text('#bylineInfo') || text('tr.po-brand td.a-span9 span'),
                        price: text('.a-price .a-offscreen') || text('#priceblock_ourprice') || text('#priceblock_dealprice'),
                        listPrice: text('.basisPrice .a-offscreen') || text('.a-text-price .a-offscreen'),
                        rating: text('#acrPopover span.a-icon-alt') || text('[data-hook="rating-out-of-text"]'),
                        reviewCount: text('#acrCustomerReviewText') || text('[data-hook="total-review-count"]'),
                        availability: text('#availability span'),
                        seller: text('#merchant-info') || text('#sellerProfileTriggerId'),
                        categories: texts('#wayfinding-breadcrumbs_feature_div li a', 20),
                        featureBullets: texts('#feature-bullets li span.a-list-item', 80).filter(value => !/^make sure/i.test(value)),
                        description: text('#productDescription') || text('#bookDescription_feature_div'),
                        aplusLines,
                        carouselTexts,
                        imageAlts,
                        ocrTexts: uniq(ocrTexts, 120),
                        ocrStatus,
                        productOverview: productOverviewRows,
                        technicalSpecifications: technicalSpecificationRows,
                        detailBullets,
                        importantInformation: text('#importantInformation') || text('#legal_feature_div'),
                        highResolutionImages: images,
                    };
                }
            });
            const payload = result?.result || {};
            return { ...payload, url: payload.url || tab.url || '' };
        } catch (error) {
            return {
                source: 'chrome-extension',
                url: tab.url || '',
                title: tab.title || '',
                extractionError: error.message,
            };
        }
    }

    async function triggerAmazonArticlePipeline(urls, payloads, onStatus = () => {}) {
        if (payloads && payloads.length > 1) {
            const results = [];
            for (let i = 0; i < payloads.length; i += 1) {
                const payload = payloads[i];
                const singleUrl = payload.url || payload.canonicalUrl || '';
                onStatus(`🚀 GitHub Actions dispatch送信中... ${i + 1}/${payloads.length}`);
                results.push(await triggerAmazonArticlePipeline(singleUrl ? [singleUrl] : [], [payload], onStatus));
            }
            return results;
        }

        const actionPayloads = (payloads || []).map(buildActionsPayload);
        const requestId = `amazon-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        onStatus(`🚀 GitHub Actions dispatch送信中... (${requestId})`);

        const response = await fetch(`${BLOG_API_BASE}/api/trigger`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                request_id: requestId,
                mode: 'single',
                source_type: 'amazon',
                source_urls: urls,
                source_payloads: actionPayloads,
                status: '単品'
            })
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const details = data.details ? ` / ${data.details}` : '';
            throw new Error(`${data.error || `HTTP ${response.status}`}${details}`);
        }
        onStatus(formatActionRunStatus(data));
        return data;
    }

    if (createArticleButton) {
        createArticleButton.addEventListener('click', async () => {
            const originalText = createArticleButton.textContent;
            try {
                createArticleButton.disabled = true;
                createArticleButton.textContent = '起動中...';
                setArticleStatus('🟦 記事作成ボタンを受け付けました。Amazon商品ページを解析中...');

                const scope = pageDetailSelectEl ? pageDetailSelectEl.value : 'current';
                const tabs = await collectAmazonDetailTargets(scope);
                if (tabs.length === 0) {
                    setArticleStatus('⚠️ Amazon商品ページが見つかりません');
                    return;
                }

                const payloads = [];
                for (let i = 0; i < tabs.length; i += 1) {
                    setArticleStatus(`🔄 Amazon商品詳細を抽出中... ${i + 1}/${tabs.length}`);
                    payloads.push(await collectAmazonDetailPayload(tabs[i]));
                }
                const urls = payloads.map(payload => payload.url).filter(Boolean);

                setArticleStatus(`🚀 ${payloads.length}件の記事作成をGitHub Actionsへ起動中...`);
                const results = await triggerAmazonArticlePipeline(urls, payloads, setArticleStatus);
                const resultList = Array.isArray(results) ? results : [results];
                const runCount = resultList.filter(item => item?.run?.html_url).length;
                const dispatchCount = resultList.filter(item => item?.success).length;
                if (resultList.length === 1 && resultList[0]?.success) {
                    setArticleStatus(formatActionRunStatus(resultList[0]));
                } else if (runCount > 0) {
                    setArticleStatus(`✅ ${dispatchCount}件のActions起動完了。Run検出: ${runCount}件`);
                } else {
                    setArticleStatus(`✅ ${dispatchCount}件のActions dispatch受付済み。GitHub側でRun作成待ちです`);
                }
            } catch (error) {
                console.error('Amazon記事作成エラー:', error);
                setArticleStatus(`❌ 記事作成に失敗: ${error.message}`);
            } finally {
                createArticleButton.disabled = false;
                createArticleButton.textContent = originalText;
            }
        });
    }

    // 設定パネルの表示/非表示
    settingsButton.addEventListener('click', () => {
        if (settingsPanel.style.display === 'none') {
            settingsPanel.style.display = 'block';
            if (promptPanel) promptPanel.style.display = 'none';
            if (mainPanel) mainPanel.style.display = 'block';
        } else {
            settingsPanel.style.display = 'none';
        }
    });

    // プロンプト管理機能
    if (promptButton && promptPanel) {
        promptButton.addEventListener('click', () => {
            if (promptPanel.style.display === 'none') {
                promptPanel.style.display = 'block';
                if (settingsPanel) settingsPanel.style.display = 'none';
                if (mainPanel) mainPanel.style.display = 'none';
                loadPrompts();
            } else {
                promptPanel.style.display = 'none';
                if (mainPanel) mainPanel.style.display = 'block';
            }
        });

        const loadPrompts = () => {
            chrome.storage.sync.get(['prompts'], (result) => {
                const prompts = result.prompts || {};
                const titles = Object.keys(prompts).sort();

                if (promptTitleSelect) {
                    promptTitleSelect.innerHTML = '<option value="">-- 新規作成 --</option>';
                    titles.forEach(title => {
                        const option = document.createElement('option');
                        option.value = title;
                        option.textContent = title;
                        promptTitleSelect.appendChild(option);
                    });
                }
            });
        };

        if (promptTitleSelect) {
            promptTitleSelect.addEventListener('change', async (e) => {
                const selectedTitle = e.target.value;
                if (selectedTitle) {
                    chrome.storage.sync.get(['prompts'], (result) => {
                        const prompts = result.prompts || {};
                        const prompt = prompts[selectedTitle];
                        if (prompt) {
                            if (promptTitleInput) promptTitleInput.value = selectedTitle;
                            if (promptContent) promptContent.value = prompt.content || '';
                            if (prompt.content) {
                                copyToClipboardRobust(prompt.content).then((ok) => {
                                    if (ok) {
                                        console.log('プロンプトをクリップボードにコピーしました:', selectedTitle);
                                    }
                                });
                            }
                        }
                    });
                } else {
                    if (promptTitleInput) promptTitleInput.value = '';
                    if (promptContent) promptContent.value = '';
                }
            });
        }

        if (promptSaveButton) {
            promptSaveButton.addEventListener('click', () => {
                const title = promptTitleInput ? promptTitleInput.value.trim() : '';
                const content = promptContent ? promptContent.value.trim() : '';

                if (!title) {
                    alert('タイトル名を入力してください。');
                    return;
                }

                if (!content) {
                    alert('プロンプト内容を入力してください。');
                    return;
                }

                chrome.storage.sync.get(['prompts'], (result) => {
                    const prompts = result.prompts || {};
                    prompts[title] = { content: content, updatedAt: new Date().toISOString() };
                    chrome.storage.sync.set({ prompts: prompts }, () => {
                        alert('プロンプトを保存しました!');
                        loadPrompts();
                        if (promptTitleSelect) {
                            promptTitleSelect.value = title;
                            promptTitleSelect.dispatchEvent(new Event('change'));
                        }
                    });
                });
            });
        }

        if (promptCopyButton) {
            promptCopyButton.addEventListener('click', async () => {
                const content = promptContent ? promptContent.value.trim() : '';
                if (!content) {
                    alert('コピーするプロンプトがありません。');
                    return;
                }

                const ok = await copyToClipboardRobust(content);
                if (ok) {
                    const originalText = promptCopyButton.textContent;
                    const originalBgColor = promptCopyButton.style.backgroundColor || '#28a745';
                    promptCopyButton.textContent = '✅ コピー完了!';
                    promptCopyButton.style.backgroundColor = '#28a745';
                    setTimeout(() => {
                        promptCopyButton.textContent = originalText;
                        promptCopyButton.style.backgroundColor = originalBgColor;
                    }, 2000);
                } else {
                    alert('コピーに失敗しました。');
                }
            });
        }

        if (promptDeleteButton) {
            promptDeleteButton.addEventListener('click', () => {
                const selectedTitle = promptTitleSelect ? promptTitleSelect.value : '';
                const inputTitle = promptTitleInput ? promptTitleInput.value.trim() : '';
                const titleToDelete = selectedTitle || inputTitle;
                if (!titleToDelete) {
                    alert('削除するタイトルを選択、またはタイトル名を入力してください。');
                    return;
                }

                if (!confirm(`「${titleToDelete}」を削除してもよろしいですか?`)) {
                    return;
                }

                chrome.storage.sync.get(['prompts'], (result) => {
                    const prompts = result.prompts || {};
                    if (!(titleToDelete in prompts)) {
                        alert('指定のタイトルは存在しません。');
                        return;
                    }
                    delete prompts[titleToDelete];
                    chrome.storage.sync.set({ prompts: prompts }, () => {
                        alert('プロンプトを削除しました。');
                        loadPrompts();
                        if (promptTitleInput) promptTitleInput.value = '';
                        if (promptContent) promptContent.value = '';
                        if (promptTitleSelect) promptTitleSelect.value = '';
                    });
                });
            });
        }

        loadPrompts();
    }

    // 複数リンク一括取得機能（新規追加）
    const multiLinkButton = document.getElementById('multiLinkButton');

    if (multiLinkButton) {
        multiLinkButton.addEventListener('click', async () => {
            try {
                // ボタンの状態を変更
                const originalText = multiLinkButton.textContent;
                const originalBgColor = multiLinkButton.style.backgroundColor || '';
                multiLinkButton.textContent = '🔄';
                multiLinkButton.disabled = true;

                // アフィリエイトタグを取得
                chrome.storage.sync.get(['affiliateTag'], async (syncResult) => {
                    const affiliateTag = syncResult.affiliateTag || 'hiroshit-22';

                    try {
                        // 全タブを取得
                        const allTabs = await chrome.tabs.query({ currentWindow: true });
                        const allLinksData = [];
                        let successCount = 0;
                        let failCount = 0;

                        // 各タブを順番に処理
                        for (let i = 0; i < allTabs.length; i++) {
                            const currentTab = allTabs[i];

                            // システムページをスキップ
                            if (!currentTab.url ||
                                currentTab.url.startsWith('chrome://') ||
                                currentTab.url.startsWith('chrome-extension://') ||
                                currentTab.url.startsWith('about:')) {
                                continue;
                            }

                            // Amazon商品ページ以外をスキップ
                            if (!currentTab.url.includes('amazon.co.jp/') ||
                                !currentTab.url.includes('/dp/')) {
                                continue;
                            }

                            try {
                                // アフィリエイトリンク取得スクリプトを実行
                                const [result] = await chrome.scripting.executeScript({
                                    target: { tabId: currentTab.id },
                                    func: (tag) => {
                                        // タイトル取得
                                        const titleElement = document.querySelector('#productTitle, h1.a-size-large');
                                        const title = titleElement ? titleElement.textContent.trim() : '';

                                        // ASIN取得
                                        let asin = '';
                                        const asinInput = document.querySelector('input[name="ASIN"]');
                                        if (asinInput) {
                                            asin = asinInput.value;
                                        } else {
                                            const urlMatch = window.location.href.match(/\/dp\/([A-Z0-9]{10})/);
                                            if (urlMatch) asin = urlMatch[1];
                                        }

                                        // アフィリエイトURL生成
                                        const affiliateUrl = asin ? `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${tag}` : '';

                                        return { title, affiliateUrl };
                                    },
                                    args: [affiliateTag]
                                });

                                if (result && result.result && result.result.title && result.result.affiliateUrl) {
                                    allLinksData.push(result.result);
                                    successCount++;
                                } else {
                                    failCount++;
                                }
                            } catch (error) {
                                console.error(`タブ ${currentTab.id} でエラー:`, error.message);
                                failCount++;
                            }
                        }

                        // データが1件も取得できなかった場合
                        if (allLinksData.length === 0) {
                            multiLinkButton.textContent = originalText;
                            multiLinkButton.style.backgroundColor = originalBgColor;
                            multiLinkButton.disabled = false;
                            return;
                        }

                        // タイトルとURLを整形
                        const textToCopy = allLinksData.map(item => `${item.title}\n\n${item.affiliateUrl}`).join('\n\n');

                        // クリップボードにコピー
                        const ok = await copyToClipboardRobust(textToCopy);

                        if (ok) {
                            // 成功時の視覚的フィードバック
                            multiLinkButton.textContent = '✅';
                            multiLinkButton.style.backgroundColor = '#28a745';
                            setTimeout(() => {
                                multiLinkButton.textContent = originalText;
                                multiLinkButton.style.backgroundColor = originalBgColor;
                                multiLinkButton.disabled = false;
                            }, 1500);
                        } else {
                            // 失敗時
                            multiLinkButton.textContent = originalText;
                            multiLinkButton.style.backgroundColor = originalBgColor;
                            multiLinkButton.disabled = false;
                        }
                    } catch (error) {
                        console.error('全タブリンク取得エラー:', error);
                        multiLinkButton.textContent = originalText;
                        multiLinkButton.style.backgroundColor = originalBgColor;
                        multiLinkButton.disabled = false;
                    }
                });
            } catch (error) {
                console.error('複数リンク取得エラー:', error);
                multiLinkButton.disabled = false;
            }
        });
    }


    // アフィリエイトリンク作成機能
    if (affiliateLinkButton) {
        affiliateLinkButton.addEventListener('click', async () => {
            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

                if (!tab || !tab.url) {
                    console.error('有効なタブが見つかりません');
                    return;
                }

                // アフィリエイトタグを取得
                chrome.storage.sync.get(['affiliateTag'], async (result) => {
                    const affiliateTag = result.affiliateTag || 'hiroshit-22';

                    // ページからタイトルとASINを取得するスクリプト
                    const [scriptResult] = await chrome.scripting.executeScript({
                        target: { tabId: tab.id },
                        func: (tag) => {
                            // タイトル取得
                            const titleElement = document.querySelector('#productTitle, h1.a-size-large');
                            const title = titleElement ? titleElement.textContent.trim() : '';

                            // ASIN取得
                            let asin = '';
                            const asinInput = document.querySelector('input[name="ASIN"]');
                            if (asinInput) {
                                asin = asinInput.value;
                            } else {
                                const urlMatch = window.location.href.match(/\/dp\/([A-Z0-9]{10})/);
                                if (urlMatch) asin = urlMatch[1];
                            }

                            // アフィリエイトURL生成
                            const affiliateUrl = asin ? `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${tag}` : '';

                            return { title, affiliateUrl };
                        },
                        args: [affiliateTag]
                    });

                    if (scriptResult && scriptResult.result) {
                        const { title, affiliateUrl } = scriptResult.result;

                        if (title && affiliateUrl) {
                            // クリップボードにコピー
                            const textToCopy = `${title}\n${affiliateUrl}`;
                            const ok = await copyToClipboardRobust(textToCopy);

                            if (ok) {
                                // ボタンの見た目を一時的に変更
                                const originalText = affiliateLinkButton.textContent;
                                affiliateLinkButton.textContent = '✅';
                                affiliateLinkButton.style.backgroundColor = '#28a745';
                                setTimeout(() => {
                                    affiliateLinkButton.textContent = originalText;
                                    affiliateLinkButton.style.backgroundColor = '';
                                }, 1500);
                            }
                        }
                    }
                });
            } catch (error) {
                console.error('アフィリエイトリンク作成エラー:', error);
            }
        });
    }

    // 保存された設定を読み込み
    chrome.storage.sync.get([
        'affiliateTag',
        'itemCount',
        'minRating',
        'minReviews',
        'sortOrder',
        'mode'
    ], (result) => {
        affiliateTagEl.value = result.affiliateTag || '';
        itemCountEl.value = result.itemCount || 50;
        minRatingEl.value = result.minRating || 4.0;
        minReviewsEl.value = result.minReviews || 10;
        sortOrderEl.value = result.sortOrder || 'default';
        if (modeSelectEl) {
            modeSelectEl.value = result.mode || 'productPage';
        }

        if (statusTargetEl) {
            statusTargetEl.textContent = result.itemCount || 50;
        }
        if (statusModeEl) {
            const modeMap = {
                coupon: 'クーポン取得(グリッド)',
                brand: 'ブランド個別ページ',
                furusato: 'ふるさと納税取得用',
                currentPage: '現在ページ取得',
                productPage: '個別商品ページ',
                currentPageAI: '現在ページをAI用取得',
                allTabsAI: '全タブページをAI用取得',
                standard: '標準スクレイプ'
            };
            const disp = modeMap[result.mode || 'productPage'] || '個別商品ページ';
            statusModeEl.textContent = disp;
        }
    });

    // UIの値が変更されたら自動で保存する関数
    const saveOptions = () => {
        chrome.storage.sync.set({
            affiliateTag: affiliateTagEl.value,
            itemCount: itemCountEl.value,
            minRating: minRatingEl.value,
            minReviews: minReviewsEl.value,
            sortOrder: sortOrderEl.value,
            mode: modeSelectEl ? modeSelectEl.value : 'productPage'
        });

        if (statusTargetEl) {
            statusTargetEl.textContent = itemCountEl.value;
        }
        if (statusModeEl && modeSelectEl) {
            const modeMap = {
                coupon: 'クーポン取得(グリッド)',
                brand: 'ブランド個別ページ',
                furusato: 'ふるさと納税取得用',
                currentPage: '現在ページ取得',
                productPage: '個別商品ページ',
                currentPageAI: '現在ページをAI用取得',
                allTabsAI: '全タブページをAI用取得',
                standard: '標準スクレイプ'
            };
            statusModeEl.textContent = modeMap[modeSelectEl.value] || '個別商品ページ';
        }
    };

    affiliateTagEl.addEventListener('change', saveOptions);
    itemCountEl.addEventListener('change', saveOptions);
    minRatingEl.addEventListener('change', saveOptions);
    minReviewsEl.addEventListener('change', saveOptions);
    sortOrderEl.addEventListener('change', saveOptions);
    if (modeSelectEl) modeSelectEl.addEventListener('change', saveOptions);

    // 実行ボタンの処理(省略 - 既存のコードをそのまま使用)
    // ※ 以降のコードは元のまま継続


    // #################################################
    // ### ここからがrunCurrentPageAIScraper関数 ###
    // #################################################
    function runCurrentPageAIScraper(config) {
        const affiliateTag = config.affiliateTag || 'hiroshit-22';

        // テキスト抽出用のヘルパー関数
        const extractText = (element) => {
            if (!element) return '';
            const clone = element.cloneNode(true);
            const scripts = clone.querySelectorAll('script, style, noscript');
            scripts.forEach(s => s.remove());
            return clone.textContent.trim().replace(/\s+/g, ' ');
        };

        // 重複テキストを除去するヘルパー関数
        const removeDuplicates = (text) => {
            if (!text || text.length < 50) return text;

            const sentences = text.split(/[。\n]/).map(s => s.trim()).filter(s => s.length > 10);
            const uniqueSentences = [];
            const seen = new Set();

            for (const sentence of sentences) {
                const normalized = sentence.replace(/\s+/g, '');

                let isDuplicate = false;

                if (seen.has(normalized)) {
                    isDuplicate = true;
                } else {
                    for (const existingNorm of seen) {
                        const similarity = calculateSimilarity(normalized, existingNorm);
                        if (similarity > 0.9) {
                            isDuplicate = true;
                            break;
                        }
                    }
                }

                if (!isDuplicate) {
                    uniqueSentences.push(sentence);
                    seen.add(normalized);
                }
            }

            return uniqueSentences.join(' ');
        };

        const calculateSimilarity = (str1, str2) => {
            const longer = str1.length > str2.length ? str1 : str2;
            const shorter = str1.length > str2.length ? str2 : str1;

            if (longer.length === 0) return 1.0;

            if (longer.includes(shorter)) {
                return shorter.length / longer.length;
            }

            const editDistance = getEditDistance(str1, str2);
            return (longer.length - editDistance) / longer.length;
        };

        const getEditDistance = (str1, str2) => {
            const matrix = [];

            for (let i = 0; i <= str2.length; i++) {
                matrix[i] = [i];
            }

            for (let j = 0; j <= str1.length; j++) {
                matrix[0][j] = j;
            }

            for (let i = 1; i <= str2.length; i++) {
                for (let j = 1; j <= str1.length; j++) {
                    if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
                        matrix[i][j] = matrix[i - 1][j - 1];
                    } else {
                        matrix[i][j] = Math.min(
                            matrix[i - 1][j - 1] + 1,
                            matrix[i][j - 1] + 1,
                            matrix[i - 1][j] + 1
                        );
                    }
                }
            }

            return matrix[str2.length][str1.length];
        };

        // 「この商品について」セクションを抽出
        const extractFeatureBullets = (doc) => {
            const results = [];

            const featureBullets = doc.querySelectorAll('#feature-bullets ul li span.a-list-item');
            if (featureBullets.length > 0) {
                const items = [];
                featureBullets.forEach(span => {
                    const itemText = span.textContent.trim();
                    if (itemText && itemText.length > 5) {
                        items.push('・' + itemText);
                    }
                });
                if (items.length > 0) {
                    results.push({ text: items.join(' '), count: items.length });
                }
            }

            if (results.length === 0) {
                const featureBulletsBtf = doc.querySelectorAll('#feature-bullets-btf ul li span.a-list-item');
                if (featureBulletsBtf.length > 0) {
                    const items = [];
                    featureBulletsBtf.forEach(span => {
                        const itemText = span.textContent.trim();
                        if (itemText && itemText.length > 5) {
                            items.push('・' + itemText);
                        }
                    });
                    if (items.length > 0) {
                        results.push({ text: items.join(' '), count: items.length });
                    }
                }
            }

            if (results.length > 0) {
                return results[0].text;
            }
            return "";
        };

        // 「メーカーによる説明」セクションを抽出(重複除去機能付き)
        const extractManufacturerDescription = (doc) => {
            const extractedTexts = [];

            const aplusModules = doc.querySelectorAll('[class*="aplus-module"], [id*="aplus"]');
            if (aplusModules.length > 0) {
                aplusModules.forEach(module => {
                    const clone = module.cloneNode(true);
                    const images = clone.querySelectorAll('img');
                    images.forEach(img => img.remove());

                    const tables = clone.querySelectorAll('table');
                    tables.forEach(table => {
                        const tableText = table.textContent.toLowerCase();
                        if (tableText.includes('カートに入れる') ||
                            tableText.includes('カスタマーレビュー') ||
                            tableText.includes('価格') ||
                            tableText.includes('寸法') ||
                            tableText.includes('重量') ||
                            tableText.includes('再生周波数')) {
                            table.remove();
                        }
                    });

                    const text = extractText(clone);
                    if (text.length > 50) {
                        extractedTexts.push(text);
                    }
                });
            }

            const brandStory = doc.querySelector('#aplusBrandStory_feature_div, [id*="brandStory"]');
            if (brandStory) {
                const text = extractText(brandStory);
                if (text.length > 50) {
                    extractedTexts.push(text);
                }
            }

            if (extractedTexts.length > 0) {
                const combinedText = extractedTexts.join(' ');
                const uniqueText = removeDuplicates(combinedText);

                if (uniqueText.length > 100) {
                    return uniqueText;
                }
            }

            return "";
        };

        // 「商品情報」セクションを抽出
        const extractProductDetailsSection = (doc) => {
            const productDetails = doc.querySelector('#productDetails_feature_div');
            if (!productDetails) return "";

            const tableData = [];
            const tables = productDetails.querySelectorAll('table.prodDetTable');

            tables.forEach(table => {
                const rows = table.querySelectorAll('tr');
                rows.forEach(row => {
                    const th = row.querySelector('th');
                    const td = row.querySelector('td');

                    if (th && td) {
                        const thText = th.textContent.trim();
                        const tdText = td.textContent.trim();

                        if (thText && tdText && !thText.includes('おすすめ度') && !thText.includes('Amazon 売れ筋ランキング')) {
                            tableData.push(`${thText}: ${tdText}`);
                        }
                    }
                });
            });

            return tableData.join(' ');
        };

        // 「商品の説明」セクションを抽出
        const extractProductDescription = (doc) => {
            const results = [];

            const productDesc = doc.querySelector('#productDescription');
            if (productDesc) {
                const text = extractText(productDesc);
                if (text.length > 100) {
                    results.push({ text: text, length: text.length });
                }
            }

            if (results.length === 0) {
                const aplusContent = doc.querySelectorAll('[class*="aplus-module"], [id*="aplus"]');
                if (aplusContent.length > 0) {
                    let allText = '';
                    aplusContent.forEach(el => {
                        allText += extractText(el) + ' ';
                    });
                    const text = allText.trim();
                    if (text.length > 100) {
                        results.push({ text: text, length: text.length });
                    }
                }
            }

            if (results.length > 0) {
                return results[0].text;
            }
            return "";
        };

        // 現在のページから情報を取得
        const doc = document;

        // タイトル取得
        const titleElement = doc.querySelector('#productTitle, h1.a-size-large');
        const title = titleElement ? titleElement.textContent.trim() : '商品タイトル不明';
        const brandElement = doc.querySelector('#bylineInfo, tr.po-brand td.a-span9 span, .po-brand .po-break-word');
        const brand = brandElement ? brandElement.textContent.trim().replace(/\s+/g, ' ') : '';
        const categoryElement = doc.querySelector('#wayfinding-breadcrumbs_feature_div ul li:last-child a');
        const category = categoryElement ? categoryElement.textContent.trim().replace(/\s+/g, ' ') : '個別商品ページ';

        // ASIN取得
        let asin = '';
        const asinInput = doc.querySelector('input[name="ASIN"]');
        if (asinInput) {
            asin = asinInput.value;
        } else {
            const urlMatch = window.location.href.match(/\/dp\/([A-Z0-9]{10})/);
            if (urlMatch) asin = urlMatch[1];
        }

        // URL生成
        const amazonUrl = asin ? `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${affiliateTag}` : window.location.href;

        // 価格取得
        const priceElement = doc.querySelector('.a-price[data-a-color="price"] span.a-offscreen, .a-price span.a-offscreen');
        const price = priceElement ? priceElement.textContent.replace(/[^0-9]/g, '') : '';

        // 参考価格取得
        const referencePriceElement = doc.querySelector('.a-price.a-text-price[data-a-strike="true"] span.a-offscreen');
        const referencePrice = referencePriceElement ? referencePriceElement.textContent.replace(/[^0-9]/g, '') : '';

        // レビュー平均取得
        const ratingElement = doc.querySelector('span[data-hook="rating-out-of-text"], i.a-icon-star span.a-icon-alt');
        let rating = '';
        if (ratingElement) {
            const ratingText = ratingElement.textContent;
            const match = ratingText.match(/[\d.]+/);
            if (match) rating = match[0];
        }

        // レビュー数取得
        const reviewCountElement = doc.querySelector('#acrCustomerReviewText, span[data-hook="total-review-count"]');
        let reviewCount = '';
        if (reviewCountElement) {
            const match = reviewCountElement.textContent.match(/[\d,]+/);
            if (match) reviewCount = match[0].replace(/,/g, '');
        }

        // AI用詳細情報取得
        const text1 = extractFeatureBullets(doc);
        const manufacturerDesc = extractManufacturerDescription(doc);
        const productDetailsSection = extractProductDetailsSection(doc);
        const text2 = manufacturerDesc
            ? `${manufacturerDesc} ${productDetailsSection}`.trim()
            : productDetailsSection;
        const text3 = extractProductDescription(doc);

        // ★ 戻り値として商品データを返す(クリップボードコピーは行わない)
        return {
            category: category,
            title: title,
            amazonUrl: amazonUrl,
            brand: brand,
            price: price,
            referencePrice: referencePrice,
            rating: rating,
            reviewCount: reviewCount,
            text1: text1,
            text2: text2,
            text3: text3
        };
    }

    // #################################################
    // ### ここまでがrunCurrentPageAIScraper関数 ###
    // #################################################
    function runProductPageScraper(config) {
        const clean = (value) => String(value || '')
            .replace(/\u200e|\u200f/g, '')
            .replace(/\s+/g, ' ')
            .trim();
        const text = (selector) => clean(document.querySelector(selector)?.textContent || '');
        const attr = (selector, name) => clean(document.querySelector(selector)?.getAttribute(name) || '');

        const extractAsin = () => {
            const asinInput = document.querySelector('input[name="ASIN"]');
            if (asinInput?.value) return asinInput.value;
            const dataAsin = document.querySelector('[data-asin]')?.getAttribute('data-asin');
            if (/^[A-Z0-9]{10}$/.test(dataAsin || '')) return dataAsin;
            const urlMatch = window.location.href.match(/\/(?:dp|gp\/product|gp\/aw\/d)\/([A-Z0-9]{10})/i);
            if (urlMatch) return urlMatch[1].toUpperCase();
            const queryMatch = window.location.href.match(/[?&]asin=([A-Z0-9]{10})/i);
            return queryMatch ? queryMatch[1].toUpperCase() : '';
        };

        const asin = extractAsin();
        const title = text('#productTitle') || text('h1.a-size-large') || clean(document.title);
        const brand = text('#bylineInfo') || text('tr.po-brand td.a-span9 span') || text('.po-brand .po-break-word');
        const category = text('#wayfinding-breadcrumbs_feature_div ul li:last-child a') || '個別商品ページ';
        const price = text('#corePrice_feature_div .a-price .a-offscreen') ||
            text('#priceblock_ourprice') ||
            text('#priceblock_dealprice') ||
            text('.a-price[data-a-color="price"] .a-offscreen') ||
            text('.a-price .a-offscreen');
        const referencePrice = text('.basisPrice .a-price.a-text-price .a-offscreen') ||
            text('.a-price.a-text-price .a-offscreen');
        const availability = text('#availability span');
        const seller = text('#merchant-info') || text('#sellerProfileTriggerId');

        let rating = '';
        const ratingText = text('span[data-hook="rating-out-of-text"]') || text('i.a-icon-star span.a-icon-alt');
        const ratingMatch = ratingText.match(/[\d.]+/);
        if (ratingMatch) rating = ratingMatch[0];

        let reviewCount = '';
        const reviewText = text('#acrCustomerReviewText') || text('span[data-hook="total-review-count"]');
        const reviewMatch = reviewText.match(/[\d,]+/);
        if (reviewMatch) reviewCount = reviewMatch[0].replace(/,/g, '');

        const affiliateTag = config.affiliateTag || 'hiroshit-22';
        const amazonUrl = asin
            ? `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${affiliateTag}`
            : window.location.href;

        return {
            category,
            title,
            amazonUrl,
            asin,
            brand,
            price,
            referencePrice,
            rating,
            reviewCount,
            availability,
            seller
        };
    }

    function runCurrentListPageScraper(config) {
        const affiliateTag = config.affiliateTag || 'hiroshit-22';
        const maxItems = config.itemCount || 50;
        const minReviewCount = config.minReviewCount || 0;

        const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
        const getCategoryName = () => {
            const selectors = [
                'div#departments span.a-text-bold',
                '#wayfinding-breadcrumbs_feature_div ul li:last-child a',
                'span.zg_banner_text',
                'h1'
            ];
            for (const selector of selectors) {
                const value = clean(document.querySelector(selector)?.textContent || '');
                if (value) return value;
            }
            return 'カテゴリ不明';
        };

        const products = [];
        const seenAsins = new Set();
        const selectors = [
            'div[data-component-type="s-search-result"]',
            '.ProductGridItem__itemOuter__KUtvv',
            '.GridItem-module__container_PW2gdkwTj1GQzdwJjejN',
            '.ProductUIRender__grid-item-v2__Ipp8M',
            '.a-carousel-card'
        ];

        document.querySelectorAll(selectors.join(', ')).forEach(el => {
            if (products.length >= maxItems) return;
            const sponsoredLabel = el.querySelector('.puis-sponsored-label-text, [data-cy*="sponsored"], .puis-label-popover-default');
            if (sponsoredLabel && /スポンサー|Sponsored/i.test(sponsoredLabel.textContent || '')) return;

            let asin = el.querySelector('[data-asin]')?.dataset.asin || el.dataset.asin;
            if (!asin && el.dataset.csaCItemId?.includes(':')) {
                let potentialAsin = el.dataset.csaCItemId.split(':')[0].replace(/^amzn1\.asin\./, '');
                if (/^[A-Z0-9]{10}$/.test(potentialAsin)) asin = potentialAsin;
            }
            if (!asin || seenAsins.has(asin)) return;

            const priceElement = el.querySelector('.a-price[data-a-color="price"] span.a-offscreen, .a-price[data-a-color="base"] span.a-offscreen, .a-price .a-offscreen');
            const price = clean(priceElement?.textContent || '');
            if (!price) return;

            const reviewCountElement = el.querySelector('a[href*="#customerReviews"], span[aria-label*="評価"]');
            let reviewCount = '0';
            const reviewMatch = clean(reviewCountElement?.textContent || reviewCountElement?.getAttribute('aria-label') || '').match(/[\d,]+/);
            if (reviewMatch) reviewCount = reviewMatch[0].replace(/,/g, '');
            if (parseInt(reviewCount || '0', 10) < minReviewCount) return;

            const nameSelectors = [
                'h2[aria-label] span',
                'h2 a span.a-text-normal',
                'h2 span.a-text-normal',
                'h2 a span',
                '.a-size-base-plus.a-color-base.a-text-normal',
                'a.a-link-normal[title]',
                'p[id^="title-"] .a-truncate-full',
                'span.a-truncate-full',
                'h2 span'
            ];
            let name = '';
            for (const selector of nameSelectors) {
                const nameElement = el.querySelector(selector);
                const value = clean(nameElement?.title || nameElement?.textContent || '');
                if (value && value.length > 3) {
                    name = value.replace(/\[.*?\]|【.*?】/g, '').trim();
                    break;
                }
            }
            if (!name) name = '商品名不明';

            const referencePriceElement = el.querySelector('.a-price.a-text-price[data-a-strike="true"] span.a-offscreen, .a-price.a-text-price .a-offscreen');
            const referencePrice = clean(referencePriceElement?.textContent || '');

            let rating = '';
            const ratingElement = el.querySelector('i[class*="a-star-mini"] .a-icon-alt, i.a-icon-star-small .a-icon-alt, i.a-icon-star .a-icon-alt');
            const ratingMatch = clean(ratingElement?.textContent || '').match(/[\d.]+/);
            if (ratingMatch) rating = ratingMatch[0];

            seenAsins.add(asin);
            products.push({
                name,
                price,
                referencePrice,
                rating,
                reviewCount,
                url: `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${affiliateTag}`
            });
        });

        return {
            category: getCategoryName(),
            products
        };
    }

    function runCouponGridScraperForRows(config) {
        const affiliateTag = config.affiliateTag || 'hiroshit-22';
        const priorityBrands = ['apple', 'anker', 'dji', 'bose', 'shure', 'sony'];
        const productElements = document.querySelectorAll('.GridItem-module__container_PW2gdkwTj1GQzdwJjejN');
        const products = [];

        productElements.forEach(el => {
            const productCard = el.querySelector('.ProductCard-module__card_uyr_Jh7WpSkPx4iEpn4w');
            if (!productCard) return;
            const asin = productCard.dataset.asin;
            if (!asin) return;
            const nameElement = productCard.querySelector('p[id^="title-"] .a-truncate-full');
            const name = nameElement ? nameElement.textContent.trim() : '商品名不明';
            const couponElement = productCard.querySelector('.a-section.a-spacing-mini > .a-section.a-spacing-none');
            const couponInfo = couponElement ? couponElement.textContent.trim().replace(/\s+/g, ' ') : 'クーポン情報なし';
            const priceElement = productCard.querySelector('div[data-testid="price-section"] span.a-offscreen');
            const price = priceElement ? priceElement.textContent.replace('価格:', '').trim() : '価格不明';
            const url = `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${affiliateTag}`;
            products.push({ name, couponInfo, price, url });
        });

        products.sort((a, b) => {
            const aNameLower = a.name.toLowerCase();
            const bNameLower = b.name.toLowerCase();
            const aPriorityIndex = priorityBrands.findIndex(brand => aNameLower.includes(brand));
            const bPriorityIndex = priorityBrands.findIndex(brand => bNameLower.includes(brand));
            const aPriority = aPriorityIndex !== -1 ? aPriorityIndex : Infinity;
            const bPriority = bPriorityIndex !== -1 ? bPriorityIndex : Infinity;
            if (aPriority !== bPriority) return aPriority - bPriority;
            return aNameLower.localeCompare(bNameLower);
        });

        return { category: 'クーポン', products };
    }

    function runFurusatoScraperForRows(config) {
        const maxItems = config.itemCount || 10;
        const affiliateTag = config.affiliateTag || 'hiroshit-22';
        const products = [];
        const productContainers = document.querySelectorAll('div[data-cel-widget^="acsux-widgets_content-grid_row"]');

        productContainers.forEach(container => {
            if (products.length >= maxItems) return;
            const linkElement = container.querySelector('a');
            const textElement = container.querySelector('._Y29ud_bxcGridText_3AiaV p');
            const imgElement = container.querySelector('img');
            if (!linkElement || !textElement || !imgElement || imgElement.src.includes('1x1_blank.png')) return;

            const relativeUrl = linkElement.getAttribute('href');
            const originalUrl = new URL(relativeUrl, window.location.origin).href;
            const separator = originalUrl.includes('?') ? '&' : '?';
            const newUrl = `${originalUrl}${separator}tag=${affiliateTag}`;
            const textLines = textElement.innerText.split('\n');
            let name = '';
            if (textLines.length > 2) {
                const cityName = textLines[1].trim();
                const priceString = textLines[textLines.length - 1].trim();
                name = `${cityName} ${priceString}`;
            }
            if (name) products.push({ name, url: newUrl });
        });

        return { category: 'ふるさと納税', products };
    }

    function runBrandPageSheetScraper(config) {
        const affiliateTag = config.affiliateTag || 'hiroshit-22';
        const priorityBrands = config.priorityBrands || ['apple', 'anker', 'dji', 'bose', 'shure', 'sony', 'samsung', 'amazon', 'insta360'];
        const products = [];
        const seenAsins = new Set();
        const productContainerSelectors = [
            '.ProductGridItem__itemOuter__KUtvv',
            '.GridItem-module__container_PW2gdkwTj1GQzdwJjejN',
            '.ProductUIRender__grid-item-v2__Ipp8M',
            'div[data-component-type="s-search-result"]',
            '.a-carousel-card'
        ];

        document.querySelectorAll(productContainerSelectors.join(', ')).forEach(el => {
            let asin = null;
            const asinContainer = el.querySelector('[data-asin]');
            if (asinContainer) {
                asin = asinContainer.dataset.asin;
            } else if (el.dataset.asin) {
                asin = el.dataset.asin;
            } else if (el.dataset.csaCItemId && el.dataset.csaCItemId.includes(':')) {
                let potentialAsin = el.dataset.csaCItemId.split(':')[0].replace(/^amzn1\.asin\./, '');
                if (/^[A-Z0-9]{10}$/.test(potentialAsin)) asin = potentialAsin;
            }
            if (!asin || seenAsins.has(asin)) return;
            seenAsins.add(asin);

            const nameElement = el.querySelector(
                'a.Overlay__overlay__LloCU[title], h2.a-size-base.a-text-normal span, span.a-truncate-full, .a-size-base-plus.a-text-normal, h2 a span, p[id^="title-"] .a-truncate-full, a.a-link-normal[title]'
            );
            const name = nameElement ? (nameElement.title || nameElement.textContent).trim() : '商品名不明';

            const priceElement = el.querySelector(
                '.ProductGridItem__buyPrice__hNEg6 span.Price__whole__mQGs5, span.a-price[data-a-color="base"] span.a-offscreen, .ProductCard-module__priceToPay_olAgJzVNGyj2javg2pAe span.a-offscreen, .a-price .a-offscreen'
            );
            let price = priceElement ? priceElement.textContent.replace(/セール特価:|価格:|タイムセール価格:/, '').trim() : '価格不明';
            if (price !== '価格不明' && !price.startsWith('¥')) price = '¥' + price;

            const referencePriceElement = el.querySelector(
                '.StrikeThroughPrice__strikePrice__stBvh span.Price__whole__mQGs5, .a-price.a-text-price[data-a-strike="true"] span.a-offscreen, .ProductCard-module__wrapPrice__sMO92NjAjHmGPn3jnIH .a-price .a-offscreen'
            );
            let referencePrice = referencePriceElement ? referencePriceElement.textContent.replace(/過去価格:|参考価格:/, '').trim() : '';
            if (referencePrice && !referencePrice.startsWith('¥')) referencePrice = '¥' + referencePrice;

            let discountInfo = '';
            const discountBadgeElement = el.querySelector(
                '.PriceSavings__priceSavings__QNKjj, span.apex-savings-percent, .style_filledRoundedBadgeLabel__Vo-4g'
            );
            if (discountBadgeElement) {
                const discountText = discountBadgeElement.textContent.trim().replace('-', '');
                discountInfo += discountText + ' OFF';
            }
            const couponElement = el.querySelector('.s-coupon-unclipped, .s-coupon-clipped, .ProductCard-module__badgeContainer_MLO5roh0cMYvmI7ZELJC');
            if (couponElement) {
                if (discountInfo) discountInfo += ' + ';
                discountInfo += couponElement.textContent.trim().replace(/\s+/g, ' ');
            }
            const couponInfo = discountInfo || '割引/クーポンなし';
            const url = `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${affiliateTag}`;
            products.push({ name, couponInfo, price, referencePrice, url });
        });

        products.sort((a, b) => {
            const aNameLower = a.name.toLowerCase();
            const bNameLower = b.name.toLowerCase();
            const aPriorityIndex = priorityBrands.findIndex(brand => aNameLower.includes(brand));
            const bPriorityIndex = priorityBrands.findIndex(brand => bNameLower.includes(brand));
            const aPriority = aPriorityIndex !== -1 ? aPriorityIndex : Infinity;
            const bPriority = bPriorityIndex !== -1 ? bPriorityIndex : Infinity;
            if (aPriority !== bPriority) return aPriority - bPriority;
            return aNameLower.localeCompare(bNameLower);
        });

        return { category: 'ブランド個別ページ', products };
    }

    executeJsButton.addEventListener('click', async () => {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

        if (!tab || !tab.url) {
            statusMessageEl.textContent = '⚠️ 有効なタブが見つかりません';
            return;
        }

        const mode = modeSelectEl ? modeSelectEl.value : 'productPage';

        if (mode === 'currentPage') {
            try {
                const targets = await collectAmazonPageTargets(pageDetailSelectEl?.value || 'current');
                const results = await executeOnTabs(targets, runCurrentListPageScraper, () => [{
                    affiliateTag: affiliateTagEl.value,
                    itemCount: parseInt(itemCountEl.value, 10),
                    minReviewCount: parseInt(minReviewsEl.value, 10)
                }], '現在ページ');
                const rows = results.flatMap(result =>
                    buildListRows(result.products || [], result.category || 'カテゴリ不明', sortOrderEl.value, '現在ページ取得')
                );
                await outputRows(rows, {
                    headers: SHEET_HEADERS.slice(0, 14),
                    sheetSuccessPrefix: '現在ページ取得をSheetsへ書き込みました',
                    copySuccessMessage: `✅ 現在ページ取得 ${rows.length}件をコピーしました`
                });
            } catch (error) {
                console.error('現在ページ取得エラー:', error);
                statusMessageEl.textContent = `❌ 現在ページ取得に失敗しました: ${error.message}`;
                setTimeout(() => updateStatus(), 5000);
            }
            return;
        }

        if (mode === 'productPage') {
            try {
                const targets = await collectAmazonDetailTargets(pageDetailSelectEl?.value || 'current');
                const results = await executeOnTabs(targets, runProductPageScraper, () => [{
                    affiliateTag: affiliateTagEl.value
                }], '個別商品ページ');
                const rows = results.map(result => buildProductDetailRow(result, '個別商品ページ'));
                await outputRows(rows, {
                    headers: SHEET_HEADERS.slice(0, 14),
                    sheetSuccessPrefix: '個別商品ページをSheetsへ書き込みました',
                    copySuccessMessage: `✅ 個別商品ページ ${rows.length}件をコピーしました`
                });
            } catch (error) {
                console.error('個別商品ページ取得エラー:', error);
                statusMessageEl.textContent = `❌ 個別商品ページ取得に失敗しました: ${error.message}`;
                setTimeout(() => updateStatus(), 5000);
            }
            return;
        }

        // 現在ページAI用取得モード
        if (mode === 'currentPageAI') {
            try {
                const targets = await collectAmazonDetailTargets(pageDetailSelectEl?.value || 'current');
                const results = [];
                for (let i = 0; i < targets.length; i += 1) {
                    statusMessageEl.textContent = `🔄 AI用商品ページ ${i + 1}/${targets.length} を詳細抽出中...`;
                    chrome.storage.local.set({ status: `🔄 AI用商品ページ ${i + 1}/${targets.length} を詳細抽出中...` });
                    results.push(await collectAmazonDetailPayload(targets[i]));
                }
                const rows = results.map(buildCurrentPageAIRow);
                await outputRows(rows, {
                    headers: SHEET_HEADERS,
                    sheetSuccessPrefix: 'AI用商品情報をSheetsへ書き込みました',
                    copySuccessMessage: `✅ AI用商品情報 ${rows.length}件をコピーしました`
                });
            } catch (error) {
                console.error('ページ取得エラー:', error);
                statusMessageEl.textContent = `❌ ページ取得に失敗しました: ${error.message}`;
                setTimeout(() => updateStatus(), 5000);
            }
            return;
        }

        // 全タブページをAI用取得モード → 全タブでアフィリエイトリンク作成
        if (mode === 'allTabsAI') {
            try {
                const targets = await collectAmazonDetailTargets('allTabs');
                const results = await executeOnTabs(targets, runProductPageScraper, () => [{
                    affiliateTag: affiliateTagEl.value
                }], '全タブリンク');
                const rows = results.map(result => buildProductDetailRow(result, '全タブリンク'));
                const copyText = results.map(item => `${item.title}\n\n${item.amazonUrl}`).join('\n\n');
                await outputRows(rows, {
                    headers: SHEET_HEADERS.slice(0, 14),
                    copyText,
                    sheetSuccessPrefix: '全タブリンクをSheetsへ書き込みました',
                    copySuccessMessage: `✅ 全タブリンク ${rows.length}件をコピーしました`
                });
            } catch (error) {
                console.error('全タブリンク取得エラー:', error);
                statusMessageEl.textContent = `❌ 全タブリンク取得に失敗しました: ${error.message}`;
                setTimeout(() => updateStatus(), 5000);
            }
            return;
        }

        if (mode === 'coupon') {
            try {
                const targets = await collectAmazonPageTargets(pageDetailSelectEl?.value || 'current');
                const results = await executeOnTabs(targets, runCouponGridScraperForRows, () => [{
                    affiliateTag: affiliateTagEl.value
                }], 'クーポンページ');
                const rows = results.flatMap(result => (result.products || []).map(p => buildBaseSheetRow({
                    category: result.category || 'クーポン',
                    title: p.name || '',
                    amazonUrl: p.url || '',
                    asin: p.asin || extractAsinFromUrl(p.url || ''),
                    productName: p.couponInfo || '',
                    price: normalizePrice(p.price),
                    status: 'クーポン取得'
                })));
                const copyText = results
                    .flatMap(result => result.products || [])
                    .map(p => `${p.name}\n価格:${p.price}⇛${p.couponInfo}\n${p.url}`)
                    .join('\n\n');
                await outputRows(rows, {
                    headers: SHEET_HEADERS.slice(0, 14),
                    copyText,
                    sheetSuccessPrefix: 'クーポン取得結果をSheetsへ書き込みました',
                    copySuccessMessage: `✅ クーポン取得 ${rows.length}件をコピーしました`
                });
            } catch (error) {
                console.error('クーポン取得エラー:', error);
                statusMessageEl.textContent = `❌ クーポン取得に失敗しました: ${error.message}`;
                setTimeout(() => updateStatus(), 5000);
            }
            return;
        }

        if (mode === 'furusato') {
            try {
                const targets = await collectAmazonPageTargets(pageDetailSelectEl?.value || 'current');
                const results = await executeOnTabs(targets, runFurusatoScraperForRows, () => [{
                    affiliateTag: affiliateTagEl.value,
                    itemCount: parseInt(itemCountEl.value, 10)
                }], 'ふるさと納税ページ');
                const rows = results.flatMap(result => (result.products || []).map(p => buildBaseSheetRow({
                    category: result.category || 'ふるさと納税',
                    title: p.name || '',
                    amazonUrl: p.url || '',
                    asin: p.asin || extractAsinFromUrl(p.url || ''),
                    status: 'ふるさと納税'
                })));
                const copyText = results
                    .flatMap(result => result.products || [])
                    .map(p => `${p.name}\n${p.url}`)
                    .join('\n');
                await outputRows(rows, {
                    headers: SHEET_HEADERS.slice(0, 14),
                    copyText,
                    sheetSuccessPrefix: 'ふるさと納税取得結果をSheetsへ書き込みました',
                    copySuccessMessage: `✅ ふるさと納税 ${rows.length}件をコピーしました`
                });
            } catch (error) {
                console.error('ふるさと納税取得エラー:', error);
                statusMessageEl.textContent = `❌ ふるさと納税取得に失敗しました: ${error.message}`;
                setTimeout(() => updateStatus(), 5000);
            }
            return;
        }

        if (mode === 'brand') {
            try {
                const targets = await collectAmazonPageTargets(pageDetailSelectEl?.value || 'current');
                const results = await executeOnTabs(targets, runBrandPageSheetScraper, () => [{
                    affiliateTag: affiliateTagEl.value,
                    priorityBrands: ['apple', 'anker', 'dji', 'bose', 'shure', 'sony', 'samsung', 'amazon', 'insta360']
                }], 'ブランドページ');
                const rows = results.flatMap(result => (result.products || []).map(p => buildBaseSheetRow({
                    category: result.category || 'ブランド個別ページ',
                    title: p.name || '',
                    amazonUrl: p.url || '',
                    asin: p.asin || extractAsinFromUrl(p.url || ''),
                    productName: p.couponInfo || '',
                    price: normalizePrice(p.price),
                    referencePrice: normalizePrice(p.referencePrice),
                    status: 'ブランド個別ページ'
                })));
                const copyText = results
                    .flatMap(result => result.products || [])
                    .map(p => {
                        const discountPart = p.couponInfo && p.couponInfo !== '割引/クーポンなし' ? `【${p.couponInfo}】` : '';
                        const referencePricePart = p.referencePrice ? ` ←${p.referencePrice}(参考価格)` : '';
                        return `${p.name}\n価格:${discountPart}${p.price}${referencePricePart}\n${p.url}`;
                    })
                    .join('\n\n');
                await outputRows(rows, {
                    headers: SHEET_HEADERS.slice(0, 14),
                    copyText,
                    sheetSuccessPrefix: 'ブランド個別ページをSheetsへ書き込みました',
                    copySuccessMessage: `✅ ブランド個別ページ ${rows.length}件をコピーしました`
                });
            } catch (error) {
                console.error('ブランド個別ページ取得エラー:', error);
                statusMessageEl.textContent = `❌ ブランド個別ページ取得に失敗しました: ${error.message}`;
                setTimeout(() => updateStatus(), 5000);
            }
            return;
        }

        // クーポン取得(グリッド)モード
        if (modeSelectEl && modeSelectEl.value === 'coupon') {
            function runCouponGridScraper(config) {
                const affiliateTag = config.affiliateTag || 'hiroshit-22';
                const priorityBrands = ['apple', 'anker', 'dji', 'bose', 'shure', 'sony'];

                const scrapeProducts = () => {
                    const productElements = document.querySelectorAll('.GridItem-module__container_PW2gdkwTj1GQzdwJjejN');
                    const products = [];
                    productElements.forEach(el => {
                        const productCard = el.querySelector('.ProductCard-module__card_uyr_Jh7WpSkPx4iEpn4w');
                        if (!productCard) return;
                        const asin = productCard.dataset.asin;
                        if (!asin) return;
                        const nameElement = productCard.querySelector('p[id^="title-"] .a-truncate-full');
                        const name = nameElement ? nameElement.textContent.trim() : '商品名不明';
                        const couponElement = productCard.querySelector('.a-section.a-spacing-mini > .a-section.a-spacing-none');
                        const couponInfo = couponElement ? couponElement.textContent.trim().replace(/\s+/g, ' ') : 'クーポン情報なし';
                        const priceElement = productCard.querySelector('div[data-testid="price-section"] span.a-offscreen');
                        const price = priceElement ? priceElement.textContent.replace('価格:', '').trim() : '価格不明';
                        const url = `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${affiliateTag}`;
                        products.push({ name, couponInfo, price, url });
                    });
                    return products;
                };

                const formatDataAndSort = (productList) => {
                    productList.sort((a, b) => {
                        const aNameLower = a.name.toLowerCase();
                        const bNameLower = b.name.toLowerCase();
                        const aPriorityIndex = priorityBrands.findIndex(brand => aNameLower.includes(brand));
                        const bPriorityIndex = priorityBrands.findIndex(brand => bNameLower.includes(brand));
                        const aPriority = aPriorityIndex !== -1 ? aPriorityIndex : Infinity;
                        const bPriority = bPriorityIndex !== -1 ? bPriorityIndex : Infinity;
                        if (aPriority !== bPriority) return aPriority - bPriority;
                        const aBrand = aNameLower.split(' ')[0];
                        const bBrand = bNameLower.split(' ')[0];
                        if (aBrand < bBrand) return -1;
                        if (aBrand > bBrand) return 1;
                        return 0;
                    });
                    let formattedText = '';
                    productList.forEach(p => {
                        formattedText += `${p.name}\n`;
                        formattedText += `価格:${p.price}⇛${p.couponInfo}\n`;
                        formattedText += `${p.url}\n\n`;
                    });
                    return { formattedText, totalCount: productList.length, sortedList: productList };
                };

                const createCopyUI = (textToCopy, totalCount) => {
                    const existingUI = document.getElementById('custom-amazon-scraper-ui');
                    if (existingUI) existingUI.remove();
                    const uiContainer = document.createElement('div');
                    uiContainer.id = 'custom-amazon-scraper-ui';
                    uiContainer.style.cssText = `
                        position: fixed; bottom: 20px; right: 20px;
                        background-color: #f9f9f9; border: 1px solid #ccc; border-radius: 8px;
                        padding: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.2);
                        z-index: 9999; font-family: "Amazon Ember", Arial, sans-serif;
                        font-size: 16px; line-height: 1.5; text-align: center; color: #111;
                    `;
                    const message = document.createElement('p');
                    message.textContent = `合計 ${totalCount} 件の商品を検出しました。`;
                    message.style.margin = '0 0 15px 0';
                    uiContainer.appendChild(message);
                    const copyButton = document.createElement('button');
                    copyButton.textContent = 'クリップボードにコピー';
                    copyButton.style.cssText = `
                        padding: 10px 20px; border: none; background-color: #232f3e;
                        color: white; border-radius: 5px; cursor: pointer;
                        margin-right: 10px; font-size: 14px;
                    `;
                    copyButton.onmouseover = () => { copyButton.style.backgroundColor = '#4a5b70'; };
                    copyButton.onmouseout = () => { copyButton.style.backgroundColor = '#232f3e'; };
                    copyButton.onclick = async () => {
                        const tryNavigator = async () => {
                            try {
                                if (navigator.clipboard && navigator.clipboard.writeText) {
                                    await navigator.clipboard.writeText(textToCopy);
                                    return true;
                                }
                            } catch (_) { }
                            return false;
                        };
                        const tryTextarea = () => {
                            try {
                                const textarea = document.createElement('textarea');
                                textarea.value = textToCopy;
                                textarea.style.position = 'fixed';
                                textarea.style.top = '-1000px';
                                textarea.style.left = '-1000px';
                                document.body.appendChild(textarea);
                                textarea.focus();
                                textarea.select();
                                const ok = document.execCommand('copy');
                                document.body.removeChild(textarea);
                                return ok;
                            } catch (_) { return false; }
                        };
                        try {
                            const ok = (await tryNavigator()) || tryTextarea();
                            if (!ok) throw new Error('copy failed');
                            copyButton.textContent = 'コピー完了!';
                            copyButton.style.backgroundColor = '#28a745';
                            copyButton.disabled = true;
                            setTimeout(() => { uiContainer.remove(); }, 1500);
                        } catch (err) {
                            console.error('クリップボードへのコピーに失敗しました:', err);
                            alert('クリップボードへのコピーに失敗しました。コンソールを確認してください。');
                        }
                    };
                    uiContainer.appendChild(copyButton);
                    const closeButton = document.createElement('button');
                    closeButton.textContent = '閉じる';
                    closeButton.style.cssText = `
                        padding: 10px 20px; border: 1px solid #ccc; background-color: #fff;
                        color: #333; border-radius: 5px; cursor: pointer; font-size: 14px;
                    `;
                    closeButton.onmouseover = () => { closeButton.style.backgroundColor = '#f0f0f0'; };
                    closeButton.onmouseout = () => { closeButton.style.backgroundColor = '#fff'; };
                    closeButton.onclick = () => { uiContainer.remove(); };
                    uiContainer.appendChild(closeButton);
                    document.body.appendChild(uiContainer);
                };

                const allProducts = scrapeProducts();
                if (allProducts.length > 0) {
                    const { formattedText, totalCount, sortedList } = formatDataAndSort(allProducts);
                    console.clear();
                    console.log(`%c▓ ▓ ▓  Amazon商品情報取得結果(${totalCount}件) ▓ ▓ ▓ `, "color: white; background-color: #232f3e; padding: 4px; border-radius: 4px; font-weight: bold;");
                    console.table(sortedList, ["name", "price", "couponInfo", "url"]);
                    createCopyUI(formattedText, totalCount);
                } else {
                    alert('対象となる商品が見つかりませんでした。');
                }
            }

            chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: runCouponGridScraper,
                args: [{
                    affiliateTag: affiliateTagEl.value
                }]
            });
            return;
        }

        // ふるさと納税取得用モード
        if (modeSelectEl && modeSelectEl.value === 'furusato') {
            function runFurusatoScraper(config) {
                const maxItemsToCopy = config.itemCount || 10;
                const affiliateTag = config.affiliateTag || 'hiroshit-22';

                const productContainers = document.querySelectorAll('div[data-cel-widget^="acsux-widgets_content-grid_row"]');
                if (productContainers.length === 0) {
                    alert("商品情報が見つかりませんでした。ページの構造が変更された可能性があります。");
                    return;
                }
                const productData = [];
                productContainers.forEach(container => {
                    if (productData.length >= maxItemsToCopy) return;
                    const linkElement = container.querySelector('a');
                    const textElement = container.querySelector('._Y29ud_bxcGridText_3AiaV p');
                    const imgElement = container.querySelector('img');
                    if (linkElement && textElement && imgElement && !imgElement.src.includes('1x1_blank.png')) {
                        const relativeUrl = linkElement.getAttribute('href');
                        const originalUrl = new URL(relativeUrl, window.location.origin).href;
                        const separator = originalUrl.includes('?') ? '&' : '?';
                        const newUrl = `${originalUrl}${separator}tag=${affiliateTag}`;
                        const textLines = textElement.innerText.split('\n');
                        let name = '';
                        if (textLines.length > 2) {
                            const cityName = textLines[1].trim();
                            const priceString = textLines[textLines.length - 1].trim();
                            name = `${cityName} ${priceString}`;
                        }
                        if (name) {
                            productData.push(`${name}\n${newUrl}`);
                        }
                    }
                });
                const clipboardText = productData.join('\n');
                const itemCount = productData.length;
                if (itemCount === 0) {
                    alert("抽出できる商品がありませんでした。");
                    return;
                }
                const copyRobust = async (text) => {
                    try { if (navigator.clipboard && navigator.clipboard.writeText) { await navigator.clipboard.writeText(text); return true; } } catch (_) { }
                    try { const ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.top = '-1000px'; ta.style.left = '-1000px'; document.body.appendChild(ta); ta.focus(); ta.select(); const ok = document.execCommand('copy'); document.body.removeChild(ta); return ok; } catch (_) { return false; }
                };
                copyRobust(clipboardText).then(ok => {
                    if (ok) {
                        alert(`${itemCount}件の商品情報をクリップボードにコピーしました!`);
                        console.log("ふるさと納税: ", itemCount, "件");
                    } else {
                        alert('コピーに失敗しました。');
                    }
                });
            }

            chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: runFurusatoScraper,
                args: [{
                    affiliateTag: affiliateTagEl.value,
                    itemCount: parseInt(itemCountEl.value, 10)
                }]
            });
            return;
        }

        // ブランド個別ページモード
        if (modeSelectEl && modeSelectEl.value === 'brand') {
            function runBrandPageScraper(config) {
                const affiliateTag = config.affiliateTag || 'hiroshit-22';
                const priorityBrands = config.priorityBrands || ['apple', 'anker', 'dji', 'bose', 'shure', 'sony', 'samsung', 'amazon', 'insta360'];

                let scrapedProducts = [];
                let scrapedAsins = new Set();

                const copyRobust = async (text) => {
                    try {
                        if (navigator.clipboard && navigator.clipboard.writeText) {
                            await navigator.clipboard.writeText(text);
                            return true;
                        }
                    } catch (_) { }
                    try {
                        const ta = document.createElement('textarea');
                        ta.value = text;
                        ta.style.position = 'fixed';
                        ta.style.top = '-1000px';
                        ta.style.left = '-1000px';
                        document.body.appendChild(ta);
                        ta.focus();
                        ta.select();
                        const ok = document.execCommand('copy');
                        document.body.removeChild(ta);
                        return ok;
                    } catch (_) { return false; }
                };

                const scrapeAndAppendVisibleProducts = () => {
                    const productContainerSelectors = [
                        '.ProductGridItem__itemOuter__KUtvv',
                        '.GridItem-module__container_PW2gdkwTj1GQzdwJjejN',
                        '.ProductUIRender__grid-item-v2__Ipp8M',
                        'div[data-component-type="s-search-result"]',
                        '.a-carousel-card'
                    ];
                    const productElements = document.querySelectorAll(productContainerSelectors.join(', '));
                    let newProductsCount = 0;
                    productElements.forEach(el => {
                        let asin = null;
                        const asinContainer = el.querySelector('[data-asin]');
                        if (asinContainer) {
                            asin = asinContainer.dataset.asin;
                        } else if (el.dataset.asin) {
                            asin = el.dataset.asin;
                        } else if (el.dataset.csaCItemId && el.dataset.csaCItemId.includes(':')) {
                            let potentialAsin = el.dataset.csaCItemId.split(':')[0];
                            if (potentialAsin.startsWith('amzn1.asin.')) {
                                potentialAsin = potentialAsin.substring('amzn1.asin.'.length);
                            }
                            if (/^[A-Z0-9]{10}$/.test(potentialAsin)) {
                                asin = potentialAsin;
                            }
                        }
                        if (!asin || scrapedAsins.has(asin)) return;
                        scrapedAsins.add(asin);

                        const nameElement = el.querySelector(
                            'a.Overlay__overlay__LloCU[title], h2.a-size-base.a-text-normal span, span.a-truncate-full, .a-size-base-plus.a-text-normal, h2 a span, p[id^="title-"] .a-truncate-full, a.a-link-normal[title]'
                        );
                        const name = nameElement ? (nameElement.title || nameElement.textContent).trim() : '商品名不明';

                        const priceElement = el.querySelector(
                            '.ProductGridItem__buyPrice__hNEg6 span.Price__whole__mQGs5, span.a-price[data-a-color="base"] span.a-offscreen, .ProductCard-module__priceToPay_olAgJzVNGyj2javg2pAe span.a-offscreen'
                        );
                        let price = priceElement ? priceElement.textContent.replace(/セール特価:|価格:|タイムセール価格:/, '').trim() : '価格不明';
                        if (!price.startsWith('¥')) { price = '¥' + price; }

                        const referencePriceElement = el.querySelector(
                            '.StrikeThroughPrice__strikePrice__stBvh span.Price__whole__mQGs5, .a-price.a-text-price[data-a-strike="true"] span.a-offscreen, .ProductCard-module__wrapPrice__sMO92NjAjHmGPn3jnIH .a-price .a-offscreen'
                        );
                        let referencePrice = referencePriceElement ? referencePriceElement.textContent.replace(/過去価格:|参考価格:/, '').trim() : '';
                        if (referencePrice && !referencePrice.startsWith('¥')) { referencePrice = '¥' + referencePrice; }

                        let discountInfo = '';
                        const discountBadgeElement = el.querySelector(
                            '.PriceSavings__priceSavings__QNKjj, span.apex-savings-percent, .style_filledRoundedBadgeLabel__Vo-4g'
                        );
                        if (discountBadgeElement) {
                            const discountText = discountBadgeElement.textContent.trim().replace('-', '');
                            discountInfo += discountText + ' OFF';
                        }
                        const couponElement = el.querySelector('.s-coupon-unclipped, .s-coupon-clipped, .ProductCard-module__badgeContainer_MLO5roh0cMYvmI7ZELJC');
                        if (couponElement) {
                            if (discountInfo) discountInfo += ' + ';
                            discountInfo += couponElement.textContent.trim().replace(/\s+/g, ' ');
                        }
                        const couponInfo = discountInfo || '割引/クーポンなし';
                        const url = `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${affiliateTag}`;
                        scrapedProducts.push({ name, couponInfo, price, referencePrice, url });
                        newProductsCount++;
                    });
                    if (newProductsCount > 0) {
                        console.log(`${newProductsCount} 件の新しい商品を追加しました。現在の合計: ${scrapedProducts.length} 件`);
                    } else {
                        console.log("新しい商品は見つかりませんでした。ページをスクロールしたか、既に全件取得済みです。");
                    }
                    updateUIMessage();
                };

                const formatAndCopyAll = async () => {
                    if (scrapedProducts.length === 0) {
                        alert('商品はまだ1件も取得されていません。');
                        return;
                    }
                    const sortedList = [...scrapedProducts].sort((a, b) => {
                        const aNameLower = a.name.toLowerCase();
                        const bNameLower = b.name.toLowerCase();
                        const aPriorityIndex = priorityBrands.findIndex(brand => aNameLower.includes(brand));
                        const bPriorityIndex = priorityBrands.findIndex(brand => bNameLower.includes(brand));
                        const aPriority = aPriorityIndex !== -1 ? aPriorityIndex : Infinity;
                        const bPriority = bPriorityIndex !== -1 ? bPriorityIndex : Infinity;
                        if (aPriority !== bPriority) return aPriority - bPriority;
                        const aBrand = aNameLower.split(' ')[0];
                        const bBrand = bNameLower.split(' ')[0];
                        if (aBrand < bBrand) return -1;
                        if (aBrand > bBrand) return 1;
                        return 0;
                    });
                    let formattedText = '';
                    sortedList.forEach(p => {
                        formattedText += `${p.name}\n`;
                        const discountPart = p.couponInfo !== '割引/クーポンなし' ? `【${p.couponInfo}】` : '';
                        const referencePricePart = p.referencePrice ? ` ←${p.referencePrice}(参考価格)` : '';
                        formattedText += `価格:${discountPart}${p.price}${referencePricePart}\n`;
                        formattedText += `${p.url}\n\n`;
                    });
                    const ok = await copyRobust(formattedText);
                    if (ok) {
                        alert(`${scrapedProducts.length} 件の商品情報をクリップボードにコピーしました!`);
                        console.clear();
                        console.log(`%c▓ ▓ ▓  Amazon商品情報取得結果(合計 ${scrapedProducts.length}件) ▓ ▓ ▓ `, "color: white; background-color: #232f3e; padding: 4px; border-radius: 4px; font-weight: bold;");
                        console.table(sortedList);
                    } else {
                        alert('コピーに失敗しました。コンソールを確認してください。');
                    }
                };

                const resetScraper = () => {
                    scrapedProducts = [];
                    scrapedAsins.clear();
                    console.clear();
                    console.log("データをリセットしました。");
                    updateUIMessage();
                };

                const updateUIMessage = () => {
                    const messageEl = document.getElementById('custom-scraper-message');
                    if (messageEl) {
                        messageEl.textContent = `取得済み: ${scrapedProducts.length} 件`;
                    }
                };

                const createAppendUI = () => {
                    const existingUI = document.getElementById('custom-amazon-scraper-ui');
                    if (existingUI) existingUI.remove();
                    const uiContainer = document.createElement('div');
                    uiContainer.id = 'custom-amazon-scraper-ui';
                    uiContainer.style.cssText = `position: fixed; bottom: 20px; right: 20px; background-color: #f9f9f9; border: 1px solid #ccc; border-radius: 8px; padding: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.2); z-index: 9999; font-family: "Amazon Ember", Arial, sans-serif; font-size: 14px; text-align: center; color: #111;`;
                    const message = document.createElement('p');
                    message.id = 'custom-scraper-message';
                    message.style.margin = '0 0 10px 0';
                    message.style.fontWeight = 'bold';
                    uiContainer.appendChild(message);
                    const buttonContainer = document.createElement('div');
                    buttonContainer.style.display = 'flex';
                    buttonContainer.style.gap = '8px';
                    const appendButton = document.createElement('button');
                    appendButton.textContent = '取得&追記';
                    appendButton.style.cssText = `padding: 8px 12px; border: none; background-color: #007bff; color: white; border-radius: 5px; cursor: pointer;`;
                    appendButton.onclick = scrapeAndAppendVisibleProducts;
                    buttonContainer.appendChild(appendButton);
                    const copyButton = document.createElement('button');
                    copyButton.textContent = '全件コピー';
                    copyButton.style.cssText = `padding: 8px 12px; border: none; background-color: #232f3e; color: white; border-radius: 5px; cursor: pointer;`;
                    copyButton.onclick = formatAndCopyAll;
                    buttonContainer.appendChild(copyButton);
                    const resetButton = document.createElement('button');
                    resetButton.textContent = 'リセット';
                    resetButton.style.cssText = `padding: 8px 12px; border: 1px solid #ccc; background-color: #fff; color: #333; border-radius: 5px; cursor: pointer;`;
                    resetButton.onclick = resetScraper;
                    buttonContainer.appendChild(resetButton);
                    uiContainer.appendChild(buttonContainer);
                    document.body.appendChild(uiContainer);
                    updateUIMessage();
                };

                createAppendUI();
                console.log("ブランド個別ページ用スクリプトの準備が完了しました。ページをスクロールし、「取得&追記」で追加してください。");
            }

            chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: runBrandPageScraper,
                args: [{
                    affiliateTag: affiliateTagEl.value,
                    priorityBrands: ['apple', 'anker', 'dji', 'bose', 'shure', 'sony', 'samsung', 'amazon', 'insta360']
                }]
            });
            return;
        }

        // 標準スクレイプモード
        const sheetsEnabledForStandard = await isSheetsEnabled();
        const config = {
            affiliateTag: affiliateTagEl.value,
            itemCount: parseInt(itemCountEl.value, 10),
            minRating: parseFloat(minRatingEl.value),
            minReviewCount: parseInt(minReviewsEl.value, 10),
            sortOrder: sortOrderEl.value,
            mode: mode,
            sheetsEnabled: sheetsEnabledForStandard
        };
        // スクレイピング開始前の状態を設定
        chrome.storage.local.set({
            isScraping: true,
            status: '取得中...',
            scrapedProducts: [],
            shouldStop: false,
            mode: mode
        });

        statusMessageEl.textContent = '🔄 スクレイピング開始...';

        // スクレイピング関数
        function scrapeAmazonPage(config) {
            const TOTAL_PRODUCTS_TO_SCRAPE = config.itemCount;
            const affiliateTag = config.affiliateTag;
            const MIN_REVIEW_COUNT = config.minReviewCount;
            const SORT_ORDER = config.sortOrder;

            let scrapedProducts = [];
            let scrapedAsins = new Set();
            let isScraping = false;
            let currentCategory = 'カテゴリ不明';

            const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

            const getCategoryName = () => {
                const selectors = [
                    'div#departments span.a-text-bold',
                    '#wayfinding-breadcrumbs_feature_div ul li:last-child a',
                    'span.zg_banner_text',
                ];
                for (const selector of selectors) {
                    const el = document.querySelector(selector);
                    if (el && el.textContent.trim()) return el.textContent.trim();
                }
                return 'カテゴリ不明';
            };

            const scrapeAndAppendVisibleProducts = () => {
                const productContainerSelectors = [
                    'div[data-component-type="s-search-result"]',
                    '.ProductGridItem__itemOuter__KUtvv',
                    '.GridItem-module__container_PW2gdkwTj1GQzdwJjejN',
                    '.ProductUIRender__grid-item-v2__Ipp8M',
                    '.a-carousel-card'
                ];
                document.querySelectorAll(productContainerSelectors.join(', ')).forEach(el => {
                    // スポンサー商品を除外
                    const sponsoredLabel = el.querySelector('.puis-sponsored-label-text, [data-cy*="sponsored"], .puis-label-popover-default');
                    if (sponsoredLabel && (sponsoredLabel.textContent.includes('スポンサー') || sponsoredLabel.textContent.includes('Sponsored'))) {
                        return;
                    }

                    let asin = el.querySelector('[data-asin]')?.dataset.asin || el.dataset.asin;
                    if (!asin && el.dataset.csaCItemId?.includes(':')) {
                        let potentialAsin = el.dataset.csaCItemId.split(':')[0];
                        if (/^[A-Z0-9]{10}$/.test(potentialAsin)) asin = potentialAsin;
                    }
                    if (!asin || scrapedAsins.has(asin)) return;

                    const priceElement = el.querySelector('.a-price[data-a-color="price"] span.a-offscreen, .a-price[data-a-color="base"] span.a-offscreen');
                    const price = priceElement ? priceElement.textContent : '価格不明';
                    if (price === '価格不明') return;

                    const reviewCountElement = el.querySelector('a[href*="#customerReviews"]');
                    let reviewCount = '0';
                    if (reviewCountElement) {
                        const match = reviewCountElement.textContent.trim().match(/[\d,]+/);
                        if (match) reviewCount = match[0].replace(/,/g, '');
                    }
                    if (parseInt(reviewCount, 10) < MIN_REVIEW_COUNT) return;

                    scrapedAsins.add(asin);

                    // 【修正】商品名取得ロジックの強化
                    const nameSelectors = [
                        // スポンサー商品のタイトル(aria-label付き)
                        'h2[aria-label] span',
                        // 通常の検索結果のタイトル
                        'h2 a span.a-text-normal',
                        'h2 span.a-text-normal',
                        // その他のパターン
                        'h2 a span',
                        '.a-size-base-plus.a-color-base.a-text-normal',
                        'a.a-link-normal[title]',
                        'h2.a-size-mini span',
                        // フォールバック用
                        'h2 span'
                    ];

                    let rawName = '商品名不明';
                    for (const selector of nameSelectors) {
                        const nameElement = el.querySelector(selector);
                        if (nameElement) {
                            const text = (nameElement.title || nameElement.textContent || '').trim();
                            if (text && text.length > 3 && text !== '商品名不明') {
                                rawName = text;
                                break;
                            }
                        }
                    }

                    // デバッグ用: 商品名が取得できなかった場合のログ
                    if (rawName === '商品名不明') {
                        console.warn(`商品名取得失敗 ASIN: ${asin}`, el);
                    }

                    // ブランド名や不要な記号を削除
                    const name = rawName.replace(/\[.*?\]|【.*?】/g, '').trim();

                    const referencePriceElement = el.querySelector('.a-price.a-text-price[data-a-strike="true"] span.a-offscreen');
                    const referencePrice = referencePriceElement ? referencePriceElement.textContent : '';

                    let rating = '評価なし';
                    const ratingElement = el.querySelector('i[class*="a-star-mini"] .a-icon-alt, i.a-icon-star-small .a-icon-alt');
                    if (ratingElement && ratingElement.textContent.includes('5つ星のうち')) {
                        rating = ratingElement.textContent.replace('5つ星のうち', '').trim();
                    }
                    const url = `https://www.amazon.co.jp/dp/${asin}/ref=nosim?tag=${affiliateTag}`;
                    scrapedProducts.push({ name, price, referencePrice, rating, reviewCount, url });
                });

                // ストレージに保存してポップアップに反映
                chrome.storage.local.set({
                    scrapedProducts: scrapedProducts,
                    currentCategory: currentCategory,
                    isScraping: isScraping
                });
            };

            const startAutomaticScraping = async () => {
                if (isScraping) return;
                isScraping = true;
                currentCategory = getCategoryName();
                console.log(`カテゴリ「${currentCategory}」の取得を開始します。目標: ${TOTAL_PRODUCTS_TO_SCRAPE}件, 最低レビュー数: ${MIN_REVIEW_COUNT}件`);

                chrome.storage.local.set({
                    scrapedProducts: scrapedProducts,
                    currentCategory: currentCategory,
                    isScraping: isScraping,
                    status: '取得中...',
                    shouldStop: false
                });

                try {
                    while (scrapedProducts.length < TOTAL_PRODUCTS_TO_SCRAPE) {
                        // 停止フラグをチェック
                        const storage = await chrome.storage.local.get(['shouldStop']);
                        if (storage.shouldStop) {
                            console.log('%c停止が要求されました', "color: orange; font-weight: bold;");
                            break;
                        }

                        window.scrollTo(0, document.body.scrollHeight);
                        await sleep(1500);
                        scrapeAndAppendVisibleProducts();
                        if (scrapedProducts.length >= TOTAL_PRODUCTS_TO_SCRAPE) {
                            console.log(`%c取得完了: 目標の ${TOTAL_PRODUCTS_TO_SCRAPE} 件以上に達しました。`, "color: green; font-weight: bold;");
                            break;
                        }
                        const nextButton = document.querySelector('a.s-pagination-next, .a-last a');
                        if (nextButton && !nextButton.classList.contains('s-pagination-disabled') && nextButton.href) {
                            nextButton.click();
                            await sleep(3000);
                        } else {
                            console.log(`%c取得完了: 最後のページに到達しました。`, "color: green; font-weight: bold;");
                            break;
                        }
                    }
                } catch (error) {
                    console.error("エラー:", error);
                    chrome.storage.local.set({ status: 'エラー発生', isScraping: false });
                } finally {
                    isScraping = false;
                    const storage = await chrome.storage.local.get(['shouldStop']);
                    const finalStatus = storage.shouldStop ? '停止しました' : '取得完了';
                    chrome.storage.local.set({
                        scrapedProducts: scrapedProducts,
                        currentCategory: currentCategory,
                        isScraping: false,
                        status: finalStatus,
                        sortOrder: SORT_ORDER,
                        mode: config.mode || 'productPage',
                        autoCompleted: !storage.shouldStop
                    });

                    // 自動完了の場合、クリップボードにコピー
                    if (!storage.shouldStop && scrapedProducts.length > 0 && !config.sheetsEnabled) {
                        await sleep(500); // 少し待ってからコピー

                        const headers = ['カテゴリ', 'タイトル', 'Amazon URL', 'ブランド', '製品名', '価格', '参考価格', 'レビュー平均', 'レビュー数'].join('\t');

                        let sortedList = [...scrapedProducts];
                        if (SORT_ORDER === 'asc') {
                            sortedList.sort((a, b) => parseInt(a.reviewCount, 10) - parseInt(b.reviewCount, 10));
                        } else if (SORT_ORDER === 'desc') {
                            sortedList.sort((a, b) => parseInt(b.reviewCount, 10) - parseInt(a.reviewCount, 10));
                        }

                        const dataRows = sortedList.map(p => [
                            currentCategory, p.name, p.url, '', '',
                            p.price.replace(/[^0-9]/g, ''),
                            p.referencePrice.replace(/[^0-9]/g, ''),
                            p.rating, p.reviewCount
                        ].join('\t'));

                        const tsvText = [headers, ...dataRows].join('\n');

                        const tryAutoCopy = async () => {
                            try {
                                if (navigator.clipboard && navigator.clipboard.writeText) {
                                    await navigator.clipboard.writeText(tsvText);
                                    return true;
                                }
                            } catch (_) { }
                            try {
                                const ta = document.createElement('textarea');
                                ta.value = tsvText;
                                ta.style.position = 'fixed';
                                ta.style.top = '-1000px';
                                ta.style.left = '-1000px';
                                document.body.appendChild(ta);
                                ta.focus();
                                ta.select();
                                const ok = document.execCommand('copy');
                                document.body.removeChild(ta);
                                return ok;
                            } catch (_) { return false; }
                        };
                        const ok = await tryAutoCopy();
                        if (ok) {
                            console.log(`%c自動コピー完了: ${dataRows.length} 件をクリップボードにコピーしました。`, "color: blue; font-weight: bold;");
                            chrome.storage.local.set({ status: '✅ 完了 & コピー済み' });
                        } else {
                            console.warn('自動コピーは失敗しました。ポップアップのコピーを使用してください。');
                            chrome.storage.local.set({ status: '取得完了(コピーはポップアップから実行してください)' });
                        }
                    } else if (!storage.shouldStop && scrapedProducts.length > 0 && config.sheetsEnabled) {
                        chrome.storage.local.set({ status: '取得完了(Sheets書き込み待ち)' });
                    }
                }
            };

            // メイン処理の実行
            console.log("拡張機能からスクリプトを実行しました (Ver. 10.0)");
            startAutomaticScraping();
        }

        try {
            await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: scrapeAmazonPage,
                args: [config]
            });

            if (sheetsEnabledForStandard) {
                const completed = await waitForLocalScrapeCompletion();
                const rows = buildListRows(
                    completed.scrapedProducts || [],
                    completed.currentCategory || 'カテゴリ不明',
                    completed.sortOrder || sortOrderEl.value,
                    '標準スクレイプ'
                );
                await writeRowsToSheet(rows, '標準スクレイプ結果をSheetsへ書き込みました');
            } else {
                statusMessageEl.textContent = '✅ スクレイピング完了';
                setTimeout(() => updateStatus(), 1000);
            }
        } catch (error) {
            console.error('実行エラー:', error);
            statusMessageEl.textContent = '❌ 実行に失敗しました';
            chrome.storage.local.set({
                isScraping: false,
                status: 'エラー'
            });
        }
    });




    // ステータス更新の監視
    const updateStatus = () => {
        chrome.storage.local.get([
            'scrapedProducts',
            'currentCategory',
            'isScraping',
            'status',
            'sortOrder',
            'mode'
        ], (result) => {
            const products = result.scrapedProducts || [];
            const category = result.currentCategory || '-';
            const status = result.status || '待機中';
            const sortOrder = result.sortOrder || sortOrderEl.value;
            const mode = modeSelectEl ? modeSelectEl.value : (result.mode || 'productPage');

            if (statusMessageEl) {
                statusMessageEl.textContent = status === '取得中...' ? `取得中... ${products.length} / ${itemCountEl.value}` : status;
            }
            if (statusCategoryEl) {
                statusCategoryEl.textContent = category;
            }
            if (statusCountEl) {
                statusCountEl.textContent = products.length;
            }
            if (statusSortEl) {
                const sortText = sortOrder === 'asc' ? '昇順' : sortOrder === 'desc' ? '降順' : 'デフォルト';
                statusSortEl.textContent = sortText;
            }
            if (statusModeEl) {
                const modeMap = {
                    coupon: 'クーポン取得(グリッド)',
                    brand: 'ブランド個別ページ',
                    furusato: 'ふるさと納税取得用',
                    currentPage: '現在ページ取得',
                    productPage: '個別商品ページ',
                    currentPageAI: '現在ページをAI用取得',
                    allTabsAI: '全タブページをAI用取得',
                    standard: '標準スクレイプ'
                };
                statusModeEl.textContent = modeMap[mode] || '個別商品ページ';
            }
        });
    };

    setInterval(updateStatus, 500);
    updateStatus();

    // 【修正】全件コピーボタン - chrome.storage.localから取得するように変更
    if (copyAllButton) {
        copyAllButton.addEventListener('click', async () => {
            // ★ 重要: chrome.storage.local に変更
            chrome.storage.local.get(['scrapedProducts', 'currentCategory', 'sortOrder', 'mode'], async (localResult) => {
                const products = localResult.scrapedProducts || [];
                const category = localResult.currentCategory || 'カテゴリ不明';
                const sortOrder = localResult.sortOrder || sortOrderEl.value;
                const mode = localResult.mode || 'productPage';

                if (products.length === 0) {
                    statusMessageEl.textContent = '⚠️ コピーするデータがありません';
                    chrome.storage.local.set({ status: '⚠️ コピーするデータがありません' });
                    setTimeout(() => updateStatus(), 2000);
                    return;
                }

                let dataRows = [];

                if (mode === 'currentPageAI') {
                    dataRows = products.map(buildCurrentPageAIRow);
                } else {
                    dataRows = buildListRows(products, category, sortOrder, mode === 'standard' ? '標準スクレイプ' : mode);
                }

                const width = Math.max(...dataRows.map(row => row.length));
                const headers = SHEET_HEADERS.slice(0, width);
                const tsvText = makeTsv(headers, dataRows);

                try {
                    const ok = await copyToClipboardRobust(tsvText);
                    if (!ok) throw new Error('copy failed');

                    const originalText = copyAllButton.textContent;
                    copyAllButton.textContent = '✅ コピー完了!';
                    copyAllButton.style.backgroundColor = '#28a745';
                    statusMessageEl.textContent = `✅ ${dataRows.length}件をコピーしました`;
                    chrome.storage.local.set({ status: `✅ ${dataRows.length}件をコピーしました` });
                    setTimeout(() => {
                        copyAllButton.textContent = originalText;
                        copyAllButton.style.backgroundColor = '';
                    }, 2000);
                } catch (error) {
                    statusMessageEl.textContent = '❌ コピーに失敗しました';
                    chrome.storage.local.set({ status: '❌ コピーに失敗しました' });
                    setTimeout(() => updateStatus(), 2000);
                }
            });
        });
    }

    // 停止ボタン
    if (stopButton) {
        stopButton.addEventListener('click', async () => {
            chrome.storage.local.get(['isScraping'], async (result) => {
                if (!result.isScraping) {
                    statusMessageEl.textContent = '⚠️ 実行中のタスクがありません';
                    setTimeout(() => updateStatus(), 2000);
                    return;
                }

                chrome.storage.local.set({
                    isScraping: false,
                    status: '停止しました',
                    shouldStop: true
                });

                statusMessageEl.textContent = 'ℹ️ 停止しました';
                setTimeout(() => updateStatus(), 2000);
            });
        });
    }
});
