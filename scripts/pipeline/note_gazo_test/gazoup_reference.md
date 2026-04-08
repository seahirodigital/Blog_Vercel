# note 画像アップロード総合リファレンス

## 目的

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py` の既存下書き生成工程を活かしつつ、note の記事画像を安定して下書き保存するための実測結果を残す。

このメモは 2026-04-08 時点の検証結果であり、成功条件は「画像アップロード後に再読み込みしても画像が残っていること」とする。

## 最新結論

2026-04-08 の最新成功系は ver2.0 で、座標固定ではなく DOM ベースで通せた。

- 下書き作成は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py` の既存 API フローを使う
- トップ画像追加は `button[aria-label="画像を追加"]` を押す
- 画像選択は `画像をアップロード` のテキスト導線から `expect_file_chooser()` と `set_files()` で通す
- 画像トリミング確定は `div.ReactModal__Content.CropModal__content[role="dialog"][aria-modal="true"]` 配下の `保存` を押す
- その直後に保存しない
- 先にトップ画像エリアのローディング完了を待ち、`main img` が増えたことを確認してから上部 `下書き保存` を押す
- 最後に再読み込みし、`main img` が残っていることを確認する


## 主要ファイル

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_gazo_test\gazoup_reference.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_gazo_test\note_image_draft_test.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_gazo_test\artifacts\`

## 実行例

既定本文で実行する場合:

```powershell
python "C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_gazo_test\note_image_draft_test.py"
```

認証が切れている場合:

```powershell
python -X utf8 "C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py" --save-cookies
```

本文を差し替える場合:

```powershell
python "C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_gazo_test\note_image_draft_test.py" `
  --markdown-path "C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\sample.md"
```

画像を差し替える場合:

```powershell
python "C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_gazo_test\note_image_draft_test.py" `
  --image-path "C:\Users\HCY\Downloads\Image_fx.png"
```

## 出力物

実行後は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_gazo_test\artifacts\` に次を保存する。

- `run_report.json`
- `controls_before.json`
- `controls_after_menu.json`
- `controls_after_popup_save.json`
- `before_upload.png`
- `before_upload.html`
- `after_menu_open.png`
- `after_menu_open.html`
- `crop_modal_open.png`
- `crop_modal_open.html`
- `after_popup_save.png`
- `after_popup_save.html`
- `after_upload_ready.png`
- `after_upload_ready.html`
- `after_draft_save.png`
- `after_draft_save.html`
- `after_reload.png`
- `after_reload.html`

## 既定本文

旧 `sample_note_image.md` の内容は、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_gazo_test\note_image_draft_test.py` の内蔵既定本文へ移した。

既定本文の趣旨は次の通り。

- `C:\Users\HCY\Downloads\Image_fx.png` を note エディタへ追加できるかを確認する
- 既存の API 下書き作成フローを使う
- 画像は note エディタの UI から追加する
- 保存の成否は再読み込み後の画像残存で確認する

## 結論

2026-04-08 時点では、最も安定した流れは次の通りだった。

1. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py` の既存工程で下書き URL を作る
2. その `https://editor.note.com/notes/{key}/edit/` を Playwright で開く
3. `button[aria-label="画像を追加"]` を押す
4. `画像をアップロード` の導線を押し、`C:\Users\HCY\Downloads\Image_fx.png` を `expect_file_chooser()` と `set_files()` で渡す
5. `div.ReactModal__Content.CropModal__content[role="dialog"][aria-modal="true"]` 配下の `保存` を押す
6. トップ画像エリアがローディング中の 3 点表示から抜け、`main img` が増えるまで待つ
7. その後にエディタ上部の `下書き保存` を押す
8. ページを再読み込みする
9. `main img` が 1 件以上あることを確認する

## 初期調査で分かったこと

初期フェーズでは次を確認した。

1. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py` の API 下書き作成フローは、画像追加テストのベースとして再利用しやすい
2. `https://editor.note.com/notes/new` の直接オープンは `AccessDenied` になった
3. 初回の失敗要因は認証切れとプロキシ継承にあった
4. `note_draft_poster.py` の `_verify_session()` は false を返しても、実際の `_create_draft_api()` は成功するケースがあった
5. そのため ver2.0 では、検証 API の結果だけで止めず、まず実際の下書き作成を試すようにした

つまり、初期のボトルネックは画像アップロード以前に認証と入口選定だったが、最終的には解消済みである

## なぜ既存工程を活かしたか

理由は単純で、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py` は次の重要部分を既に持っていたから。

- Cookie を読み込んで note セッションを引き継ぐ
- `POST /api/v1/text_notes` で下書きの骨組みを作る
- `POST /api/v1/text_notes/draft_save?id={id}&is_temp_saved=true` で本文を保存する
- 最後に `https://editor.note.com/notes/{key}/edit/` を返せる

