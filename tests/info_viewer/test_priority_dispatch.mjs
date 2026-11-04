import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { timingSafeEqual } from 'node:crypto';

const source = await readFile(new URL('../../api/info-viewer.js', import.meta.url), 'utf8');
const requests = [];
const context = vm.createContext({
  Buffer, URL, URLSearchParams, setTimeout, console,
  process: { env: { INFO_VIEWER_GAS_SECRET: 'test-secret', GITHUB_TOKEN: 'test-token' } },
  fetch: async (url, options) => {
    requests.push({ url, options });
    return { status: 204, ok: true };
  },
});
const module = new vm.SourceTextModule(source, { context });
await module.link(async (specifier) => {
  if (specifier === 'node:crypto') {
    return new vm.SyntheticModule(['timingSafeEqual'], function () { this.setExport('timingSafeEqual', timingSafeEqual); }, { context });
  }
  if (specifier.includes('info-viewer-notion')) {
    return new vm.SyntheticModule(['default'], function () { this.setExport('default', () => {}); }, { context });
  }
  return new vm.SyntheticModule(['syncGitHubActionsRefreshToken'], function () { this.setExport('syncGitHubActionsRefreshToken', () => {}); }, { context });
});
await module.evaluate();
const response = {
  setHeader() {},
  status(code) { this.statusCode = code; return this; },
  json(value) { this.body = value; return this; },
};
await module.namespace.default({
  method: 'POST', query: { resource: 'priority' }, headers: { 'x-info-viewer-gas-secret': 'test-secret' },
  body: { source: 'gas-sheet-watcher', video_url: 'https://www.youtube.com/watch?v=I8HV_SQPKRY' },
}, response);
assert.equal(response.statusCode, 200);
assert.equal(response.body.workflowTriggered, true);
assert.equal(requests.length, 1);
assert.match(requests[0].url, /api\.github\.com/);
assert.equal(JSON.parse(requests[0].options.body).client_payload.source, 'gas-sheet-watcher');
requests.length = 0;
const manualResponse = {
  setHeader() {},
  status(code) { this.statusCode = code; return this; },
  json(value) { this.body = value; return this; },
};
await module.namespace.default({
  method: 'POST', query: { resource: 'priority' }, headers: { 'x-info-viewer-gas-secret': 'test-secret' },
  body: { video_url: 'https://www.youtube.com/watch?v=I8HV_SQPKRY' },
}, manualResponse);
assert.equal(manualResponse.statusCode, 200);
assert.equal(requests.length, 1);
assert.match(requests[0].url, /actions\/workflows\/info-viewer-queue.yml\/dispatches/);
assert.equal(JSON.parse(requests[0].options.body).inputs.video_url, 'https://www.youtube.com/watch?v=I8HV_SQPKRY');
console.log('定期通知は状態ファイルへ書き込まず Actions を起動します。');
