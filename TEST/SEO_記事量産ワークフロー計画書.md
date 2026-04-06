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
4. Antigravity Workflow から「取得 → シート保存 → 手動選別 → 母艦記事化」を再開できる

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
  - キーワードの Buy / Do / Know
  - 分類語彙と優先順
  - TSV 形式での出力

### 重要な判断

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\reference\suggest_keywords.js` は、そのまま移植するのではなく、**Python で新しく書き直す**方が安全です。  
ただし、DOMロジックだけでなく、**分類語彙・クエリ判定順・並び順のノウハウは流用**する。  
理由は、文字化けしたラベル群を無理に救済するより、Python で保守しやすく書き直したうえで、既存JSの運用知見だけを継承した方が安全だからです。

## 5. 全体アーキテクチャ案

### 全体像

```text
シードキーワード
  ↓
Playwright + Chromium でラッコキーワード取得
  ↓
Google Spreadsheet に保存
  ↓
ユーザーが状況列で手動選別
  ↓
スプレッドシート再読込
  ↓
正規化・重複除去・意図分類
  ↓
完成版記事の見出し設計
  ↓
母艦記事の本文生成
  ↓
キーワード別リライト
  ↓
品質チェック
  ↓
Markdown / JSON / CSV で保存
  ↓
Antigravity Workflow から手動再開
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
│  ├─ .gitignore
│  ├─ env\
│  │  └─ google-service-account.json
│  ├─ output\
│  │  └─ macbook_neo\
│  ├─ prompts\
│  │  ├─ 031-1-best-outline-prompt.md
│  │  ├─ 031-2-best-article-enhancer-prompt.md
│  │  └─ 031-3-kobetsu-writer-prompt.md
│  └─ scripts\
│     ├─ 031_1_keyword_pipeline.py
│     ├─ 031_2_master_article_generator.py
│     ├─ 031_3_kobetsu_writer.py
│     └─ 031_9_run_factory.py
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
- 生データは Google Spreadsheet と JSON の両方へ保存する
- 取得失敗時はスクリーンショットと HTML を保存する

### Google Spreadsheet 保存ルール

- 保存先: `https://docs.google.com/spreadsheets/d/1_qjAWcrgGHY8xTQdiUrK-v_gJsXEb8FH9ABUvEpcVMo/edit?gid=894792171#gid=894792171`
- タブ名: 取得したキーワード名
  - 例: `macbook neo`
- 保存位置: 右端タブ
- ヘッダー:
  - `キーワード`
  - `検索ボリューム`
  - `クエリタイプ`
  - `状況`
- ヘッダー装飾:
  - 黒塗り
  - 白文字
- `状況 = 不要` の行は後段で除外する
- それ以外の行は、ユーザーが手動で採用管理する

### 記事化対象の決め方

- 何を記事化するかはユーザーが決める
- 自動で `記事化` を確定しない
- スプレッドシート上で不要行を除外し、必要な行だけを再開時に使う
- 行数が多い場合は、ユーザーが手動で採用対象を絞る前提にする

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


### 期待する分析出力

- 検索者が知りたい論点一覧
- 比較したい論点一覧
- 購入前に不安な論点一覧
- 使い方・設定・トラブル解決系の論点一覧

### 不足論点の定義

この計画における「不足論点」は、AIが一般論として思いついた補足事項ではない。  
**不足論点とは、サジェストキーワードに明示されている、ユーザーがすでに知りたがっている疑問そのもの**を指す。

- 書き手が書きたい論点を足してはいけない
- サジェストに現れていない一般論だけで膨らませてはいけない
- 「不足しているかどうか」は、`03-director` 通過後の記事がサジェストキーワードに対する答えをすでに持っているかどうかで判定する
- 不足論点は必ずサジェストキーワード単位で洗い出す

### 前作サジェストの活用ルール

新製品や後継機種では、前作のサジェストキーワードが非常に重要な材料になる。  
ユーザーは新製品でも、前作で知りたかったことをほぼ同じように知りたがるためである。

#### 例

