# techreference_info

## 1. 文書の目的
本書は、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\info_viewer` に関する技術メモ、試行錯誤、つまずき、運用ノウハウをまとめた実務向けリファレンスである。

仕様の正本は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\info_viewer\仕様書.md` とし、本書はその裏側にある判断理由を残す。

## 2. 現在の構成要約
### 2.1 viewer 側
主な実装ファイル:

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\public\info_viewer\index.html`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\info-viewer.js`

viewer は `manifest.json` を読み、記事本文は `articleId` 指定で都度取得する。

### 2.2 自動取得側
主な実装ファイル:

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\info_viewer\runner.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\info_viewer\modules\state_store.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\info_viewer\modules\gemini_formatter.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\info_viewer\modules\manifest_builder.py`

### 2.3 workflow 側
主な実装ファイル:

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-queue.yml`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-pipeline.yml`

## 3. 実装フェーズごとの学び
### 3.1 第一弾
第一弾では viewer を先に完成させた。

理由:

- 取得自動化がまだ不安定でも、最終的な見え方を先に固めた方が判断しやすい
- `manifest.json` を中間フォーマットにすると、viewer と pipeline を疎結合にできる

この判断は有効だった。
後から `failures` や `processingLogs` を `manifest.json` に足しても viewer 本体を大きく壊さずに済んだ。

### 3.2 第二弾
第二弾は「配線はできるが、歩留まりが安定しない」段階で止まりやすかった。

詰まりやすかった箇所:

- Apify 取得失敗
- Gemini の 503
- Gemini の 429
- OneDrive 保存
- Sheets 更新

そこで、単なる `None` 返しではなく、各段階が失敗理由を返す形へ揃えた。

### 3.3 第三弾の着手内容
第三弾で先に入れたのは「見た目の検索やソート」ではなく、「自動で記事が出来上がっている体験を支える運用側」である。

先に入れたもの:

- queue state
- schedule 分離
- defer
- retry wait
- Gemini 直列化

後回しにしたもの:

- viewer の検索
- viewer のソート
- 操作 UI の追加

## 4. もっとも大きかった詰まり
### 4.1 Gemini の高負荷と quota
最も大きい詰まりは Gemini である。

実際に出たエラー傾向:

- `503 UNAVAILABLE`
- `429 RESOURCE_EXHAUSTED`
- `500 api_error`
- `too_many_requests`

ここから分かったこと:

- 「一度にたくさん投げる」のではなく「1件終わったら次」にしないと止まりやすい
- 無料枠では 1 run の中で全部終わらせる思想は弱い
- 失敗を次回へ送る設計が必須

### 4.2 旧 fallback 方式の問題
以前は Gemini transport を複数経路で試す作りがあり、失敗時に実質リクエスト数が増えやすかった。

現在の判断:

- 既定 transport は `models.generate_content`
- まず 1 経路に絞る
- quota 到達時は無理に続けない

### 4.3 長文入力問題
文字起こしが長い動画では、入力サイズ由来の失敗も考慮が必要だった。

現在の対策:

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\info_viewer\modules\gemini_formatter.py`
- 45000 文字へトリムした fallback を用意
- 入力制限系エラーのときだけ trimmed variant に進む

## 5. queue 方式へ切り替えた理由
### 5.1 旧 daily 1 回では体験が弱い
旧 `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-pipeline.yml` は 1 日 1 回の schedule だった。

問題:

- Sheets に動画が追加されてもすぐ拾えない
- quota 失敗時の再試行までの待ちが長い
- 自動で増えていく感じが出にくい

### 5.2 sync と process を分けた
そこで、1 本の run で全部やるのをやめ、以下に分割した。

- 30分ごとの `sync_only`
- 1時間ごとの `process_queue`

この分割で良くなった点:

- 新しい動画 URL を先に保持できる
- Gemini が詰まっても収集自体は止まりにくい
- quota 時に backlog を自然に貯められる

