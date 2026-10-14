const INFO_VIEWER_CONFIG = Object.freeze({
  spreadsheetId: '1cw6RC1XX4nAYvfZrBq7nmTtrr2oGFsSI0r_pVIxGxAc',
  channelSheetName: 'チャンネル設定',
  videoSheetName: '動画リスト',
  endpoint: 'https://blog-vercel-dun.vercel.app/api/info-viewer?resource=priority',
  secretProperty: 'INFO_VIEWER_GAS_SECRET',
  stateProperty: 'INFO_VIEWER_DISPATCH_META_V1',
  videoPropertyPrefix: 'INFO_VIEWER_DISPATCH_VIDEO_',
  pollFunction: 'pollInfoViewerNewVideos',
  retryMinutes: 10,
  redispatchMinutes: 45,
  maxDispatchesPerRun: 4,
  maxStateEntries: 1000,
});

const INFO_VIEWER_ALIASES = Object.freeze({
  viewer: ['info_viewer', 'info-viewer', 'info viewer', 'viewer'],
  channelName: ['チャンネル', 'チャンネル名', 'channel', 'channel name'],
  channelUrl: ['チャンネルURL', 'channel_url', 'channel url'],
  videoUrl: ['動画URL', 'video_url', 'url'],
  videoTitle: ['動画タイトル', 'タイトル', 'title', '動画名'],
  publishedAt: ['投稿日', '公開日', 'published_at', 'publishedAt'],
  videoUpdatedAt: ['動画更新日時', '更新日時', 'updated_at', 'updatedAt', 'video_updated_at', 'videoUpdatedAt'],
  status: ['状況', 'status'],
  exclude: ['不要判定', '除外', 'skip', 'exclude'],
});

/**
 * 初回設定用。秘密値はソースへ残さず、Script Propertiesへ保存する。
 * clasp run setInfoViewerGasSecret --params '["秘密値"]' から呼び出す。
 */
function setInfoViewerGasSecret(secret) {
  const value = String(secret || '').trim();
  if (value.length < 24) {
    throw new Error('INFO_VIEWER_GAS_SECRET は24文字以上で設定してください。');
  }
  PropertiesService.getScriptProperties().setProperty(INFO_VIEWER_CONFIG.secretProperty, value);
  return { configured: true };
}

/**
 * 既存動画を基準点として記録した後、1分間隔の監視を有効化する。
 * 導入前のpending/failedは通知対象に戻さない。
 */
function installInfoViewerDispatcher() {
  const secret = getRequiredSecret_();
  if (!secret) {
    throw new Error('INFO_VIEWER_GAS_SECRET が未設定です。');
  }

  const targets = loadAllVideoUrls_();
  const now = new Date().toISOString();
  const state = {
    version: 1,
    installedAt: now,
    updatedAt: now,
    videos: {},
  };

  targets.forEach((video) => {
    state.videos[video.key] = {
      videoUrl: video.videoUrl,
      rowNumber: video.rowNumber,
      firstSeenAt: now,
      lastSeenAt: now,
      status: 'legacy',
      attempts: 0,
      lastDispatchAt: '',
      nextRetryAt: '',
      lastError: '',
    };
  });

  saveState_(state);
  removeDispatcherTriggers_();
  ScriptApp.newTrigger(INFO_VIEWER_CONFIG.pollFunction).timeBased().everyMinutes(1).create();

  return {
    installed: true,
    baselineCount: targets.length,
    triggerCount: getDispatcherTriggerCount_(),
    installedAt: now,
  };
}

/**
 * 動画リストの新規対象URLをVercel経由でGitHub Actionsへ通知する。
 */
