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
     * スプレッドシートIDをURLから抽出
     */
    extractSpreadsheetId(url) {
        const match = url.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
        return match ? match[1] : null;
    }

    /**
     * OAuth2認証を実行
     */
    async authenticate() {
        try {
            const config = await this.getConfig();
            
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
             * スプレッドシートにデータを追加
             */
            async appendData(data) {
                try {
                    const config = await this.getConfig();
                    const spreadsheetId = this.extractSpreadsheetId(config.spreadsheetUrl);
                    
                    if (!spreadsheetId) {
                        throw new Error('スプレッドシートURLが無効です');
                    }

                    const sheetName = config.sheetName || 'ブランド製品名仕訳';
                    const token = await this.getAccessToken();

                    // ヘッダー行をチェック
                    const hasHeader = await this.checkHeader(spreadsheetId, sheetName, token);
                    
                    if (!hasHeader) {
                        // ヘッダーを追加
                        await this.addHeader(spreadsheetId, sheetName, token);
                    }

                    // データを追加
                    // シート名はクエリパラメータではなく、パス内で適切にエンコード
                    const range = `'${sheetName}'!A:J`;  // ★ A:I→A:Jに変更
                    const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`;

                    console.log('Sheets API URL:', url);
                    console.log('データ行数:', data.length);

                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Authorization': `Bearer ${token}`,
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            values: data
                        })
                    });

                    if (!response.ok) {
                        const errorText = await response.text();
                        console.error('API Error Response:', errorText);
                        let errorMessage = `API Error (${response.status})`;
                        try {
                            const error = JSON.parse(errorText);
                            errorMessage = error.error?.message || errorMessage;
                        } catch (e) {
                            errorMessage = errorText || errorMessage;
                        }
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
                 * ヘッダー行の存在をチェック
                 */
                async checkHeader(spreadsheetId, sheetName, token) {
                    try {
                        const range = `'${sheetName}'!A1:J1`;  // ★ I1→J1に変更
                        const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}`;

                        console.log('ヘッダーチェック URL:', url);

                        const response = await fetch(url, {
                            headers: {
                                'Authorization': `Bearer ${token}`
                            }
                        });

                        if (!response.ok) {
                            console.warn('ヘッダーチェック失敗:', response.status);
                            return false;
                        }

                        const result = await response.json();
                        return result.values && result.values.length > 0;
                    } catch (error) {
                        console.error('ヘッダーチェックエラー:', error);
                        return false;
                    }
                }

                /**
                 * ヘッダー行を追加
                 */
                async addHeader(spreadsheetId, sheetName, token) {
                    try {
                        // ★ HTML列を追加
                        const headers = [['カテゴリ', 'タイトル', 'Amazon URL', 'ブランド', '製品名', '価格', '参考価格', 'レビュー平均', 'レビュー数', 'HTML']];
                        const range = `'${sheetName}'!A1:J1`;  // ★ I1→J1に変更
                        const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?valueInputOption=RAW`;

                        console.log('ヘッダー追加 URL:', url);

                        const response = await fetch(url, {
                            method: 'PUT',
                            headers: {
                                'Authorization': `Bearer ${token}`,
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                values: headers
                            })
                        });

                        if (!response.ok) {
                            const errorText = await response.text();
                            console.error('ヘッダー追加エラーレスポンス:', errorText);
                            throw new Error(`ヘッダー追加に失敗しました (${response.status}): ${errorText}`);
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