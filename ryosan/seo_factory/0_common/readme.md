# SEO Factory Common README

更新日: 2026-04-07
対象リポジトリ: `%USERPROFILE%\OneDrive\開発\Blog_Vercel`

## 1. このファイルの役割

このファイルは、`0_common` に集約すべき仕様、メモ、責務分担、ログ、再発防止事項をまとめるための README である。

ここに書くもの:

- 最新の正規構成
- Python とこのチャットの責務分担
- スプレッドシート仕様
- 出力仕様
- 元記事仕様
- validator 仕様
- 過去の失敗
- 不整合をなくすための更新ルール

ここに書かないもの:

- 母艦記事や個別記事の本文ルール
- プロンプトの禁止事項
- 実行順だけを説明するワークフロー本文

## 2. 3本のファイルの役割分担

- `%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\SEO_記事量産ワークフロー運用版_20260407.md`
  - 0 から 3 までの実行順を完遂するためのワークフロー
- `%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\seo_factory\0_common\promptreference.md`
  - プロンプト、執筆ルール、禁止事項、見出しルール
- `%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\seo_factory\0_common\readme.md`
  - 仕様、メモ、ログ、責務分担、不整合防止の管理

## 3. 最新の正規構成

```text
%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\
├─ input\
│  └─ <任意の元記事>.md
└─ seo_factory\
   ├─ env\
   │  └─ google-service-account.json
   ├─ 0_common\
   │  ├─ promptreference.md
   │  ├─ readme.md
   │  └─ scripts\
   │     ├─ 031_3_article_validator.py
   │     └─ 031_5_run_factory.py
   ├─ 1_keyword_collect\
   │  ├─ SKILL.md
   │  └─ scripts\
   │     └─ 031_1_keyword_pipeline.py
   ├─ 2_base_article\
   │  ├─ SKILL.md
   │  ├─ prompts\
   │  │  ├─ 031-1-best-outline-prompt.md
   │  │  └─ 031-2-best-article-enhancer-prompt.md
   │  └─ scripts\
   │     └─ 031_2_master_article_generator.py
   ├─ 3_variant_article\
   │  ├─ SKILL.md
   │  ├─ prompts\
   │  │  └─ 031-4-kobetsu-writer-prompt.md
   │  └─ scripts\
   │     └─ 031_4_kobetsu_writer.py
   └─ output\
      └─ <slug>\
         ├─ memo\
         ├─ master_article.md
         └─ variants\
```

## 4. 正規の参照先

以下を正規の更新先とする。

- 元記事入力
  - `%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\input\`
- 共通実行口
  - `%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\seo_factory\0_common\scripts\031_5_run_factory.py`
- 共通 validator
  - `%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\seo_factory\0_common\scripts\031_3_article_validator.py`
- キーワード収集
  - `%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\seo_factory\1_keyword_collect\scripts\031_1_keyword_pipeline.py`
- 母艦記事材料
  - `%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\seo_factory\2_base_article\scripts\031_2_master_article_generator.py`
- 個別記事ジョブ
  - `%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\seo_factory\3_variant_article\scripts\031_4_kobetsu_writer.py`

## 5. Python とこのチャットの責務分担

### 5.1 Python がやること

- ラッコキーワード取得
- Google Spreadsheet 保存
- Google Spreadsheet 再読込
- `不要` 除外と採用行整理
- 並び順整理
- outline 作成
- 元記事ベースの bundle 作成
- 母艦記事 validator 実行
- 個別記事ジョブ作成
- 個別記事 validator 実行

### 5.2 Python がやらないこと

- `Gemini` を使った本文生成
- `master_article.md` の自動作成
- `variants\*.md` の自動作成

### 5.3 このチャットがやること

- 元記事を読み、母艦記事本文を作る
- job を読み、骨格H2＋関連論点H2を抽出して個別記事を作る（母艦の全H2を持ち込まない）
- validator 結果を見て修正方針を決める
- ユーザーがラッコ検索キーワードをまだ提示していない場合は、実行前に必ず確認する

### 5.4 ワークフロー開始条件

- ユーザーが `%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\input\` に母艦の土台記事 Markdown を入れる
- ユーザーがこのチャットでラッコ検索キーワードを提示する
- この 2 点が揃うまで Python 実行を開始しない
- ラッコ検索キーワードは記事本文から自動推測しない
- ユーザーから検索キーワード提示が無い場合は、このチャットで必ず確認する

## 6. スプレッドシート仕様

対象シート:

`https://docs.google.com/spreadsheets/d/1_qjAWcrgGHY8xTQdiUrK-v_gJsXEb8FH9ABUvEpcVMo/edit?gid=894792171#gid=894792171`

### 6.1 保存先タブ

- 取得キーワード名を右端タブへ保存する
- タブ名は、ユーザーがチャットで提示したラッコ検索キーワードをそのまま使う
- 例: `macbook neo`

### 6.2 名称の分離

- ラッコ検索キーワード: `macbook neo`
- スプレッドシートタブ名: `macbook neo`
- 出力スラッグ: `macbook_neo`
- `macbook_neo` は出力フォルダ名であり、ラッコ検索キーワードやシート名としてそのまま使わない