function pollInfoViewerNewVideos() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) {
    return { skipped: true, reason: '別の監視処理が実行中です。' };
  }

  try {
    const state = loadState_();
    if (!state.installedAt) {
      throw new Error('初期化されていません。installInfoViewerDispatcher を先に実行してください。');
    }

    const now = new Date();
    const nowIso = now.toISOString();
    const videos = loadTargetVideos_();
    const activeKeys = new Set();
    let dispatchCount = 0;
    let completedCount = 0;
    let deferredCount = 0;
    const errors = [];

    videos.forEach((video) => {
      activeKeys.add(video.key);
      const existing = state.videos[video.key];
      const record = existing || {
        videoUrl: video.videoUrl,
        rowNumber: video.rowNumber,
        firstSeenAt: nowIso,
        lastSeenAt: nowIso,
        status: 'pending',
        attempts: 0,
        lastDispatchAt: '',
        nextRetryAt: '',
        lastError: '',
      };

      record.videoUrl = video.videoUrl;
      record.rowNumber = video.rowNumber;
      record.lastSeenAt = nowIso;
      state.videos[video.key] = record;

      if (video.status === '完了') {
        if (record.status !== 'legacy') {
          record.status = 'done';
        }
        record.lastError = '';
        completedCount += 1;
        return;
      }
      if (record.status === 'legacy' || dispatchCount >= INFO_VIEWER_CONFIG.maxDispatchesPerRun) {
        return;
      }
      if (!isDispatchDue_(record, now)) {
        deferredCount += 1;
        return;
      }

      try {
        const response = dispatchVideo_(video);
        record.status = 'dispatched';
        record.attempts = Number(record.attempts || 0) + 1;
        record.lastDispatchAt = nowIso;
        record.nextRetryAt = new Date(now.getTime() + INFO_VIEWER_CONFIG.redispatchMinutes * 60000).toISOString();
        record.lastError = '';
        record.responseMessage = response.message || '';
        dispatchCount += 1;
      } catch (error) {
        record.status = 'retry';
        record.attempts = Number(record.attempts || 0) + 1;
        record.lastError = String(error && error.message ? error.message : error);
        record.nextRetryAt = new Date(now.getTime() + INFO_VIEWER_CONFIG.retryMinutes * 60000).toISOString();
        errors.push(`${video.videoUrl}: ${record.lastError}`);
      }
    });

    Object.keys(state.videos).forEach((key) => {
      const record = state.videos[key];
      if (!activeKeys.has(key) && record.status !== 'legacy') {
        record.status = 'removed';
      }
    });

    state.updatedAt = nowIso;
    pruneState_(state);
    saveState_(state);

    return {
      scanned: videos.length,
      dispatched: dispatchCount,
      completed: completedCount,
      deferred: deferredCount,
      errors,
    };
  } finally {
    lock.releaseLock();
  }
}

function getInfoViewerDispatcherStatus() {
  const state = loadState_();
  const counts = {};
  Object.values(state.videos || {}).forEach((record) => {
    const status = String(record.status || 'unknown');
    counts[status] = Number(counts[status] || 0) + 1;
  });
  return {
    configured: Boolean(PropertiesService.getScriptProperties().getProperty(INFO_VIEWER_CONFIG.secretProperty)),
    installedAt: state.installedAt || '',
    updatedAt: state.updatedAt || '',
    triggerCount: getDispatcherTriggerCount_(),
    counts,
  };
}

function uninstallInfoViewerDispatcher() {
  removeDispatcherTriggers_();
  return { uninstalled: true, triggerCount: getDispatcherTriggerCount_() };
}