- `iPhone 17` の母艦記事を作る場合
  - `iPhone 17 + サジェスト語`
  - `iPhone 16 + サジェスト語`
  - この両方を洗い出して統合分析する

このとき、`iPhone 16` の後ろに出ているサジェスト語は、`iPhone 17` に対してもユーザーが聞きたい論点候補として扱う。  
たとえば `iPhone 16 バッテリー` `iPhone 16 発熱` `iPhone 16 サイズ` `iPhone 16 比較` が強ければ、`iPhone 17` の母艦記事でも同じ軸を必ず検討する。

### 分析の目的

- 現行製品のサジェストから、今そのまま聞かれている疑問を回収する
- 前作サジェストから、次世代製品でも高確率で引き継がれる疑問を回収する
- その両方を統合して、母艦記事へ足すべき不足論点を決める

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
- 見出しの順序はユーザー需要順を優先し、`Buy大 → Know大 → Buy中 → Know中 → Buy小` を先頭側へ寄せる

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

### 母艦記事の原則

母艦記事は、`03-director` までに生成された記事を捨てて作り直すのではない。  
**`03` までの本文と基本見出しを残したまま、サジェストキーワードに対する不足回答を追加して長文化し、網羅性を高めた完成版へ育てる**ものと定義する。

- `03` までの情報は原則として削除しない
- `03` までの基本見出し構造は大きく崩さない
- 追加する情報は、サジェストキーワードに対応する答えとして追記する
- 追加回答は、後段でサジェストごとのアンサー記事へ切り出しやすいように配置する

### 母艦記事で追加すべき内容

- サジェストキーワードごとの結論
- その結論を支える詳細説明
- 比較、評判、注意点、FAQの不足分
- 前作サジェスト由来の論点
- 後段の量産記事で独立見出し化しやすい補助小見出し

### 母艦記事の書式ルール

- 見出し直下で、紹介商品が解決する課題と解決方法を先に示す
- その後に短文の解説を置く
- 要点は箇条書きで整理する
- 箇条書きは体言止めにし、`です・ます` は使わない
- 各箇条書きは20字以内を目安に短くする
- 各箇条書きは必ず結論単語を文頭に置き、`結論語：説明` の形にする
- 最後に簡易まとめで章を締める

### 母艦記事で必ず触れる内容

- 見出しにある疑問への解決策
- 解決策の具体的なやり方・方法
- 比較、価格、評判、注意点のうち該当するもの
- 前作サジェスト由来で現行製品にも残る論点

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

### 量産記事の基本原則

量産記事は、母艦記事からサジェストキーワードへの答えを抽出し、**そのキーワードに対するアンサー記事**として再構成する。  
このとき、母艦記事で足したサジェスト回答を中心に使うが、`03` までの基本見出し構造は大きく崩さない。

- 記事冒頭で結論を先に書く
- その後に詳細を複数の小見出しへ分解して示す
- `03` までの基本見出しの骨格は維持する
- ただし、対象サジェストに合わせて小見出しや説明順は調整する
- 母艦から不要部分を削るだけでなく、対象サジェストに必要な答えを前面に出す
- 個別記事は、母艦記事の H2 構造と論点順をテンプレートとして流用する
- 別テンプレートで新規作文してはいけない
- 過不足検証で母艦に追加した不足回答を、個別記事でもそのまま引き継ぐ

### アンサー記事の理想形

- H1 で対象サジェストに答える
- 冒頭で結論を明示する
- 中盤で理由、比較、注意点を小見出しに分解する
- FAQ で残る不安を潰す
- 母艦記事の流れを壊しすぎずに対象疑問へ最短で答える

### 個別記事の絶対見出しルール

- 個別記事では、すべての H2 見出しに対象検索キーワードを必ず含める
- H2 見出しは必ず `対象検索キーワード：見出し名` の形にする
- 例:
  - `## macbook neo インディゴ：結論`
  - `## macbook neo インディゴ：選定基準`
  - `## macbook neo インディゴ：注意点`
- 対象検索キーワードを省略した H2 は許可しない
- H3 / H4 は使わず、個別記事の主要論点はすべて H2 で表現する

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

