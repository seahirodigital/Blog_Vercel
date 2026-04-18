# techreference_info

## 1. この文書の目的
この文書は、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\info_viewer` に関する実装メモです。  
特に 2026-04-16 の調査で判明した「見かけ上は成功しているのに viewer に記事が出ない」問題について、次に同じところでつまずかないための知見をまとめます。

この文書は仕様書ではなく、以下を残すための技術メモです。

- 誤解しやすかったポイント
- 実際の原因
- 調査の順番
- 再発防止のための確認観点

正式な最終仕様は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\info_viewer\仕様書.md` を参照してください。

## 2. 今回の事象
### 2.1 見えていた症状
GitHub Actions の実行結果では success に見えるにもかかわらず、viewer に新しい記事が出てこない状態が発生した。  
実行ログには次のような表示があった。

- `実行モード: sync_only`
- `Sheets 差分取得とキュー同期のみ実行しました。`
- `成功: 0件`
- `失敗: 0件`

このログだけを見ると「Apify も Gemini も動いていない」「処理が壊れている」と見えやすい。

### 2.2 実際に起きていたこと
問題は 1 つではなく、次の 2 層に分かれていた。

1. 直近 run が `sync_only` だったため、そもそも Gemini を実行しない run を見ていた
2. workflow の出力先と viewer / API の参照先がずれており、処理されていても新記事が viewer に出なかった

## 3. 最重要の学び
### 3.1 `success` は「記事生成成功」を意味しない
`info_viewer` の workflow では、`sync_only` でも正常終了する。  
つまり Actions の緑色の success は「ジョブが壊れず終わった」ことしか保証しない。

記事生成が実際に行われたかは、必ず以下を確認する。

- `実行モード`
- `処理対象件数`
- `Apify で文字起こし取得`
- `Gemini candidate`
- `成功: N件`
- `失敗: N件`

### 3.2 `sync_only` は仕様どおり Gemini を動かさない
`sync_only` は以下だけを行う。

- Google Sheets の差分取得
- キュー同期
- `pipeline_state.json` 更新
- `manifest.json` 再生成

以下は行わない。

- Apify による文字起こし取得
- Gemini による Markdown 整形
- 新規記事ファイルの生成

そのため、`sync_only` の run を見て「Gemini が走っていない」と判断してはいけない。

### 3.3 `process_queue` で初めて記事生成が動く
記事生成を確認したい場合は、`process_queue` の run を見る。  
1件だけ強制検証したい場合は、`video_url` を指定した `workflow_dispatch` が最も確実。

## 4. 今回の本当の原因
### 4.1 OneDrive 保存先の不一致
workflow 側が旧保存先に書き込み、viewer / API 側は新保存先を参照していた。

旧保存先:

- `Obsidian in Onedrive 202602/Vercel_Blog/情報取得/info_viewer`

正しい保存先:

- `Obsidian in Onedrive 202602/Vercel_Blog/info_viewer`

このズレにより、Apify / Gemini が成功しても viewer 側には反映されないことがあった。

### 4.2 API が「最初に見つかった manifest」を拾っていた
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\info-viewer.js` は、候補フォルダの中から最初に見つかった `manifest.json` / `pipeline_state.json` を使う実装だった。  
新旧フォルダが共存していると、古い manifest を拾う可能性があった。

結果として、

- 実ファイルは新しい
- viewer は古い manifest を見ている

という不整合が起きえた。

### 4.3 Gemini の一時障害時フォールバック不足
修正後の再検証で、Gemini が `503 UNAVAILABLE` を返した際に、次の候補キーへ即時フォールバックせず failure 扱いになる箇所が見つかった。  
このため、一時的な Gemini 側障害がそのまま記事生成失敗になっていた。

## 5. 修正内容
### 5.1 workflow の保存先統一
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-queue.yml` の
`INFO_VIEWER_ONEDRIVE_FOLDER` を新保存先へ統一した。

正:

- `Obsidian in Onedrive 202602/Vercel_Blog/info_viewer`

### 5.2 API の manifest / state 選択ロジック修正
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\api\info-viewer.js` を修正し、候補の中から
「最初に見つかったもの」ではなく「最新日時のもの」を選ぶようにした。

評価の基準:

- `generatedAt`
- `updatedAt`
- `runId`

これにより、新旧フォルダが残っていても最新成果物を優先できる。

### 5.3 Gemini retryable エラー時のフォールバック追加
以下を修正した。

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\info_viewer\modules\gemini_formatter.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\info_viewer\runner.py`

対応内容:

- `503`
- `429`
- 一部の transport エラー

