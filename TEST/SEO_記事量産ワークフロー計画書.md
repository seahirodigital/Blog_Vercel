# SEO記事量産ワークフロー計画書

作成日: 2026-04-06
対象リポジトリ: `C:\Users\HCY\OneDrive\開発\Blog_Vercel`

## 1. 目的

### Why

いま必要なのは、1本ずつ人手で記事を書く運用ではなく、1つの軸となる高品質な完成版記事を作り、その完成版を各SEOキーワード向けに自然にリライトして量産できる仕組みです。  
この仕組みがあれば、検索意図ごとにズレた記事を毎回ゼロから書く必要がなくなり、品質と速度を両立できます。

### ベネフィット

- サジェストキーワードを起点に、検索ニーズを漏れなく拾える
- 1本の完成版記事を母艦にすることで、記事品質を一定化できる
- キーワードごとのリライトを自動化し、量産時の工数を大幅に下げられる
- `Google Ads` 登録なしでキーワード収集を開始できる

## 2. ゴール

この計画で目指す完成形は次の4段階です。

1. シードキーワードを入力すると、サジェストキーワード一覧を自動取得できる
2. 取得キーワードを分析し、検索意図を広くカバーする「完成版記事」の構成と本文を1本作れる
3. 完成版記事をもとに、各サジェストキーワード向けに見出し順序・見出し名・本文内の語彙を調整した派生記事を作れる
4. GitHub Actions から一連の処理を定期または手動で実行できる

## 3. 非ゴール

今回の計画書段階では、以下はまだ完成対象に含めません。

- 実際の本番記事の大量生成
- 本番公開フローの完全自動化
- 収益化導線の最適化
- 検索順位の自動取得

## 4. 現状資産の確認

既存リポジトリには、すでに記事生成の土台として再利用できる資産があります。

- 既存パイプライン本体  
  `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\main.py`
- AI生成の中核  
  `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\blog_pipeline.py`
- 既存依存関係  
  `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\requirements.txt`
- サジェスト取得の参照JS  
  `C:\Users\HCY\OneDrive\開発\Blog_Vercel\reference\suggest_keywords.js`

### 現状の読み取り結果

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\requirements.txt` には `playwright` が含まれている
- 既存の `blog_pipeline.py` は「下書き → 編集 → 最終化」という3段構成を持っており、完成版記事生成に転用しやすい
- `suggest_keywords.js` は文字コード崩れがあるが、以下の挙動は読み取れる
  - ラッコキーワード結果テーブルの走査
  - ページ送りで全件取得
  - キーワードの Buy / Do / Know っぽい分類
  - TSV 形式での出力

### 重要な判断

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\reference\suggest_keywords.js` は、そのまま移植するのではなく、**Python で新しく書き直す**方が安全です。  
理由は、文字化けしたラベル群を無理に救済するより、DOMロジックだけを参考にして再実装した方が保守しやすいからです。

## 5. 全体アーキテクチャ案

### 全体像

```text
シードキーワード
  ↓
Playwright + Chromium でラッコキーワード取得
  ↓
正規化・重複除去・意図分類
  ↓
キーワードクラスタ分析
  ↓
完成版記事の見出し設計
  ↓
完成版記事の本文生成
  ↓
キーワード別リライト
  ↓
品質チェック
  ↓
Markdown / JSON / CSV で保存
  ↓
GitHub Actions から定期実行
```

### 推奨実装方針

まずは PoC を `TEST` 配下で完結させ、安定後に本体パイプラインへ昇格します。  
これにより、既存の `scripts\pipeline` を壊さずに検証できます。

## 6. 推奨ディレクトリ構成

PoC 実装の第一案です。

```text
C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\
├─ SEO_記事量産ワークフロー計画書.md
├─ seo_factory\
│  ├─ run_factory.py
│  ├─ requirements.txt
│  ├─ config\
│  │  └─ pipeline.example.json
│  ├─ collectors\
│  │  └─ rakko_suggest_collector.py
│  ├─ analyzers\
│  │  ├─ keyword_normalizer.py
│  │  ├─ keyword_intent_classifier.py
│  │  └─ keyword_cluster_builder.py
│  ├─ generators\
│  │  ├─ master_outline_generator.py
│  │  ├─ master_article_generator.py
│  │  └─ keyword_variant_rewriter.py
│  ├─ exporters\
│  │  ├─ markdown_exporter.py
│  │  ├─ json_exporter.py
│  │  └─ csv_exporter.py
│  ├─ prompts\
│  │  ├─ 01-master-outline.md
│  │  ├─ 02-master-article.md
│  │  └─ 03-keyword-rewrite.md
│  ├─ data\
│  │  ├─ raw\
│  │  ├─ normalized\
│  │  ├─ master\
│  │  └─ variants\
│  └─ tests\
│     ├─ test_keyword_normalizer.py
│     ├─ test_intent_classifier.py
│     └─ test_variant_rewriter.py
└─ .github\
   └─ workflows\
      └─ seo-article-factory.yml
```

