# 周辺機器記事生成機能 実装計画・開発進捗書

- 文書作成日: 2026-08-12
- 最終更新日: 2026-08-12
- 状態: 設計計画第5版作成済み・実装未着手
- 仕様書: `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/docs/accessories_spec.md`
- 対象リポジトリ: `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel`
- MLX関連資産: `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX`
- 既存MLX記事生成本体: `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog`

## 1. この文書の目的

既存の親記事から複数の周辺機器記事を生成し、OneDriveへ保存してBlog Vercelで閲覧・編集・予約投稿できる機能を段階的に実装する。

この文書は実装計画と開発進捗の正本を兼ねる。各作業を完了したら、進捗表、検証結果、開発履歴を同時に更新し、現在地と残作業を一つの文書で判断できる状態を維持する。

## 2. 最終目標

Blog Vercelの左サイドパネルにある親記事を右クリックし、生成エンジンとして `MLX` または `Gemini` を指定すると、次の処理が行われる状態を完成とする。

1. 親記事の本文とメタ情報を取得する。
2. Googleスプレッドシートの `周辺機器DB` と照合して子記事カテゴリ候補を表示する。
3. 右クリックした記事を親記事として固定し、ユーザーがチェックボックスで生成対象カテゴリを複数選択する。
4. 選択カテゴリごとに一つのOneDriveジョブJSONと、`周辺機器DB_LLM`の一行を登録する。
5. 親記事を複製し、選択したエンジンだけで冒頭案内文と、親製品を主語にするための最小限の商品紹介文調整を生成する。
6. OneDriveのBlog Vercel記事ルート直下にある `周辺機器` フォルダへ子記事群だけを保存する。
7. 子記事Markdownには公開本文だけを書き、Frontmatter、YAML、JSON、SEO管理値、ジョブ情報などの管理情報を一切混入させない。
8. H1と既存SEO形式のH2をカテゴリ向けに変換し、親記事の結論以外の本文、章数、階層、順序、既存リンクを維持する。
9. 対象商品群の全商品を結論だけへ追加し、商品リンクまとめは生成しない。
10. `周辺機器DB_LLM`で作成日時、完了日時、子記事タイトル、進捗、記事リンク、親記事を一覧確認できる。
11. 最初の実装段階から、Blog Vercelで生成条件、対象カテゴリ、対象商品群、使用プロンプト、進捗、完成記事を確認できる。
12. MLX自動処理に失敗しても、登録済みジョブをMacの`.command`から選んで同じ処理を手動復旧できる。
13. 生成後の子記事は、既存UIのnote即時投稿・手動予約をそのまま利用できる。

## 3. 現行実装の調査結果

### 3.1 Blog Vercel

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/pipeline/main.py` は、入力取得、AI生成、アフィリエイト挿入、OneDrive保存を実行する。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/pipeline/modules/blog_pipeline.py` はGeminiによる多段生成とAPIキー切替を持つ。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/gemini_runtime.py` はGemini呼び出しを共通化している。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/articles.js` はOneDrive内のMarkdownとサブフォルダを扱える。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/index.html` はフォルダ表示、記事編集、複数選択、移動、note投稿予約に対応している。
- 現在の新規記事保存APIはルートフォルダ保存が基本であり、`周辺機器` サブフォルダへの新規保存機能は追加が必要である。
- 現在の一覧表示はOneDriveのフォルダ階層を表示できるが、記事外の親子関係管理JSONを解釈した論理的な親子表示は行っていない。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/index.html` には、記事の右クリックコンテキストメニュー、選択モード、記事チェックボックスがすでにある。一方、「周辺機器記事作成」と専用モーダルは未実装である。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api` 直下には現在12個のJavaScript APIがあり、直接配置型のVercel Function数も12になる構成である。
- Vercel公式仕様ではHobbyプランの直接配置型Functionsは1デプロイ12個までであり、新しいAPIファイルを単純追加する余裕はない。
- `https://blog-vercel-dun.vercel.app/` がVercel本番環境からHTTP 200を返すことは2026-08-12に確認した。
- Vercel CLIには認証情報がなく、ダッシュボード内の契約プラン表示と使用量メーターは確認できていない。Function上限の判断はVercel公式仕様とリポジトリ内の実ファイル数に基づく。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/trigger-info-viewer.js` はinfo_viewer専用であり、ユーザー指示により周辺機器APIの枠として置換できる。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/info-viewer.js` はnote投稿ワークフローからも条件付き参照があるため、不要な影響を避けて当面維持する。

### 3.2 MLX

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX` はMLXサーバーやDiscord経由起動の入口である。
- 実際の記事生成処理は `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/MLX/run_geamma4_blog_mlx.py` にある。
- MLXはOpenAI互換の `/v1/chat/completions` を利用し、モデル検出、ストリーミング、再試行、文字数・H2数などの品質検査を実装済みである。
- 現行MLXは最終段ではなく、記事作成前の `Step00` で `seo_keyword`、`brand`、`model`、`description`、`reason`、`source` を生成し、`locked_seo` として後続工程へ引き継ぐ。
- 最終の `Step3` 後は本文抽出、SEO正規化、アフィリエイト挿入、ファイル名生成、OneDrive保存、実行レポートJSON保存を行う。
- 現行の完成Markdown自体にはYAML Frontmatterが付かない。この本文専用形式を維持し、周辺機器の管理情報も完成Markdownへ追加しない。
- 現存する過去の最終Markdownの中には本文先頭に `【思考プロセス】` が残ったものがあるため、周辺機器記事の最終検査では内部思考、作業説明、採点ログを明示的に不合格とする。
- 既存MLX処理はGoogle Sheetsの商品行を入口とするため、Blog Vercelで選択した親記事を直接受け取る専用モードは追加が必要である。
- MLXはMacのlocalhostで動作する。インターネット上のVercelから、家庭内Macのlocalhostへ直接HTTP接続することは通常できない。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/start_mlx.command` は、必要なPython・実行スクリプトを検査し、MLXサーバーを起動して記事生成を実行し、ログと保存先を日本語表示できている。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_MLX_discrod.command` は `--server-only` でlocalhostのMLXモデルサーバーだけを確認・起動できる。
- 周辺機器専用の `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/accessories_worker.py` と `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command` はまだ存在しない。

### 3.3 Gemini

- GitHub Actions上でGeminiだけを使って記事生成からOneDrive保存まで実行する基盤がすでにある。
- 既存の通常記事プロンプトは周辺機器記事専用ではないため、周辺機器向けの抽出、構成、品質検査を独立モジュールとして追加する必要がある。
- Gemini APIキーはVercelまたはGitHub Actionsのサーバー側Secretだけで扱い、ブラウザへ返さない。

### 3.4 サンプル記事

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/docs/accessories_sample_article.md`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/docs/accessories_sample_article_goal_example copy.md`

上記2ファイルは現時点で同一内容である。iPad本体記事の中にキーボード、保護フィルム、ケース、充電器などが混在している。ただし第一ゴールではカテゴリ特化記事へ全面改稿せず、親記事を複製し、H1・既存SEO形式のH2・結論だけを対象カテゴリ向けに変更するための参考入力として利用する。

## 4. 採用する基本設計

### 4.1 生成エンジンは独立完結させる

`MLX` と `Gemini` は前工程・後工程として連結しない。ジョブ作成時の `engine` により一方だけを選び、選ばれたエンジンが全工程を単独で完結させる。

| エンジン | 実行場所 | 単独で担当する範囲 |
| --- | --- | --- |
| `mlx` | Macローカル | 親記事解析、カテゴリ判定、プロンプト適用、子記事生成、品質検査、本文専用Markdownと管理JSONの分離保存 |
| `gemini` | GitHub Actions | 親記事解析、カテゴリ判定、プロンプト適用、子記事生成、品質検査、本文専用Markdownと管理JSONの分離保存 |

共通にするのは入力ジョブ形式、マスタ、テンプレート、出力形式、品質基準だけとする。片方が停止しても、もう片方の実行経路には影響させない。

### 4.2 Blog VercelからローカルMLXを動かす方式

VercelからMacへ直接接続する代わりに、Googleスプレッドシートの `周辺機器DB_LLM` をユーザー向けキュー兼一覧、OneDriveジョブJSONを不変な実行内容・ロックの正本として使う「Mac側ポーリング方式」を採用する。

MLXジョブを登録する前にクライアントがMacであることを確認する。Windowsでは「MLXで作成」を無効化してAPIを呼ばず、Geminiだけを利用可能にする。Macではワーカーheartbeatも確認し、有効なら自動処理を優先する。heartbeatが失効していてもOneDriveジョブJSONと `周辺機器DB_LLM` の `記事化` 行までは登録し、「自動処理は待機中・`.command`で手動復旧可能」と表示する。

```text
Blog Vercel画面
  ↓ 親記事・カテゴリ・engine=mlxを指定
Vercel API
  ↓ 選択カテゴリごとにOneDriveへジョブJSONを保存
Blog_Vercel_Accessories_Control/jobs/<job_id>.json（state=pending）
  ↓ 同じjob_idで周辺機器DB_LLMへ1子記事1行を登録（進捗=記事化、生成エンジン=MLX）
Googleスプレッドシート「周辺機器DB_LLM」
  ↓ Mac側ワーカーが記事化行を定期取得し、job_idでOneDriveジョブを取得・ロック
ローカルMLXワーカー
  ↓ localhostのMLX APIで生成
<ONEDRIVE_FOLDER>/周辺機器/<YYYYMMDD_HHMM_親記事タイトル冒頭20文字>/へ子記事Markdownを保存
  ↓ OneDriveジョブと周辺機器DB_LLMを更新
Blog_Vercel_Accessories_Control/jobs/<job_id>.json（state=completed）
周辺機器DB_LLM: 完了日時・進捗=完了・記事URLリンク
  ↓
Blog Vercel画面が状態と生成記事を再取得
```

この方式を選ぶ理由:

- Macの受信ポートをインターネットへ公開しなくてよい。
- 固定IP、ルーター設定、トンネルサービスが不要である。
- Vercelの実行時間制限と、時間のかかるローカル生成を分離できる。
- OneDrive認証と保存経路を既存資産から再利用できる。
- MacやMLXが停止中でもジョブが消えず、再起動後に続行できる。
- `job_id` により二重生成を防ぎ、失敗内容もBlog Vercelから確認できる。
- ユーザーは `周辺機器DB_LLM` だけを見れば、作成対象、成功、失敗、記事リンクを一覧確認できる。
- 自動ワーカーが動かなかった場合も、同じ行とジョブを`.command`から処理できる。

Mac側自動ワーカーの動作:

1. 15秒間隔を初期値として `周辺機器DB_LLM` の `進捗=記事化` かつ `生成エンジン=MLX` を確認する。
2. 行のジョブIDでOneDriveジョブJSONを取得し、原子的に `processing` 扱いへ移すかロック情報を書き込む。
3. 指定された親記事をOneDriveから取得する。
4. MLXのモデル一覧とヘルスチェックを行う。
5. 一ジョブ一カテゴリを順次生成する。初期実装ではMacのメモリ圧迫を避けるため並列生成しない。
6. 記事を品質検査し、合格した記事だけ保存する。
7. OneDriveジョブJSONを `completed` または `failed` へ更新する。
8. 成功時はシートへ完了日時、`完了`、記事URLを、失敗時は `失敗` と公開可能なエラー概要を更新する。
9. 同じ `job_id` を再取得しても完成済み記事を重複作成しない。

Macログイン時の自動起動は `launchd` を使用する。シェルを開き続ける運用には依存させない。初期実装ではトンネル方式を採用せず、必要性が確認された場合だけ将来選択肢として再評価する。

#### 4.2.1 `.command`によるMLX手動復旧

自動ワーカーで処理できない場合に備え、次のダブルクリック用入口を必須実装する。

`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command`

このコマンドは、既存 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/start_mlx.command` の絶対パス検査、ログ、終了表示と、既存 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_MLX_discrod.command --server-only` のMLX起動方法を再利用する。既存コマンド自体は変更しない。

手動モードの処理:

1. `周辺機器DB_LLM` のMLX向け `記事化` 行を取得する。
2. 作成日時、記事タイトル、対象周辺機器、大元記事タイトル、大元記事リンク、ジョブIDを番号付きで表示する。
3. 候補なしなら記事やカテゴリを推測せず終了する。
4. 複数候補はユーザーが番号で選択し、選択後に対象を再表示する。
5. ジョブIDでOneDriveの `pending` または再試行可能な `failed` ジョブJSONを取得し、スキーマ、プロンプトSHA-256、マスタ行スナップショット、現在状態を検査する。
6. 有効な別ワーカーのlease、完了済みジョブ、再試行不能エラーは処理せず理由を表示する。
7. MLXサーバーを確認・起動し、自動ワーカーと同じ関数でロック、生成、検査、保存、シート更新を行う。
8. 成功時は保存先と記事URL、失敗時は公開可能なエラー概要とログの絶対パスを表示する。

`.command`は自動ワーカーの代替実装ではなく、同じ `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/accessories_worker.py` を手動一回実行モードで呼ぶ薄い起動ラッパーとする。自動・手動が同時起動してもOneDriveのETag条件更新、lease、冪等性キーで一方だけが処理権を取得する。

### 4.3 Geminiの実行方式

`engine=gemini` の場合は、Blog Vercelが `周辺機器DB_LLM` へ `進捗=記事化`、`生成エンジン=Gemini` の行を登録し、専用GitHub Actionsを `workflow_dispatch` で起動する。GitHub Actionsは対応するOneDriveジョブJSONを取得・ロックし、Geminiだけで全工程を実行して子記事を保存し、シートを `完了` または `失敗` へ更新する。

MLX用キューと同じジョブ形式を使うが、処理主体はGitHub Actionsとする。これによりUI、マスタ、保存形式を共通化しながら、実行経路は独立させる。

### 4.4 Vercel Function枠の維持

Vercel Hobbyの12 Functions上限を超えないことを実装上の必須条件とする。

採用するAPI構成:

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/trigger-info-viewer.js` を廃止し、その1枠を `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js` へ置換する。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/trigger-accessories.js` は作らない。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js` の1ファイル内で、カテゴリ候補取得、商品群プレビュー、プロンプト一覧・取得・保存・削除、MLX heartbeat確認、ジョブ登録、Gemini workflow起動、ジョブ状態取得、生成済み子記事取得をHTTPメソッドと `action` で分岐する。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/info-viewer.js` は、既存noteワークフローの条件付き参照を保護するため当面残す。
- 変更後も `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api` 直下を12ファイル以下に保つ自動検査を追加する。

置換により `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/info_viewer/index.html` のパイプライン起動操作は利用できなくなる。ユーザーはinfo_viewerを使用していないため許容するが、既存の閲覧APIとnote投稿互換に使われる `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/info-viewer.js` は維持する。

根拠となるVercel公式資料:

- `https://vercel.com/docs/functions/runtimes`
- `https://vercel.com/docs/limits`

### 4.5 公開本文と管理情報の完全分離

子記事Markdownは、Blog Vercelで編集し、公開・note投稿する本文だけを保持する。管理の都合でFrontmatter、YAML、JSONヘッダー、HTMLコメント、不可視文字へ情報を埋め込むことも禁止する。

エンジン内部の結果は `article_markdown` と `management_metadata` を別フィールドとして扱い、保存関数には `article_markdown` だけを渡す。LLMの生応答全体をそのまま保存するフォールバック、先頭・末尾を雑に切り取って本文扱いするフォールバック、メタ情報と本文の文字列連結を実装しない。MLX/Gemini各エンジン内の検査に加え、共通保存層でも同じ禁止検査を必ず再実行する。

記事へ書かない情報:

- `parent_id`、OneDrive item ID、元パス
- `job_id`、状態、試行回数、worker ID
- `generation_engine`、モデル名
- プロンプトID、改訂番号、テンプレートrevision
- SEOキーワード、メタディスクリプション管理値、採点結果
- 商品群ID、ASIN一覧、生成時刻、内部思考、作業ログ

これらは記事ルート外の管理用JSONだけへ保存する。完成Markdownの最初の空白でない行は必ず一つだけのH1とし、UTF-8 BOM、Frontmatter、YAML文書区切り、JSON包み、記事全体を囲うコードフェンス、プロンプト復唱を許可しない。

異常な出力を自動削除して合格扱いにすると誤削除を見逃すため、違反を検出した結果は保存しない。同じ生成エンジンで再生成し、最大回数を超えた場合はカテゴリ単位で失敗にする。決定的に挿入するアフィリエイト本文も含め、OneDrive保存直前の最終成果物を再検査する。

### 4.6 開発前状態への復元保証

周辺機器機能のアプリケーション実装前に、次の復元点を作成済みである。

- 開発前コミット: `e91127abd28450a024b147855d0404722a3e8dbc`
- 復元タグ: `pre-accessories-runtime-20260812-e91127a`
- 復元記録: `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel_restore/pre_accessories_20260812/RESTORE.md`
- Git bundle: `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel_restore/pre_accessories_20260812/Blog_Vercel_pre_accessories.bundle`
- 未追跡資料: `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel_restore/pre_accessories_20260812/untracked_docs`

`git bundle verify`、タグ参照、SHA-256を検証済みである。さらにbundleを `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel_restore/pre_accessories_20260812/restore_verification` へ実際にcloneし、HEADが開発前コミットと一致し、追跡対象の作業ツリーがcleanであることを確認済みである。復元時は現行リポジトリへ直接上書きせず、bundleから別の絶対パスへ復元して比較・動作確認した後に反映する。

## 5. データ設計

### 5.1 周辺機器ルールマスタ

正本:

- GoogleスプレッドシートID: `1ioLnPe9z6vO0tuN3I_qcDi6buS8GCaYowbjq8LTOT94`
- タブ名: `周辺機器DB`
- gid: `287376508`

ユーザーが直接編集するこのタブを唯一の正本とし、`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/accessories/data/accessory_master.csv` は作らない。実行高速化のため一時キャッシュを作る場合もユーザー管理用DBとはせず、取得元スプレッドシートID、タブ名、取得日時、内容SHA-256を付け、シート取得成功時にだけ更新する。

列定義:

| スプレッドシート列 | 必須 | 内容 |
| --- | --- | --- |
| 親製品検出キーワード | 必須 | 親記事との照合語 |
| 周辺機器カテゴリID | 必須 | 安定したカテゴリID |
| 周辺機器カテゴリ名 | 必須 | UI表示名 |
| タイトル形式 | 必須 | 子記事タイトルのひな型 |
| アフィリエイトセクション | 必須 | `affiliate_links.txt` 内のおすすめ商品群名。例: `battery`、`cable` |
| デフォルト有効 | 必須 | 生成画面で初期選択するか |
| 使用テンプレートファイル | 必須 | 使用するMarkdownテンプレート |
| 表示優先度 | 任意 | 候補表示順 |