function loadTargetVideos_() {
  const spreadsheet = SpreadsheetApp.openById(INFO_VIEWER_CONFIG.spreadsheetId);
  const channelRows = loadRows_(spreadsheet.getSheetByName(INFO_VIEWER_CONFIG.channelSheetName));
  const videoRows = loadRows_(spreadsheet.getSheetByName(INFO_VIEWER_CONFIG.videoSheetName));
  const channelsByName = {};
  const channelsByUrl = {};

  channelRows.forEach((row) => {
    const viewerFlag = pick_(row, INFO_VIEWER_ALIASES.viewer);
    if (!viewerFlag) return;
    const channelName = pick_(row, INFO_VIEWER_ALIASES.channelName);
    const channelUrl = pick_(row, INFO_VIEWER_ALIASES.channelUrl);
    if (!channelName && !channelUrl) return;
    const channel = {
      channelName: channelName || channelUrl,
      channelUrl,
      titleFilter: viewerFlag === '取得' ? '' : viewerFlag,
    };
    if (channelName) channelsByName[normalizeKey_(channelName)] = channel;
    if (channelUrl) channelsByUrl[normalizeKey_(channelUrl)] = channel;
  });

  return videoRows.reduce((result, row) => {
    const videoUrl = normalizeYouTubeUrl_(pick_(row, INFO_VIEWER_ALIASES.videoUrl));
    if (!videoUrl || pick_(row, INFO_VIEWER_ALIASES.exclude)) return result;
    const rowChannelName = pick_(row, INFO_VIEWER_ALIASES.channelName);
    const rowChannelUrl = pick_(row, INFO_VIEWER_ALIASES.channelUrl);
    const channel = channelsByName[normalizeKey_(rowChannelName)] || channelsByUrl[normalizeKey_(rowChannelUrl)];
    if (!channel) return result;

    const title = pick_(row, INFO_VIEWER_ALIASES.videoTitle);
    if (channel.titleFilter && !title.toLocaleLowerCase().includes(channel.titleFilter.toLocaleLowerCase())) {
      return result;
    }

    result.push({
      key: videoUrl,
      rowNumber: row._rowNumber,
      videoUrl,
      title,
      channelName: channel.channelName,
      channelUrl: channel.channelUrl,
      publishedAt: pick_(row, INFO_VIEWER_ALIASES.publishedAt),
      videoUpdatedAt: pick_(row, INFO_VIEWER_ALIASES.videoUpdatedAt),
      status: pick_(row, INFO_VIEWER_ALIASES.status),
    });
    return result;
  }, []);
}

function loadAllVideoUrls_() {
  const spreadsheet = SpreadsheetApp.openById(INFO_VIEWER_CONFIG.spreadsheetId);
  return loadRows_(spreadsheet.getSheetByName(INFO_VIEWER_CONFIG.videoSheetName)).reduce((result, row) => {
    const videoUrl = normalizeYouTubeUrl_(pick_(row, INFO_VIEWER_ALIASES.videoUrl));
    if (!videoUrl) return result;
    result.push({
      key: videoUrl,
      rowNumber: row._rowNumber,
      videoUrl,
    });
    return result;
  }, []);
}

function loadRows_(sheet) {
  if (!sheet) throw new Error('必要なシートが見つかりません。');
  const values = sheet.getDataRange().getDisplayValues();
  if (values.length < 2) return [];
  const headers = values[0];
  return values.slice(1).map((valuesRow, index) => {
    const row = { _rowNumber: index + 2 };
    headers.forEach((header, columnIndex) => {
      row[String(header || '').trim()] = valuesRow[columnIndex];
    });
    return row;
  });
}

function dispatchVideo_(video) {
  const response = UrlFetchApp.fetch(INFO_VIEWER_CONFIG.endpoint, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'x-info-viewer-gas-secret': getRequiredSecret_(),
    },
    payload: JSON.stringify({
      resource: 'priority',
      source: 'gas-sheet-watcher',
      video_url: video.videoUrl,
      title: video.title,
      channelName: video.channelName,
      channelUrl: video.channelUrl,
      publishedAt: video.publishedAt,
      videoUpdatedAt: video.videoUpdatedAt,
      rowNumber: video.rowNumber,
      sheetStatus: video.status,
    }),
    muteHttpExceptions: true,
  });
  const status = response.getResponseCode();
  const text = response.getContentText();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (error) {
    payload = { error: text };
  }
  if (status < 200 || status >= 300 || payload.success === false) {
    throw new Error(`通知に失敗しました: HTTP ${status} ${payload.error || payload.warning || text}`);
  }
  if (!payload.workflowTriggered) {
    throw new Error(payload.warning || 'GitHub Actionsを起動できませんでした。');
  }
  return payload;
}

function isDispatchDue_(record, now) {
  if (!record.nextRetryAt) return true;
  const next = new Date(record.nextRetryAt);
  return Number.isNaN(next.getTime()) || next.getTime() <= now.getTime();
}

