const GITHUB_API = 'https://api.github.com';
const SECRET_NAME = 'ONEDRIVE_REFRESH_TOKEN';
const DEFAULT_REPOSITORY = 'seahirodigital/Blog_Vercel';
const SYNC_INTERVAL_MS = 10 * 60 * 1000;

let lastSyncedAt = 0;
let lastSyncedToken = '';

async function loadSodium() {
  const sodiumModule = await import('libsodium-wrappers');
  const sodium = sodiumModule.default || sodiumModule;
  await sodium.ready;
  return sodium;
}

function getGitHubToken() {
  return process.env.GITHUB_TOKEN || process.env.GH_PAT || '';
}

function getGitHubRepository() {
  return process.env.GITHUB_REPOSITORY || process.env.GITHUB_REPO || DEFAULT_REPOSITORY;
}

function shouldSkipSync(refreshToken, force) {
  if (force) return false;
  if (refreshToken !== lastSyncedToken) return false;
  return Date.now() - lastSyncedAt < SYNC_INTERVAL_MS;
}

async function encryptSecret(publicKey, value) {
  const sodium = await loadSodium();
  const keyBytes = sodium.from_base64(publicKey, sodium.base64_variants.ORIGINAL);
  const valueBytes = sodium.from_string(value);
  const encryptedBytes = sodium.crypto_box_seal(valueBytes, keyBytes);
  return sodium.to_base64(encryptedBytes, sodium.base64_variants.ORIGINAL);
}

export async function syncGitHubActionsRefreshToken(refreshToken, options = {}) {
  const tokenValue = String(refreshToken || '').trim();
  if (!tokenValue) return false;

  if (shouldSkipSync(tokenValue, Boolean(options.force))) {
    return true;
  }

  const githubToken = getGitHubToken();
  if (!githubToken) {
    console.warn('GITHUB_TOKEN/GH_PAT が未設定のため、GitHub Actions Secret の同期をスキップします');
    return false;
  }

  try {
    const repository = getGitHubRepository();
    const headers = {
      Authorization: `Bearer ${githubToken}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    };

    const keyRes = await fetch(`${GITHUB_API}/repos/${repository}/actions/secrets/public-key`, {
      headers,
    });
    if (!keyRes.ok) {
      console.warn('GitHub Actions Secret 公開鍵取得失敗:', keyRes.status, await keyRes.text());
      return false;
    }

    const keyData = await keyRes.json();
    const encryptedValue = await encryptSecret(keyData.key, tokenValue);
    const updateRes = await fetch(`${GITHUB_API}/repos/${repository}/actions/secrets/${SECRET_NAME}`, {
      method: 'PUT',
      headers: {
        ...headers,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        encrypted_value: encryptedValue,
        key_id: keyData.key_id,
      }),
    });

    if (!updateRes.ok) {
      console.warn('GitHub Actions Secret 更新失敗:', updateRes.status, await updateRes.text());
      return false;
    }

    lastSyncedAt = Date.now();
    lastSyncedToken = tokenValue;
    console.log('✅ OneDrive refresh token をGitHub Actions Secretへ同期しました');
    return true;
  } catch (error) {
    console.warn('GitHub Actions Secret 同期エラー:', error.message);
    return false;
  }
}