## 8. Antigravity Workflow 優先方針

### Why

今回の量産記事フローでは、途中でユーザーが手動選別する工程が重要です。  
そのため、最初から GitHub Actions へ寄せるより、**Antigravity Workflow で「途中停止と再開」がしやすい形を優先**します。

### 基本方針

- GitHub Actions 実装は保留する
- 初期版は Antigravity Workflow から手動起動する
- 初回は「収集してシート保存」で停止する
- ユーザーが Google Spreadsheet の `状況` 列を編集した後に再開する

### 想定フロー

1. `seed_keyword` を指定してラッコキーワード取得
2. Google Spreadsheet の右端タブへ保存
3. ユーザーが `状況` 列を手動更新
4. シートを再読込して母艦記事生成を再開
5. 量産記事生成へ進む

## 9. 無料運用方針

### Why

今回の条件では、`Google Ads` の登録を使わずに回せることが前提です。  
そのため、キーワード取得と記事生成のコストは切り分けて考える必要があります。

### 無料で進めやすい部分

- Playwright + Chromium によるブラウザ操作
- Antigravity Workflow の手動実行
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
2. 取得キーワードを Google Spreadsheet の右端タブへ保存できる
3. ユーザーが `状況` 列で不要キーワードを手動除外できる
4. スプレッドシート再読込後に母艦記事の見出しを1本生成できる
5. スプレッドシート再読込後に母艦記事本文を1本生成できる
6. 後段で量産記事へ分岐しやすい構造を保てる

## 12. 実装ステップ

### ステップ1

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_1_keyword_pipeline.py` を作成し、Playwright での全ページ取得、正規化、`Know / Do / Buy` 分類、Google Spreadsheet 保存と再読込を1本へ統合する

### ステップ2

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_2_master_article_generator.py` を作成し、完成版見出し生成と母艦記事生成を1本へ統合する

### ステップ3

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_3_kobetsu_writer.py` を作成し、母艦記事を使った派生記事を量産する

### ステップ4

`C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_9_run_factory.py` を作成し、Antigravity Workflow から「取得して停止」「シート再読込で再開」を一気通貫で実行できるようにする

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

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\reference\suggest_keywords.js` は、DOM走査だけでなく、分類語彙と並び順のノウハウも流用する
- `Buy大 → Know大 → Buy中 → Know中 → Buy小` の順序を Python 側でも維持する
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
  - `03` 完了記事を読み、サジェストキーワードに対する未回答部分だけを洗い出す
- `032-best-article-enhancer`
  - `031` の改善方針を反映して、`03` までの情報を削らずに、サジェストの答えを追加した母艦記事へ増強する
- `033-best-seo-polisher`
  - タイトル、導入、見出し順、強調点、メタ説明文をSEO向けに最終調整する
- `04-affiliate-link-manager`
  - 既存どおり、アフィリエイト挿入とAmazon導線を付与する

### スプレッドシートの「量産元」分岐

今回の運用では、Googleスプレッドシートの `状況` 列の値によって、通すパイプラインを切り替える。

- `単品`
  - 通常フロー
- `複数`
  - 通常フロー
- `情報`
  - 通常フロー
- `量産元`
  - ベスト記事化付きフロー

### フロー分岐の定義

#### 通常フロー

```text
01-writer
  ↓
02-editor
  ↓
03-director
  ↓
04-affiliate-link-manager
```