## 7. 処理フロー詳細

## 7.1 フェーズ1: サジェストキーワード取得

### Why

完成版記事の質は、最初に拾うキーワードの網羅性でかなり決まります。  
ここが弱いと、後段のAI生成がどれだけ上手くても、検索意図の抜け漏れが残ります。

### 実装方針

- 使用技術: `Python + Playwright + Chromium`
- 対象URL例:  
  `https://rakkokeyword.com/result/suggestKeywords?q=macbook+Neo&mode=google`
- 取得対象:
  - サジェストキーワード
  - 区分列
  - ページ番号
  - 取得元キーワード
  - 取得日時

### 実装要件

- `ul.pagination` を辿って全ページ取得する
- 1ページ目だけで終わらず、最後のページまで回す
- 重複キーワードは除去する
- 生データは JSON と CSV の両方で保存する
- 取得失敗時はスクリーンショットと HTML を保存する

### 出力イメージ

1レコードの最低項目は以下です。

```json
{
  "seed_keyword": "macbook neo",
  "suggest_keyword": "macbook neo 評判",
  "source": "rakkokeyword",
  "category_label": "大",
  "page": 3,
  "fetched_at": "2026-04-06T10:00:00+09:00"
}
```

### 注意点

- ラッコキーワードの DOM 変更に弱いので、セレクタは1箇所に集約する
- Bot 対策やアクセス制限が入る可能性があるため、待機時間と再試行を設ける
- 利用規約やアクセス頻度の妥当性は実装時に必ず確認する

## 7.2 フェーズ2: キーワード正規化と意図分析

### Why

サジェストは、そのままだと表記ゆれ・重複・類似意図が混ざります。  
ここを整理せずに量産すると、内容が薄い派生記事やカニバリが発生しやすくなります。

### 実装方針

- 全キーワードを小文字化・空白統一・全角半角の揺れ補正
- 重複除去
- キーワードを意図ごとに分類
  - `Know`
  - `Do`
  - `Buy`
  - 必要なら `Compare`
  - 必要なら `Trouble`

### 期待する分析出力

- 検索者が知りたい論点一覧
- 比較したい論点一覧
- 購入前に不安な論点一覧
- 使い方・設定・トラブル解決系の論点一覧

### 方針

初期版では単純ルールベースで始めます。  
その後、必要であれば LLM 分類を追加します。

## 7.3 フェーズ3: 完成版記事の見出し設計

### Why

量産品質を支えるのは、各派生記事ではなく「母艦となる完成版記事」の設計です。  
ここが弱いと、派生記事も全部弱くなります。

### 実装方針

- フェーズ2の分析結果を入力として、網羅性の高い見出し構成を生成する
- 1つのキーワードに寄せすぎず、クラスタ全体の疑問を吸収する
- 見出しの順序は「結論 → 比較 → 詳細 → FAQ」を基本形にする

### 完成版記事の構成要件

- H1 はクラスタ全体を代表する検索意図を含む
- H2 は主要意図を漏れなくカバーする
- H3 は比較・注意点・おすすめ・FAQ で補完する
- 最後に CTA やアフィリエイト導線を差し込める形にする

### 想定成果物

- `master_outline.json`
- `master_outline.md`

## 7.4 フェーズ4: 完成版記事の本文生成

### Why

派生記事の品質は、完成版記事の情報密度と論理の通りやすさでほぼ決まります。  
先に高密度な1本を作っておく方が、後段のリライトが安定します。

### 実装方針

- 既存の  
  `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\blog_pipeline.py`  
  の3段構成を参考にする
- ただし入力を「YouTube文字起こし」ではなく「キーワード分析結果 + 見出し設計」に差し替える
- 完成版記事は Markdown で保存する

### 推奨プロンプト分割

1. アウトライン生成
2. 本文ドラフト生成
3. SEO/可読性/重複修正
4. 最終整形

### 品質条件