照合は大文字小文字と全角半角を正規化し、同じ周辺機器カテゴリIDは一件にまとめる。複数キーワード一致時も同一カテゴリの記事を重複生成しない。空行、不正な真偽値、重複ID、存在しないテンプレート、存在しないアフィリエイトセクションがある場合は、Blog Vercelの候補取得を失敗させて日本語で該当行を表示する。

ジョブ登録時に使用行の全値、スプレッドシートID、タブ名、取得行番号、内容SHA-256をOneDriveジョブJSONの `master_snapshot` へ固定する。生成実行時は `周辺機器DB` を再読込して値を差し替えず、登録済みスナップショットを使う。

### 5.2 `周辺機器DB_LLM`記事化キュー・進捗一覧

正本となるスプレッドシートは `周辺機器DB` と同じで、タブ名を `周辺機器DB_LLM` とする。このタブはGemini・MLX共通の処理候補一覧であり、ユーザー向けの生成履歴一覧でもある。

一つの子記事につき一行を登録する。右クリック画面で三カテゴリを選択した場合は、同じバッチIDを持つ三行と三つのOneDriveジョブJSONを作る。これにより記事ごとに失敗・完了・URLを管理できる。

先頭列はユーザー指定の順序に固定する。

| 順番 | 列 | 書込主体 | 規則 |
| --- | --- | --- | --- |
| 1 | 作成日時 | Blog Vercel | ジョブと行を確定した日時 |
| 2 | 完了日時 | Gemini・MLX | 記事保存成功時だけ設定。失敗時は空欄 |
| 3 | 記事タイトル | Blog Vercel | 生成予定タイトル。完成後も同じ値を維持 |
| 4 | 進捗 | Blog Vercel・各ワーカー・ユーザー | `記事化`、`失敗`、`完了`だけを許可 |
| 5 | 記事URLリンク | Gemini・MLX | 完了した子記事のリンク。未完了・失敗は空欄 |
| 6 | 大元記事タイトル | Blog Vercel | 親記事タイトル |
| 7 | 大元記事リンク | Blog Vercel | 親記事のリンク |

右側へ次の運用列を追加する。

| 列 | 表示 | 内容 |
| --- | --- | --- |
| 対象周辺機器 | 表示 | バッテリー、ケーブルなど、何を記事化するか |
| 生成エンジン | 表示 | `MLX` または `Gemini` |
| エラー概要 | 表示 | 秘密情報を除いたユーザー向け失敗理由 |
| ジョブID | 非表示可・削除禁止 | OneDriveジョブJSONとの一対一キー |
| バッチID | 非表示可・削除禁止 | 同じ右クリック操作で作った複数行のグループキー |

進捗運用:

- `記事化`: 生成対象。処理中もこの値を維持し、詳細状態はOneDriveジョブJSONで管理する。
- `失敗`: 生成、検査、記事保存のいずれかで失敗した状態。エラー概要を設定する。記事保存後のシート更新失敗は記事生成の失敗とせず、OneDriveジョブJSONの `registry_sync=pending` として同じ完了日時・記事URLの再同期だけを行う。
- `完了`: OneDriveへ本文専用Markdownを保存し、記事URLを取得できた状態。

Geminiは `進捗=記事化` かつ `生成エンジン=Gemini`、MLXは `進捗=記事化` かつ `生成エンジン=MLX` の行だけを候補にする。ユーザーが再試行可能な `失敗` 行を `記事化` へ戻すと、対応OneDriveジョブの試行回数を増やして再実行する。`完了` 行、ジョブID欠落行、入力不備による再試行不能行は処理しない。

シートの行位置は並び替えで変わるため、行番号を永続キーにしない。ジョブID列を検索して更新し、同じジョブIDが複数行に存在する場合は安全のため更新・生成を停止する。

Blog Vercelは、OneDriveジョブJSONを仮登録し、`周辺機器DB_LLM` 行の登録に成功してからジョブを `pending` として確定する。シート登録に失敗したジョブは実行対象にせず `registration_failed` として残し、UIから再登録できるようにする。これによりOneDriveとシートの片方だけに実行可能データが残ることを防ぐ。

### 5.3 おすすめ商品群

おすすめ商品の正本は、既存パイプラインと同じ次のファイルとする。

`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt`

`accessory_products.csv` は作らない。既存の `===MEMO1===`、`===MEMO2===` などを残したまま、周辺機器カテゴリ用の名前付きセクションを追加する。

```text
===battery===
▼おすすめバッテリーA
商品説明
Amazon URL

▼おすすめバッテリーB
商品説明
Amazon URL

===cable===
▼おすすめケーブルA
商品説明
Amazon URL
```

解析規則:

1. `===battery===` のような行をセクション開始マーカーとする。
2. 次に現れる任意の `===XXXX===` マーカー直前までを一つの商品群とする。
3. セクション内では、`▼` から次の `▼` 直前までを一商品ブロックとする。
4. 次の `▼` がない場合は、次のセクションマーカーまたはファイル末尾までを一商品ブロックとする。
5. `▼` ブロック内の改行、説明、価格表記、URLを原文のまま保持する。
6. おすすめ商品群では全ブロックを元の順番で一括掲載し、ランダム化、抜粋、要約、LLMによる書き換えを行わない。
7. 指定されたセクションがない、空である、または `▼` ブロックが一件もない場合は生成前エラーとしてUIへ表示する。

`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/pipeline/prompts/04-affiliate-link-manager/insert_affiliate_links.py` の既存ルールは、通常記事パイプライン用として変更せず維持する。

- H2「結論」直前へ指定MEMO全文
- 3、5、7番目など対象H2直前へ重複なしのランダムな `▼` ブロック
- 最初の挿入位置へ免責事項を一回
- 記事末尾へ指定MEMO全文

周辺機器の子記事では、新たに追加するカテゴリ商品群に対して上記スクリプトを呼ばない。呼ぶとH2前や記事末尾へも新規リンクが入り、「新たなおすすめリンクは結論だけ」という第一ゴールに反するためである。親記事に元から存在するアフィリエイト本文とURLは、結論外も含めて位置・文面を変更せず継承する。

周辺機器専用処理は、該当する名前付きセクションの全 `▼` ブロックを元の順番で結論内へ一回だけ挿入する。各ブロックの製品名、説明、価格表記、URL、改行は原文のまま保持する。通常記事用アフィリエイト挿入器が使うAmazonアソシエイト免責文やAI整形・編集の注記は、周辺機器子記事のおすすめ一覧へ追加しない。

MLXとGeminiには商品群本文を自由編集させない。選択したエンジンは、親製品名とカテゴリ名を含む冒頭案内文、および各 `▼` ブロックの主語・助詞・接続・最小限の言い回しだけを調整する。商品名行、URL、型番、容量、出力、価格、数値、商品順を固定し、「おすすめ商品のリンクまとめ」は生成しない。

### 5.4 エンジン別プロンプトとテンプレート

配置予定:

`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/accessories/templates/tpl_*.md`

決定的な組立処理を含む共通入力:

- `{PARENT_ID}`
- `{PARENT_TITLE}`
- `{PRODUCT_NAME}`
- `{PARENT_BODY}`
- `{PARENT_CONCLUSION}`
- `{PARENT_SPECS}`
- `{PARENT_SEO_PREFIX}`
- `{PARENT_IMMUTABLE_HASHES}`
- `{CATEGORY_ID}`
- `{CATEGORY_NAME}`
- `{KEYWORDS}`
- `{AFFILIATE_SECTION}`
- `{RECOMMENDED_PRODUCT_GROUP}`
- `{CURRENT_YEAR}`

MLX用・Gemini用プロンプトへ渡すのは、原則として `{PARENT_CONCLUSION}`、親記事から確認済みの `{PARENT_SPECS}`、対象カテゴリ、番号付きの全商品ブロックだけとする。`{PARENT_BODY}` と `{PARENT_IMMUTABLE_HASHES}` は決定的な複製・検査処理だけで使用し、モデルへ記事全文を書き直させない。

プロンプトは完成記事ではなく、次の内部構造だけを返す契約にする。

- 親製品の仕様要約
- 商品ブロック番号ごとのおすすめ理由

入力データにない仕様、価格、互換性、レビューを創作しないこと、見出し・URL・商品ブロックを生成しないこと、Frontmatter、YAML、公開用メタ情報、内部思考、作業説明を返さないことを明記する。エンジン応答は内部データとして検証し、その生応答を記事本文や管理JSONへそのまま保存しない。最終Markdownは必ず決定的な組立処理が作る。

MLX用とGemini用のプロンプトは別物として、記事ルート外の次のクラウド管理領域へ保存する。

```text
Blog_Vercel_Accessories_Control/prompts/
├── index.json
├── mlx/
│   └── <prompt_id>.md
└── gemini/
    └── <prompt_id>.md
```

`index.json` はエンジン別のプロンプト名、`prompt_id`、改訂番号、既定指定、更新日時を持つ。プロンプト本文に秘密情報を含めない。更新時は改訂番号と本文SHA-256を更新し、生成ジョブには選択された `prompt_id` と改訂番号を固定して記録する。これにより生成途中のプロンプト変更が実行中ジョブへ混入しない。

Blog Vercelの「プロンプト歯車」は、エンジンプルダウン、プロンプトプルダウン、本文編集、保存、削除を提供する。削除は確認操作を必須とし、既定または実行中ジョブが参照する改訂を直接削除しない。

### 5.5 ジョブJSON

OneDrive Graph上の制御データ配置:

`Blog_Vercel_Accessories_Control/jobs/<job_id>.json`

主要フィールド:

```json
{
  "schema_version": 2,
  "job_id": "acc_20260812_xxxxxxxx",
  "batch_id": "acc_batch_20260812_xxxxxxxx",
  "status": "pending",
  "engine": "mlx",
  "client_platform": "mac",
  "registry": {
    "spreadsheet_id": "1ioLnPe9z6vO0tuN3I_qcDi6buS8GCaYowbjq8LTOT94",
    "sheet_name": "周辺機器DB_LLM",
    "job_id_column": "ジョブID"
  },
  "prompt": {
    "prompt_id": "accessories_mlx_default",
    "revision": 1,
    "sha256": "プロンプト本文のSHA-256"
  },
  "parent": {
    "file_id": "OneDrive item ID",
    "parent_id": "安定した親記事ID",
    "title": "親記事タイトル",
    "path": "親記事の相対パス",
    "web_url": "親記事リンク"
  },
  "category": {
    "category_id": "charger",
    "category_name": "充電器",
    "affiliate_section": "charger",
    "planned_title": "製品名 充電器おすすめ：親記事タイトルの題意"
  },
  "master_snapshot": {
    "spreadsheet_id": "1ioLnPe9z6vO0tuN3I_qcDi6buS8GCaYowbjq8LTOT94",
    "sheet_name": "周辺機器DB",
    "source_row": 2,
    "sha256": "使用行全値のSHA-256"
  },
  "requested_at": "2026-08-12T00:00:00+09:00",
  "started_at": null,
  "completed_at": null,
  "attempt": 0,
  "worker_id": null,
  "lease_expires_at": null,
  "result": null,
  "error": null
}
```

状態遷移:

```text
registration_pending → pending → processing → completed
                    ↘ registration_failed  ↘ failed
```

一ジョブは一カテゴリ・一子記事だけを扱う。複数カテゴリの右クリック操作は `batch_id` でまとめ、Blog Vercelのバッチ表示だけが「一部成功」を計算する。再実行時は `parent_id + category_id + engine + template_revision` と既存子記事管理JSONを確認し、完成済み記事をスキップする。

`周辺機器DB_LLM` の行は検索時の入口であるが、処理権の取得はOneDriveジョブJSONのETag条件更新で行う。行番号は並び替えで変化するため保存せず、更新時にジョブID列を再検索する。シート上で同一ジョブIDが重複、欠落、別エンジンへ変更されている場合は実行しない。

### 5.6 子記事管理JSON

子記事Markdownには管理情報を付けず、次の情報を記事ルート外の `children/<child_id>.json` へ保存する。

```json
{
  "schema_version": 1,
  "child_id": "parent001_child_charger",
  "parent_id": "parent001",
  "relation_type": "accessory",
  "category_id": "charger",
  "title": "親製品におすすめの充電器",
  "status": "draft",
  "generation_engine": "mlx",
  "generation_model": "実行時モデルID",
  "job_id": "acc_20260812_xxxxxxxx",
  "batch_id": "acc_batch_20260812_xxxxxxxx",
  "prompt_id": "accessories_mlx_default",
  "prompt_revision": 1,
  "template_revision": "sha256の短縮値",
  "created_at": "2026-08-12T14:00:00+09:00",
  "completed_at": "2026-08-12T14:10:00+09:00",
  "article_item_id": "OneDrive item ID",
  "article_path": "周辺機器/parent001/parent001_child_charger.md",
  "affiliate_section": "charger",
  "recommended_product_urls": ["https://www.amazon.co.jp/dp/XXXXXXXXXX/ref=nosim?tag=hiroshit-22"],
  "recommended_product_asins": ["XXXXXXXXXX"]
}
```

`generation_engine` と `generation_model` を分け、MLXとGeminiの生成結果を記事本文を読まずに判別できるようにする。秘密値は管理JSON、ジョブ、ログへ保存しない。

`周辺機器DB_LLM` はこのJSONの全項目を複製しない。ユーザーが確認する作成日時、完了日時、タイトル、進捗、記事リンク、親記事、対象周辺機器、生成エンジン、エラー概要と、結合キーのジョブID・バッチIDだけを保持する。

### 5.7 OneDrive保存構造

既存のBlog Vercel記事ルートである `ONEDRIVE_FOLDER` 直下に、記事表示専用の `周辺機器` フォルダを作る。

```text
<ONEDRIVE_FOLDER>/
└── 周辺機器/
    └── <YYYYMMDD_HHMM_親記事タイトル冒頭20文字>/
        ├── <parent_id>_child_keyboard.md
        ├── <parent_id>_child_case.md
        └── <parent_id>_child_charger.md
```

フォルダ名の日付と時刻はジョブの `created_at` を日本時間へ変換した値とし、タイトル部分はOneDriveで使用できない文字を除去した親記事タイトルの先頭20文字とする。同一バッチは同じ `created_at` を共有するため、同じ親記事の複数カテゴリが同じ可読フォルダへ入る。

`周辺機器` フォルダ内には子記事Markdownだけを保存し、ジョブJSON、ロック、heartbeat、親記事参照情報、実行レポートを置かない。親記事本体は現在位置から移動しない。

制御データは記事ルート外のOneDrive Graph論理パスへ分離する。

```text
Blog_Vercel_Accessories_Control/
├── jobs/
│   ├── registration/
│   ├── registration_failed/
│   ├── pending/
│   ├── processing/
│   ├── completed/
│   └── failed/
├── parents/
│   └── <parent_id>.json
├── children/
│   └── <child_id>.json
├── prompts/
│   ├── index.json
│   ├── mlx/
│   └── gemini/
└── reports/
    └── <job_id>.json
```

実装では制御データの基点を `ACCESSORIES_CONTROL_FOLDER` として環境変数化し、既定値を上記パスとする。Blog Vercelの記事一覧はこの制御データ領域を読まず、`<ONEDRIVE_FOLDER>/周辺機器/` のMarkdownだけを記事として扱う。

## 6. 処理仕様

### 6.1 親記事解析

1. Markdown Frontmatterがあれば親記事入力としてだけ解析し、子記事Markdownへ複製しない。
2. 最初のH1を親タイトルとして使用し、製品名、既存SEO接頭辞、タイトル接尾辞を分離する。製品名は記事外管理JSONの確定済み `brand`・`model` を最優先し、なければH1と本文からルールベースで抽出する。`レビュー`、`比較`、`まとめ` などの旧記事軸は製品名へ含めない。複数候補が残る場合は実行前UIで確認させ、推測のまま生成しない。
3. H2「結論」を含む見出しがあれば、そのH2から次のH2直前までを結論部とする。
4. H2「結論」がなければ、H1直後から最初のH2直前までの導入ブロックを「冒頭結論」として扱う。現行サンプル記事はこの形式である。
5. H1、結論部、各H2/H3、その他本文を位置情報付きで分解する。
6. 全H2を変換対象として印を付ける。元見出しの題意は保持し、H3以下は変換対象にしない。
7. 変更許可範囲をH1文字列、全H2文字列、結論への追記位置に限定し、それ以外の不変領域ごとにSHA-256を計算する。
8. 本文から製品名、カテゴリ、接続規格、サイズ、世代など、結論の仕様要約に利用できる根拠付き情報を抽出する。
9. ルールベース一致を先に行い、LLMのカテゴリ判定はマスタ内カテゴリから選ぶ分類処理に限定する。
10. 判定根拠となった本文断片をジョブ結果へ記録する。

カテゴリ抽出、結論位置、変更許可範囲をLLMだけに任せず、再実行時に同じ結果を得やすい構成にする。H1がない、見出し構造を安全に分解できない、または不変領域を確定できない記事は、推測で加工せず生成前エラーにする。

### 6.2 カテゴリ選択

Blog Vercelは `周辺機器DB` の自動判定結果をそのまま実行せず、チェックボックスで候補を表示する。初期設定では候補を選択済みにしてもよいが、ユーザーが不要カテゴリを外せるようにする。

一回の右クリック操作を一バッチとする。複数選択された各親記事のタイトル直下へカテゴリチェックボックスだけを表示し、選択した「親記事×カテゴリ」ごとに一つのジョブJSONと `周辺機器DB_LLM` の一行を作る。ランチャーは固定件数上限を持たず、バッチIDから未処理ジョブを一件ずつ取得する。

### 6.3 記事生成

第一ゴールは「親記事派生型」とする。MLXまたはGeminiに記事全文を再生成させず、親記事を決定的に複製して、許可した四領域だけを変更する。

変更を許可する領域:

1. H1の見出し文字列
2. 全H2の見出し文字列
3. H1直後へ追加する、周辺機器商品を紹介する旨の短い一文
4. 結論部の末尾へ追加する、主語と最小限の言い回しだけを調整した全商品ブロック

H1は、既存タイトルから `レビュー`、`比較`、`違い`、`まとめ` などの記事軸を除いて製品名を確定し、親タイトルの接尾辞を付けずに次の完全一致形式へ変換する。

```text
# {製品名} {カテゴリ名}おすすめまとめ
```