### 5.3 state/pipeline_state.json の役割
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\info_viewer\modules\state_store.py` を追加し、`pipeline_state.json` を持つようにした。

これで可能になったこと:

- pending の保持
- retry 時刻の保持
- active / inactive の判定
- done 済みの再判定
- 失敗理由を manifest とは別に持つこと

## 6. 実 run から得た知見
### 6.1 run `24180648716`
用途:

- Gemini 直列化の挙動確認

分かったこと:

- 動画ごとの待機は効いている
- ただし quota 自体は解決しない

### 6.2 run `24182954517`
用途:

- queue workflow 導入後の手動確認

確認できたこと:

- `process_queue` モードで起動
- `scanned=5`
- `added=5`
- `done=1`
- `処理対象件数=2`
- 1 件目で Gemini が `503` と `429`
- 残件が defer へ送られた

この run は「queue と defer の骨格が動いた」確認として重要である。

### 6.3 run `24185904735`
用途:

- schedule 発火確認

確認できたこと:

- event が `schedule`
- 自動収集はもう始まっている

## 7. viewer と pipeline をつなぐ key 設計
### 7.1 URL 正規化
動画対応づけの基準はタイトルではなく URL である。

理由:

- タイトルは後で変わる
- OneDrive のファイル名は短縮される
- YouTube URL は watch / shorts / youtu.be など揺れがある

そのため `normalize_youtube_url` を基準キーにしている。

### 7.2 manifest を中間フォーマットにした理由
viewer が Google Sheets と OneDrive を毎回直接突き合わせるより、pipeline 側で一度 `manifest.json` に整形する方が安定する。

利点:

- viewer が軽い
- failure 情報を一緒に渡せる
- UI 側で「記事なし」や「最終失敗」を出しやすい

## 8. ログの見方
### 8.1 GitHub Actions ログ
まず見る場所:

- `Info Viewer Pipeline` の run log

確認順:

1. `実行モード`
2. `キュー同期`
3. `処理対象件数`
4. `Apify`
5. `Gemini`
6. `OneDrive保存`
7. `状況更新`
8. `処理後キュー状況`

### 8.2 manifest の failure
viewer 側で最終失敗を見るときは `manifest.json` の以下を見ればよい。

- `lastFailureStage`
- `lastFailureMessage`
- `lastFailureAt`

### 8.3 pipeline_state.json
再試行待ちの実体は `pipeline_state.json` 側にある。

重要項目:

- `status`
- `nextRetryAt`
- `attemptCount`
- `lastError`
- `lastStage`

## 9. 現在の不一致と注意点
### 9.1 trigger API は legacy workflow を叩く
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\trigger-info-viewer.js` は、まだ `info-viewer-pipeline.yml` を dispatch している。

つまり現状は以下の二重構造である。

- 定期実行: `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-queue.yml`
- API 手動起動: `C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-pipeline.yml`

これは今後解消すべき技術的負債である。

### 9.2 API 側 default folder と workflow env
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\info-viewer.js` の default folder は旧値を持つ。

一方、queue workflow は以下を使う。

- `Obsidian in Onedrive 202602/Vercel_Blog/情報取得/info_viewer`

そのため、運用上は `INFO_VIEWER_ONEDRIVE_FOLDER` の環境変数 override が正しく入っている前提で整合が取れている。

### 9.3 main.py と runner.py の二段構成
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\info_viewer\main.py` は実体ではなく、`runner.py` を呼ぶ薄い入口である。

注意点:

- 仕様変更は原則 `runner.py` 側で行う
- `main.py` だけ見てロジックを追うと古い実装に見える

### 9.4 OneDrive 上での py_compile
OneDrive 配下では `.pyc` の rename 時にアクセス拒否が出ることがある。

実際に遭遇した症状:

- `py_compile` 実行時に `__pycache__` への rename で `Permission denied`

対処:

- AST parse に切り替える
- または `PYTHONDONTWRITEBYTECODE=1` を使う

## 10. 今後の改善候補
優先度が高いもの:

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\trigger-info-viewer.js` を新 queue workflow 対応へ揃える
- viewer 側の検索
- viewer 側のソート
- `processingLogs` の可視化
- defer 対象の明示表示
- quota 時の待機戦略の最適化

優先度は次点:

- UI 文言の第一弾表記整理
- 失敗理由の分類表示
- queue 状態の操作 UI

## 11. 実務メモ
### 11.1 第二弾の本当の完成条件
第二弾の本当の完成条件は「対象動画が安定して自動記事化される」である。

現状は「配線できた」「viewer で見える」「自動収集が開始した」までは到達しているが、歩留まりの安定はこれから詰める段階である。

### 11.2 第三弾の優先順位
第三弾は UI 追加より運用安定を先に進める方針が妥当である。

現時点の優先順:

1. 差分取得
2. 再処理キュー
3. 夜間を含む定期実行
4. quota 時の自然 defer
5. その後に検索とソート

### 11.3 一言で言うと
現在の `info_viewer` は「viewer は既に使える」「自動収集も始まった」「ただし Gemini の無料枠と高負荷が最後のボトルネック」という状態である。
