# note 画像アップロード総合リファレンス

## 目的

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py` の既存下書き生成工程を活かしつつ、note の記事画像を安定して下書き保存するための実測結果を残す。

このメモは 2026-04-08 時点の検証結果であり、成功条件は「画像アップロード後に再読み込みしても画像が残っていること」とする。


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
- `controls_after.json`
- `controls_after_insert.json`
- `before_upload.png`
- `before_upload.html`
- `after_upload.png`
- `after_upload.html`
- `after_save.png`
- `after_save.html`

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
3. トップ画像アイコンを押す
4. `画像をアップロード` を押す
5. `C:\Users\HCY\Downloads\Image_fx.png` を選択する
6. 画像トリミング系ポップアップの `保存` を押す
7. エディタ上部の `下書き保存` を押す
8. ページを再読み込みする
9. `img` 要素が 1 件以上あることを確認する

## 初期調査で分かったこと

初期フェーズでは次を確認した。

1. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py` の API 下書き作成フローは、画像追加テストのベースとして再利用しやすい
2. `https://editor.note.com/notes/new` の直接オープンは `AccessDenied` になった
3. 初回の失敗要因は認証切れとプロキシ継承にあった
4. 認証更新後は、既存の `_create_draft_api()` を使えば edit URL を安定して取得できた

つまり、初期のボトルネックは画像アップロード以前に認証と入口選定だったが、最終的には解消済みである

## なぜ既存工程を活かしたか

理由は単純で、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\note_draft_poster.py` は次の重要部分を既に持っていたから。

- Cookie を読み込んで note セッションを引き継ぐ
- `POST /api/v1/text_notes` で下書きの骨組みを作る
- `POST /api/v1/text_notes/draft_save?id={id}&is_temp_saved=true` で本文を保存する
- 最後に `https://editor.note.com/notes/{key}/edit/` を返せる

つまり、画像アップロードだけを追加すればよく、`https://editor.note.com/notes/new` を無理に開く必要がなかった。

実際に `https://editor.note.com/notes/new` はこの環境で `AccessDenied` だったため、新規作成ページ直叩きより既存下書き URL を使う方が正攻法だった。

## なぜ座標ベースで実施したか

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

- 下書き URL: `https://editor.note.com/notes/na8ef5750a583/edit/`
- `IMG_COUNT_BEFORE=0`
- ポップアップ `保存` 実行後、その場の `IMG_COUNT_AFTER_POPUP_SAVE=0`
- 上部 `下書き保存` 実行後に再読み込み
- `IMG_COUNT_AFTER_RELOAD=1`

この結果により、保存成功は確認済み。