全H2は、見出し階層と元の題意を維持しながら次の形式へ変換する。

```text
## {製品名} {カテゴリ名}おすすめ: {既存H2の題意}
```

たとえば `battery` なら「製品名 バッテリーおすすめ」、`cable` なら「製品名 ケーブルおすすめ」、内部ID `adapter` なら表示名「充電器」を使う。元見出しが製品名と旧記事軸で始まる場合は旧記事軸を題意から除く。`Captions`、動画名、独自見出しを含め、全H2へ接頭辞を付ける。H2数、出現順、階層は変えず、H3以下と見出し直下の本文は変更しない。カテゴリ特化の選び方、比較、FAQ、新しい章を追加しない。

選択したエンジンへは親製品名、カテゴリ名、番号付き商品ブロックだけを渡す。エンジンは短い冒頭案内文と、各商品ブロックの主語・助詞・接続・最小限の言い回しだけを調整した全文を返す。MLXとGeminiはそれぞれ単独で完結し、片方の出力をもう片方へ渡さない。

記事への追加は次の順序に固定する。

1. H1直後の短い冒頭案内文
2. 最初の親商品ブロック直後に設ける専用結論内の、調整済み `▼` 商品ブロック全件

対象セクションの全 `▼` ブロックを一件も省略せず、原文順で一回だけ掲載する。商品名行、URL、型番、容量、出力、価格、数値は固定し、入力にない事実を追加しない。「おすすめ商品のリンクまとめ」は掲載しない。

MLX実装では既存の全文記事生成を再利用せず、冒頭一文と商品文の限定調整だけを行う。Geminiも同じ限定入出力契約とし、不合格時は選択中の同一エンジンだけで再試行する。

確定処理順:

1. 親記事を構造分解し、変更許可範囲以外のSHA-256を記録する。
2. H2「結論」またはH1直後の冒頭結論を特定する。
3. `affiliate_links.txt` の対象セクションから全 `▼` ブロックを原文順で取得する。
4. 選択したMLXまたはGeminiだけで、冒頭案内文と商品ブロックの限定調整を生成する。
5. 商品件数、参照番号、商品名行、URL、数値仕様、原文との類似度、禁止内容を検査する。
6. 親記事を複製し、H1と全H2の文字列を決定的に変更し、H1直後へ冒頭案内文を追加する。
7. 最初の親商品ブロック直後へ専用結論見出しと調整済み商品ブロックを決定的に挿入する。通常記事用 `insert_affiliate_links.py` は呼ばず、リンクまとめも作らない。
8. 不変領域のSHA-256、見出し数・階層・順序、商品名・URL・数値・商品順、新規URLの位置、内部思考、Frontmatter、YAML、JSON、管理値の非混入を最終検査する。改行コードはLFへ正規化して比較する。
9. `locked_seo`、ジョブ、プロンプト、親子関係を記事ルート外の子記事管理JSONへ組み立てる。
10. 合格した本文専用Markdownだけを `<ONEDRIVE_FOLDER>/周辺機器/<YYYYMMDD_HHMM_親記事タイトル冒頭20文字>/` へ保存し、管理JSONを制御データ領域へ保存する。日時は同一バッチのジョブ作成日時を日本時間へ変換して使う。
11. `周辺機器DB_LLM` の同じジョブID行へ、完了日時、`進捗=完了`、記事URLリンクを書き込む。生成・検査・保存に失敗した場合は `進捗=失敗` とエラー概要を書き込む。

検査違反は文字列を自動削除して通過させない。AI応答部分の違反は同じエンジンで限定再生成し、親記事複製・見出し変換・商品挿入・不変領域の違反は再生成で隠さず実装エラーとして保存を停止する。上限到達時は保存せずカテゴリ別エラーにする。記事保存後にシート更新だけが失敗した場合は記事を失敗扱いで再生成せず、OneDriveジョブの `registry_sync` を `pending` として保持し、同じ記事URLでシート更新だけを再試行する。

### 6.4 保存と冪等性

- ファイル名は `<parent_id>_child_<category_id>.md` とする。
- 保存先は `<ONEDRIVE_FOLDER>/周辺機器/<YYYYMMDD_HHMM_親記事タイトル冒頭20文字>/` に固定する。同一バッチでは共通の作成日時を使い、同じ親記事の複数カテゴリを同じ可読フォルダへまとめる。
- 同じ組み合わせの既存記事がある場合は、通常実行では上書きせず `skipped_existing` とする。
- UIで明示した再生成時だけ新しい内容へ更新する。
- 更新前の既存記事はOneDriveのバージョン履歴で復元できることを確認してから再生成機能を有効化する。
- 一記事の失敗で他カテゴリの成功結果を破棄しない。

### 6.5 Blog Vercel表示

最初の縦断実装から、既存フォルダツリーと周辺機器生成UIを同時に提供する。UX確認を後続フェーズへ送らない。

- 左サイドパネルの記事上で右クリックする。
- 既存コンテキストメニューの「周辺機器記事作成」を押す。
- 右クリック対象が選択集合に含まれる場合は、複数選択中の全記事をモーダルへ渡す。
- 各記事タイトルの直下へ、検出カテゴリ名だけのコンパクトなチェックボックス行を表示する。
- 商品数、生成予定タイトル、商品一覧、最大件数案内などの補助文は表示しない。
- 使用するエンジン別プロンプト名と改訂番号
- 選択した全「親記事×カテゴリ」を共通バッチIDで登録する。
- 「MLXで作成」「Geminiで作成」「戻る」「プロンプト歯車」の4操作
- プロンプト歯車内のエンジンプルダウン、プロンプト選択、編集、保存、削除
- ジョブ状態表示
- 子記事へのリンク
- 子記事管理JSONから取得した `generation_engine` の表示タグ
- 一部失敗時のカテゴリ別エラー表示
- `周辺機器DB_LLM` へ登録した行数、ジョブID、バッチID、登録失敗の表示

Windowsでは「MLXで作成」を無効表示してMLXジョブを登録しない。Macでワーカーheartbeatが有効なら自動処理予定、失効中ならジョブ登録後に手動復旧が必要であることを表示する。GeminiはクライアントOSに関係なく利用可能とする。

対象エンジンの既定プロンプトがない、または選択プロンプトの取得・SHA-256検証に失敗した場合は生成ボタンを無効化する。暗黙の内蔵プロンプトへフォールバックせず、どのプロンプトを使うか確定できる場合だけジョブを登録する。

親子関係と生成エンジン表示は、可読性のための保存フォルダ名ではなく、記事ルート外の親・子管理JSONと `周辺機器DB_LLM` のジョブID・OneDrive item IDを利用する。記事Markdownへ管理情報を埋め込まず、一覧取得時に全記事本文を読む負荷も避ける。

### 6.6 note投稿・予約

生成された子記事は通常記事と同じOneDrive記事として既存UIから開く。note下書き、即時投稿、予約投稿は、既存 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/note-draft.js` と `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/note-post.js` をユーザーが手動操作して行う。

周辺機器機能専用のnote投稿API、親記事公開時刻を基準にした自動時間差予約、予約案自動生成は実装しない。既存UIが周辺機器記事のOneDrive file IDを通常どおり受け取り、Frontmatterや管理メタ情報を含まない本文だけをnoteへ渡すことを回帰確認する。

## 7. 実装対象ファイル

### 7.1 Blog Vercelへ新規追加

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/accessories/templates/tpl_default.md`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/main.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/job_schema.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/sheet_master_loader.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/sheet_registry.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/affiliate_group.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/parent_analyzer.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/heading_converter.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/conclusion_builder.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/article_assembler.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/prompt_builder.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/prompt_store.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/article_validator.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/metadata_store.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/onedrive_store.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/engines/gemini_engine.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/lib/accessories-sheets.js`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/.github/workflows/accessories-gemini.yml`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/tests/accessories/`

### 7.2 MLX側へ新規追加

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/accessories_worker.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/com.blogvercel.accessories-worker.plist`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/MLX/accessories_engine.py`

`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command` はダブルクリック時に手動一回実行モード、`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/com.blogvercel.accessories-worker.plist` は常駐監視モードで、同じ `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/accessories_worker.py` を起動する。

### 7.3 最小変更する既存ファイル

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/index.html`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/articles.js`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/pipeline/prompts/04-affiliate-link-manager/affiliate_links.txt`

既存 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/start_mlx.command`、`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/Gemma_start.command`、`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_MLX_discrod.command` は変更せず、周辺機器用`.command`からMLXサーバー起動方法だけを再利用する。

### 7.4 Vercel Function枠として置換する既存ファイル

- 置換元: `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/trigger-info-viewer.js`
- 置換先: `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js`

この置換はinfo_viewerのパイプライン起動機能を停止させる。実装時は削除・置換対象とFunction総数を再確認し、12個以下であることを検証してからデプロイする。

既存の通常記事生成、Xpost_blog、note投稿処理へ周辺機器固有ロジックを混在させない。既存 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/pipeline/prompts/04-affiliate-link-manager/insert_affiliate_links.py` は通常記事パイプライン専用として変更せず、周辺機器子記事からは呼ばない。名前付きおすすめ商品群の解析、見出し変換、結論限定挿入、不変領域検査は周辺機器専用モジュールへ分離する。

## 8. 実装フェーズと受け入れ条件

### フェーズ0: 契約固定、Function枠確保、UX骨格

- [x] 開発前コミット、復元タグ、Git bundle、未追跡資料、SHA-256を保存して復元点を検証する。
- [x] Googleスプレッドシート `周辺機器DB` の必須列、初期カテゴリ、アフィリエイトセクションを確定する。
- [x] `周辺機器DB_LLM` の先頭7列、運用列、進捗候補 `記事化`・`失敗`・`完了`、入力規則を固定する。
- [x] 一子記事一ジョブ・一行とし、複数カテゴリをバッチIDで束ねるジョブJSON Schema v2を固定する。
- [x] `affiliate_links.txt` に `===battery===`、`===adapter===`、`===cable===` の初期商品群を追加する。
- [x] 名前付きセクションと全 `▼` ブロックを取得するパーサーを実装する。
- [x] サンプル親記事から期待する初期3カテゴリをテストで固定する。
- [x] H2「結論」と、H2「結論」がない場合のH1直後から最初のH2直前までの冒頭結論を識別するルールを固定する。
- [x] H1の完全一致形式と、全H2の題意を保持するカテゴリ見出し変換ルールを固定する。
- [x] H1文字列、対象H2文字列、結論追記位置以外を不変領域とするSHA-256契約を固定する。
- [x] 新規カテゴリ商品リンクを結論だけへ置き、既存親記事リンクを元位置に維持する契約を固定する。
- [x] 子記事管理JSON Schema、プロンプト索引Schema、`周辺機器DB` 行スナップショットSchemaをテストで固定する。
- [x] MLX用・Gemini用プロンプトの出力を、冒頭案内文と商品ブロックの主語・最小限の言い回し調整だけに限定する。
- [x] 子記事Markdownが公開本文専用であることを出力契約として固定する。
- [x] MLXとGemini共通の品質基準を最大3試行、H1一件、商品件数・順序一致、禁止情報拒否として固定する。
- [x] `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/trigger-info-viewer.js` を置換し、Vercel Function総数を12個以下に保つテストを追加する。
- [x] 既存記事右クリックメニューへ「周辺機器記事作成」を追加する。
- [x] 親記事固定、カテゴリチェックボックス、商品群プレビュー、「MLXで作成」「Geminiで作成」「戻る」「プロンプト歯車」を持つ専用モーダル骨格を追加する。
- [x] プロンプト歯車へエンジン・プロンプトの各プルダウンと編集・保存・削除UI骨格を追加する。

完了条件:

- サンプル親記事から期待カテゴリが重複なく抽出される。
- 名前付きセクション内の全 `▼` ブロックが順番と改行を保持して取得される。
- 現行サンプル記事ではH2「結論」がないため、H1直後から最初のH2直前までが冒頭結論として検出される。
- サンプルのH1が「製品名 カテゴリ名おすすめまとめ」と完全一致し、全H2が題意を保持した「製品名 カテゴリ名おすすめ: 題意」形式へ変換される。
- H1、全H2、結論追記以外の親記事本文がバイト単位で一致する。
- `周辺機器DB` の必須列不足、重複カテゴリ、存在しないテンプレート、存在しない商品群、不正ジョブが明確な日本語エラーになる。
- 三カテゴリ選択時に、同じバッチIDを持つ三つのOneDriveジョブJSONと `周辺機器DB_LLM` 三行が作られる契約になる。
- `周辺機器DB_LLM` の先頭7列がユーザー指定順で、進捗が `記事化`・`失敗`・`完了`だけに制限される。
- 左サイドパネルの記事を右クリックして専用モーダルを開き、カテゴリチェックボックスと4操作を確認できる。
- 最初の空白でない行がH1でない、またはFrontmatter、YAML、JSON、管理値を含む完成Markdownが検査で不合格になる。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api` のFunction候補が12ファイル以下である。

### フェーズ1: UIを含むGemini縦断実装

- [x] `周辺機器DB` 読込、必須列検査、親記事解析、テンプレート展開、マスタ行スナップショットを実装する。
- [x] `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js` にカテゴリ候補、商品群プレビュー、プロンプト管理、一子記事一ジョブ登録、`周辺機器DB_LLM` 行登録、Gemini起動、状態取得を統合する。
- [ ] OneDrive仮ジョブ作成、シート行登録、`pending`確定、`registration_failed`復旧の整合処理を実装する。
- [x] MLX用・Gemini用プロンプトの一覧、取得、保存、改訂、確認付き削除を記事ルート外のクラウド領域へ実装する。
- [x] Gemini単独エンジンを実装する。
- [x] Geminiによる結論用仕様要約・商品別おすすめ理由の生成と、Gemini内の限定再試行を実装する。
- [x] 親記事複製、H1・H2見出し変換、結論組立、不変領域SHA-256検査を実装する。
- [x] おすすめ商品群の全件を結論だけへ一括挿入し、子記事経路では通常アフィリエイト挿入器を呼ばない処理を実装する。
- [x] SEO管理値、ジョブ、親子関係、生成エンジンを子記事管理JSONへ保存し、Markdownへ連結しない処理を実装する。
- [x] 保存直前の完成Markdownに対する本文専用検査と同一エンジン再生成を実装する。
- [x] `<ONEDRIVE_FOLDER>/周辺機器/<YYYYMMDD_HHMM_親記事タイトル冒頭20文字>/` の作成と子記事だけの保存を実装する。
- [x] 制御データを記事ルート外へ保存する。
- [x] Gemini専用GitHub Actionsを実装する。
- [x] Gemini成功時の完了日時・`完了`・記事URL、失敗時の`失敗`・エラー概要更新を実装する。
- [x] 記事保存後にシート更新だけ失敗した場合の `registry_sync=pending` 再同期を実装する。
- [x] UIの進捗ポーリング、カテゴリ別結果、完成記事リンクを実データへ接続する。

完了条件:

- Blog Vercelの左サイドパネルで親記事を右クリックし、「周辺機器記事作成」からカテゴリ、商品群、Geminiプロンプトを確認して生成を開始できる。
- Geminiだけで一つの親記事から複数の子記事を生成できる。
- 選択カテゴリごとに `周辺機器DB_LLM` へ一行ずつ登録され、生成エンジンがGeminiになる。
- 指定した名前付きセクションの全商品が、原文と順番を保って結論へ一回だけ掲載される。
- 新規カテゴリ商品URLは結論内だけに存在し、3・5・7番目のH2前や記事末尾へ追加されない。
- 親記事に元からあるアフィリエイト本文とURLは、元の位置と内容を維持する。
- 親記事との差分がH1、変換対象H2、結論追記だけであり、その他本文のSHA-256が一致する。
- 子記事だけがBlog Vercelルート直下の `周辺機器` フォルダへ保存され、既存UIから開ける。
- 子記事MarkdownがH1から始まり、Frontmatter、YAML、JSON、SEO管理値、ジョブ情報、プロンプト情報を含まない。
- Gemini失敗時にMLXへ自動切替しない。
- 一部失敗は個別ジョブとシート行の `失敗` に残り、バッチ表示では成功・失敗の内訳を確認できる。
- 完了行には完了日時と記事URL、失敗行にはエラー概要が入り、親記事タイトルとリンクは登録時のまま残る。
- APIキー、OneDriveトークン、ローカルMLX接続情報がブラウザへ露出しない。

### フェーズ2: UIを含むMLX縦断実装

- [x] 既存MLXの全文記事生成と `Step00` は子記事経路へ流用せず、SEO管理値を親タイトルと検証済み限定出力から記事外JSONへ決定的に保存する。
- [x] 親製品名・カテゴリ名・番号付き商品ブロックを受け取り、冒頭案内文と最小限に調整した商品ブロックだけを返すMLX専用エンジンを実装する。
- [x] `周辺機器DB_LLM` の `記事化`・`生成エンジン=MLX` 行を監視し、ジョブIDでOneDrive制御データを取得するMac側ワーカーを実装する。
- [x] ジョブロック、heartbeat、lease、再試行、冪等性を実装する。
- [x] MLX停止中の待機と復旧後の再開を実装する。
- [x] `launchd` 定義と起動・停止・状態確認入口を整備する。
- [x] フェーズ1で作った同じUIの `MLX` 選択を実ジョブへ接続する。
- [x] WindowsではMLXボタンを無効化し、Macではheartbeat失効中もジョブと `記事化` 行を登録して手動復旧案内を表示する制御を実装する。
- [x] Gemini経路と同じ決定的な組立処理で、全おすすめ商品群を結論だけへ挿入し、通常記事用アフィリエイト挿入器を呼ばない。
- [x] `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command` のダブルクリック手動一回実行モードを実装する。
- [x] 手動モードでMLX向け `記事化` 行の番号付き一覧、対象選択、候補なし終了、既存MLXサーバー起動、結果表示を実装する。
- [x] 自動・手動で同じ処理関数とOneDriveロックを使用し、同時起動時の二重生成を防ぐ。
- [x] MLX成功・失敗時の `周辺機器DB_LLM` 更新と、シート更新だけの再同期を実装する。

完了条件:

- Blog VercelでMLXを選ぶと、Macへの受信接続なしでジョブが処理される。
- MLXだけで親記事解析、SEO管理値生成、結論用要約・理由生成、決定的な親記事派生、品質検査、本文専用Markdownと管理JSONの分離保存まで完結する。
- Gemini APIを設定しなくてもMLX経路が動作する。
- ジョブ登録後にMacが停止した場合もジョブが消えず、起動後に処理される。
- WindowsではMLXジョブが登録されず、Macのheartbeat失効中は自動処理せず登録済みジョブが手動復旧候補に残る。
- 同じジョブを再取得しても子記事が重複しない。
- 内部思考や作業ログが完成Markdownへ残らない。
- 自動ワーカー停止時も、登録済み行を`.command`から選び、MLXサーバー起動から記事保存・シート更新まで完了できる。
- 候補がない場合、完了済みの場合、有効leaseがある場合は勝手に記事を生成しない。

### フェーズ3: 本番検証と運用安定化

- [ ] サンプル親記事でGemini経路を実行する。
- [ ] 同じ親記事でMLX経路を実行する。
- [ ] 各エンジンが独立完結していることを確認する。
- [ ] `battery`、`cable` など指定群の全商品、改行、URL、掲載順を人手確認する。
- [ ] 親記事と子記事を差分比較し、H1、変換対象H2、結論追記以外に変更がないことを人手確認する。
- [ ] 新規カテゴリ商品URLが結論だけにあり、親記事既存URLは元位置を維持することを人手確認する。
- [ ] Vercel本番UIで生成開始、進捗、完成記事表示、編集、保存を確認する。
- [ ] 本番UIで右クリック導線、カテゴリチェックボックス、4操作、エンジン別プロンプト編集を確認する。
- [ ] `周辺機器` フォルダの記事を既存UIで選択し、既存note手動予約画面まで進めることを確認する。
- [ ] Mac再起動後のワーカー自動復帰を確認する。
- [ ] 自動ワーカーを停止し、`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command` のダブルクリックだけで未処理MLX行を完成させる。
- [ ] 自動ワーカーと`.command`を同時起動し、一方だけがジョブを取得することを確認する。
- [ ] `周辺機器DB_LLM` の作成日時、完了日時、記事タイトル、進捗、記事URL、大元記事タイトル、大元記事リンクを人手確認する。
- [ ] 失敗ジョブの再実行と二重生成防止を確認する。
- [ ] Vercelデプロイ後のFunction総数が12個以下であることを確認する。
- [ ] Gemini・MLXの各完成Markdownをバイト単位で検査し、公開本文以外が混入していないことを確認する。
- [ ] 復元bundleを再検証し、開発前コミットを参照できることを確認する。

完了条件:

- MLXとGeminiの両経路で各一回以上、実データの端から端まで成功する。
- 初期実装から必要なUXを本番で確認できる。
- 既存本番機能に回帰がない。
- note投稿は既存UIの手動操作だけで利用できる。
- エラー時に、どの親記事・カテゴリ・工程で失敗したかBlog Vercelから判別できる。
- `周辺機器DB_LLM`だけを見て、Gemini・MLXそれぞれの作成対象、失敗、完了、記事リンク、親記事を判別できる。

## 9. テスト計画

### 9.1 単体テスト

- `周辺機器DB` の必須列、空行、不正値、重複カテゴリ、シート取得失敗
- `周辺機器DB` 行スナップショットの値、取得元、SHA-256固定
- `周辺機器DB_LLM` の先頭7列順序、運用列、進捗許可値
- `周辺機器DB_LLM` のジョブID欠落・重複・エンジン不一致拒否
- 一カテゴリ一ジョブ一行と、複数カテゴリの共通バッチID
- シート並び替え後も行番号ではなくジョブIDで更新すること
- タイトルやエラー概要をシートへ書く際の数式注入防止とURL列の安全なリンク設定
- キーワード正規化とカテゴリ重複排除
- テンプレート変数の不足検出
- 子記事管理JSONの必須項目、エスケープ、再解析
- プロンプト索引のエンジン分離、改訂番号、SHA-256、既定プロンプト保護
- エンジン結果が冒頭案内文と調整済み商品ブロックだけであり、記事全文、見出し、リンクまとめ、管理メタ情報を含まないこと
- エンジン内部結果、管理JSON、完成Markdownが分離され、保存関数へ完成した公開本文だけが渡ること
- job_id・batch_id生成、`registration_pending`を含む状態遷移、registry sync状態
- 出力ファイル名の禁止文字除去
- 既存記事検出と再生成判定
- `===XXXX===` セクション終端判定
- `▼` ブロックの全件取得、順番保持、改行保持
- H2「結論」の明示検出と、存在しない場合のH1直後から最初のH2直前までの冒頭結論検出
- H1の製品名・既存接尾辞分離と「製品名 カテゴリ名おすすめ：」形式への変換
- 親製品SEO接頭辞を持つH2だけの変換、および独自H2・H3以下の不変確認
- H1数、H2数、見出し階層、見出し順序の維持
- H1、変換対象H2、結論追記位置以外の不変領域SHA-256一致
- エンジン出力の仕様要約、商品ブロック別理由の件数・参照番号・根拠・反復・内部思考・作業ログ・禁止表現検査
- 全商品ブロックの全文・順番一致と、理由が各ブロックに一対一で対応すること
- 商品名と原文URLのリンクまとめが全件・原文順であること
- 親記事との差分URLの全てが結論範囲内にあり、親記事既存URLは元位置に残ること
- 周辺機器子記事経路が通常記事用 `insert_affiliate_links.py` を呼ばないこと
- UTF-8 BOM、Frontmatter、YAML文書区切り、JSON包み、記事全体のコードフェンス、HTMLコメント内管理値、管理キーの混入拒否
- 混入検出時に文字列除去で保存せず、同一エンジン再生成または失敗になること
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api` 直下のJavaScript API数が12以下であることの検査

