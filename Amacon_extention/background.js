// メッセージリスナーを設定
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'updateStorage') {
        // chrome.storage.localにデータを保存
        chrome.storage.local.set(request.data, () => {
            sendResponse({ success: true });
        });
        return true; // 非同期レスポンスを示す
    }
    
    if (request.action === 'getStorage') {
        // chrome.storage.localからデータを取得
        chrome.storage.local.get([request.key], (result) => {
            sendResponse({ value: result[request.key] });
        });
        return true; // 非同期レスポンスを示す
    }
});