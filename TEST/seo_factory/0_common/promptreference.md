# プロンプト運用リファレンス

更新日: 2026-04-07
対象リポジトリ: `C:\Users\HCY\OneDrive\開発\Blog_Vercel`

## 1. このファイルの目的

このファイルは、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\0_common\`、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\1_keyword_collect\`、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\2_base_article\`、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\3_variant_article\` を運用する際の恒久ルール集である。

過去のやり取りで発生したルール違反、品質低下、AIメタ文混入、一般論への逃避を再発させないために作成する。

以後、母艦記事と個別記事の設計・生成・修正は、必ずこのファイルを参照して判断する。

2026-04-07 以降は、`C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\` 由来の記事を母艦化の土台として扱わない。
母艦記事の土台は常に `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\reference\` 配下の参照記事とする。

### 1.1 ワークフロー順一覧表

| 実行順 | フェーズフォルダ | 説明 | 使うプロンプト | 実行する Python | Python がやること | このチャットがやること | 主な出力先 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | `0_common` | 共通ルール、出力命名規則、完了条件、共通 validator、全体実行入口をまとめる工程。 | `promptreference.md` | `scripts/031_5_run_factory.py`<br>`scripts/031_3_article_validator.py` | 全体オーケストレーション、母艦検証、個別記事検証を担当する。 | 実行前にルール、過去の失敗、参照記事運用、完了条件を確認する。 | `output/<seed>/memo/...` |
| 1 | `1_keyword_collect` | ラッコ取得、スプシ保存、手動選別後の再開までを1つのフェーズにまとめる工程。 | なし | `../1_keyword_collect/scripts/031_1_keyword_pipeline.py`<br>`../0_common/scripts/031_5_run_factory.py` | サジェスト取得、意図分類、記事候補判定、Google スプレッドシート保存、再読込、採用行抽出を行う。 | 本文は書かず、採用キーワードが母艦工程へ渡せる状態になったかを確認する。 | Google スプレッドシートの対象タブ<br>`output/<seed>/memo/current_keywords.json`<br>`output/<seed>/memo/previous_keywords.json` |
| 2 | `2_base_article` | 母艦記事のアウトライン、bundle、参照記事ベースの本文作成、母艦検証までを順に完了させる工程。 | `../2_base_article/prompts/031-1-best-outline-prompt.md`<br>`../2_base_article/prompts/031-2-best-article-enhancer-prompt.md`<br>`promptreference.md` | `../2_base_article/scripts/031_2_master_article_generator.py`<br>`../0_common/scripts/031_5_run_factory.py`<br>`scripts/031_3_article_validator.py` | アウトライン生成、参照記事構造解析、母艦 bundle 出力、母艦記事検証を行う。 | `output/<seed>/reference/<任意の参照記事>.md` を土台に `master_article.md` を作り、検証 NG なら戻して修正する。 | `output/<seed>/master_article.md`<br>`output/<seed>/memo/outline.md`<br>`output/<seed>/memo/031_2_master_research_bundle.md`<br>`output/<seed>/memo/031_3_master_validation_report.md` |
| 3 | `3_variant_article` | 個別記事ジョブ生成、個別記事執筆、個別記事検証までを順に完了させる工程。 | `../3_variant_article/prompts/031-4-kobetsu-writer-prompt.md`<br>`promptreference.md` | `../3_variant_article/scripts/031_4_kobetsu_writer.py`<br>`../0_common/scripts/031_5_run_factory.py`<br>`scripts/031_3_article_validator.py` | job 生成、対象キーワードごとの H2 条件整理、個別記事検証を行う。 | job を読み、各 `variants/<target_keyword>.md` を書き、validator を通して完了扱いにする。 | `output/<seed>/memo/031_4_kobetsu_jobs.md`<br>`output/<seed>/variants/<target_keyword>.md`<br>`output/<seed>/memo/031_4_variant_validation_report.md` |

## 2. 最重要目的

- 受け取った入力記事の強みを壊さない
- 検索キーワードで不足している部分のみを追加する
- 一般論ではなく、各採用SEOキーワードごとの調査結果を冒頭結論と本文へ反映する
- 読者が「冒頭の結論に価値があるから続きを読む」と判断できる記事にする
- 母艦記事を質の高い情報源にし、その内容を使って個別記事へ展開する

## 3. 守るべき大原則

### 3.1 入力記事尊重

- 受け取った記事本文は、すでに整っている前提で扱う
- 自然な導入文、読者向け説明、H2直下の簡易解説、箇条書き、章末まとめは保持対象
- 全面書き換え禁止
- 無意味な言い換え禁止
- 短くして劣化させる行為を禁止
- AIっぽい不自然文へ豹変させる行為を禁止

### 3.2 不足分だけ追加

- 追加対象は、検索キーワードで不足している部分のみ
- すでに自然に答えている内容は触らない
- 書き手が書きたい一般論を足さない
- 同じ内容を別表現で重ねない

### 3.3 調査必須

- 母艦記事は、採用されたSEOキーワードごとに調査を前提とする
- 調査の深さこそ記事のコアコンピタンスであり、他社との差別化要因である
- 冒頭の結論は、各キーワードごとの調査結果を要約したものでなければならない
- 調査が無い状態で一般論だけを書いてはいけない
- 調査対象は、キーワード数の分だけ発生する前提で考える

### 3.4 正式名称厳守

- 製品名は必ず公式表記へ合わせる
- 大文字小文字、漢字、ひらがな、カタカナ、スペースを含めて公式表記と一致させる
- サジェストキーワードが崩れた表記でも、本文では公式の正式名称を使う
- 例:
  - サジェスト: `macbook neo シルバー レビュー`
  - 本文表記: `MacBook Neo`

## 4. 母艦記事ルール

### 4.1 役割

- 母艦記事は、採用された複数キーワードの課題と解決策を集約した基幹記事である
- 母艦記事の出来が悪いと、個別展開したときに低品質記事を量産することになる
- 母艦記事では常に「編集長」として振る舞う

### 4.2 禁止

- 一般論だけで膨らませる
- キーワード分析そのものを本文で説明する
- 制作裏話や編集方針を本文へ出す
- `母艦記事`
- `量産元`
- `このキーワードでは`
- `この記事の使い方`
- `構造`
- `テンプレート`
- `章順`
- `切り出し`
- `検索キーワード`
- `不足回答`
- `CTA`

### 4.3 追加内容の考え方

- 各採用キーワードごとに、読者が知りたい固有の課題を整理する
- その課題に対する具体的な解決策を調査する
- 調査結果を冒頭結論と本文に反映する
- 調査結果が薄いなら、記事も薄いと判断する

### 4.4 80点記事の骨格ルール

- 80点に近かった母艦記事の強みは、狭い見出しへ圧縮せず、広い判断骨格を保ったまま採用キーワードの答えを差し込んでいた点にある
- 母艦記事の基本骨格は、原則として次の順を維持する
  - `結論`
  - `選定基準`
  - `採用キーワード別 H2`
  - `比較`
  - `メリット`
  - `デメリット`
  - `FAQ`
  - `評判`
  - `まとめ`
- 採用キーワード別 H2 は、必ず `選定基準` の後、`比較` の前に置く
- 採用キーワード別 H2 を追加しても、`比較 / メリット / デメリット / FAQ / 評判 / まとめ` を落としてはいけない
- 80点記事で良かったのは、冒頭で「今見るべき主要論点」を先に整理し、その後に各採用キーワードの答えを独立 H2 で回収していた点である
- 各採用キーワード章は、一般論ではなく、その論点に固有の判断軸と調査済み事実を先に出す
- 既存の良い母艦記事がある場合は、その骨格を baseline として bundle と validator の両方で保持する
- 新しい採用キーワードが増えても、母艦記事をゼロから別構成に作り直してはいけない
- 4見出し前後への圧縮は、80点記事のノウハウを破壊するため禁止する

### 4.5 見出し順

- 基本優先順は `Buy大 → Know大 → Buy中 → Know中 → Buy小`
- 親需要と子需要は同一記事内で統合する
- H3 / H4 は使わず、親需要も子需要も H2 で立てる

## 5. 個別記事ルール

### 5.1 母艦流用

- 個別記事は母艦記事を土台にする
- 別テンプレートで新規作文しない
- 母艦記事の良い文章資産と論点順を引き継ぐ
- 母艦記事に無い事実を創作しない
- 母艦記事の H2 構成は原則すべて維持する
- 既存の良い母艦記事がある場合は、その H2 構成と主要本文を bundle に渡して継承対象にする
- H2 数を勝手に削って圧縮してはいけない
- `結論 / 本文テーマ / 注意点 / まとめ` のような4見出し前後への圧縮を禁止する

### 5.2 H2絶対ルール

- 個別記事の H2 は必ず対象検索キーワードから始める
- 形式は必ず `対象検索キーワード：見出し名`
- 例:
  - `## macbook neo インディゴ：結論`
  - `## macbook neo インディゴ：選定基準`
  - `## macbook neo インディゴ：評判`