### 9.2 統合テスト

- Blog VercelからOneDrive仮ジョブ作成、`周辺機器DB_LLM` 行登録、`pending`確定まで
- シート行登録失敗時にOneDriveジョブが `registration_failed` となり、実行対象にならないこと
- 三カテゴリ選択時に一バッチ・三ジョブ・三行となること
- `周辺機器DB_LLM` のMLX向け `記事化` 行からMac側がジョブIDでOneDriveジョブを取得すること
- MLXヘルスチェック失敗時の待機
- MLX生成成功からOneDrive保存まで
- GitHub ActionsからGemini生成、保存まで
- Gemini・MLXの成功時に完了日時、`完了`、記事URLが対応行へ入ること
- 失敗時に `失敗`、エラー概要が入り、完了日時と記事URLが空欄になること
- シート更新だけ失敗した完成ジョブが記事を再生成せず、同じURLで再同期されること
- 一部カテゴリ失敗時に個別行が `失敗` となり、バッチ集計が一部成功を示すこと
- Blog Vercelのジョブ状態取得
- Blog Vercelのカテゴリ・商品群プレビュー
- 左サイドパネルの記事右クリックから専用モーダルが開き、右クリックした一記事が親として固定されること
- 記事の複数選択中でも右クリックした一記事だけが親となり、他の選択記事を親入力へ混ぜないこと
- カテゴリチェックボックスの複数選択と「MLXで作成」「Geminiで作成」「戻る」「プロンプト歯車」の動作
- MLX用・Gemini用プロンプトの分離、保存、改訂、確認付き削除、実行中改訂の保護
- プロンプト未選択、取得失敗、SHA-256不一致では生成ジョブを登録しないこと
- WindowsではMLXジョブが登録されずGeminiだけを利用でき、Macのheartbeat失効中はMLXジョブが登録されて手動復旧案内が出ること
- `<ONEDRIVE_FOLDER>/周辺機器/<YYYYMMDD_HHMM_親記事タイトル冒頭20文字>/` のフォルダ一覧と子記事表示
- 記事ルート外の制御データ保存と、記事Markdownへの管理情報非混入
- 親記事と子記事の構造差分がH1、全H2、結論追記だけであること
- 新規カテゴリ商品URLが結論だけにあり、親記事の既存リンクが元位置と原文を保つこと
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command` をダブルクリック相当で実行し、候補一覧・番号選択・MLX起動・保存・シート更新まで完了すること
- 手動候補なし、完了済み、有効lease、再試行不能エラーでは生成しないこと
- 自動ワーカーと`.command`の同時実行で一方だけがOneDriveロックを取得すること
- `失敗` 行をユーザーが `記事化` へ戻した場合だけ、同じジョブIDの試行回数を増やして再実行すること

### 9.3 回帰テスト

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/articles.js` の一覧、取得、保存、移動、複製、削除
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/index.html` の編集とMarkdownプレビュー
- note下書き、即時投稿、予約投稿
- noteへ渡る本文にFrontmatter、YAML、管理メタ情報が追加されないこと
- 通常のYouTube記事生成
- Amazon直接入力記事生成
- 既存MLXのGoogleスプレッドシート `ブランド製品名仕訳` を入口とする通常記事生成
- 既存 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/start_mlx.command` と `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_MLX_discrod.command` の通常動作
- 通常記事では既存 `insert_affiliate_links.py` のH2前・記事末尾挿入が従来どおり動作すること
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/info-viewer.js` を使う既存閲覧とnote互換経路
- Xpost_blog
- 復元bundleから別フォルダへcloneでき、HEADが `e91127abd28450a024b147855d0404722a3e8dbc` と一致すること

`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/trigger-info-viewer.js` を使うinfo_viewerパイプライン起動は、周辺機器APIへの枠置換により廃止するため回帰対象外とする。

## 10. 未決事項

実装開始前または該当フェーズ開始前に、次を決定する。

- 周辺機器マスタの初期カテゴリ数と内容
- `affiliate_links.txt` で使用する初期セクション名と `category_id` の対応
- 既存親記事へ安定した `parent_id` がない場合の採番規則
- MLXワーカーのポーリング間隔と稼働時間帯
- MLXジョブを一度に一件だけ処理するか、モデルのメモリに応じて将来並列化するか
- Geminiで利用するモデル名と一ジョブの上限
- 生成済み記事の再生成時に上書きするか、改訂版を別ファイルにするか

未決事項をコード内の暗黙値で確定させない。決定した内容はこの章から削除せず、「決定事項」へ移して日付と理由を残す。

## 11. 決定事項

| 日付 | 決定 | 理由 |
| --- | --- | --- |
| 2026-08-12 | MLXとGeminiは独立完結させる | 片方への依存や自動フォールバックをなくし、単独運用と比較を可能にするため |
| 2026-08-12 | VercelからMLXへの依頼はOneDriveキューとMac側ポーリングを使う | localhost公開を避け、停止中のジョブ保持と既存OneDrive資産の再利用を両立するため |
| 2026-08-12 | 親記事は第一弾で移動しない | 既存UI、保存先、元記事URLへの影響を最小化するため |
| 2026-08-12 | おすすめ商品は既存 `affiliate_links.txt` の名前付きセクションで管理する | 既存アフィリエイト運用を維持し、同じファイルから商品群を管理するため |
| 2026-08-12 | 名前付きセクション内の全 `▼` ブロックを一括掲載する | おすすめ商品を省略、ランダム化、LLM改変せず掲載するため |
| 2026-08-12 | 第一ゴールの子記事は親記事派生型とし、カテゴリ特化の全面改稿を行わない | 親記事の内容と構成を維持し、カテゴリSEO見出しと結論のおすすめ情報だけを追加するため |
| 2026-08-12 | 子記事で変更できるのはH1、対象SEO形式H2、結論追記だけとする | 本編を大きく変えず、意図しないAI改稿を不変領域ハッシュで検出するため |
| 2026-08-12 | 新規カテゴリ商品群は結論へだけ挿入し、通常記事用アフィリエイト挿入器を子記事経路では呼ばない | H2前や記事末尾への新規リンク分散を防ぎ、結論だけで仕様とおすすめを確認できるようにするため |
| 2026-08-12 | 親記事に既存のリンクは結論外も含めて元位置に維持する | 親記事の既存本文と運用上のリンクを壊さないため |
| 2026-08-12 | 周辺機器カテゴリ対応ルールはGoogleスプレッドシート `周辺機器DB` を唯一の正本とする | ユーザーがコードやCSVを扱わず、単語と生成カテゴリの対応を直接編集できるようにするため |
| 2026-08-12 | `周辺機器DB_LLM` をGemini・MLX共通の一子記事一行キュー兼進捗一覧とする | 作成対象、失敗、完了、記事リンク、親記事をユーザーが一画面で確認できるようにするため |
| 2026-08-12 | 詳細状態、ロック、確定済み入力はOneDriveジョブJSONを正とする | シートの並び替え・手動編集・同時実行があっても生成内容と排他制御を壊さないため |
| 2026-08-12 | MLX自動処理が動かない場合は `start_accessories_worker.command` で同じジョブを手動復旧する | Blog Vercelからの自動実行を優先しつつ、登録済み作業をMacから確実に再開できるようにするため |
| 2026-08-12 | `周辺機器` フォルダには子記事Markdownだけを保存する | Blog Vercelの記事一覧と制御データを混在させないため |
| 2026-08-12 | 最初の縦断実装から生成UXを含める | 実行経路の完成前から操作性と情報量を確認するため |
| 2026-08-12 | note投稿と予約は既存UIの手動操作だけを使う | 周辺機器専用の予約自動化が不要なため |
| 2026-08-12 | `api/trigger-info-viewer.js` のFunction枠を単一の `api/accessories.js` へ置換する | Vercel Hobbyの12 Functions上限を維持するため |
| 2026-08-12 | 子記事Markdownは公開本文専用とし、管理情報は記事外JSONへ完全分離する | Frontmatter、YAML、SEO管理値、ジョブ情報などが公開記事やnoteへ混入することを防ぐため |
| 2026-08-12 | 周辺機器生成は左サイドパネルの記事右クリックから開始する | 仕様書で指定された既存コンテキストメニューとチェックボックスUXを実現するため |
| 2026-08-12 | MLX用・Gemini用プロンプトを記事ルート外のクラウド領域で別管理する | エンジンごとの能力差に合わせて独立編集し、実行改訂を固定するため |
| 2026-08-12 | WindowsではMLXジョブを登録せず、Macのheartbeat失効時もジョブを登録して手動復旧案内を表示する | MLXがない端末から無効な処理を作らず、Macでは自動処理不能時も同じ依頼を`.command`で実行できるようにするため |
| 2026-08-12 | アプリケーション実装前のGit bundle、タグ、未追跡資料、復元試験を保持する | 既存ツールを開発前状態へ戻せることを実証してから変更を始めるため |
| 2026-08-12 | 次回AI向け引き継ぎ手順の章は設けない | 本文全体を実装計画兼進捗の正本として管理するため |
| 2026-08-12 | `winmacsync` は使用しない | ユーザーの明示指示による |

## 12. リスクと対策

| リスク | 影響 | 対策 |
| --- | --- | --- |
| MacまたはMLXが停止している | MLXジョブが自動で進まない | Macからはジョブとシート行を登録し、heartbeat失効を表示する。登録済みジョブは `pending` またはlease切れで保持し、`.command`から手動復旧できるようにする |
| 同じジョブを自動・手動で同時取得する | 子記事が重複する | OneDrive ETag条件更新、`job_id` lease、出力キーによる冪等性を自動・手動で共用する |
| `周辺機器DB` の列名・値を誤編集する | 候補が欠落または誤分類される | 実行前に必須列、重複ID、テンプレート、アフィリエイトセクションを検査し、該当行を日本語表示する |
| `周辺機器DB` を生成途中で変更する | 同じジョブの内容が途中で変わる | ジョブ登録時の行全値とSHA-256をOneDriveジョブJSONへ固定し、実行時の再読込で置換しない |
| `周辺機器DB_LLM` を並び替える | 別の行へ結果を書き込む | 行番号を永続保存せず、更新直前に一意なジョブIDで行を検索する |
| `周辺機器DB_LLM` のジョブIDを重複・削除する | 誤更新または別記事生成になる | 重複・欠落を検出したら生成と更新を停止し、Blog Vercelと`.command`へ理由を表示する |
| OneDriveジョブ作成とシート行登録の片方だけ成功する | 一覧にないジョブ、実行不能な行が残る | 仮ジョブ、シート登録、`pending`確定の順に処理し、失敗は `registration_failed` へ隔離して再登録可能にする |
| 記事保存後にシート更新だけ失敗する | 完成記事が失敗表示のまま残る | 記事を再生成せず `registry_sync=pending` として同じURLのシート更新だけを再試行する |
| Google Sheets APIの割当・認証障害 | ルール取得、キュー登録、進捗更新が止まる | 指数バックオフ、明確な日本語エラー、登録途中状態、後続再同期を実装し、暗黙のローカルCSVへ切り替えない |
| シートへ書くタイトルが数式として解釈される | 意図しない数式実行や表示崩れが起きる | ユーザー由来文字列を値として書き込み、先頭の数式記号を無害化し、URLは安全なリンク列として設定する |
| OneDriveの同期待ち・競合 | 状態表示が遅れる、二重処理 | Graph APIの応答を正とし、ローカル同期フォルダのファイル監視には依存しない |
| MLXの長時間生成・途中停止 | ジョブが `processing` のまま残る | heartbeat、lease期限、最大試行回数を持たせる |
| Gemini quota・一時障害 | Geminiジョブが失敗する | Gemini内のキー切替と再試行だけを行い、MLXへは自動切替しない |
| LLMが商品仕様やURLを創作する | 誤情報記事になる | 商品群をLLMに生成させず、`affiliate_links.txt` の原文を生成後に決定的処理で挿入する |
| LLMが親記事全体を改稿する | 元記事の情報、文体、構成が失われる | モデルへ記事全文を生成させず、結論・根拠付き仕様・商品ブロックだけを渡し、仕様要約と理由だけを受け取る |
| H2「結論」が存在しない | おすすめ商品群の挿入先を誤る | H1直後から最初のH2直前までを冒頭結論とする。H1やH2構造を安全に解析できない場合は保存せずエラーにする |
| 全H2の題意が見出し変換で失われる | 動画、キャプション、独自章を識別できなくなる | 全H2へ同一接頭辞を付けつつ元見出しの題意を保持し、H2数・順序・H3以下を不変検査する |
| 新規カテゴリリンクが結論外へ漏れる | 第一ゴールと異なる記事になる | 親子URL差分を取り、新規URL集合が結論内だけに存在することを最終検査する |
| 決定的な組立処理が親本文を変える | AIを限定しても本文が壊れる | H1、対象H2、結論追記以外の不変領域SHA-256を親子で比較し、不一致なら保存しない |
| `affiliate_links.txt` の価格や説明が古くなる | 古い商品情報を全記事へ掲載する | 商品群プレビューを実行前UIに表示し、ファイル正本をユーザーが更新してから生成する |
| 名前付き商品群のマーカーや `▼` が壊れる | 商品欠落や別カテゴリ混入が起きる | 生成前パーサー検証で停止し、対象セクション、ブロック件数、プレビューを表示する |
| MLX出力に内部思考が残る | 公開記事へ作業ログが混入する | `【思考プロセス】`、`<think>`、作業説明を最終検査で拒否する |
| Frontmatter、YAML、JSON、SEO管理値が記事へ混入する | 公開記事やnoteへ管理情報が露出する | 本文専用出力契約、禁止パターン検査、H1先頭検査を行い、違反結果は保存せず同一エンジンで再生成する |
| 自動除去が正しい本文まで削る | 記事欠落を見逃したまま公開する | 混入箇所だけを削って合格扱いにせず、生成結果全体を不合格にする |
| プロンプト編集が実行中ジョブへ混入する | 同じジョブ内で記事品質が変わる | ジョブ作成時にプロンプトID、改訂番号、SHA-256を固定する |
| 使用中プロンプトを削除する | 再実行不能またはジョブ失敗になる | 確認付き削除、既定プロンプト保護、実行中改訂の削除禁止を実装する |
| OS判定やheartbeat判定を誤る | Windowsから無効なMLX操作が行われる、またはMacの手動復旧ジョブを登録できない | API側でWindowsからのMLXジョブ登録を拒否する。Macではheartbeatを自動処理か手動復旧かの表示判定にだけ使い、失効中もジョブと `記事化` 行は登録する |
| 開発中の変更で既存ツールが壊れる | 現行運用へ戻せない | 検証済みGit bundleと未追跡資料をリポジトリ外へ保持し、別フォルダ復元試験を維持する |
| 親記事タイトル変更 | 親子参照が切れる | ファイル名ではなくOneDrive item IDと安定した `parent_id` を使う |
| Vercel Function数が12を超える | Hobbyプランでデプロイできない | `trigger-info-viewer.js` を `accessories.js` へ1対1で置換し、APIファイル数の自動検査を行う |
| info_viewerのパイプライン起動APIを置換する | info_viewer画面から新規起動できなくなる | ユーザーがinfo_viewerを使用していないことを前提とし、閲覧用 `api/info-viewer.js` は維持する |
| `public/index.html` の大規模化 | 回帰リスクが高まる | 周辺機器UIロジックを可能な限り独立API・独立関数へ分離し、変更箇所を限定する |
| マスタの手動編集ミス | 実行時に一括失敗する | 実行前検証コマンドとUIのマスタ診断結果を用意する |

## 13. 秘密情報の管理ルール

- Gemini APIキー、Amazon認証情報、OneDrive認証情報、Googleサービスアカウント情報、GitHub Tokenをリポジトリ、記事Markdown、スプレッドシート、ジョブJSON、子記事管理JSON、プロンプト、ブラウザ保存領域へ書かない。
- Vercelで必要な秘密値はVercel Environment Variablesだけで扱う。
- GitHub Actionsで必要な秘密値はGitHub Actions Secretsだけで扱う。
- Mac側ワーカーの秘密値は既存のサーバー側・ローカル専用Secret保管を利用し、OneDrive同期対象へ複製しない。
- `周辺機器DB` と `周辺機器DB_LLM` には、記事タイトル、公開リンク、ジョブ識別子、公開可能なエラー概要だけを書き、認証トークン、プロンプト本文、親記事本文、内部エラー全文を書かない。
- API応答、例外、ログにはトークンやWebhook URLを含めない。外部APIのエラー本文を記録する場合は秘密値をマスクする。
- Blog Vercelのブラウザへ返すのはジョブID、状態、記事ID、公開可能なエラー概要だけとする。
- MLXサーバーは原則localhostで待ち受け、外部公開しない。
- トンネル方式を将来採用する場合は、認証、接続元制限、短期トークン、監査ログを別途設計してから導入する。
- 機密ファイルの読み取り・変更が必要になった場合は、理由とリスクを提示し、ユーザーの個別許可を得てから行う。

## 14. `winmacsync` の扱い

このプロジェクトおよび本機能の調査、実装、検証、文書更新では `winmacsync` を使用しない。

- セッション開始時に自動実行しない。
- グローバルスキル使用前にも実行しない。
- ファイル変更後にも実行しない。
- 同期やバックアップのための代替手段として勝手に起動しない。

この方針は2026-08-12のユーザー指示に基づく。変更する場合は、ユーザーからの新しい明示指示を必要とする。

## 15. 開発進捗

### 全体進捗

| 項目 | 状態 | 更新日 | 備考 |
| --- | --- | --- | --- |
| 仕様書確認 | 完了 | 2026-08-12 | `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/docs/accessories_spec.md` を確認 |
| 現行Blog Vercel調査 | 完了 | 2026-08-12 | Gemini、OneDrive、Vercel UI、note予約経路を確認 |
| 現行MLX調査 | 完了 | 2026-08-12 | Step00のSEOメタ情報、最終保存、レポート、Frontmatter未付与を確認 |
| Vercel Function上限調査 | 完了 | 2026-08-12 | Vercelプロジェクト認証後にAPI 12ファイルとビルド出力を確認。`api/trigger-info-viewer.js` の枠を `api/accessories.js` へ置換し、上限内の12 Functionsを維持 |
| 既存アフィリエイト仕様調査 | 完了 | 2026-08-12 | `===MEMO<n>===`、`▼` ブロック、既存挿入位置を確認 |
| 実装計画第2版 | 完了 | 2026-08-12 | 商品群、Function枠、保存先、初期UX、note方針を改訂 |
| UX仕様再確認 | 完了 | 2026-08-12 | 現行UIの右クリック、選択モード、チェックボックスを確認し、未実装の専用導線を特定 |
| 開発前復元点 | 完了 | 2026-08-12 | タグ、bundle、未追跡資料、SHA-256を保存し、別フォルダへの実復元に成功 |
| 実装計画第3版 | 完了 | 2026-08-12 | 本文専用出力、管理JSON分離、右クリックUX、プロンプト管理、復元保証を追加 |
| 実装計画第4版 | 完了 | 2026-08-12 | 親記事派生型、H1・対象H2変換、結論限定の商品挿入、不変領域検査へ改訂 |
| 実装計画第5版 | 完了 | 2026-08-12 | `周辺機器DB`正本化、`周辺機器DB_LLM`キュー、MLX`.command`手動復旧を追加 |
| clasp・シート契約準備 | 完了 | 2026-08-12 | ユーザーが `seedAccessoryCategories` を実行。実APIプレビューで `battery`、`adapter`、`cable` と各商品数を確認 |
| フェーズ0 | 完了 | 2026-08-12 | 契約、Function枠、右クリックUI、チェックボック、MLX/Geminiボタン、単体テストを実装。ユーザーによる実クリック試験を残す |
| フェーズ1 | 進行中 | 2026-08-12 | Gemini縦断ソースを実装。GitHub Actions・OneDrive・本番UIの実ジョブ確認待ち |
| フェーズ2 | 進行中 | 2026-08-12 | MLXエンジン、ポーラー、`.command`、launchd定義、Blog VercelからTerminalを開くMac URLランチャー、ライブ進捗を実装。実MLXジョブの完走確認待ち |
| フェーズ3 | 進行中 | 2026-08-12 | Vercel本番公開と本番読み取り専用プレビューまで完了。ユーザーによる右クリック操作とGemini/MLX各1ジョブの確認を残す |
| 運用UI改善 | 完了 | 2026-08-13 | 生成結果の再表示、OneDrive直下記事の5件単位読込数、全件・カテゴリ別チェック一括切替を実装 |
| 生成再試行・履歴復帰改善 | 完了 | 2026-08-13 | 生成を2回へ短縮し、商品名開始の文頭、シート正本の生成結果復帰、明示的な一括チェックボックスを本番で確認 |
| 記事構成・MLX速度設定改善 | 完了 | 2026-08-13 | 最初の親商品ブロック直後への専用結論、読込数手入力、記事からの履歴復帰、MLX 1～3回設定を本番で確認 |
| SEOタイトル派生生成 | 進行中 | 2026-08-13 | 右クリック「タイトル変更」、複数キーワード整形、一キーワード一ジョブ、限定MLX生成、同一フォルダ保存を実装。ユーザーによる本番実MLX試験待ち |

進捗状態は `未着手`、`進行中`、`保留`、`完了` のいずれかで更新する。`完了` にする場合は、対応する検証結果または根拠を開発履歴へ記録する。

## 16. 開発履歴

### 2026-08-12: 仕様調査と実装計画作成

実施内容:

- 周辺機器記事生成の仕様書とサンプル記事を確認した。
- Blog VercelのGemini生成、OneDrive CRUD、フォルダ表示、複数選択、note予約機能を確認した。
- MLXの実体が `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/MLX/run_geamma4_blog_mlx.py` にあり、OpenAI互換APIと品質検査を利用していることを確認した。
- MLXとGeminiを直列に組み合わせず、各エンジンが単独完結する構成へ固定した。
- Blog VercelからMLXを起動する経路として、OneDriveジョブキューをMac側ワーカーが取得する方式を採用した。
- 初期案では商品情報の創作を防ぐため別の商品候補マスタを設ける計画としたが、設計計画第2版で廃止した。
- `winmacsync` を使用しない方針を記録した。

確認できた課題:

- VercelからMacのlocalhostへ直接接続できない。
- 既存MLXランナーはGoogle Sheetsの商品行を入口としており、親記事入力モードがない。
- 仕様書の周辺機器マスタだけでは紹介する実在商品を確定できない。
- 既存記事APIは新規ファイルの任意サブフォルダ保存に未対応である。
- 初期調査ではFrontmatterによる親子関係を候補に含めたが、設計計画第3版で記事外管理JSONへ変更した。

対策:

- OneDriveキューとMac側ポーリングを採用し、Macへの外部着信を不要にする。
- 共通入力・出力契約を設けつつ、MLXエンジンとGeminiエンジンを独立させる。
- 初期案では検証済み商品候補マスタとAmazon Creators APIを利用する想定だったが、設計計画第2版では既存 `affiliate_links.txt` の名前付き商品群を正本とする方式へ変更した。
- 任意サブフォルダ保存とジョブ状態取得を周辺機器専用APIとして追加する。

検証結果:

- この段階では読み取り調査と計画書作成だけを実施した。
- アプリケーションコード、ワークフロー、秘密情報は変更していない。
- `winmacsync` は実行していない。

### 2026-08-12: ユーザー確認を反映した設計第2版

実施内容:

- 現行MLXが `Step00` でSEOメタ情報を生成し、最終段では本文保存と実行レポートを作る一方、完成MarkdownへYAML Frontmatterを付けていないことを確認した。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api` 直下が12ファイルであり、Vercel Hobbyの直接配置型Functions上限12個に達していることを確認した。
- Vercel本番トップがHTTP 200で応答することを確認した。Vercel CLIは未認証であり、ダッシュボード内の使用量メーターまでは確認できなかった。
- `api/trigger-info-viewer.js` の1枠を単一の `api/accessories.js` へ置換し、別のトリガーAPIを作らない方針へ変更した。
- `accessory_products.csv` の計画を廃止し、既存 `affiliate_links.txt` に `===battery===`、`===cable===` などの名前付き商品群を置く方針へ変更した。
- 名前付きセクション内の全 `▼` ブロックを、順番と原文を保持しておすすめ商品欄へ一括掲載する仕様へ変更した。
- 設計計画第2版では、通常アフィリエイトの既存挿入位置を子記事でも維持し、おすすめ商品群を別処理で追加する方針だった。この子記事向け方針は設計計画第4版で廃止した。
- 子記事保存先を `<ONEDRIVE_FOLDER>/周辺機器/<parent_id>/` とし、`周辺機器` フォルダにはMarkdownだけを置く構成へ変更した。
- ジョブ、ロック、親記事参照、レポートは記事ルート外の `Obsidian in Onedrive 202602/Blog_Vercel管理/周辺機器/` へ分離する方針とした。
- Blog Vercelの生成UXを後続フェーズへ送らず、最初の縦断実装から含めるようフェーズを再編した。
- note投稿と予約は既存UIの手動操作だけを使い、自動時間差予約を計画から削除した。