function normalizeYouTubeUrl_(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const match = raw.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|shorts\/|live\/))([A-Za-z0-9_-]{6,})/i);
  return match ? `https://www.youtube.com/watch?v=${match[1]}` : raw;
}

function normalizeKey_(value) {
  return String(value || '').trim().replace(/[\s_]+/g, '').toLocaleLowerCase();
}

function pick_(row, aliases) {
  const aliasKeys = new Set(aliases.map(normalizeKey_));
  for (const [key, value] of Object.entries(row)) {
    if (aliasKeys.has(normalizeKey_(key))) return String(value || '').trim();
  }
  return '';
}

function getRequiredSecret_() {
  const secret = PropertiesService.getScriptProperties().getProperty(INFO_VIEWER_CONFIG.secretProperty);
  if (!secret) throw new Error('INFO_VIEWER_GAS_SECRET が未設定です。');
  return secret;
}

function loadState_() {
  const properties = PropertiesService.getScriptProperties().getProperties();
  const raw = properties[INFO_VIEWER_CONFIG.stateProperty];
  let state = { version: 1, installedAt: '', updatedAt: '', videos: {} };
  try {
    if (raw) state = { ...state, ...JSON.parse(raw) };
    state.videos = {};
    Object.entries(properties).forEach(([key, value]) => {
      if (!key.startsWith(INFO_VIEWER_CONFIG.videoPropertyPrefix)) return;
      const record = JSON.parse(value);
      if (record && record.videoUrl) state.videos[record.videoUrl] = record;
    });
    return state;
  } catch (error) {
    throw new Error(`通知状態を読み込めません: ${error.message}`);
  }
}

function saveState_(state) {
  const scriptProperties = PropertiesService.getScriptProperties();
  const existing = scriptProperties.getProperties();
  const nextProperties = {
    [INFO_VIEWER_CONFIG.stateProperty]: JSON.stringify({
      version: state.version || 1,
      installedAt: state.installedAt || '',
      updatedAt: state.updatedAt || '',
    }),
  };

  Object.values(state.videos || {}).forEach((record) => {
    if (!record || !record.videoUrl) return;
    nextProperties[videoPropertyKey_(record.videoUrl)] = JSON.stringify(record);
  });
  scriptProperties.setProperties(nextProperties, false);

  Object.keys(existing)
    .filter((key) => key.startsWith(INFO_VIEWER_CONFIG.videoPropertyPrefix) && !(key in nextProperties))
    .forEach((key) => scriptProperties.deleteProperty(key));
}

function videoPropertyKey_(videoUrl) {
  const digest = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(videoUrl || ''));
  const hex = digest.map((value) => (`0${(value & 0xff).toString(16)}`).slice(-2)).join('');
  return `${INFO_VIEWER_CONFIG.videoPropertyPrefix}${hex}`;
}

function pruneState_(state) {
  const entries = Object.entries(state.videos || {});
  if (entries.length <= INFO_VIEWER_CONFIG.maxStateEntries) return;
  entries.sort((left, right) => {
    const leftTime = Date.parse(left[1].lastSeenAt || left[1].firstSeenAt || '') || 0;
    const rightTime = Date.parse(right[1].lastSeenAt || right[1].firstSeenAt || '') || 0;
    return rightTime - leftTime;
  });
  state.videos = Object.fromEntries(entries.slice(0, INFO_VIEWER_CONFIG.maxStateEntries));
}

function removeDispatcherTriggers_() {
  ScriptApp.getProjectTriggers()
    .filter((trigger) => trigger.getHandlerFunction() === INFO_VIEWER_CONFIG.pollFunction)
    .forEach((trigger) => ScriptApp.deleteTrigger(trigger));
}

function getDispatcherTriggerCount_() {
  return ScriptApp.getProjectTriggers()
    .filter((trigger) => trigger.getHandlerFunction() === INFO_VIEWER_CONFIG.pollFunction)
    .length;
}