### 5.3 本文ルール

- AIメタ文禁止
- 母艦記事の説明をそのまま読者へ見せない
- 「この記事は母艦から作った」などの制作事情を出さない
- 読者の疑問に答える文だけを書く
- 冒頭から対象キーワードの結論を出す
- 構成を短く整理するために、母艦の論点を落としてはいけない

### 5.4 H2直下の文頭ルール

- 母艦記事でも個別記事でも、H2直下の最初の1文は、その見出しキーワードを自然に含めて始める
- 例:
  - NG: `先行レビューでいちばん大事なのは...`
  - OK: `MacBook Neoの先行レビューでいちばん大事なのは...`
- 例:
  - NG: `ケースを選ぶ基準が多く見えても...`
  - OK: `MacBook Neoのケース選びで基準にしたいのは...`
- 見出し名と本文冒頭の主語をずらさない
- 主語が抜けた一般論で始めない

### 5.5 おすすめ見出しの制限

- `おすすめ` 見出しでは、おすすめ製品のランキング記事にしない
- アフィリエイト記事でも、本文で提供すべき価値は「商品を選ぶ判断軸」である
- AIが勝手におすすめ製品を決めない
- 公式情報として候補商品名や価格を紹介するのは可
- ただし結論と箇条書きは、商品名ではなく判断基準へ寄せる
- 特に `ケース おすすめ` では、以下を優先して書く
  - 何を守りたいか
  - 専用品か互換品か
  - 寸法やポート位置の互換性
  - 持ち運び頻度
  - 収納時の厚みや出し入れ