つまり、画像アップロードだけを追加すればよく、`https://editor.note.com/notes/new` を無理に開く必要がなかった。

実際に `https://editor.note.com/notes/new` はこの環境で `AccessDenied` だったため、新規作成ページ直叩きより既存下書き URL を使う方が正攻法だった。

## ver2.0 のDOMセレクタ方針

ver2.0 では、2026-04-08 に取得した次の HTML を根拠に、明示的な DOM セレクタで処理する。

- 参考スクリーンショット:
  `C:\Users\HCY\Pictures\Screenshots\スクリーンショット 2026-04-08 155953.png`
- 参考スクリーンショット:
  `C:\Users\HCY\Pictures\Screenshots\スクリーンショット 2026-04-08 160430.png`

採用した主セレクタ:

- トップ画像追加:
  `button[aria-label="画像を追加"]`
- 画像アップロード導線:
  `text=画像をアップロード`
- トリミングモーダル:
  `div.ReactModal__Content.CropModal__content[role="dialog"][aria-modal="true"]`
- トリミングモーダル内保存:
  上記 dialog 配下の `get_by_role("button", name="保存")`
- 上部下書き保存:
  `get_by_role("button", name="下書き保存")`
- 保存判定:
  `main img`

使わない方がよいもの:

- `id=":rj:"` や `id=":rk:"` のような React の動的 ID
- 単純な固定座標

追加で必要だった待機:

- モーダル内 `保存` の直後は、トップ画像エリアが即画像化せず、3 点ローディングになる
- この段階で `下書き保存` すると、画像が draft に残らないことがある
- そのため ver2.0 では、`main img` が増えるまで待ってから `下書き保存` を押す

## なぜ座標ベースで実施したか

この節は v1.0 の試行錯誤ログであり、最新版の推奨ではない。

セレクタ方式だけで最後まで通そうとすると、今回の note UI では不安定だったため。

### 不安定だった理由

- 画面上に見えているのに `get_by_role(..., name=...)` がタイムアウトする場面があった
- `画像を追加` や `下書き保存` のような日本語ラベルが、Playwright 側では文字化けしたり strict 判定で落ちることがあった
- トップ画像まわりの UI は、通常の本文ツールバーと別レイヤーで出ており、ポップアップ要素が動的に差し込まれていた
- `保存` ボタンは画像アップロード後のモーダル内にあり、同名ボタンの誤検出や可視状態判定のぶれが起きた

### 座標ベースが有効だった理由

- 同一セッションで同じ viewport を使うと、トップ画像 UI の表示位置がほぼ固定だった
- 実際にボタン一覧と座標を取得した結果、クリック位置を固定すれば期待通りの UI が開いた
- 画像アップロード後の `保存` も、モーダル右下の座標を押すことで意図したボタンに届いた

要するに、DOM 上では不安定でも、見た目の位置は安定していたため、今回は座標方式が最も再現性が高かった。

## 成功した実測値

前提:

- viewport: `1440 x 1100`
- locale: `ja-JP`
- ログイン済み Cookie: `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_storage_state.json`
- 画像: `C:\Users\HCY\Downloads\Image_fx.png`

成功時に使った暫定座標:

1. トップ画像アイコン: `x=520, y=125`
2. `画像をアップロード`: `x=650, y=180`
3. ポップアップ内 `保存`: `x=1030, y=844`
4. 上部 `下書き保存`: `x=1270, y=25`

注意:

- これは 2026-04-08 時点の実測値で、ブラウザ倍率、左サイドバー状態、viewport が変わるとズレる可能性がある
- 再利用時は毎回 viewport を固定すること

## 実際に成功した処理順

1. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py` の `_create_draft_api()` で下書きを作る
2. 返却された `editor_url` を Playwright で開く
3. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py` の `_wait_for_editor_content()` で本文ロード完了まで待つ
4. `img` の初期数を数える
5. `x=520, y=125` をクリックしてトップ画像アイコンを押す
6. `x=650, y=180` をクリックして `画像をアップロード` を押す
7. `page.expect_file_chooser()` でファイルダイアログを待ち、`C:\Users\HCY\Downloads\Image_fx.png` を渡す
8. 画像トリミング用ポップアップが出た後、`x=1030, y=844` をクリックしてモーダル内 `保存` を押す
9. `x=1270, y=25` をクリックして上部の `下書き保存` を押す
10. 十分に待機してからページを再読み込みする
11. 再読み込み後の `img` 数が `1` 以上であることを確認する

## 試行錯誤の結果

### 失敗した試行 1