確認できた課題:

- APIを単純追加するとVercel Hobbyの12 Functions上限を超える。
- 設計計画第2版では完成Markdownに周辺機器管理用Frontmatterがないことを課題としたが、設計計画第3版でFrontmatter自体を禁止し、記事外管理JSONへ変更した。
- 過去のMLX完成Markdownには内部思考が残った例があり、最終検査の強化が必要である。
- 現行 `insert_affiliate_links.py` は数値MEMO専用で、名前付き商品群を全件一括取得する処理を持たない。
- `api/trigger-info-viewer.js` の置換後はinfo_viewer画面からパイプラインを起動できなくなる。

対策:

- info_viewer専用トリガー枠を周辺機器用の単一APIへ1対1で置換し、Function総数を増やさない。
- 設計計画第2版では `locked_seo` から周辺機器専用Frontmatterを付ける方針だったが、設計計画第3版で廃止した。`locked_seo` は記事外の子記事管理JSONにだけ保存する。
- 内部思考と作業ログを最終検査の拒否条件にする。
- 既存通常アフィリエイト処理を通常記事用として変更せず、名前付き商品群パーサーを周辺機器専用モジュールとして追加する。子記事から既存挿入器を呼ばない点は設計計画第4版で追加した。
- 閲覧とnote互換に使われる `api/info-viewer.js` は維持する。

検証結果:

- 計画書内のデータ設計、API構成、保存先、処理順、対象ファイル、フェーズ、テスト、未決事項、決定事項、リスク、進捗を新方針へ更新した。
- アプリケーションコード、API、workflow、`affiliate_links.txt` の実データはまだ変更していない。
- `winmacsync` は実行していない。

### 2026-08-12: 本文専用出力・右クリックUX・復元保証を反映した設計第3版

実施内容:

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/docs/accessories_spec.md` のUX指定を再読し、左サイドパネルの記事右クリックから開始することを現行要件として固定した。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/index.html` に既存の右クリックコンテキストメニュー、選択モード、記事チェックボックスがあることを確認した。
- 「周辺機器記事作成」、専用モーダル、「MLXで作成」「Geminiで作成」「戻る」「プロンプト歯車」は未実装であることを確認した。
- 子記事MarkdownへのFrontmatter、YAML、JSON、SEO管理値、ジョブ情報、生成情報の付与を全面的に廃止し、公開本文だけを保存する設計へ変更した。
- 親子関係、SEO管理値、生成エンジン、プロンプト改訂などを記事ルート外の子記事管理JSONへ分離した。
- MLX用とGemini用のプロンプトをクラウドで別管理し、歯車UIから表示、編集、保存、確認付き削除を行う設計を追加した。
- 設計計画第3版ではWindowsおよびMacワーカーheartbeat失効中にMLXジョブを登録しない方針だった。Mac側の方針は設計計画第5版で、ジョブを登録して手動復旧できる方式へ変更した。
- アプリケーション実装前のコミット、Gitタグ、bundle、未追跡資料、SHA-256をリポジトリ外へ保存した。
- bundleから別フォルダへ実際にcloneし、開発前コミット `e91127abd28450a024b147855d0404722a3e8dbc` へ復元できることを確認した。

検証結果:

- 復元記録は `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel_restore/pre_accessories_20260812/RESTORE.md` に保存した。
- 復元試験先 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel_restore/pre_accessories_20260812/restore_verification` のHEADは開発前コミットと一致し、追跡対象の作業ツリーはcleanだった。
- アプリケーションコード、API、workflow、`affiliate_links.txt` の実データ、秘密情報は変更していない。
- `winmacsync` は実行していない。

### 2026-08-12: 親記事派生型へ変更した設計第4版

実施内容:

- 第一ゴールを、カテゴリ特化記事の全面生成から「親記事を維持し、H1・既存SEO形式H2・結論だけを対象カテゴリ向けに変更する方式」へ変更した。
- H1と変換対象H2を「製品名 バッテリーおすすめ：」「製品名 ケーブルおすすめ：」などの形式へ変換し、既存の接尾辞、見出し数、階層、順序を維持する仕様へ変更した。
- MLXとGeminiのプロンプト出力を、親製品の仕様要約と商品ブロック別おすすめ理由だけに限定した。記事全文、見出し、商品本文、URLは生成させない。
- 親記事の本文複製、見出し変換、全 `▼` 商品ブロック、免責事項、リンクまとめの挿入は、周辺機器専用の決定的な処理が行う仕様へ変更した。
- 新規カテゴリ商品群は結論へ一回だけ掲載し、子記事経路では通常記事用 `insert_affiliate_links.py` を呼ばない方針へ変更した。親記事に元からあるリンクは結論外も含めて元位置を維持する。
- H1、変換対象H2、結論追記以外の親記事本文を不変領域とし、SHA-256で意図しない変更を検出する仕様を追加した。

確認結果:

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/docs/accessories_sample_article.md` には「結論」を含むH2がないため、H1直後から最初のH2直前までを冒頭結論として扱う必要がある。
- 既存 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/pipeline/prompts/02-editor-prompt.txt` には、結論以降のH2へ共通SEO接頭辞を付ける既存ルールがあり、子記事では接頭辞部分だけをカテゴリ向けに変換できる。
- 既存 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/pipeline/prompts/04-affiliate-link-manager/insert_affiliate_links.py` はH2前と記事末尾へリンクを挿入するため、結論限定の子記事要件とは両立しない。