- 主要キーワードを不自然でない形で含む
- FAQ を持つ
- 比較軸、向いている人、向いていない人を明示する
- 情報が薄い見出しを残さない

## 7.5 フェーズ5: キーワード別リライト量産

### Why

このフェーズが、今回の目的である「量産」の核心です。  
ただし単なる単語置換では弱く、検索意図に合わせて見出し順序まで変える必要があります。

### 実装方針

完成版記事を入力にして、各サジェストキーワード向けに以下を変化させます。

- H1
- H2 の順序
- H2 の文言
- 冒頭リード文
- FAQ
- メタディスクリプション
- 強調する比較ポイント

### 変えてよいもの

- キーワードの語順
- 見出しの並び
- 比較観点
- 訴求の重み

### 変えてはいけないもの

- 事実関係
- 完成版記事の核となる結論
- 誤解を招く大幅な主張変更

### 派生記事の最低要件

- キーワードごとに H1 が適合している
- 上位の検索意図に沿った冒頭文になっている
- 少なくとも 30% 以上は見出し構造または文章の焦点が変化している
- ほぼ同一記事になっていない

### 出力イメージ

- `variants\macbook_neo_評判.md`
- `variants\macbook_neo_比較.md`
- `variants\macbook_neo_おすすめ.md`

## 7.6 フェーズ6: 品質チェック

### Why

量産系フローは、速く回るほど「重複」「不自然な置換」「見出しの破綻」が混ざりやすくなります。  
なので、公開前の機械チェックを必ず挟みます。

### 自動チェック項目

- タイトル重複
- H1 と本文の不一致
- 禁止語や不自然な連呼
- 文字数不足
- FAQ 未生成
- 派生記事同士の類似度が高すぎるケース

## 8. GitHub Actions 設計案

## 8.1 基本方針

最初からジョブを細かく分けすぎるより、初期版は1本のワークフローで最後まで流す方が保守しやすいです。

### 推奨ワークフロー名

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\seo-article-factory.yml`

### 実行トリガー

- `workflow_dispatch`
- `schedule`

### 想定ジョブ

1. `collect_keywords`
2. `analyze_keywords`
3. `build_master_article`
4. `rewrite_variants`
5. `quality_gate`
6. `upload_artifacts`

### 初期入力パラメータ

- `seed_keyword`
- `top_n`
- `rewrite_limit`
- `publish_mode`

## 8.2 実行イメージ

```text
workflow_dispatch
  ↓
seed_keyword = macbook neo
  ↓
collect_keywords
  ↓
analyze_keywords
  ↓
build_master_article
  ↓
rewrite_variants
  ↓
quality_gate
  ↓
artifact 保存
```

## 9. 無料運用方針

### Why

今回の条件では、`Google Ads` の登録を使わずに回せることが前提です。  
そのため、キーワード取得と記事生成のコストは切り分けて考える必要があります。

### 無料で進めやすい部分

- Playwright + Chromium によるブラウザ操作
- GitHub Actions の手動実行
- ローカル保存
- CSV / JSON / Markdown 出力

### 無料にならない可能性がある部分

- LLM による見出し生成
- LLM による完成版記事生成
- LLM によるキーワード別リライト

### 現実的な選択肢

1. 既存の `GEMINI_API_KEY` を流用し、利用量を抑えながら PoC を回す
2. 無料枠があるモデルを使う
3. ローカルモデルに切り替える


## 10. 主要リスク

1. ラッコキーワードの DOM 変更で収集が止まる
2. アクセス制限で Playwright 実行が不安定になる
3. キーワードカニバリで派生記事同士が競合する
4. 量産時に薄い記事が増える
5. LLM コストが想定より膨らむ
6. 参照JSの文字化けに引きずられて誤移植する

## 11. 成功条件

初回 PoC の成功条件は以下です。

1. `macbook neo` のサジェストを全件取得できる
2. 重複除去済みキーワード一覧を JSON / CSV で出力できる
3. 完成版記事の見出しを1本生成できる
4. 完成版記事本文を1本生成できる
5. 3本以上の派生記事を自動生成できる
6. 派生記事ごとに H1 / 導入 / 見出し順序が変化している

## 12. 実装ステップ

### ステップ1

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\collectors\rakko_suggest_collector.py` を作成し、Playwright で全ページ取得できるようにする

### ステップ2

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\analyzers\keyword_normalizer.py` と  
`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\analyzers\keyword_intent_classifier.py` を作成し、整形と分類を安定化する

### ステップ3

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\generators\master_outline_generator.py` を作成し、完成版見出しを生成する