## 6. 箇条書きルール

- 体言止めを基本とする
- `です / ます` を箇条書きに入れない
- 文頭は `結論語：` の形にする
- ただし、名詞だけの羅列にしない
- 短くても意味が通る説明にする

### NGの考え方

- `保護基準：移動量確認`
- `軽量基準：携帯頻度確認`

### GOODの考え方

- `保護基準：移動量で保護の要素が変化`
- `軽量基準：携帯頻度はどの程度か`

## 7. スプレッドシート運用ルール

対象シート:
`https://docs.google.com/spreadsheets/d/1_qjAWcrgGHY8xTQdiUrK-v_gJsXEb8FH9ABUvEpcVMo/edit?gid=894792171#gid=894792171`

### 7.1 タブ保存

- 取得キーワード名を右端タブへ保存
- 例: `macbook neo`

### 7.2 ヘッダー

- `キーワード`
- `検索ボリューム`
- `クエリタイプ`
- `状況`

### 7.3 並び順

- `Buy大`
- `Know大`
- `Buy中`
- `Know中`
- `Buy小`
- それ以外は後ろでよい

### 7.4 デフォルト不要ルール

- `小` はすべて `不要`
- `中` の `Know / Do` は `不要`
- `大 / 中` で語尾が `とは` は `不要`
- 全英語キーワードは `不要`
- シードキーワード完全一致は `不要`
- `の / を / に / で / は / が / と` などの助詞入り重複は `不要`

### 7.5 採用ルール

- 後段の母艦記事生成と個別記事生成では、`不要` 以外の行を処理対象にする
- `状況` が空欄の行も処理対象に含める
- `不要` は常に除外する

## 8. このチャット実行ルール

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\0_common\scripts\031_5_run_factory.py` は、常に材料生成と検証だけを担当する
- `Gemini` や `google-genai` を使って Python 側が本文を書く運用は廃止する
- Python 側は、キーワード収集、スプレッドシート読込、分類、並び順整理、調査メモ作成、見出し候補整理、母艦記事検証、個別記事ジョブ生成までを担当する
- 本文の仕上げは、このチャットで行う
- 共通ルール、出力命名規則、完了条件、検証観点は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\0_common\promptreference.md` に集約する
- 母艦記事の土台は `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\reference\` 配下の参照記事とする
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\0_common\scripts\031_5_run_factory.py` の `--use-llm` / `--skip-llm` は互換用オプションであり、実際の本文作成モードは変わらない
- 材料生成実行で `master_article.md` を自動生成してはいけない
- 材料生成実行で `variants` 配下の個別記事を自動生成してはいけない
- 材料生成実行では、以下の材料ファイルを保存する
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\memo\current_keywords.json`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\memo\previous_keywords.json`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\memo\outline.json`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\memo\outline.md`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\memo\031_2_master_research_bundle.json`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\memo\031_2_master_research_bundle.md`
  - 参照記事が未配置の場合は、`reference` ディレクトリ不足を明示して停止する