これらを retryable error として判定し、次の Gemini 候補キーへ進めるようにした。

## 6. 調査時につまずいたポイント
### 6.1 直近 run だけを見ると誤判定しやすい
今回の最初の誤解はここだった。  
`schedule` の最新 run が `sync_only` で正常終了していたため、
「Gemini が全く実行されていない」と見えてしまった。

対策:

- 直近 run だけでなく、同日の `process_queue` run も確認する
- `event=schedule` だけでなく `workflow_dispatch` も確認する
- run ID 単位で `mode` を必ず読む

### 6.2 queue 状態を見ずに「なぜ処理されない」を考えてしまいがち
`process_queue` を実行しても、必ずその場で記事生成されるとは限らない。  
`nextRetryAt` が未来時刻の場合、対象は `deferred` のままで、その run では処理されない。

対策:

- `pipeline_state.json` の `status` を見る
- `nextRetryAt` を見る
- `queueable=0` / `deferred` を読む

### 6.3 failure と quota defer は意味が違う
Gemini の `429` や quota 制限時は、「壊れた」のではなく「待てば再開できる」状態である。  
このときは `deferred` として次回 run に回すのが正しい。

対策:

- `failed` と `deferred` を混同しない
- `recommendedWaitSeconds` が出ているかを見る
- 即修正ではなく、設計どおりの defer かを先に判断する

### 6.4 viewer 側の見え方だけでパイプライン全体を判断しない
viewer に記事が出ない理由は、生成失敗だけではない。

- manifest が古い
- 保存先が違う
- article file はあるが manifest に載っていない
- API が別フォルダを見ている

この層を分けて確認する必要がある。

## 7. 再発防止チェックリスト
### 7.1 まず最初に見るべき順番
1. GitHub Actions の run の `mode` を確認する
2. `success / failure` 件数を確認する
3. `Apify` と `Gemini` のログ有無を確認する
4. `INFO_VIEWER_ONEDRIVE_FOLDER` を確認する
5. 最新 `manifest.json` の `generatedAt` を確認する
6. `pipeline_state.json` の `status` / `nextRetryAt` を確認する
7. viewer API がどの manifest を返しているか確認する

### 7.2 `sync_only` を見たときの判断ルール
`sync_only` の run を見たら、次のように考える。

- これは記事生成 run ではない
- Gemini が走っていなくても正常
- 記事生成可否の判定材料にはしない

### 7.3 `process_queue` を見たときの判断ルール
`process_queue` の run を見たら、次を確認する。

- `処理対象件数`
- `Apify で文字起こし取得`
- `Gemini candidate`
- `成功`
- `失敗`
- `manifest 更新完了`

この 6 つが揃って初めて「記事生成がどこまで進んだか」を判断しやすい。

## 8. 1件だけ確実に検証する方法
再現確認や修正確認では、`video_url` 指定の `workflow_dispatch` が最も扱いやすい。

考え方:

- queue の defer 状態に引っ張られにくい
- 対象を 1 件に限定できる
- ログが読みやすい

確認したいログ:

- `処理対象件数: 1`
- `Apify で文字起こし取得`
- `Gemini candidate`
- `成功: 1件`
- `失敗: 0件`

## 9. 今後の運用ノウハウ
### 9.1 「viewer に出ない」を 3 層に分ける
`viewer に出ない` は次の 3 層に分けて考える。

1. queue に乗っていない
2. 記事生成に失敗している
3. 生成済みだが manifest / API / viewer 反映でこぼれている

この切り分けを最初にやると、調査がかなり短くなる。

### 9.2 保存先は 1 つに寄せる
OneDrive 上の保存先は 1 つに統一し、旧パスを残したまま運用しない。  
過渡期で旧パスを残す場合でも、viewer 側は必ず「最新 manifest 優先」にする。

### 9.3 legacy workflow を判断材料にしない
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\info-viewer-pipeline.yml` は legacy 扱い。  
現在の本線は `info-viewer-queue.yml` であり、挙動確認は必ずこちらを基準にする。

## 10. 最終確認済みの状態
2026-04-16 時点で、以下を確認済み。

- workflow の保存先は新保存先へ統一済み
- viewer API は最新 manifest / state を優先取得できる
- Gemini の一時エラー時は次候補キーへフォールバックできる
- `video_url` 指定 run で Apify → Gemini → manifest 更新 → 成功 まで確認済み

このため、現時点の `info_viewer` は
「正しく値を取得し、Apify と Gemini の処理を通し、viewer に出す」ための基礎部分は復旧済みである。