検証結果:

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/docs/accessories_spec.md` と本計画書を第4版の生成契約へ更新した。
- アプリケーションコード、既存プロンプト、API、workflow、`affiliate_links.txt` の実データ、秘密情報は変更していない。
- `winmacsync` は実行していない。

### 2026-08-12: スプレッドシート管理とMLX手動復旧を追加した設計第5版

実施内容:

- Googleスプレッドシート `周辺機器DB` を、親記事内の単語・規格と生成する周辺機器カテゴリの対応ルールの唯一の正本へ変更した。
- ローカル `accessory_master.csv` の新規作成計画を廃止し、ユーザーがスプレッドシートから直接ルールを編集できるようにした。
- ユーザーが作成済みの `周辺機器DB_LLM` タブを、Gemini・MLX共通の一子記事一行キュー兼進捗一覧として採用した。
- `周辺機器DB_LLM` の先頭列を、作成日時、完了日時、記事タイトル、進捗、記事URLリンク、大元記事タイトル、大元記事リンクの順に固定した。
- 対象周辺機器、生成エンジン、エラー概要、ジョブID、バッチIDを運用列として追加する設計にした。
- シートの進捗を `記事化`、`失敗`、`完了` の三値に固定し、詳細状態と排他ロックはOneDriveジョブJSONへ分離した。
- 複数カテゴリ選択を一カテゴリ一ジョブ・一行へ変更し、同じ右クリック操作をバッチIDでまとめるジョブJSON Schema v2へ変更した。
- 自動MLXが動かない場合に、`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command` をダブルクリックして未処理行を選択し、同じジョブを処理する必須予備経路を追加した。
- Macのheartbeat失効中でもジョブと `記事化` 行を登録し、手動復旧できる方針へ変更した。WindowsではMLXジョブを登録しない。

確認結果:

- 既存通常MLXは、同じスプレッドシートIDの `ブランド製品名仕訳` タブを入口としている。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/start_mlx.command` は、MLXサーバー起動、記事生成、ログ、保存先の表示まで実装済みであり、周辺機器用`.command`の起動設計へ再利用できる。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_MLX_discrod.command` は `--server-only` でMLXモデルサーバーを確認・起動できる。
- このMacには `clasp` がインストールされておらず、非公開スプレッドシートの匿名取得はHTTP 401だったため、`周辺機器DB` と `周辺機器DB_LLM` の現行列内容はまだ実地確認していない。

検証結果:

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/docs/accessories_spec.md` と本計画書へ、タブの役割、列、進捗、OneDriveジョブとの整合、MLX自動・手動経路、テスト、リスクを反映した。
- スプレッドシート本体、アプリケーションコード、既存MLX起動ファイル、API、workflow、`affiliate_links.txt` の実データ、秘密情報は変更していない。
- `winmacsync` は実行していない。

### 2026-08-12: 周辺機器記事生成のソース実装を開始

実施内容:

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/trigger-info-viewer.js` を削除対象とし、同じ1枠へ `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js` を実装した。
- 左サイドパネルの記事右クリックへ「周辺機器記事作成」を追加し、親記事固定、カテゴリチェックボックス、商品プレビュー、MLX・Gemini選択、単一のプロンプト歯車、進捗表示を実装した。
- `周辺機器DB` と `周辺機器DB_LLM` をGoogle Sheets APIで読み書きし、一カテゴリ一ジョブ・一行、共通バッチID、ジョブIDによる行更新を実装した。
- マスタ行全値とSHA-256、プロンプト本文とSHA-256をジョブへ固定し、実行前に改変を拒否するようにした。
- `affiliate_links.txt` へ `battery` 2商品、`adapter` 2商品、`cable` 3商品を追加し、全 `▼` ブロックを原文順で解析する処理を実装した。
- VercelとGitHub ActionsはGit管理対象外の `affiliate_links.txt` をローカルファイルとして仮定せず、OneDriveの正本から実行時に取得するようにした。
- 既存アフィリエイト編集UIでMEMOを保存しても、`battery`、`adapter`、`cable` などの名前付き商品群を消さない結合処理へ修正した。
- LLMへ記事全文を生成させず、親記事の仕様根拠、結論、番号付き商品ブロックから、仕様要約と商品別おすすめ理由の限定JSONだけを最大3回で生成させるようにした。
- H1と結論以降の既存SEO形式H2だけをシートのタイトル形式へ変換し、結論へ仕様要約、理由、免責事項、全商品原文、リンクまとめを決定的に追加する処理を実装した。
- Frontmatter、YAML先頭、JSON包み、記事全体コードフェンス、内部思考、管理キー、HTML管理コメントを保存前に拒否し、子記事MarkdownをH1から始まる公開本文だけに限定した。
- SEO管理値、親子関係、エンジン、プロンプト改訂、不変領域SHA-256を記事ルート外の管理JSONへ分離した。
- 子記事を `<ONEDRIVE_FOLDER>/周辺機器/<parent_id>/` へ保存し、管理JSONとジョブを `Blog_Vercel_Accessories_Control` へ分離した。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/.github/workflows/accessories-gemini.yml` を追加し、Gemini単独の実行経路を実装した。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/MLX/accessories_engine.py` と `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/accessories_worker.py` を追加し、Geminiへ切り替えないMLX単独経路を実装した。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command` は、先にシート候補を一覧・選択し、対象確定後だけ既存 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_MLX_discrod.command --server-only` を使うようにした。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/com.blogvercel.accessories-worker.plist` と `--install-launchd` 入口を実装した。既存MLX起動ファイルは変更していない。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/google_apps_script/Code.js` へ必須ヘッダーと初期3カテゴリの非上書き投入関数を保存した。
- 一時Apps Scriptへ同じ関数をclasp pushし、入力規則を含むAPI実行デプロイを実行者本人限定でversion 5へ更新した。

検証結果:

- Python単体テスト12件は商品群、記事組立、明示結論、本文専用拒否、不変領域SHA-256、初期3カテゴリ照合、Sheet契約、ジョブ改変拒否、Vercel Function数を検査して合格した。
- JavaScriptのAPI・共通モジュール構文、商品件数、タイトル形式、テンプレートパストラバーサル拒否、MEMO保存時の商品群保持を検査して合格した。
- `.command` は `bash -n`、launchd定義は `plutil -lint`、Pythonは `compileall` に合格した。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api` 直下は12ファイルであり、削除前後でVercel Function候補数を増やしていない。
- Vercel公式資料上、直接配置型のHobbyは12 Functionsが上限である。Vercel CLIは未認証のため、プロジェクトダッシュボードの実使用量とデプロイ後の関数一覧は未確認である。
- `vercel build --yes` は保存済みVercel認証が無効なため、プロジェクト取得前に停止した。ビルドエラーではなく認証待ちである。
- `clasp run seedAccessoryCategories` は実行API側で関数を認識できず、`周辺機器DB` の初期3行が実際に入ったことは未確認である。Apps Script画面から同関数を一回実行する必要がある。
- ローカル画面の自動ブラウザ接続を開始できなかったため、右クリックメニューとモーダルの実クリック確認は未完了である。JSX構文検査は合格している。
- Gemini・MLXとも秘密情報を使う実ジョブはまだ実行していない。launchdも未登録であり、既存 `.env` やサービスアカウント鍵は読み取っていない。
- `winmacsync` は実行していない。

次の実行確認:

- Google Apps Scriptで `seedAccessoryCategories` を一回実行し、`周辺機器DB` に `battery`、`adapter`、`cable` が各一行だけ存在することを確認する。
- 変更をコミット・pushしてVercelとGitHub Actionsへ反映し、本番UIからGeminiの一ジョブを実行する。
- Macで `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command` をダブルクリックし、MLXの一ジョブを実行する。
- 実ジョブ成功後に `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command --install-launchd` を実行し、Macログイン後のheartbeatを確認する。
- 完成した子記事を親記事と比較し、H1、対象H2、結論追記以外が変わっていないこと、商品群とリンクが結論だけにあること、Frontmatter等がないことを人手確認する。

### 2026-08-12: Vercel認証と本番前の実接続確認

実施内容:

- 旧Vercel CLI `39.4.2` が旧認証方式廃止によりHTTP 410になることを特定し、`58.9.4` へ更新した。
- Vercelアカウント `seahirodigital-3988` でCLI認証し、対象プロジェクト `blog-vercel` との接続を確認した。
- ユーザーの個別許可後、`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/credentials/service_account.json` を値非表示でVercelの `GOOGLE_SERVICE_ACCOUNT_JSON` へ登録した。ProductionとPreviewだけをSensitive属性とし、Developmentには保存していない。
- `package.json` の `dev` が `vercel dev` を再帰呼び出しする問題を修正し、ローカルVercelサーバーを起動できるようにした。
- MLX用とGemini用のプロンプを並行初期化した際、OneDriveの同名フォルダ作成が競合してHTTP 409になる不具合を特定した。JavaScriptとPythonの両方で、409後に既存フォルダを再取得する冪等処理へ修正した。
- 右クリックから `openAccessoryModal` を通じて、MLX/Geminiボタンが同じ `/api/accessories?action=create` へ到達することを固定検査する回帰テストを追加した。

検証結果:

- `npx vercel build --yes` は成功し、`api/accessories.js` を含む12 Functionsがビルドされた。
- ローカルVercel UIはHTTP 200、記事一覧APIはHTTP 200で応答した。
- 実際の親記事を指定した読み取り専用プレビューはHTTP 200で成功した。`battery` 2商品、`adapter` 2商品、`cable` 3商品、MLX/Geminiのプロンプ改訂1を確認した。これにより `seedAccessoryCategories` 実行後のシート契約と `affiliate_links.txt` の実データ連携を確認できた。
- 実ジョブはユーザーの試験対象のため登録していない。スプレッドシートの `周辺機器DB_LLM` にテスト行も追加していない。
- ブラウザ自動操作機能はセッションの接続情報不足で使用できなかった。実クリック試験はユーザーが本番UIで行う。
- launchd定義は `plutil -lint` に合格しているが、Macログイン時の常駐動作をまだ有効にしていない。現状では `.command` をダブルクリックする手動復旧経路だけが動作する。
- `winmacsync` は実行していない。

### 2026-08-12: GitHub反映とVercel本番公開

実施内容:

- 周辺機器機能全体をコミット `32e6dac3` として `main` へpushした。
- 初回本番デプロイ後の実API確認で、VercelのCommonJS変換後に `import.meta.url` が実行できずHTTP 500になることを特定した。
- `lib/accessories-core.js` のテンプレートルート解決を `process.cwd()` へ変更し、修正コミット `d35ae8d3` を `main` へpushした。
- Git連携によるVercel ProductionデプロイがReadyになり、`https://blog-vercel-dun.vercel.app` へエイリアスされたことを確認した。

本番検証結果:

- トップUIはHTTP 200で応答し、配信HTMLに記事右クリック、「周辺機器記事作成」、「MLXで作成」、「Geminiで作成」の配線が含まれることを確認した。
- 記事一覧APIはHTTP 200で応答した。
- 本番 `GET /api/accessories?action=preview` は実際の親記事に対してHTTP 200で応答し、`battery` 2商品、`adapter` 2商品、`cable` 3商品、MLX/Geminiのプロンプを確認した。
- Vercelのデプロイ詳細で `api/accessories` がNode.js Functionとして構築され、デプロイ状態がReadyであることを確認した。
- 実ジョブの登録とLLM呼び出しは、ユーザーが本番UIで行う試験範囲として未実行のまま維持した。

現在の残作業:

- ユーザーが本番UIで左サイドパネルの記事を右クリックし、「MLXで作成」からChromeの確認を許可してTerminalが開くことを確認する。
- Geminiと1ジョブ、MLXと1ジョブを登録し、`周辺機器DB_LLM` の進捗、OneDriveの子記事保存、本文不変契約、Frontmatter非出力を確認する。
- MLXの手動実ジョブが成功した後、必要であればlaunchdを登録して常駐ポーリングを有効化する。

### 2026-08-12: MLXボタンからのTerminal起動とライブ進捗を実装

実施内容:

- Blog Vercelの「MLXで作成」でジョブ登録した後、`blogvercel-mlx://run` を呼び出す導線を追加した。
- `/Users/user/Applications/Blog Vercel MLX Launcher.app` を生成・登録し、許可されたURL形式と1〜5件のUUIDだけを `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command` へ渡すようにした。
- ブラウザの外部アプリ起動確認やポップアップ制限に備え、生成進捗内へ「Terminalをもう一度開く」を追加した。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/accessories_worker.py` を複数の `--job-id` に対応させ、一つのTerminalで選択カテゴリを順番に処理するようにした。
- Terminalへジョブ内容、MLX起動、生成、組立、本文検査、OneDrive保存、周辺機器DB_LLM更新を日本語の段階ログとして表示するようにした。
- ワーカーheartbeatへ現在工程とメッセージを追加し、Blog Vercelの生成進捗へ3秒間隔で反映するようにした。
- 生成進捗へスピナー、進捗バー、経過時間、最終確認時刻、「今すぐ更新」を追加した。

検証結果:

- Python単体テスト18件に合格し、URLスキーム、操作名、未知パラメータ、UUID件数・形式、固定ワーカー以外を実行できないことを検査した。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js` のNode.js構文と `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/index.html` のJSX構文は合格した。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/install_mlx_url_launcher.command` と `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_accessories_worker.command` は `bash -n` に合格した。
- `/Users/user/Applications/Blog Vercel MLX Launcher.app` の署名、アプリ認識、`com.blogvercel.mlx-launcher`、`blogvercel-mlx` の登録を確認した。
- 実装コミット `24bd9088` と実行権限修正コミット `f742be15` を `main` へpushした。
- Vercel Productionデプロイ `dpl_BvPpXcLqaxHMhF9deX97BwXZK1oa` がReadyとなり、`https://blog-vercel-dun.vercel.app` へ反映された。
- 本番配信HTMLに `blogvercel-mlx://run`、「Terminalをもう一度開く」、「ジョブを登録しています」、「今すぐ更新」、工程別進捗の実装が含まれることを確認した。
- 本番の複数ジョブ状態APIが不正なジョブIDをHTTP 400で拒否することを確認した。Vercel Functionsは従来どおり12件である。
- 実ジョブはユーザー試験に残し、この記事生成を伴わないランチャー登録だけを実施した。
- `winmacsync` は実行していない。

次の実行確認:

- MacのChromeで「MLXで作成」を押し、最初の確認画面で「Blog Vercel MLX Launcher.appを開く」を選択する。
- TerminalとBlog Vercelの両方で同じジョブの工程が進み、完了後に記事リンクが表示されることを確認する。
- 完成した子記事がH1、対象H2、結論追記以外を変更せず、Frontmatterや管理情報を含まないことを確認する。

### 2026-08-12: MLX経路からGemini SDK依存を分離

確認した障害:

- Blog VercelからMLXジョブ2件を起動すると、記事処理開始前に `cannot import name 'genai' from 'google' (unknown location)` で失敗した。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/.venv/bin/python3` では `google.genai` を利用できないが、既存 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/start_mlx.command` はGemma E4BのOpenAI互換MLX APIを使うため、同SDKを必要としない。
- 原因は共通実行器がMLX処理でもGeminiエンジンを起動時に無条件importしていたことであり、Gemma E4BモデルやMLXサーバーの障害ではない。

修正内容:

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/accessories/main.py` のGeminiエンジン読込を、`engine_name=Gemini` の分岐内だけで行う遅延importへ変更した。
- MLX経路は `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/MLX/accessories_engine.py` から `http://127.0.0.1:8001/v1/chat/completions` と `mlx-community/gemma-4-e4b-it-8bit` を使い、Gemini SDKへ依存しない構成を維持した。
- 共通実行器へGeminiのトップレベルimportが再混入しない回帰テストを追加した。
- 同じジョブの再実行で、OneDrive応答にcharsetがない場合にPython `requests`が日本語の `▼` を誤判定し、商品ブロックを発見できない第二の問題を特定した。
- 親記事と `affiliate_links.txt` はHTTPヘッダー推測に依存せず、UTF-8 BOM対応で明示デコードするよう修正した。UTF-8以外は文字化けしたまま処理せず停止する。

実運用確認:

- 修正後、失敗済みMLXジョブ `0b3d4e9b-229c-4b71-ac2a-f7ca658b0181` と `30b79975-f248-4341-b59f-6e02c87fbf15` を同じジョブIDで再実行した。
- 既存 `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/start_MLX_discrod.command --server-only` でMLXサーバーが起動し、`mlx-community/gemma-4-e4b-it-8bit` によるバッテリー記事とアダプター記事の生成が完了した。
- 両記事とも生成結果組立、Frontmatter・管理情報検査、OneDrive保存、`周辺機器DB_LLM` の完了日時・記事リンク更新まで成功した。
- 本番状態APIで両ジョブの `state=completed` と `registrySync=completed` を確認した。
- OneDriveへ保存されたMarkdownを再取得し、両記事ともH1開始、禁止メタ情報なし、Amazon商品リンクありを確認した。
- Python単体テスト21件、MLX用仮想環境での共通実行器・Gemma E4Bアダプターimport、Vercelビルドに合格した。
- `python-dotenv could not parse statement starting at line 11` は既存環境ファイルに対する警告として残るが、必要な認証値とMLX設定は読み込まれ、今回の2ジョブは完了している。秘密情報を含む既存環境ファイルは変更していない。

### 2026-08-12: 子記事見出し・保存フォルダ・おすすめ一覧を運用仕様へ修正

変更内容:

- 親H1が `M5 iPad Pro レビュー比較違いまとめ` の場合、製品名を `M5 iPad Pro` と確定し、子H1を `M5 iPad Pro バッテリーおすすめまとめ` または `M5 iPad Pro 充電器おすすめまとめ` とする決定的変換へ変更した。
- 結論以降や既存SEO形式だけに限定せず、全H2を `製品名 カテゴリ名おすすめ: 元見出しの題意` へ変換するよう変更した。H2数・順序・階層、H3以下、本文は維持する。
- `adapter` は既存ジョブ・アフィリエイトセクションとの互換性を保つ内部IDとして維持し、ユーザー向けカテゴリ名と見出しを `充電器` へ変更した。
- 周辺機器子記事のおすすめ一覧へAmazonアソシエイト免責文およびAI整形・編集の注記を新規挿入しないよう変更した。
- 子記事保存先を親記事IDだけのフォルダから、ジョブ作成日時の日本時間と親記事タイトル冒頭10文字を使う `<YYYYMMDD_HHMM_親記事タイトル冒頭10文字>` フォルダへ変更した。同一バッチの複数カテゴリは同じ日時を共有する。

検証項目:

- Python単体テストで、M5 iPad ProのH1完全一致、全H2変換、旧記事軸の除去、免責文非挿入、OneDrive禁止文字除去、日本時間フォルダ名を固定する。
- JavaScript側のプレビュー用タイトル生成もPython側と同じH1規則になることを検査する。
- Vercelビルド後、本番プレビューで `adapter` の表示名が `充電器`、生成予定タイトルが `M5 iPad Pro 充電器おすすめまとめ` になることを確認する。
- 既存の生成済みバッテリー・充電器記事は、本文を再生成せずH1・全H2・免責文だけを移行し、親記事IDフォルダを可読フォルダ名へ変更する。

実運用確認結果:

- Python単体テスト25件、JavaScript構文検査、M5 iPad Proのタイトル変換検査、`git diff --check`、Vercelローカルビルドに合格した。
- 実装コミット `dca12163` を `main` へpushし、Vercel Productionデプロイ `dpl_5U3jKQT3HuUQA4byvg1mTu5kgSQw` がReadyとなり、`https://blog-vercel-dun.vercel.app` へ反映された。
- 本番プレビューで、親記事 `M5 iPad Pro レビュー比較違いまとめ` に対して `M5 iPad Pro バッテリーおすすめまとめ`、`M5 iPad Pro 充電器おすすめまとめ`、`M5 iPad Pro ケーブルおすすめまとめ` が返ることを確認した。既存シートの `adapter` 旧表記は、原文スナップショットとSHA-256を維持したまま実行時だけ「充電器」へ安全に読み替える。
- Apps Scriptへ `migrateAdapterCategoryToCharger` をclasp pushし、version 5のAPI実行デプロイを作成した。claspからの関数直接実行はApps Script側の実行権限で拒否されたため、シート原文を破壊的に更新せず、Blog VercelとMLXの読込層で旧表記互換を有効にした。
- 生成済み2記事を同じOneDrive item IDのまま更新し、バッテリー記事と充電器記事のH1完全一致、全22件のH2接頭辞、免責文非混入を再取得して確認した。
- 既存の親記事IDフォルダを `20260812_2213_M5 iPad Pr` へ名称変更し、同フォルダ内に2記事が残ることをBlog Vercelの記事一覧APIで確認した。記事URLは同じOneDrive item IDのまま維持されている。

### 2026-08-12: 商品文の限定調整・複数親記事バッチへ変更

確定した変更:

- MLX・Geminiは親記事の仕様要約を生成せず、親製品名とカテゴリ名を含む冒頭案内文、および各商品ブロックの主語・助詞・接続・最小限の言い回しだけを生成する。
- `affiliate_links.txt` の商品名行、URL、型番、容量、出力、価格、数値、商品順を固定する。元文に理由がない場合だけ、親製品を主語にする一文を追加できる。
- 「おすすめ商品のリンクまとめ」、商品別の追加見出し、Amazonアソシエイト免責文、AI整形・編集注記を生成しない。
- 親記事はH1、全H2、H1直後の短い案内文、結論末尾の商品ブロック以外を変更しない。
- 実運用記事の `## Marshall Acton 4レビュー比較まとめ：結論` で配置を再検証し、`結論`単独だけでなく既存SEO接頭辞付きH2も結論範囲として識別するよう修正した。
- 商品ブロック検査ではLFとCRLFを正規化し、改行コードだけの差を原文改変と誤判定しない。商品名・URL・数値仕様・順序・変更量を個別に検査する。
- 複数選択時のコンテキストメニューを `周辺機器記事作成（N件）` とし、ポップアップは各記事タイトルの直下へカテゴリ名のチェックボックス行だけを表示する。
- 選択した全「親記事×カテゴリ」を一つのバッチIDで登録する。MLX URLにはジョブIDを列挙せずバッチIDだけを渡し、ワーカーが同バッチの未処理ジョブを固定件数上限なしで一件ずつ処理する。
- 子記事フォルダ名を `<YYYYMMDD_HHMM_親記事タイトル冒頭20文字>` へ変更する。

実運用確認対象:

- 失敗ジョブ `d4fff3dd-e759-485c-97b5-b840704972de` を新プロンプト契約へ移行し、親記事 `Marshall Acton 4レビュー比較まとめ：自宅での音楽体験を格段に向上させるホームスピーカー` からバッテリー子記事を再生成する。
- 完成記事で冒頭案内文、全H2、商品名・URL・数値維持、リンクまとめ非出力、20文字フォルダ名、`周辺機器DB_LLM` 完了更新を確認する。

実運用確認結果:

- コミット `e7a48f8e` で商品文の限定調整、複数親記事UI、バッチID実行、20文字フォルダを実装し、コミット `cd7b5117` で既存SEO接頭辞付き結論H2の識別を修正した。
- Vercel Productionデプロイ `dpl_HzAtWi3pf5AFabwm43w9MzHrdDKg` がReadyとなり、`https://blog-vercel-dun.vercel.app` へ反映された。
- MLXとGeminiのOneDrive保存プロンプトを契約v2へ更新し、失敗ジョブ `d4fff3dd-e759-485c-97b5-b840704972de` を同じジョブIDで実MLX再実行した。1回目で完了し、OneDrive記事ID `FFCC26DEDBBA4E70!s18f3a546db6c41348682ad0445d6dd3a` を保存した。
- 保存フォルダは `20260812_2326_Marshall Acton 4レビュー` となり、日時と親記事タイトル先頭20文字の規則に一致した。
- 保存済みMarkdownを再取得し、H1が `# Marshall Acton 4 バッテリーおすすめまとめ`、全9件のH2が指定接頭辞付き、冒頭案内文が親製品とカテゴリを含むことを確認した。
- バッテリー2商品は結論H2の範囲内に原順で1回ずつあり、商品名とURLは正確に1回、各商品文は `Marshall Acton 4` を主語に含む。追加商品ブロック内に免責文、AI編集注記、「おすすめ商品のリンクまとめ」はなく、Frontmatterもない。
- 親記事と実際の追加文から決定的に再組立したMarkdownが保存済みMarkdownとバイト一致し、`周辺機器DB_LLM` は対象ジョブ1行のみが `完了`、完了日時・記事URL一致となった。
- Python単体テスト31件、API構文、画面JSX構文、MLXワーカー構文、Vercel本番相当ビルドに合格した。`python-dotenv` の既存環境ファイル11行目に対する警告は残るが、秘密情報は表示・変更せず、実ジョブは完了した。

### 2026-08-13: フォルダの全期間設定継承と件数最新化

- 子フォルダに個別設定がない場合は、最も近い親フォルダの「全期間読み込み」と読込上限を継承する。子で明示的にON/OFFした場合は子の設定を優先する。
- フォルダの浅い読込みでOneDrive Graphから全ページ列挙した直下要素数を `currentChildCount` として返し、開いたフォルダ自身の古い `childCount` を必ず上書きする。

### 2026-08-13: アフィリンク全セクション編集と共通説明文対応

- 管理APIのMEMO専用解析を廃止し、`affiliate_links.txt` にある全 `===名前===` セクションを記載順で読込み・往復保存する。画面は `MEMO1 / MEMO2 / battery / adapter / cable` を「メモ1 / メモ2 / バッテリー / 充電器 / ケーブル」と表示する。
- 名前付きセクション直後から最初の `▼` までをカテゴリ共通説明文とし、各 `▼` から次の `▼` までをURLの有無にかかわらず一ブロックとして欠落なく保持する。
- MLXとGeminiのプロンプト契約をv3に上げ、カテゴリ共通説明文を限定JSONで返す。変更は `おすすめ`行の主語を親製品名へ切り替える範囲に限定し、その他の行は完全一致、行数、URL、数値・英数字の保持を保存前に検査する。

実運用確認結果:

- コミット `54995eb3` を `main` へpushし、Vercel Productionデプロイ `dpl_GrGWU3MNZzJDgfNyywqG1Ug5h7C8` がReadyとなった。
- 公開APIから `MEMO1 / MEMO2 / battery / adapter / cable` が記載順で返り、表示名が「メモ1 / メモ2 / バッテリー / 充電器 / ケーブル」であることを確認した。
- OneDrive実ファイルで、`battery`の共通説明文16行・ `▼` 14ブロック、`adapter`の共通説明文18行・ `▼` 19ブロック、`cable`の共通説明文14行・ `▼` 13ブロックを欠落なく取得した。
- MLXとGeminiのOneDrive保存プロンプトはどちらも契約v3・改訂3となり、`adapted_section_intro` を含むことを確認した。
- Python単体テス35件、全セクション往復保存、API構文、JSX構文、Python構文、Vercel本番相当ビルドに合格した。

### 2026-08-13: MLXの主語必須検査とJSON出力不合格を修正

確認した原因:

- `scripts/accessories/prompt_builder.py` で、各商品ブロックとカテゴリ共通説明文の両方に親製品名が必ず含まれることを合格条件にしていた。これは主語調整を nice to have とする運用と矛盾していた。
- MLX応答は返答全体をそのまま `json.loads()` に渡していた。前後の説明、Markdownコードフェンス、JSON構文崩れをすべて同じ「LLM応答が指定JSONではありません」としており、原因を判別できなかった。
- vMLXの `http://127.0.0.1:8001/openapi.json` で `response_format` の `json_schema` 対応を確認し、Gemma E4Bの実応答でも有効なJSONだけを返せることを確認した。

修正内容:

- 商品ブロックとカテゴリ共通説明文は、親製品名を含まない原文のままでも合格とする。主語調整を行う場合だけ、従来どおり変更範囲、URL、数値、行数を検査する。
- 保存プロンプト契約をv4とし、「自然にできる場合のみ主語を調整し、不自然な場合は原文を返す」と明記する。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/MLX/accessories_engine.py` にvMLXの厳密JSON Schemaを設定し、3キーと商品配列の型を生成時点で強制する。
- 応答解析はコードフェンスと前後説明付きJSONを回収し、回収できない場合はJSON解析エラーの行・列を表示する。

検証結果:

- Python単体テス38件に合格した。原文のままの共通説明文・商品ブロックを合格にする回帰テストを含む。
- 起動中の `mlx-community/gemma-4-e4b-it-8bit` へ厳密JSON Schemaを付けて実リクエストし、前後文のない有効JSON、指定3キー、商品配列を確認した。
- Python構文、Node.js構文、`git diff --check`、Vercel本番相当ビルドに合格した。
- 実装コミット `e73e1d07` を `main` へpushし、Vercel Productionデプロイ `dpl_EYKyGRDC4CTASw1btgKkhKLBjP2k` がReadyとなり、`https://blog-vercel-dun.vercel.app` へ反映された。
- 本番APIからMLX・Gemini両方のOneDrive保存プロンプトを更新し、どちらも契約v4・改訂4・同一SHA-256であることを確認した。

### 2026-08-13: 改行保持・累積エラーフィードバック・警告付き出力

確認した原因:

- OneDriveへ保存されたMarkdownの通常改行は残っていたが、Blog VercelのMarkdown描画設定がソフト改行を画面上で空白として扱っていた。
- カテゴリ共通説明文と商品ブロックを原文と完全に同じ行数にする検査があり、安全な補足行まで不合格にしていた。
- MLX再試行時に「前回不合格」としか伝えておらず、実際の検査エラーを次の試行で修正できなかった。
- 3回不合格の場合は記事を一件も保存しないため、ユーザーが手作業で修正できる成果物も残らなかった。

実装内容:

- Blog Vercelのプレビューだけ通常改行を改行表示する。OneDrive保存Markdownとnote送信本文にはHTMLの `<br>` を追加せず、通常のMarkdown改行を維持する。
- カテゴリ共通説明文と商品ブロックは、原文行と空行の削除を禁止する。原文行を順番どおり保持した行の追加は許可し、原文より行数または空行数が減った場合だけ不合格にする。
- 全体類似度60%と行ごとの類似度65%を合否条件から外し、原文行、商品名、URL、数値仕様、順番を個別に保護する。
- 2回目へ1回目の検査エラー、3回目へ1回目と2回目の検査エラーを累積して渡す。
- 3回とも不合格の場合、不合格なLLM応答は保存せず、決定的な冒頭文、カテゴリ共通説明文の原文、全商品ブロックの原文で子記事を保存する。
- 安全な原文フォールバックは `完了` として記事URLを保持し、OneDriveジョブJSONとBlog Vercelの生成進捗へ `警告あり・出力済み`、出力方式、全試行エラーを表示する。ターミナルにも同じ警告を表示する。
- 親記事取得、OneDrive保存、壊れたジョブなど、安全な記事自体を作れない障害は警告付き保存の対象外とし、従来どおり `失敗` にする。

検証項目:

- 保存Markdown、記事組立コード、noteへ渡す本文にリテラルの `<br>` を挿入しない。
- Blog Vercelプレビューで通常改行だけが画面上の改行として表示される。
- 原文行を保った追加行は合格し、原文行または空行を減らす出力は不合格になる。
- 3回分の検査エラーが累積し、3回不合格時も原文とURLを保持した記事が保存される。
- Blog Vercelの生成進捗とMLXターミナルで、警告付き出力と各試行エラーを確認できる。

実運用確認結果:

- Python単体テスト46件、Python構文、API構文、Blog Vercel JSX構文、`git diff --check`、Vercel本番相当ビルドに合格した。
- 稼働中の `mlx-community/gemma-4-e4b-it-8bit` へ改行を含む共通説明文と商品ブロックを実送信し、JSON文字列の改行が各行と空行を保ち、リテラルのHTML `<br>` を含まないことを確認した。
- 失敗済みジョブ `05e63c3f-8933-4c0e-8106-1f1b54a03d10` を再実行した。1回目は原文14行に対し11行、2回目と3回目は13行で不合格となり、各回の検査エラーを次回へ累積して3回処理した。
- 3回不合格後、安全な原文フォールバックへ移行し、記事 `Insta360 X6 ケーブルおすすめまとめ` をOneDrive item ID `FFCC26DEDBBA4E70!s8cf2915f22aa4a83bc1a60c2e0d56c45` として保存した。
- ターミナルに `警告`、原文で出力した旨、3回分の行数エラー、記事URLを表示し、`周辺機器DB_LLM` は記事URLを持つ `完了` へ更新した。
- 実装コミット `4ba4f685` を `main` へpushし、Vercel Productionデプロイ `dpl_6Ua46rvPrNecqWHsTctW9o6XQgyR` がReadyとなり、`https://blog-vercel-dun.vercel.app` へ反映された。
- 本番HTMLで表示専用の `breaks: true` と警告表示UIを確認した。本番ステータスAPIでも対象ジョブが `completed`、`outputMode=safe_source_fallback`、警告、3回分のエラー、記事URLを返すことを確認した。
- MLXとGeminiのOneDrive保存プロンプトを契約v5・改訂5へ更新した。両方のSHA-256は `0ca282e4a0bd1004052e4248a31bdacd38e239d554cf53411ace9759e0ae135c` で一致し、通常改行維持とHTML `<br>` 禁止を含む。
- 保存記事を本番記事APIから再取得し、401行、空行140行、箇条書き19行が個別行として保持され、リテラルの `<br>` が0件、Frontmatterがないことを確認した。

### 2026-08-13: noteアップ済フォルダの表示とフォルダ一括削除

確認した原因:

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/articles.js` が `noteアップ済`、`noteアップ済み` 等を除外キーワードとして扱い、OneDriveから取得してもサイドパネルと「表示フォルダの管理」へ渡していなかった。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/Obsidian in Onedrive 202602/Vercel_Blog/noteアップ済` にはMarkdownが540件あり、最新記事は2026-08-13更新だったため、非表示の原因は更新時刻ではなく明示的な除外処理だった。
- フォルダ右クリックは全期間読込みと非表示だけに対応し、フォルダ選択・削除操作はなかった。記事削除APIはDriveItem IDを削除できたが、フォルダを記事ルート内に限定する入力検査と複数処理がなかった。

実装内容:

- `noteアップ済` 系のサーバー除外を解除し、ルート一覧と「表示フォルダの管理」へ返す。初回移行時は過去の非表示設定から同フォルダだけを外してチェック済みにし、その後のユーザーON/OFFは従来どおりブラウザへ保存する。
- `noteアップ済` 配下は21日制限を使わず、更新日時の降順で直近5記事だけを初期読込みする。右クリックから5・10・25・50・100件を指定でき、追加50件も選べる。
- フォルダ右クリックへ「選択」と「削除」を追加する。選択モードではフォルダ行にチェックボックスを表示し、複数フォルダを選んだ右クリック削除に対応する。
- 親フォルダとその子フォルダを同時選択した場合は親だけを削除対象にまとめ、二重削除を防ぐ。
- 削除確認画面へ対象パス、対象数、中の記事と子フォルダも含まれることを表示する。削除はMicrosoft Graph v1.0の通常削除を使い、完全削除ではなくOneDriveのごみ箱へ移動する。
- APIはクライアントから任意のDriveItem IDを受け取らず、`ONEDRIVE_FOLDER` 配下の相対パスとして解決する。空パス、記事ルート、`.`、`..`、ファイルを拒否し、Graphでフォルダであることを確認してから削除する。

ローカル実データ確認:

- ローカルVercelの記事ルートAPIから `noteアップ済` がフォルダID `FFCC26DEDBBA4E70!s505249286a9146e182e36671fb15380e`、直下要素540件として返ることを確認した。
- 同フォルダを `includeAll=true`、`articleLimit=5` で読み込み、総数540件に対して返却5件、更新日時降順、先頭が `Insta360 X6レビュー比較まとめ：360度カメラで撮影効率化と時短を実現` であることを確認した。
- 実フォルダは削除せず、空パスと `../outside` の削除要求がHTTP 400で拒否されることを確認した。

本番反映結果:

- Python単体テスト48件、API構文、Blog Vercel JSX構文、`git diff --check`、Vercel本番相当ビルドに合格した。
- 実装コミット `0dbc8086` を `main` へpushし、Vercel Productionデプロイ `dpl_Coe9pMfddLMbnGdodmBjRG7cbgeH` がReadyとなり、`https://blog-vercel-dun.vercel.app` へ反映された。
- 本番HTMLで初期5件設定、5・10・25・50・100件の選択肢、フォルダ複数選択表示、削除確認画面を確認した。
- 本番記事ルートAPIで `noteアップ済` が初期表示対象として返り、直下要素540件であることを確認した。本番フォルダAPIでも総数540件から最新5件だけが更新日時降順で返った。
- 本番削除APIへ空フォルダパスを送信し、実データへ変更を加えず `記事ルートフォルダは削除できません` と拒否されることを確認した。実フォルダの削除試験は行っていない。

### 2026-08-13: 生成結果復帰・ルート記事数・カテゴリ一括選択

実装内容:

- MLX・Geminiの周辺機器生成レポートをブラウザのLocalStorageへ直近10バッチ保存する。モーダルを閉じた後やページ再読込み後も、フォルダの右クリックにある「周辺機器の生成結果」から進捗、警告、エラー、完成記事リンクを再表示できる。
- ジョブの親記事タイトルと作成日時から、実際の `<YYYYMMDD_HHMM_親記事タイト冒頭20文字>` を同じ規則で求め、右クリックしたフォルダのバッチを優先する。対応履歴がない場合は進行中、それもなければ最新バッチを表示する。表示時はバッチIDで `/api/accessories?action=status` を再取得する。
- 状態APIは完成記事のOneDrive item IDも返し、読込済みの子記事との一致判定を補強する。
- OneDrive直下の記事またはサイドパネルの空欄の右クリックへ、「OneDrive直下の読み込む記事数」を追加した。初期5件、最小5件、最大2000件で、5件ずつ増減する。設定はLocalStorageへ永続化する。
- ルート記事の件数指定が従来の21日フィルターで効かなくならないよう、記事だけを全期間対象にする `includeAllArticles` を追加した。フォルダ一覧の期間判定は従来どおりである。
- 周辺機器記事作成モーダルへ「すべて」と、現在表示される各カテゴリのON/OFFボタンを追加した。単一親記事と複数親記事の両方で、全チェックまたは同一カテゴリのチェックだけを一括反転できる。