#### 量産元フロー

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
04-affiliate-link-manager
```

### 量産元フローの意図

- `量産元` の記事は、通常記事として完結させることが目的ではない
- キーワード別量産の母艦になる完成版記事を作ることが目的である
- そのため、`03` の通常完成記事を一度ベースにした上で、`031` と `032` で網羅性と派生性を強化する
- その後に `04` のアフィリエイト処理へ渡す

### 量産元フローで強化する内容

- `031` では、`03` 記事が未回答のサジェスト論点を列挙する
- `032` では、その未回答論点の答えを記事へ追加し、長くても網羅的な母艦記事に仕上げる
- 追加対象は一般論ではなく、サジェストキーワードでユーザーが実際に知りたがっている論点に限定する
- 前作モデルのサジェストも、現行モデルの母艦づくりに活用する

### プロンプト分岐の定義

- `状況 = 単品`
  - `01-writer-prompt.txt` の `[単品]` を使用
- `状況 = 複数`
  - `01-writer-prompt.txt` の `[複数]` を使用
- `状況 = 情報`
  - `01-writer-prompt.txt` の `[情報]` を使用
- `状況 = 量産元`
  - `01-writer-prompt.txt` の `[量産元]` を使用
  - その後、`031-best-outline-prompt.txt`
  - その後、`032-best-article-enhancer-prompt.txt`

### 実装対象ファイル

この分岐仕様を実現する主な対象ファイルは以下とする。

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\main.py`
  - スプレッドシートの `状況` を受け、通常フローか量産元フローかをログとともに判定する
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\sheets_reader.py`
  - 処理対象ステータスに `量産元` を含める
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\modules\blog_pipeline.py`
  - `status == "量産元"` のときだけ `03` 後に `031` `032` を実行する
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\01-writer-prompt.txt`
  - `[量産元]` セクションを追加する
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\031-best-outline-prompt.txt`
  - 量産元記事の補強設計を行う
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\032-best-article-enhancer-prompt.txt`
  - ベスト記事へ増強する

### 将来拡張の方針

- さらにSEO仕上げを追加する場合は `033-best-seo-polisher` を増設する
- ただし、`量産元` の基本分岐は常に `03` の後ろに追加段を差し込む方式で統一する
- `04-affiliate-link-manager` は後処理専用として固定する

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
  - 現行製品の対象サジェストキーワード群
  - 前作製品の対象サジェストキーワード群
  - 必要なら検索意図分析結果
- 出力:
  - サジェスト単位の未回答論点一覧
  - 既存見出しで回答済みかどうかの対応整理
  - 追加すべき小見出し
  - 前作サジェスト由来で継承すべき論点
  - FAQ候補

#### 032-best-article-enhancer-prompt

- 入力:
  - `03` の記事全文
  - `031` の改善提案
- 出力:
  - `03` までの情報を残したまま、不足回答を追記して完成させた母艦記事の Markdown 全文

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
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\032-best-article-enhancer-prompt.txt` | なし | 新規作成 | `03` までの本文を残したままサジェスト回答を追加する母艦化用 | 最優先 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\033-best-seo-polisher-prompt.txt` | なし | 新規作成 | SEO仕上げ用 | 高 |
| 既存流用 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\main.py` | 実行入口 | 実行導線を再利用 | 新フローの呼び出し条件を追加 | 高 |
| 既存流用 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\insert_affiliate_links.py` | アフィリエイト挿入 | 完成版記事の後処理として利用 | 入力記事が長文化しても壊れないか確認 | 中 |
| 既存流用 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\04-affiliate-link-manager\insert_amazon_affiliate.py` | Amazon導線付与 | 完成版記事の後処理として利用 | 新構造の見出しにも挿入できるか確認 | 中 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_1_keyword_pipeline.py` | なし | 新規作成 | ラッコ取得・正規化・意図分類・Google Spreadsheet 連携を統合 | 高 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_2_master_article_generator.py` | なし | 新規作成 | 見出し生成と母艦記事生成を統合 | 高 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_3_kobetsu_writer.py` | なし | 新規作成 | 母艦記事から個別記事を生成 | 高 |
| 新規追加 | `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_9_run_factory.py` | なし | 新規作成 | 取得→停止→再開→記事生成の実行入口 | 高 |

## 19. 着手順の計画

### Why

今回の開発は、キーワード取得、ベスト記事化、量産リライトの3本柱があります。  
ただし、全部を同時に触ると検証不能になるため、**既存資産に最も近いところから順に伸ばす**のが安全です。

### 着手順

1. `03` 後に `031` `032` `033` を差し込む設計を固定する
   - まずは既存の `blog_pipeline.py` の責務を崩さず、拡張点だけを決める
2. `031-best-outline-prompt.txt` を作る
   - 最初に「サジェストに対して未回答なものだけを指摘する段」を作ると、増強の方向がブレにくい
3. `032-best-article-enhancer-prompt.txt` を作る
   - `031` の改善方針を反映して、`03` までの本文を残しつつ、完成版ベスト記事へ育てる
4. 必要なら `033-best-seo-polisher-prompt.txt` を作る
   - SEO最終調整を独立段にする
5. `blog_pipeline.py` を改修する
   - `01 → 02 → 03 → 031 → 032 → 033 → 04` を切り替え可能にする
6. `main.py` を改修する
   - 新しいフローを既存の実行入口から呼び出せるようにする
7. `TEST\seo_factory` 側のサジェスト取得と分析基盤を作る
   - Playwright、正規化、意図分類を先に完成させる
8. ベスト記事完成後に、量産リライトへ進む
   - `031_3_kobetsu_writer.py` でキーワード別記事を生成する
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

### フェーズCで守るべき制約

- 量産記事は母艦から対象サジェストの答えを抽出して作る
- 記事冒頭に結論を書く
- その後に小見出しで詳細を分解して示す
- `03` までの基本見出し骨格は大きく崩さない

### フェーズD: 収益化接続

- `04-affiliate-link-manager`
- Amazon導線
- 将来の公開導線

このフェーズの目的は、完成記事をそのまま収益化工程へ流せるようにすることです。

## 21. 現在の到達点

### Why

計画だけでなく、**2026-04-06 時点でどこまで実装と検証が終わっているか**を残しておくことで、次回の再開時に迷わず続きへ入れるようにするためです。  
特に PoC は進みが速いため、到達点を計画書へ固定しておくと、実装済みと未着手を混同しにくくなります。

### 実装済み

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_1_keyword_pipeline.py`
  - ラッコキーワードの現行 DOM に対応した Playwright 収集器を実装済み
  - 表記ゆれ整理、重複除去、収集結果の整形を実装済み
  - `Know / Do / Buy` の3分類を実装済み
  - `Compare` は `Buy`、トラブル系は `Know` に寄せる方針を反映済み
  - Google Spreadsheet の右端タブ保存と再開読込を実装済み
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_2_master_article_generator.py`
  - サジェスト起点で母艦記事用の見出し案を生成可能
  - `03` 相当の土台記事生成と、`031 / 032` による母艦記事化ロジックを実装済み
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_3_kobetsu_writer.py`
  - 母艦記事から個別記事を生成する量産器を実装済み
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_9_run_factory.py`
  - 取得 → シート保存 → 再開読込 → 見出し生成 → 母艦記事生成 → 個別記事生成の流れへ改修済み
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\prompts\031-1-best-outline-prompt.md`
  - 不足論点 = サジェストキーワード由来の未回答論点、という定義を反映済み
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\prompts\031-2-best-article-enhancer-prompt.md`
  - 入力記事の良い本文を残しつつ、母艦記事として追記強化する方針を反映済み
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\prompts\031-3-kobetsu-writer-prompt.md`
  - 個別記事では各 H2 が必ず `対象検索キーワード：見出し名` で始まるルールを反映済み