### ステップ4

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\generators\master_article_generator.py` を作成し、完成版記事を生成する

### ステップ5

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\generators\keyword_variant_rewriter.py` を作成し、派生記事を量産する

### ステップ6

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\.github\workflows\seo-article-factory.yml` を作成して自動実行できるようにする

## 13. 最初の実行対象

初回検証キーワードは、依頼内容どおり次を推奨します。

- `macbook neo`

理由は、比較・評判・おすすめ・スペック・注意点・買うべきか、など複数の検索意図に分かれやすく、PoC の確認に向いているためです。

## 14. 次にやるべきこと

この計画書の次の作業は、以下の順番が最も効率的です。

1. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory` の雛形を作る
2. Playwright の収集スクリプトを実装する
3. `macbook neo` で実データ取得を試す
4. 取得結果をもとに完成版記事生成へつなぐ

## 15. 補足メモ

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\reference\suggest_keywords.js` は、DOM走査とページ送りの参考資料としてのみ扱う
- 文言や分類辞書は Python 側で再定義する
- 既存の `scripts\pipeline` と密結合にせず、最初は `TEST` 配下で独立運用する
- PoC が安定したら `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline` への統合を検討する

## 16. ベスト記事化の追加方針

### Why

ベスト記事化を最初から別系統で作ると、既存の `01` `02` `03` と二重管理になりやすく、後から保守しづらくなります。  
そのため、**既存の `03-director` までを通過した記事を土台にして、その後ろへ追加工程を差し込む**構造に統一します。

### ベネフィット

- 既存の `01` `02` `03` をそのまま活かせる
- 改修点が `03` の後ろに集約される
- `031` `032` `033` を将来増減しやすい
- `04-affiliate-link-manager` の責務を崩さずに済む

### 新フロー

```text
01-writer
  ↓
02-editor
  ↓
03-director
  ↓
031-best-outline
  ↓
032-best-article-enhancer
  ↓
033-best-seo-polisher
  ↓
04-affiliate-link-manager
```

### 各段の役割

- `01-writer`
  - 既存どおり、原稿の初稿を作る
- `02-editor`
  - 既存どおり、文章を読みやすく整える
- `03-director`
  - 既存どおり、記事として成立する最終版へ仕上げる
- `031-best-outline`
  - `03` 完了記事を読み、検索意図の抜け漏れ、比較軸不足、FAQ不足、構成順の弱さを洗い出す
- `032-best-article-enhancer`
  - `031` の改善方針を反映して、完成版のベスト記事へ増強する
- `033-best-seo-polisher`
  - タイトル、導入、見出し順、強調点、メタ説明文をSEO向けに最終調整する
- `04-affiliate-link-manager`
  - 既存どおり、アフィリエイト挿入とAmazon導線を付与する

### 命名ルール

- `03` の派生工程は `031` `032` `033` のように、`03` の拡張として扱う
- `04` は常にアフィリエイト専用に固定する
- 今後、ベスト記事化工程を増やす場合も `034` `035` と連番で増やす

## 17. 追加するプロンプト設計

### 新規追加候補

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\031-best-outline-prompt.txt`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\032-best-article-enhancer-prompt.txt`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\033-best-seo-polisher-prompt.txt`

### 役割定義

#### 031-best-outline-prompt

- 入力:
  - `03-director` 通過後の記事全文
  - 対象キーワード群
  - 必要なら検索意図分析結果
- 出力:
  - 足りない論点一覧
  - 不要な重複
  - 追加すべき見出し
  - 並べ替えるべき見出し
  - FAQ候補

#### 032-best-article-enhancer-prompt

- 入力:
  - `03` の記事全文
  - `031` の改善提案
- 出力:
  - 完成版ベスト記事の Markdown 全文

#### 033-best-seo-polisher-prompt

- 入力:
  - `032` の完成記事
  - 主要SEOキーワード
- 出力:
  - タイトル改善
  - 導入改善
  - H2順序の微調整
  - メタ説明文
  - 最終版 Markdown

## 18. 既存資産を活かした開発着手一覧

### 方針

「既存機能がないから新規実装」ではなく、**既存のどこを流用し、どこだけを足すか**を先に固定します。  
これにより、改修の影響範囲を狭くできます。

### 一覧

