import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const script = await readFile(new URL('../../info_viewer_site/static/js/viewer.js', import.meta.url), 'utf8');

async function checkSearch(manifest) {
  const input = { value: '', handlers: {}, addEventListener(name, handler) { this.handlers[name] = handler; } };
  const status = { textContent: '' };
  const results = { innerHTML: '' };
  const elements = { 'viewer-data': { textContent: '[]' }, 'search-input': input, 'search-status': status, 'search-results': results };
  const seen = [];
  const article = { id: 'example', url: '/articles/example/', title: '確認用の記事', channelName: 'テスト', persons: [], text: '検索対象の本文' };
  const document = {
    body: { dataset: { pageKind: 'list', indexVersion: '1' } },
    getElementById(id) { return elements[id] || null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  const window = { location: { search: '' }, history: { replaceState() {} }, localStorage: { getItem() { return ''; } } };
  const context = vm.createContext({ document, window, navigator: { maxTouchPoints: 0 }, URLSearchParams, URL, console,
    fetch: async (url) => { seen.push(url); return { ok: true, json: async () => url.startsWith('/search.json') ? manifest : [article] }; },
  });
  vm.runInContext(script, context);
  input.value = '検索対象の本文';
  await input.handlers.input();
  assert.match(results.innerHTML, /確認用の記事/);
  assert.match(status.textContent, /1件/);
  return seen;
}

const shardedRequests = await checkSearch({ version: 2, parts: ['search/part-00.json'] });
assert.equal(shardedRequests.length, 2);
assert.match(shardedRequests[1], /search\/part-00\.json/);
const legacyRequests = await checkSearch([{ id: 'example', url: '/articles/example/', title: '確認用の記事', persons: [], text: '検索対象の本文' }]);
assert.equal(legacyRequests.length, 1);
console.log('分割版と従来版の本文検索を確認しました。');