### 実サイト確認済み

- ラッコキーワード実サイトで `macbook neo` を対象に Playwright 実行済み
- 全ページ巡回を確認済み
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\reference\suggest_keywords.js` のノウハウを Python 側へ流用済み
  - `kubunMap`
  - `Buy → Do → Know` の判定順
  - `Buy大 → Know大 → Buy中 → Know中 → Buy小` の優先順

### 出力済み成果物

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\macbook_neo\current_keywords.json`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\macbook_neo\outline.json`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\macbook_neo\outline.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\macbook_neo\base_article.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\macbook_neo\master_article.md`
- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\macbook_neo\031_enhancement_plan.md`

## 22. 未完了と差分

### Why

「できたこと」だけを書くと再開地点を誤るため、**未完了と差分も同じ場所に残す**必要があります。  
これにより、次回は作業の続きを正しく始められます。

### 現在の未完了

- 前作キーワード統合の実運転
  - `--previous-seed-keyword` を使った本番相当の確認は未実施
- Antigravity Workflow からの再開確認
  - 取得停止 → シート編集 → 再開の実運転は未実施

### 現在の差分

- 記事化対象は自動判定ではなく、Google Spreadsheet の手動選別へ変更した
- `状況 = 不要` の除外ロジックを優先し、それ以外の行は後段へ流す方式にしている
- GitHub Actions ではなく Antigravity Workflow 優先へ方針変更した
- no-LLM 実行は下書き保存だけに制限し、完成記事と個別記事を上書きしない方針へ切り替えた

## 23. 次の再開地点

### Why

次回の着手時に迷わないよう、**次にやるべき順番を固定**しておきます。  
これにより、検証順を崩さずに安全に先へ進めます。

### 次にやること

1. Google Spreadsheet の対象タブで `状況` 列を手動入力する
2. `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_9_run_factory.py --resume-from-sheet` で再開する
3. no-LLM 実行では `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\output\...\031_base_article_draft.md` だけが更新され、`master_article.md` と `variants` が上書きされないことを確認する
4. 完成記事の更新が必要なときは、手動編集または LLM 実行のどちらで仕上げるかを明示してから進める
5. その後に `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\scripts\031_3_kobetsu_writer.py` を使い、量産記事生成へ進む

## 24. ルール集の固定

### Why

ここまでのやり取りで、禁止事項や品質基準が複数ファイルへ分散し、同じ違反を繰り返しやすい状態になった。  
そのため、恒久参照先としてルール集を1か所へ固定する必要がある。

### 参照先

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\prompts\promptreference.md`