| 区分 | 対象ファイル | 現在の役割 | 活かし方 | 追加・変更内容 | 優先度 |
|---|---|---|---|---|---|
| 既存流用 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\blog_pipeline.py` | `01 → 02 → 03` のAI実行基盤 | 実行順制御とGemini呼び出しをそのまま使う | `031` `032` `033` を差し込める構造へ拡張 | 最優先 |
| 既存流用 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\01-writer-prompt.txt` | 初稿生成 | 既存のまま利用 | 必要ならSEO量産向けセクション追加 | 高 |
| 既存流用 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\02-editor-prompt.txt` | 編集工程 | 既存のまま利用 | 必要なら後で調整 | 中 |
| 既存流用 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\03-director-prompt.txt` | 最終品質調整 | 既存のまま利用 | `031` へ渡す前提で役割を明確化 | 高 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\031-best-outline-prompt.txt` | なし | 新規作成 | ベスト記事化の改善設計用 | 最優先 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\032-best-article-enhancer-prompt.txt` | なし | 新規作成 | ベスト記事本文の増強用 | 最優先 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\033-best-seo-polisher-prompt.txt` | なし | 新規作成 | SEO仕上げ用 | 高 |
| 既存流用 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\main.py` | 実行入口 | 実行導線を再利用 | 新フローの呼び出し条件を追加 | 高 |
| 既存流用 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\insert_affiliate_links.py` | アフィリエイト挿入 | 完成版記事の後処理として利用 | 入力記事が長文化しても壊れないか確認 | 中 |
| 既存流用 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\insert_amazon_affiliate.py` | Amazon導線付与 | 完成版記事の後処理として利用 | 新構造の見出しにも挿入できるか確認 | 中 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\collectors\rakko_suggest_collector.py` | なし | 新規作成 | サジェスト取得 | 高 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\analyzers\keyword_normalizer.py` | なし | 新規作成 | 表記ゆれ統一と重複除去 | 高 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\analyzers\keyword_intent_classifier.py` | なし | 新規作成 | Know / Do / Buy 分類 | 高 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\generators\keyword_variant_rewriter.py` | なし | 新規作成 | ベスト記事から量産記事へ変換 | 高 |

## 19. 着手順の計画

### Why

今回の開発は、キーワード取得、ベスト記事化、量産リライトの3本柱があります。  
ただし、全部を同時に触ると検証不能になるため、**既存資産に最も近いところから順に伸ばす**のが安全です。

### 着手順

1. `03` 後に `031` `032` `033` を差し込む設計を固定する
   - まずは既存の `blog_pipeline.py` の責務を崩さず、拡張点だけを決める
2. `031-best-outline-prompt.txt` を作る
   - 最初に「足りないものを指摘する段」を作ると、増強の方向がブレにくい
3. `032-best-article-enhancer-prompt.txt` を作る
   - `031` の改善方針を反映して、完成版ベスト記事を作る
4. 必要なら `033-best-seo-polisher-prompt.txt` を作る
   - SEO最終調整を独立段にする
5. `blog_pipeline.py` を改修する
   - `01 → 02 → 03 → 031 → 032 → 033 → 04` を切り替え可能にする
6. `main.py` を改修する
   - 新しいフローを既存の実行入口から呼び出せるようにする
7. `TEST\seo_factory` 側のサジェスト取得と分析基盤を作る
   - Playwright、正規化、意図分類を先に完成させる
8. ベスト記事完成後に、量産リライトへ進む
   - `keyword_variant_rewriter.py` でキーワード別記事を生成する
9. 最後に `04-affiliate-link-manager` との結合確認を行う
   - ベスト記事にも量産記事にも既存の収益化処理が通るかを見る

## 20. 実装フェーズの分け方

### フェーズA: 既存記事生成の強化

- `01`
- `02`
- `03`
- `031`
- `032`
- `033`

このフェーズの目的は、まず「ベスト記事1本」を安定して作れるようにすることです。

### フェーズB: キーワード収集と分析

- ラッコキーワード収集
- 正規化
- 意図分類
- クラスタ整理

このフェーズの目的は、ベスト記事へ渡す材料を安定供給することです。

### フェーズC: 量産リライト

- ベスト記事を母艦化
- 各キーワード向け見出し再構成
- 導入とFAQを個別化

このフェーズの目的は、量産時の品質劣化を抑えることです。

### フェーズD: 収益化接続

- `04-affiliate-link-manager`
- Amazon導線
- 将来の公開導線

このフェーズの目的は、完成記事をそのまま収益化工程へ流せるようにすることです。
