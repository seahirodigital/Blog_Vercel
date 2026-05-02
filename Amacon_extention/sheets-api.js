/**
 * Google Sheets API連携モジュール
 */

class GoogleSheetsAPI {
    constructor() {
        this.accessToken = null;
        this.tokenExpiry = null;
    }

    /**
     * 設定情報を取得
     */
    async getConfig() {
        return new Promise((resolve) => {
            chrome.storage.sync.get([
                'sheetsClientId',
                'sheetsClientSecret',
                'spreadsheetUrl',
                'sheetName',
                'sheetsAccessToken',
                'sheetsTokenExpiry'
            ], (result) => {
                resolve(result);
            });
        });
    }

    /**
     * スプレッドシートIDをURLまたはID単体から抽出
     */
    extractSpreadsheetId(url) {
        const value = String(url || '').trim();
        if (/^[a-zA-Z0-9-_]{20,}$/.test(value) && !value.includes('/')) {
            return value;
        }

        const match = value.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
        return match ? match[1] : null;
    }

    buildApiErrorMessage(status, errorText) {
        let errorMessage = `API Error (${status})`;
        try {
            const error = JSON.parse(errorText);
            errorMessage = error.error?.message || errorMessage;
        } catch (e) {
            errorMessage = errorText || errorMessage;
        }

        if (/Office file/i.test(errorMessage)) {
            return '指定先はGoogleスプレッドシートではなくOffice/Excelファイルです。Google Driveで「ファイル > Google スプレッドシートとして保存」または新規Googleスプレッドシートへコピーして、そのURL/IDを設定してください。';
        }

        return errorMessage;
    }

    /**
     * OAuth2認証を実行
     */
    async authenticate() {
        try {
            const config = await this.getConfig();
            config.sheetsClientId = config.sheetsClientId || 'manifest-oauth-client';
            
            if (!config.sheetsClientId) {
                throw new Error('Client IDが設定されていません');
            }

            // Chrome Identity APIを使用してOAuth2認証
            const token = await new Promise((resolve, reject) => {
                chrome.identity.getAuthToken({ interactive: true }, (token) => {
                    if (chrome.runtime.lastError) {
                        reject(chrome.runtime.lastError);
                    } else {
                        resolve(token);
                    }
                });
            });

            this.accessToken = token;
            this.tokenExpiry = Date.now() + (3600 * 1000); // 1時間後

            // トークンを保存
            await new Promise((resolve) => {
                chrome.storage.sync.set({
                    sheetsAccessToken: token,
                    sheetsTokenExpiry: this.tokenExpiry
                }, resolve);
            });

            return true;
        } catch (error) {
            console.error('認証エラー:', error);
            throw error;
        }
    }

    /**
     * アクセストークンを取得（必要に応じて再認証）
     */
    async getAccessToken() {
        const config = await this.getConfig();
        
        // 保存されたトークンをチェック
        if (config.sheetsAccessToken && config.sheetsTokenExpiry) {
            if (Date.now() < config.sheetsTokenExpiry) {
                this.accessToken = config.sheetsAccessToken;
                return this.accessToken;
            }
        }

        // トークンが期限切れまたは存在しない場合は再認証
        await this.authenticate();
        return this.accessToken;
    }

    /**
     * Sheets列名を生成(A, B, ... Z, AA...)
     */
    columnName(index) {
        let name = '';
        let number = index;
        while (number > 0) {
            const mod = (number - 1) % 26;
            name = String.fromCharCode(65 + mod) + name;
            number = Math.floor((number - mod) / 26);
        }
        return name;
    }

    /**
     * ヘッダー定義。AI用の長い行までそのまま入るようV列まで用意する。
     */
    buildHeaders(width = 22) {
        const headers = [
            'カテゴリ',
            'タイトル',
            'Amazon URL',
            'ブランド',
            '製品名',
            '価格',
            '参考価格',
            'レビュー平均',
            'レビュー数',
            '種別',
            '予備1',
            '予備2',
            '予備3',
            '予備4',
            '予備5',
            '予備6',
            '予備7',
            '予備8',
            '予備9',
            '商品情報1',
            '商品情報2',
            '商品情報3'
        ];
        while (headers.length < width) {
            headers.push(`追加列${headers.length + 1}`);
        }
        return headers.slice(0, width);
    }