### このルール集で固定したこと

- 入力記事の良い本文は壊さず残す
- 追加対象は検索キーワードで不足している部分のみ
- 一般論で膨らませない
- 採用されたSEOキーワードごとに綿密な調査が必要
- 調査の深さこそ記事の差別化要因である
- 冒頭の結論は調査結果の要約でなければならない
- 正式名称は公式表記へ完全一致させる
- 個別記事の H2 は必ず `対象検索キーワード：見出し名`
- H2直下の最初の1文は、必ずその見出しキーワードを自然に含めて始める
- `おすすめ` 見出しは、商品推薦ではなく選定基準を渡す記事として書く
- AIメタ文と制作裏話を本文へ出さない
- 箇条書きは短くても意味が通る説明にする
- `状況` 空欄行も処理対象に含める
- no-LLM 実行では完成記事を上書きしない

## 25. 2026-04-06 時点の追加進展

### 進展

- `C:\Users\HCY\OneDrive\開発\Blog_Vercel\promptreference.md` を新規作成し、指摘・禁止事項・現状を集約した
- 以下のプロンプトへ、調査必須・正式名称・一般論禁止・既存本文尊重・AIメタ文禁止を追記した
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\031-best-outline-prompt.txt`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\scripts\pipeline\prompts\032-best-article-enhancer-prompt.txt`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\prompts\031-1-best-outline-prompt.md`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\prompts\031-2-best-article-enhancer-prompt.md`
  - `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\seo_factory\prompts\031-3-kobetsu-writer-prompt.md`
- シート `macbook neo` タブの採用キーワードは 4 件へ増加した
  - `macbook neo ケース おすすめ`
  - `macbook neo シルバー レビュー`
  - `macbook neo 先行 レビュー`
  - `macbook neo 学割 価格`

### 現状の問題点

- 母艦記事はまだ調査の深さが足りず、冒頭結論の固有価値が弱い
- 個別記事は母艦記事の調査不足を引き継ぐため、全体として情報密度が不足しやすい
- no-LLM 実行では仮テンプレしか出せないため、完成記事扱いにしてはいけない
- 以後の改善は、採用キーワードごとに調査した具体情報を母艦記事へ入れることが最優先

### 次の優先作業

1. スプシの採用 4 キーワードごとに調査論点を整理する
2. 公式表記を揃える
3. 調査結果を母艦記事の冒頭結論と該当 H2 へ反映する
4. その母艦を使って個別記事を再生成する