`https://editor.note.com/notes/new` を直接開く方式。

結果:

- `AccessDenied` で失敗

判断:

- 新規ページ直叩きは使わない
- 既存の下書き生成 API フローを使う

### 失敗した試行 2

画像アップロード後に `Ctrl+S` だけで保存する方式。

結果:

- 画像が残らないケースがあった

原因:

- 画像アップロード後に別モーダルの `保存` が必要だった
- `Ctrl+S` はエディタ全体の保存要求であり、画像トリミングポップアップの確定にはならなかった

### 失敗した試行 3

`下書き保存` を 2 回押す方式。

結果:

- 画像が保存されない

原因:

- 画像モーダル内の `保存` が抜けていた

### 失敗した試行 4

`get_by_role('button', name='画像を追加')` や `get_by_text('画像をアップロード')` のようなテキストセレクタ中心の方式。

結果:

- 可視なのにタイムアウトする
- 取得できる回とできない回がある

原因:

- 動的 DOM
- ラベル解決のぶれ
- 日本語文字列の扱いと strict マッチの不安定さ

### 失敗した試行 5

DOM ベースで `保存` までは押せているのに、その直後にすぐ `下書き保存` した方式。

結果:

- 再読み込み後に画像が残らなかった

原因:

- モーダル内 `保存` の直後は、トップ画像エリアが即画像化されず、3 点ローディング表示になっていた
- その段階ではまだアップロード完了前で、`下書き保存` が早すぎた

改善:

- `main img` が増えるまで待ってから `下書き保存` を押す

### 成功した試行

座標ベースで

1. トップ画像アイコン
2. `画像をアップロード`
3. ポップアップ内 `保存`
4. 上部 `下書き保存`

の順に押し、最後に再読み込み後の `img` 数で確認する方式。

## 重要な観察

- ポップアップ保存直後は `img` 数が `0` のまま見えることがあった
- しかし `下書き保存` 後に再読み込みすると `img` 数が `1` になった

このため、途中の見た目だけで保存成否を判定してはいけない。

成功判定は必ず次にすること。

1. 上部の `下書き保存` を押す
2. ページを再読み込みする
3. `img` 数が増えているか確認する

## 今後の安定化指針

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py` は既存の下書き生成専用として触らない
- 画像追加は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_gazo_test\` 側で独立実装する
- viewport を毎回固定する
- ボタン文言ベースのセレクタは補助扱いにして、最終手段として座標クリックを残す
- 成功判定は「再読み込み後に画像が残ること」に固定する

## 2026-04-08 時点の最終成功ログ要約

ver2.0 の headless 実行で、DOM ベースでも保存成功を確認した。

- 下書き URL: `https://editor.note.com/notes/n0526d6251980/edit/`
- `before_image_count=0`
- `image_button_strategy=button[aria-label='画像を追加']#0`
- `upload_entry_strategy=text=画像をアップロード#0:filechooser`
- `crop_dialog_strategy=CropModal__content#0`
- `popup_save_strategy=CropModal__content#0->role_button_保存#0`
- `ready_wait_strategy=main_img_detected`
- `after_ready_image_count=1`
- `draft_save_strategy=role_button_下書き保存#0`
- `after_reload_image_count=1`

この結果により、ver2.0 の DOM ベース保存は確認済み。

## Amazon トップ画像取得メモ

### 目的

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\amazon_gazo_get.py` を使い、Amazon 商品検索のトップに出る画像を再現性高く取得する。

要件は次の2段構えとする。

1. Creator API から通常版画像を必ず 1 枚保存する
2. 商品詳細ページから高画質版を取得できた場合は `_hires` 付きでもう 1 枚保存する

### 対象ファイル

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\amazon_gazo_get.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\onedrive_sync.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_gazo_test\gazoup_reference.md`

### 最新結論

2026-04-08 時点では、Amazon Creator API の `Images.Primary.Large` は実測で 500px 級までだった。

- `Images.Primary.Small` は `75x75`
- `Images.Primary.Medium` は `160x160`
- `Images.Primary.Large` は `500x500`
- `Images.Variants.Large` も同様に `500x500`

そのため、通常版は Creator API で取得しつつ、高画質が必要な場合は商品詳細ページの DOM から `hiRes` を抽出する方針が有効だった。

### 保存先

ローカル既定保存先:

- `C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\ダウンロード_トップ画像_vercel_blog`

GitHub Actions 実行時:

- 1 次保存は `%RUNNER_TEMP%\amazon_top_images`
- その後 OneDrive API で `Vercel_Blog/ダウンロード_トップ画像_vercel_blog` へアップロード
- アップロード後は一時ファイルを削除

補足:

- GitHub Actions からローカルの `C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\ダウンロード_トップ画像_vercel_blog` は直接読めない
- そのため、Actions では Microsoft Graph API 経由で OneDrive へ退避する
- ローカル実行時は OneDrive 同期フォルダへ直接保存する

### 保存名ルール

- 通常版: `YYYYMMDD_検索キーワード.jpg`
- 高画質版: `YYYYMMDD_検索キーワード_hires.jpg`

例:

- `20260408_macbook neo.jpg`
- `20260408_macbook neo_hires.jpg`

### 実行例

```powershell
python -X utf8 "C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\amazon_gazo_get.py" "macbook neo"
```

保存先を明示したい場合:

```powershell
python -X utf8 "C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\amazon_gazo_get.py" "macbook neo" `
  --output-dir "C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\ダウンロード_トップ画像_vercel_blog"
```

### 実装ルール

#### 通常版

- Creator API の `SearchItems` を使い、検索 1 位商品の `images.primary.large` を取得する
- 通常版は必ず保存する
- 保存に成功したらこれを基準画像とする

#### 高画質版

商品詳細ページの HTML から、次の優先順で高画質 URL を探す。

1. `img#landingImage` の `data-old-hires`
2. `colorImages': { 'initial': [ { "hiRes": ... } ] }` の最初の `hiRes`

今回の検証では、添付の DOM にある次の属性が有効だった。

- `img#landingImage[data-old-hires]`
- `data-a-dynamic-image`
- `colorImages.initial[0].hiRes`

高画質 URL が取れた場合だけ `_hires` 付きで追加保存する。

### なぜこの DOM を使うか

単純に `Creator API` の `large` を使うだけだと画素が粗かったため。

実測では次を確認した。

- Creator API 返却 URL:
  `https://m.media-amazon.com/images/I/31oNas-CQFL._SL500_.jpg`
- 実サイズ:
  `500x500`
- `_SL1000_` や `_SL3000_` に書き換えても実体は `500x500` のままだった

一方、商品詳細ページでは次のような別 URL が埋まっていた。

- `https://m.media-amazon.com/images/I/61CNt9U8c0L._AC_SL1500_.jpg`

この URL は実測で `1500x916` だったため、高画質版として採用した。

### 2026-04-08 の `macbook neo` 実測結果

検索キーワード:

- `macbook neo`

検索 1 位:

- ASIN: `B0GR698XPH`
- タイトル: `Apple 2026 MacBook Neo A18 Proチップ搭載13インチノートブック：AIとApple Intelligenceのために設計、Liquid Retinaディスプレイ、8GBユニファイドメモリ、256GB SSDストレージ、1080p FaceTime HDカメラ - シトラス`

保存結果:

- 通常版:
  `C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\ダウンロード_トップ画像_vercel_blog\20260408_macbook neo.jpg`
- 通常版サイズ:
  `500x500`
- 通常版バイト数:
  `11181`
- 高画質版:
  `C:\Users\HCY\OneDrive\Obsidian in Onedrive 202602\Vercel_Blog\ダウンロード_トップ画像_vercel_blog\20260408_macbook neo_hires.jpg`
- 高画質版サイズ:
  `1500x916`
- 高画質版バイト数:
  `66614`

### 再現手順

1. `AMAZON_CLIENT_ID` と `AMAZON_CLIENT_SECRET` を User 環境変数または GitHub Actions Secrets に設定する
2. ローカル実行時は OneDrive 同期フォルダが存在することを確認する
3. `amazon_gazo_get.py` を検索キーワード付きで実行する
4. 通常版が必ず 1 枚保存されることを確認する
5. `_hires` 付き画像が追加保存されることを確認する
6. 必要なら画像サイズを確認し、通常版より高画質になっていることを確認する

### GitHub Actions 運用メモ

- `GITHUB_ACTIONS=true` かつ `RUNNER_TEMP` がある場合は、一時ディレクトリへ保存する
- OneDrive へのアップロードは `ONEDRIVE_CLIENT_ID`、`ONEDRIVE_CLIENT_SECRET`、`ONEDRIVE_REFRESH_TOKEN` を使う
- アップロード後は一時ファイルを削除する
- step output には通常版と高画質版のパスと URL を書き出す

### 既知の注意点

- `hiRes` は商品ページ DOM 依存なので、Amazon 側の HTML 構造変更には弱い
- そのため、通常版は必ず Creator API から取得する設計を維持する
- 高画質版が見つからない場合でも処理全体は失敗扱いにしない
- 高画質版の取得可否は商品によって差がある可能性がある

### push 済みコミット

- `0167e18`
- メッセージ: `Add Amazon top image hi-res fallback downloader`