ローカル検証結果:

- Python単体テス51件、`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js` と `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/articles.js` のNode.js構文、`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/index.html` のJSX構文、Vercelビルド、`git diff --check` に合格した。
- ローカルVercel APIの実OneDriveデータ45記事に対し、上限5指定で5記事、上限10指定で10記事が返ることを確認した。いずれもフォルダ数は10、`includeAll=false`のままで、フォルダ期間設定を変更していない。
- ローカル配信HTMLに「周辺機器の生成結果」「OneDrive直下の読み込む記事数」「すべて」一括選択が含まれることを確認した。
- ブラウザ操作による視覚確認は、実行環境のブラウザ接続情報が不足したため実施できなかった。データ削除と生成ジョブ実行は行っていない。
- `winmacsync` は実行していない。

本番反映結果:

- 実装コミット `5164af82` を `main` へpushした。
- Vercel Productionデプロイ `dpl_E4dcqsj94i1aEgoBWUTeWcm4uCEr` が `READY` となり、`https://blog-vercel-dun.vercel.app` へ反映された。Vercel Functionsは12件で上限内を維持した。
- 本番配信HTMLに「周辺機器の生成結果」「OneDrive直下の読み込む記事数」「すべて」一括選択と `includeAllArticles` が含まれることを確認した。
- 本番OneDriveデータ45記事に対し、上限5指定で5記事、上限10指定で10記事が返ることを確認した。どちらもフォルダ数10、`includeAll=false`、`includeAllArticles=true` である。
- 完了済みバッチ `676acc4a-1d3b-4437-9159-f43c36d304c9` の本番状態APIが2ジョブとも `state=completed`、完成記事の `articleId`と `articleUrl` を返すことを確認した。

### 2026-08-13: 生成2回化・商品名開始の文頭・生成結果復帰の正本化

確認した原因:

- 再試行上限が3回のままであり、最終的に安全な原文フォールバックを保存する運用に対して待ち時間が長かった。
- 冒頭文は親製品名とカテゴリ名を含むだけで合格していたため、「この記事では」から開始する弱い導入を防げなかった。
- 生成済みフォルダから結果を開く処理が、主にブラウザのLocalStorageへ保存した直近10バッチへ依存していた。別タブ、履歴消去、旧画面から開始したジョブではフォルダとバッチを結び付けられず、「表示できる周辺機器の生成結果がありません」となった。
- 一括選択は小さなON/OFFボタンで、プレビュー取得前は非表示になるため、通常のチェックボックスとして認識しにくかった。

実装内容:

- MLX・Geminiとも生成を最大2回とする。2回目へ1回目の検査エラーを渡し、2回とも不合格なら原文を保護した安全な記事を警告付きで保存する。
- 冒頭文は必ず親製品名から開始し、「おすすめの周辺機器をお探しではありませんか」という検索意図への問いかけと、「商品情報をあわせて紹介する」という案内の2文にする。検査でも親製品名開始と必須表現を確認する。
- 保存プロンプト契約をv6へ上げ、MLXとGeminiの両方へ同じ冒頭文契約を適用する。
- 状態APIへ `folderPath` 検索を追加する。`周辺機器DB_LLM` の作成日時と大元記事タイトルを、保存処理と同じ日本時間・先頭20文字・禁止文字除去規則でフォルダパスへ復元し、対応するバッチの全ジョブを返す。
- 状態APIは親記事ID・親記事タイトル・バッチIDも返す。フォルダ右クリックではサーバー検索を第一経路にし、LocalStorageはAPI取得失敗時だけの代替経路にする。
- 「すべて」と各カテゴリの一括操作を明示的なチェックボックスとして常時表示し、単一・複数親記事のどちらでも同じ操作にする。
- ルートHTMLへ `Cache-Control: no-store, max-age=0` を付け、古いタブ以外で旧画面がキャッシュから再表示されにくくする。

ローカル検証結果:

- Python単体テスト56件、API構文、Blog Vercel JSX構文、Python構文、Vercel本番相当ビルド、`git diff --check` に合格した。
- 生成上限2回、親製品名開始の冒頭文、不正な「この記事では」開始の拒否、フォルダパス検索、一括チェックボックス、HTMLのno-storeヘッダーを回帰テストへ追加した。
- 秘密情報を含む環境ファイルは読み取り・変更していない。`winmacsync` は実行していない。

本番反映結果:

- 実装コミット `6fbb544b` を `main` へpushした。
- Vercel Productionデプロイ `dpl_H5nyhD6228HM9kXPojoBgaaaz8SU` が `READY` となり、`https://blog-vercel-dun.vercel.app` へ反映された。
- 生成済みフォルダ `周辺機器/20260813_1503_Insta360 X6レビュー比較まとめ` だけを指定して本番状態APIを呼び、LocalStorageを使わずバッチ `676acc4a-1d3b-4437-9159-f43c36d304c9` を復元した。バッテリー・ケーブルの完了2ジョブ、親記事タイトル、両記事URL、ケーブル記事の警告と旧3試行分のエラー履歴が返ることを確認した。
- 本番プレビューを実行し、MLX・GeminiのOneDrive保存プロンプトがともに契約v6・改訂6となり、親製品名開始、検索意図への問いかけ、商品情報の案内、「この記事では」開始禁止を含むことを確認した。
- 本番配信HTMLに「すべて」とカテゴリ別の実チェックボックスがあり、ルート応答ヘッダーが `Cache-Control: no-store, max-age=0` であることを確認した。

### 2026-08-13: 最初の商品ブロック直後への専用結論・MLX回数選択

確定した変更:

- 周辺機器のカテゴリ共通説明文と全商品ブロックは、親記事の既存結論末尾ではなく、親記事に元からある最初の商品ブロック直後へ移す。
- 親記事の最初の `▼` から次の `▼` または次のH2直前までを一商品ブロックとして扱い、商品名、説明、Amazon URL、改行を分断しない。
- 最初の商品ブロック直後へ `## 親製品名 周辺機器名おすすめまとめ：結論` を決定的に追加し、その直下へ `affiliate_links.txt` の対象セクション内容を置く。2番目以降の親商品と既存本文は後続へ原順で残す。
- サイドパネルの記事右クリックと空欄右クリックの読込設定へ、5～2000件の数値入力と適用操作を追加する。既存の `−5`・`＋5` も残す。
- 記事右クリックへ「周辺機器の生成結果」を追加する。記事IDからH1を取得し、`周辺機器DB_LLM` の子記事タイトルまたは大元記事タイトルと照合して最新バッチを復元する。
- 周辺機器記事作成画面右上で、閉じるボタンの左へMLX設定の歯車を追加する。生成・修正回数は1回・2回・3回から選び、既定値を1回とする。
- MLX回数はLocalStorageだけでなく、一バッチの各OneDriveジョブJSONの `generation_options.max_attempts` へ固定する。Mac側ワーカーはジョブ値を読み、旧ジョブで値がない場合は1回を使う。
- 最終回が不合格でも不合格応答は保存せず、従来どおり原文を保護した安全な記事を警告付きで出力する。Geminiの既定回数は2回のまま維持する。

ローカル検証対象:

- 第一の親商品URL、専用結論見出し、カテゴリ商品群、第二の親商品がこの順序になること。
- 読込数へ20件・50件などを直接入力でき、5～2000件に正規化して保存されること。
- 親記事と生成子記事のどちらの記事IDからでも対応バッチを検索できること。
- MLXの1・2・3回がジョブへ保存され、未指定時は1回、不正値は拒否されること。
- Frontmatter、YAML、JSON包み、HTML `<br>`、リンクまとめ、免責文を完成Markdownへ追加しないこと。

検証結果:

- Python単体テスト59件、Node.js構文、Blog Vercel JSX構文、Python構文、`git diff --check`、Vercel本番ビルドに合格した。
- サンプル親記事を決定的に組み立て、第一の親商品Amazon URL、`## iPad Pro M5 13インチ バッテリーおすすめまとめ：結論`、`battery`の共通説明文と全商品ブロック、第二の親商品がこの順番になることを確認した。
- 実装コミット `c21f61d9` を `main` へpushした。
- Vercel Productionデプロイ `dpl_uZwJgaCQV8Z9DF5f44v1i4ggn9Sp` が `READY` となり、`https://blog-vercel-dun.vercel.app` へ反映された。
- 本番配信HTMLに、記事右クリックへ常時表示される数値入力と「適用」、記事右クリックの「周辺機器の生成結果」、周辺機器画面右上の歯車、MLX 1回・2回・3回の選択肢が含まれることを確認した。
- 本番記事APIへ20件を指定し、`articleLimit=20`、`includeAllArticles=true`、記事20件が返ることを確認した。
- 親記事ID `FFCC26DEDBBA4E70!s0ff8ff7a15054b74a074eb5899d2f83d` と、その最新子記事ID `FFCC26DEDBBA4E70!s31225b980bc44b8b83cd08c6d9925f4e` の両方から、同じバッチ `f4fec8fd-cc90-4fdb-8dd1-20e4c8454704` を復元できた。
- MLX回数4回の要求は、OneDriveやシートへジョブを登録する前に本番APIがHTTP 400と日本語エラーで拒否した。新規の実MLX記事生成はユーザー試験用として実行していない。
- ブラウザ自動操作は実行環境側の接続情報不足で開始できなかったため、配信HTML、状態API、記事API、JSX契約テストで確認した。秘密情報を含む環境ファイルは読み取り・変更せず、`winmacsync` も実行していない。

### 2026-08-13: SEOキーワード別のタイトル派生生成

確定した仕様:

- 記事右クリックの「タイトル変更」は元記事のリネームではなく、一つの元記事から複数SEOキーワード版を同じOneDriveフォルダへ生成する。
- Markdownリンク、Google検索URL、タブ列、`＋`、空欄、重複を除去し、整形後のキーワードと `{キーワード}まとめ` を登録前に一覧表示する。
- H1とH2～H6はプログラムで一括変換する。本文、Amazon商品ブロック、アフィリエイトURLは原則として維持する。
- MLXはH1直後の最初の冒頭段落と、結論直下の最初の短文だけを調整する。記事全文と商品ブロックは入力・出力対象にしない。
- 元記事に専用結論がない場合は、最初のAmazon商品ブロック直後へ `{キーワード}まとめ：結論` と短文を追加する。既に専用結論があれば同じ位置を使う。
- MLXが全試行で不合格でも、元の冒頭文・結論文を保持し、見出しだけを安全に変換した記事を警告付きで保存する。
- 同名記事は上書きしない。一つのキーワードが保存衝突しても、バッチ内の別キーワード処理は継続する。
- Vercel Function数を増やさず、`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js` の新操作として実装する。

実装ファイル:

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/index.html`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/lib/title-variants.js`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/title_variants/article_transformer.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/title_variants/job_schema.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/title_variants/prompt_builder.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/scripts/title_variants/main.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/accessories/templates/tpl_title_variant.md`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/MLX/accessories_worker.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Gemma4_AMZN_Blog/MLX/accessories_engine.py`

ローカル検証結果:

- Python単体テスト70件に合格した。SEO派生テストでは、キーワード整形、H1～H6変換、最初の商品ブロック直後への結論挿入、URL・商品行保持、MLX JSON制約、自然な語順変更の許容、同一フォルダ保存パスを確認した。
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/index.html` のBabel JSX解析、`/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js` と `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/lib/title-variants.js` のNode.js構文、Python構文、`git diff --check`に合格した。
- ユーザー保有の既存記事サンプル820行を変換し、出力824行、元URL・全商品行維持、第一の商品URLより後かつ第二の商品より前に専用結論が入ることを確認した。サンプルファイル自体は変更していない。
- Vercel本番相当ビルドが成功し、Functionsは既存の12ファイル以内を維持した。
- ローカル配信HTMLに右クリック「タイトル変更」、整形後プレビュー、複数件MLX作成、進捗、警告、記事リンク、Terminal再起動、専用プロンプト編集の各導線が含まれることを確認した。
- ブラウザ内自動操作は実行環境の接続情報不足で開始できなかったため、実クリック確認は配信HTMLとJSX契約テストで代替した。生成ジョブとOneDrive記事はまだ実作成していない。
- 秘密情報を含む環境ファイルは読み取り・変更していない。`winmacsync` は実行していない。

### 2026-08-13: 最初のAmazon URL直後への結論・生成記事のエディター導線

確定した変更:

- 結論の挿入位置を、最初の商品ブロック末尾から、最初の `▼` 以降にある最初の `amazon.co.jp` または `amzn.to` URL行の直後へ変更する。
- URLより後に元から存在する文章、二番目以降の商品、既存本文は、新しい結論と対象カテゴリ商品群より後へ原順で残す。
- 最初の商品範囲にAmazon URLがない記事は、次の `▼` または次のH2直前を代替位置として処理を継続する。
- 記事の右クリックメニューは「周辺機器記事作成」「周辺機器の生成結果」「タイトル変更」の順とする。
- 周辺機器の生成結果にある「記事を開く」は「OneDriveブラウザで開く」へ変更し、その下へ「エディターで開く」を追加する。
- 「エディターで開く」は生成結果のOneDrive item IDで本文を取得し、Blog Vercelの通常の記事編集画面へ遷移する。記事一覧に未読込でも生成結果から一時記事情報を補完する。

検証結果:

- Python単体テスト72件に合格した。Amazon URL、専用結論、対象カテゴリ商品群、URL後の親記事本文、二番目の商品がこの順序になることを確認した。
- Amazon URLがない場合の代替位置が従来どおり維持されることを確認した。
- JSX構文、Node.js構文、Python構文、`git diff --check`、Vercel本番相当ビルドに合格した。
- UI契約テストで、右クリックメニュー順、「OneDriveブラウザで開く」「エディターで開く」、OneDrive item IDを既存の記事選択処理へ渡すことを確認した。
- 実装コミット `527bea8c` を `main` へpushした。
- Vercel Productionデプロイ `dpl_ArMsuMGsa2fvRromLiP9EkbqFpcy` が `Ready` となり、`https://blog-vercel-dun.vercel.app` へ反映された。
- 本番配信HTMLで、右クリック項目が「周辺機器記事作成」「周辺機器の生成結果」「タイトル変更」の順であることと、「OneDriveブラウザで開く」「エディターで開く」、OneDrive item IDを使う編集処理が配信されていることを確認した。
- ブラウザ内自動操作は実行環境側の接続情報不足で開始できなかったため、実クリックは行わず、本番配信HTML、UI契約テスト、JSX解析で確認した。記事生成やOneDriveへの書き込みは行っていない。

### 2026-08-13: 添付実記事による挿入位置とタイトル変更UIの再修正

再確認した原因:

- 前回は「最初の `▼` 以降」に検索範囲を限定したため、実記事で `▼脅威の65％OFF...` より前にある最初の `amazon.co.jp` URLを見落とし、後方の `amzn.to` URL直後へ結論を置いていた。
- 「OneDriveブラウザで開く」「エディターで開く」は周辺機器記事作成の生成結果だけに実装され、タイトル変更の生成結果には旧表示「記事を開く」が残っていた。
- タイトル変更元に既存の結論がある場合、その見出しと商品群を現在位置から移動しないため、URL検出だけ直しても既存結論の位置は変わらない構造だった。

確定した再修正:

- `▼` の位置に関係なく、H1以降で最初に出現する `amazon.co.jp` または `amzn.to` URL行の直後を挿入位置にする。
- タイトル変更元に既存結論がある場合は、その見出しから次の同階層以上の見出し直前までを一セクションとして切り出し、最初のAmazon URL直後へ移動する。
- URLと商品行の保護検査は、結論セクションを正しい位置へ移した決定的な基準本文と照合する。結論内の商品順と本文は維持する。
- 周辺機器記事作成とタイトル変更の両生成結果へ、「OneDriveブラウザで開く」と「エディターで開く」を同じ縦並びで表示する。旧表示「記事を開く」は残さない。

ローカル検証結果:

- Python単体テスト73件に合格した。添付と同じく、最初の `amazon.co.jp` URL、結論と対象商品群、`▼脅威の65％OFF...`、後方の `amzn.to` URLの順になることを確認した。
- 既存結論セクションの移動後も、URL・商品行が欠落せず、結論内の対象商品群と残りの親記事本文がそれぞれ元順を維持することを確認した。
- 周辺機器記事作成とタイトル変更の両生成結果に二つのリンクがあり、旧表示 `記事を開く` が存在しないUI契約テストに合格した。
- JSX構文、Node.js構文、Python構文、`git diff --check`、Vercel Productionビルドに合格した。

今回の本番反映結果:

- 修正コミット `2399c61e` を `main` へpushした。
- Vercel Productionデプロイ `dpl_EEXFQ7RnZsUjiVr5GNqZaN4c2wyG` が `Ready` となり、`https://blog-vercel-dun.vercel.app` へ反映された。
- 本番配信HTMLを直接取得し、「OneDriveブラウザで開く」2件、「エディターで開く」2件、旧表示 `記事を開く` 0件、タイトル変更画面を閉じて生成記事をエディターへ渡す処理が配信されていることを確認した。
- 実MLXジョブとOneDrive記事の再生成は行っていない。修正前に生成済みの記事は自動更新されないため、同じ入力で再生成して確認する。

SEOタイトル派生機能の初回本番反映結果:

- 実装コミット `b30d893d` を `main` へpushした。
- Vercel Productionデプロイ `dpl_B7VP9cwepLrQVbGMbqVzufy54Fq1` が `Ready` となり、`https://blog-vercel-dun.vercel.app` へ反映された。
- 本番配信HTMLに記事右クリックの「タイトル変更」、整形後タイトル一覧、複数件のMLX作成、進捗、警告、完成記事リンク、Terminal再起動、`tpl_title_variant.md` のプロンプト編集導線が含まれることを確認した。
- 本番の `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/api/accessories.js` 相当APIで、空の元記事要求がOneDriveジョブを作らず `元記事の選択が必要です` と拒否されることを確認した。
- OneDrive管理領域へMLX用 `mlx-tpl_title_variant` を契約v6・改訂1・SHA-256付きで初期化した。プロンプト本文とハッシュ長だけを確認し、秘密情報は出力していない。
- 実MLXジョブ、完成記事保存、`周辺機器DB_LLM` の完了更新はユーザーの本番クリック試験用として実行していない。