### 6.3 ヘッダー

- `キーワード`
- `検索ボリューム`
- `クエリタイプ`
- `状況`

### 6.4 並び順

- `Buy大`
- `Know大`
- `Buy中`
- `Know中`
- `Buy小`

### 6.5 デフォルト不要ルール

- `小` はすべて `不要`
- `中` の `Know / Do` は `不要`
- `大 / 中` で語尾が `とは` は `不要`
- 全英語キーワードは `不要`
- ラッコ検索キーワード完全一致は `不要`
- 助詞入り重複は `不要`

### 6.6 採用ルール

- `不要` 以外の行を処理対象にする
- `状況` が空欄の行も処理対象に含める
- `不要` は常に除外する

## 7. 元記事仕様

- 元記事投入はユーザーが行う
- 母艦記事の土台は `%USERPROFILE%\OneDrive\開発\Blog_Vercel\ryosan\input\` 配下の Markdown を使う
- 複数ある場合は `master_article_backup_*.md` を除外し、そのうえで最終更新日時が最新の 1 件を使う
- `output/<slug>/reference/` は元記事の正規置き場として使わない
- `scripts\pipeline` 由来の記事を母艦化の入力として使わない
- 元記事が無い場合、`031_5_run_factory.py` は材料保存までで停止する

## 8. 出力仕様

### 8.1 母艦材料

- `output/<slug>/memo/current_keywords.json`
- `output/<slug>/memo/previous_keywords.json`
- `output/<slug>/memo/outline.json`
- `output/<slug>/memo/outline.md`
- `output/<slug>/memo/031_2_master_research_bundle.json`
- `output/<slug>/memo/031_2_master_research_bundle.md`

### 8.2 母艦検証

- `output/<slug>/memo/031_3_master_validation_report.json`
- `output/<slug>/memo/031_3_master_validation_report.md`

### 8.3 個別記事ジョブ

- `output/<slug>/memo/031_4_kobetsu_jobs.json`
- `output/<slug>/memo/031_4_kobetsu_jobs.md`

### 8.4 個別記事検証

- `output/<slug>/memo/031_4_variant_validation_report.json`
- `output/<slug>/memo/031_4_variant_validation_report.md`

## 9. validator 仕様

### 9.1 母艦記事 validator

- 採用キーワード由来の H2 を検査する
- 元記事から継承すべき H2 を検査する
- 章内行数を検査する
- 箇条書き数を検査する
- FAQ 形式を検査する

### 9.2 個別記事 validator

- 必須 H2 を検査する
- H2 直下の最初の 1 文を検査する
- 対象キーワード整合を検査する

## 10. 過去の失敗

- 調査が薄く、冒頭結論に固有価値が無かった
- 一般論で本文を埋めた
- 入力記事の良い本文を守らず、別物の文章へ書き換えた
- AI メタ文を本文へ混ぜた
- 正式名称の統一が弱かった
- 箇条書きが名詞の羅列になった
- `状況` 空欄行を自動採用して意図しないキーワード群へ差し替わった
- no-LLM 実行で仮テンプレを完成記事として上書きした
- Python 側が本文まで書こうとして一般論の強い雛形へ戻った
- 構成維持より見出し整理を優先し、母艦 H2 を 4 見出し前後へ圧縮した
- validator が H2 と冒頭一文だけを見て、本文劣化を見逃した
- `TEST\input\` 配下の元記事を固定ファイル名で扱いかけた
- ラッコ検索キーワードと出力スラッグの区別が弱く、`macbook_neo` をシート名として扱った
- 母艦記事の全H2を個別記事にそのまま持ち込み、対象キーワードと無関係な論点をこじつけて量産した（例：学割記事にケースやゲーム性能のH2を含めた）
- H2見出しに検索キーワードの小文字をそのまま使い、公式名称に変換しなかった（例：`macbook neo` → 正しくは `MacBook Neo`）
- 個別記事で冒頭イントロ（最初のH2より前の部分）を勝手に削除した
- 個別記事でH2内の文章構成（導入文→箇条書き→まとめ文）を崩し、まとめ文を勝手に削除した

## 11. 不整合をなくすための更新ルール

- 実行順を変えたら `SEO_記事量産ワークフロー運用版_20260407.md` を更新する
- 執筆ルールを変えたら `promptreference.md` を更新する
- 仕様、構成、責務分担、メモを変えたら `readme.md` を更新する
- フェーズ構成を変えたら、関連する `SKILL.md` も更新する
- 新しい正規パスに変更があったら、古い参照を残さない
- 母艦の元記事の置き場を変えたら、`031_5_run_factory.py` とワークフロー文書を同時に更新する
- ラッコ検索キーワード、シート名、出力スラッグの決め方を変えたら、`031_5_run_factory.py`、ワークフロー、README、`SKILL.md` を同時に更新する

## 12. 移行メモ

- OneDrive の制約で、旧 `TEST\seo_factory\scripts\` と `TEST\seo_factory\prompts\` のコピーが残っている場合がある
- 正規の編集先は新しいフェーズ別フォルダであり、旧フォルダは参照用にしない
- 一時キャッシュの `temp_pycache` は不要であり、ロックが無ければ削除対象とする