- `master_article.md` が既に存在する場合のみ、母艦記事検証レポートと個別記事ジョブを追加で保存する
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\memo\031_3_master_validation_report.json`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\memo\031_3_master_validation_report.md`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\memo\031_4_kobetsu_jobs.json`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\memo\031_4_kobetsu_jobs.md`
- 材料生成実行は最終記事扱いをしてはいけない
- 母艦記事が 80点 baseline 未達なら、個別記事フェーズへ進めてはいけない
- 母艦記事 validator は、現行採用キーワード由来の H2 だけでなく、参照記事から継承すべき H2 も検査する
- 母艦記事 validator は、参照記事の章内説明量、箇条書き、FAQ 形式も検査する
- 個別記事を生成したあとは `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\0_common\scripts\031_3_article_validator.py` 相当の検証を通過しなければ完了扱いにしてはいけない

## 9. 現時点の採用キーワード

2026-04-06 時点で `macbook neo` タブから採用されているキーワードは以下の 5 件。

- `macbook neo エクセル`
- `macbook neo ケース`
- `macbook neo ゲーム`
- `macbook neo ゲーム性能`
- `macbook neo ゲーム配信`

## 10. ここまでで確定した失敗原因

- 調査が薄く、冒頭結論に固有価値が無かった
- 一般論で本文を埋めた
- 入力記事の良い本文を守らず、別物の文章へ書き換えた
- AIメタ文を本文へ混ぜた
- 正式名称の統一が弱かった
- 箇条書きが名詞の羅列になり、読者に意味が伝わりにくかった
- `状況` 空欄行を自動採用したため、意図しないキーワード群へ差し替わった
- no-LLM 実行で仮テンプレを完成記事として上書きした
- Python 側が本文まで書こうとして、一般論の強い雛形へ戻った
- 構成維持より見出し整理を優先し、母艦 H2 を4見出し前後へ圧縮した

## 11. 今後の修正判断

以後の修正では、以下を毎回確認する。

- 追加内容は本当に検索キーワード由来か
- 調査結果が冒頭結論に入っているか
- 正式名称が公式表記と一致しているか
- AIメタ文が混入していないか
- 箇条書きが短くても意味を持っているか
- 参照記事の各章で行数 / 箇条書き / FAQ 形式が維持されているか
- 個別記事の H2 がすべて対象検索キーワード始まりか
- H2直下の最初の1文が見出しキーワードから自然に始まっているか
- `おすすめ` 見出しで商品推薦記事に逸れていないか
- 母艦記事の良い文章を壊していないか
- 母艦記事が 80点 baseline を維持しているか
- `CTA` を見せる見出し語が残っていないか
- `まとめ` が `まとめ & CTA` に戻っていないか
- `不要` 以外の空欄行も処理対象に含まれているか
- no-LLM 実行が完成記事を上書きしていないか
- 材料生成実行でこのチャット用の材料が十分に出ているか
- 個別記事が母艦由来の H2 構成を維持しているか
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\memo\031_4_variant_validation_report.md` が合格しているか

## 12. 関連ファイル

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\1_keyword_collect\SKILL.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\1_keyword_collect\scripts\031_1_keyword_pipeline.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\2_base_article\SKILL.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\2_base_article\scripts\031_2_master_article_generator.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\2_base_article\prompts\031-1-best-outline-prompt.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\2_base_article\prompts\031-2-best-article-enhancer-prompt.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\3_variant_article\SKILL.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\3_variant_article\scripts\031_4_kobetsu_writer.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\3_variant_article\prompts\031-4-kobetsu-writer-prompt.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\0_common\promptreference.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\0_common\scripts\031_3_article_validator.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\0_common\scripts\031_5_run_factory.py`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\<seed>\reference\<任意ファイル名>.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\SEO_記事量産ワークフロー計画書.md`