    normalizeRows(data) {
        return (data || [])
            .filter(row => Array.isArray(row))
            .map(row => row.map(value => value == null ? '' : String(value)));
    }

    /**
     * スプレッドシートにデータを追加
     */
    async appendData(data) {
        try {
            const rows = this.normalizeRows(data);
            if (rows.length === 0) {
                throw new Error('書き込むデータがありません');
            }

            const config = await this.getConfig();
            const spreadsheetId = this.extractSpreadsheetId(config.spreadsheetUrl);

            if (!spreadsheetId) {
                throw new Error('スプレッドシートURLが無効です');
            }

            const sheetName = config.sheetName || 'ブランド製品名仕訳';
            const token = await this.getAccessToken();
            const width = Math.max(22, ...rows.map(row => row.length));
            const endColumn = this.columnName(width);

            await this.ensureHeader(spreadsheetId, sheetName, token, width);

            const range = `'${sheetName}'!A:${endColumn}`;
            const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`;

            console.log('Sheets API URL:', url);
            console.log('データ行数:', rows.length);

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    values: rows
                })
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error('API Error Response:', errorText);
                const errorMessage = this.buildApiErrorMessage(response.status, errorText);
                throw new Error(errorMessage);
            }

            const result = await response.json();
            console.log('Sheets書き込み成功:', result);
            return result;
        } catch (error) {
            console.error('データ追加エラー:', error);
            throw error;
        }
    }

    /**
     * ヘッダー行を確認し、不足列だけ補完する。
     */
    async ensureHeader(spreadsheetId, sheetName, token, width = 22) {
        try {
            const endColumn = this.columnName(width);
            const range = `'${sheetName}'!A1:${endColumn}1`;
            const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}`;

            console.log('ヘッダーチェック URL:', url);

            const response = await fetch(url, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (!response.ok) {
                console.warn('ヘッダーチェック失敗:', response.status);
                await this.addHeader(spreadsheetId, sheetName, token, this.buildHeaders(width));
                return;
            }

            const result = await response.json();
            const current = result.values?.[0] || [];
            const desired = this.buildHeaders(width);
            const merged = desired.map((header, index) => current[index] || header);

            if (current.length === 0 || current.length < width || merged.some((value, index) => value !== current[index])) {
                await this.addHeader(spreadsheetId, sheetName, token, merged);
            }
        } catch (error) {
            console.error('ヘッダー確認エラー:', error);
            await this.addHeader(spreadsheetId, sheetName, token, this.buildHeaders(width));
        }
    }

    /**
     * ヘッダー行を追加/更新
     */
    async addHeader(spreadsheetId, sheetName, token, headers = this.buildHeaders()) {
        try {
            const endColumn = this.columnName(headers.length);
            const range = `'${sheetName}'!A1:${endColumn}1`;
            const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?valueInputOption=RAW`;

            console.log('ヘッダー追加 URL:', url);

            const response = await fetch(url, {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    values: [headers]
                })
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error('ヘッダー追加エラーレスポンス:', errorText);
                throw new Error(this.buildApiErrorMessage(response.status, errorText));
            }

            console.log('ヘッダー追加成功');
        } catch (error) {
            console.error('ヘッダー追加エラー:', error);
            throw error;
        }
    }

    /**
     * 認証状態をクリア
     */
    async clearAuth() {
        try {
            if (this.accessToken) {
                await new Promise((resolve, reject) => {
                    chrome.identity.removeCachedAuthToken(
                        { token: this.accessToken },
                        () => {
                            if (chrome.runtime.lastError) {
                                reject(chrome.runtime.lastError);
                            } else {
                                resolve();
                            }
                        }
                    );
                });
            }

            this.accessToken = null;
            this.tokenExpiry = null;

            await new Promise((resolve) => {
                chrome.storage.sync.remove(['sheetsAccessToken', 'sheetsTokenExpiry'], resolve);
            });
        } catch (error) {
            console.error('認証クリアエラー:', error);
        }
    }
}

// グローバルに公開
window.GoogleSheetsAPI = GoogleSheetsAPI;
