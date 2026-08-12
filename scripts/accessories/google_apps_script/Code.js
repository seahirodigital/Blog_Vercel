const TARGET_SPREADSHEET_ID = '1ioLnPe9z6vO0tuN3I_qcDi6buS8GCaYowbjq8LTOT94';

const REQUIRED_HEADERS = {
  '周辺機器DB': [
    '親製品検出キーワード', '周辺機器カテゴリID', '周辺機器カテゴリ名', 'タイトル形式',
    'アフィリエイトセクション', 'デフォルト有効', '使用テンプレートファイル', '表示優先度',
  ],
  '周辺機器DB_LLM': [
    '作成日時', '完了日時', '記事タイトル', '進捗', '記事URLリンク', '大元記事タイトル',
    '大元記事リンク', '対象周辺機器', '生成エンジン', 'エラー概要', 'ジョブID', 'バッチID',
  ],
};

// 空の先頭セルだけを補い、既存ヘッダーと衝突する場合は書き込まない。
function ensureAccessoryHeaders() {
  const spreadsheet = SpreadsheetApp.openById(TARGET_SPREADSHEET_ID);
  const plans = Object.entries(REQUIRED_HEADERS).map(([sheetName, required]) => {
    const sheet = spreadsheet.getSheetByName(sheetName);
    if (!sheet) throw new Error(`必要なタブが存在しません: ${sheetName}`);
    const existing = sheet.getRange(1, 1, 1, required.length).getDisplayValues()[0];
    const conflicts = existing
      .map((value, index) => ({ column: index + 1, value, required: required[index] }))
      .filter((item) => item.value !== '' && item.value !== item.required);
    if (conflicts.length) throw new Error(`${sheetName}の先頭行に衝突があります: ${JSON.stringify(conflicts)}`);
    return { sheet, sheetName, required, existing };
  });
  const results = plans.map(({ sheet, sheetName, required, existing }) => {
    const updated = existing.map((value, index) => value || required[index]);
    sheet.getRange(1, 1, 1, required.length).setValues([updated]);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, required.length)
      .setFontWeight('bold').setBackground('#1f4e78').setFontColor('#ffffff').setWrap(true);
    if (sheet.getMaxRows() > 1 && sheetName === '周辺機器DB') {
      const booleanValidation = SpreadsheetApp.newDataValidation()
        .requireValueInList(['TRUE', 'FALSE'], true).setAllowInvalid(false).build();
      sheet.getRange(2, 6, sheet.getMaxRows() - 1, 1).setDataValidation(booleanValidation);
    }
    if (sheet.getMaxRows() > 1 && sheetName === '周辺機器DB_LLM') {
      const statusValidation = SpreadsheetApp.newDataValidation()
        .requireValueInList(['記事化', '失敗', '完了'], true).setAllowInvalid(false).build();
      const engineValidation = SpreadsheetApp.newDataValidation()
        .requireValueInList(['MLX', 'Gemini'], true).setAllowInvalid(false).build();
      sheet.getRange(2, 4, sheet.getMaxRows() - 1, 1).setDataValidation(statusValidation);
      sheet.getRange(2, 9, sheet.getMaxRows() - 1, 1).setDataValidation(engineValidation);
    }
    return { sheetName, headers: updated };
  });
  SpreadsheetApp.flush();
  return results;
}

// 初期3カテゴリだけを追加し、同じカテゴリIDがある既存行は上書きしない。
function seedAccessoryCategories() {
  ensureAccessoryHeaders();
  const spreadsheet = SpreadsheetApp.openById(TARGET_SPREADSHEET_ID);
  const sheet = spreadsheet.getSheetByName('周辺機器DB');
  const keywords = 'iPhone、iPad、MacBook、スマートフォン、タブレット、ノートパソコン、USB-C';
  const initialRows = [
    [keywords, 'battery', 'バッテリー', '製品名 バッテリーおすすめ：', 'battery', true, 'tpl_default.md', 10],
    [keywords, 'adapter', 'アダプター', '製品名 アダプターおすすめ：', 'adapter', true, 'tpl_default.md', 20],
    [keywords, 'cable', 'ケーブル', '製品名 ケーブルおすすめ：', 'cable', true, 'tpl_default.md', 30],
  ];
  const existingIds = new Set(
    sheet.getLastRow() > 1
      ? sheet.getRange(2, 2, sheet.getLastRow() - 1, 1).getDisplayValues().flat().filter(Boolean)
      : []
  );
  const added = initialRows.filter((row) => !existingIds.has(row[1]));
  if (added.length) {
    sheet.getRange(sheet.getLastRow() + 1, 1, added.length, REQUIRED_HEADERS['周辺機器DB'].length).setValues(added);
  }
  sheet.autoResizeColumns(1, REQUIRED_HEADERS['周辺機器DB'].length);
  SpreadsheetApp.flush();
  return {
    addedCategoryIds: added.map((row) => row[1]),
    skippedCategoryIds: initialRows.filter((row) => existingIds.has(row[1])).map((row) => row[1]),
  };
}
