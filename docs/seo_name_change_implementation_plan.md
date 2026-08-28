# SEO名称変更機能 実装進展書

## 目的

複数の記事について、記事タイトルを検索語にし、記事本文で最初に見つかったAmazonリンクのOGP商品タイトルを置換語にして、確認・編集・保存・復元を一つの画面で実行できるようにする。

## 変更対象

- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/index.html`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/tests/accessories/test_seo_name_change_ui.py`
- `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/docs/seo_name_change_implementation_plan.md`

## 実装方針

1. 記事右クリックメニューへ「SEO名称変更」を追加する。
2. 画面端まで拡大・縮小できる、対象記事・検索置換・記事ビューアーの3領域モーダルを追加する。
3. 記事本文の最初のAmazon URLを抽出し、既存 `/api/ogp` から商品タイトルを取得する。
4. 検索語は記事タイトルから「レビュー比較まとめ」の空白表記揺れを除外する。
5. 置換語はAmazon表記等を正規化し、保存済み設定文字数でUnicode文字単位に切り詰める。初期値は40文字とする。
6. 個別、チェック対象、全件の置換保存と、記事単位の履歴を一段階ずつ戻して保存する操作を提供する。
7. モーダルを閉じず、現状と変換後を既存Markdown・OGP表示に近い記事ビューアーで確認できるようにする。

## 既存経路の保護

- 既存の通常検索・置換、一括置換、予約投稿、タイトル変更、記事プレビューの入口と保存処理は維持する。
- 新しいVercel Functionは追加せず、既存 `/api/articles` と `/api/ogp` を再利用する。
- 現在のローカル作業ツリーにある削除・未追跡ファイルは変更しない。
- `winmacsync` は実行しない。

## 受け入れ条件

- 単一・複数選択のどちらでも右クリックから開ける。
- 1記事1行で検索語・置換語を自由に編集できる。
- OGP取得文字数を歯車から変更・記憶できる。
- 個別置換、選択置換、全置換が保存まで完了し、モーダルが開いたままになる。
- 戻る操作が記事ごとの直前内容を保存し直す。
- 記事行全体で対象記事を切り替え、現状・変換後を確認できる。
- モーダルの四辺・四隅と、検索置換・記事ビューアー間の境界をドラッグして大きさを変更できる。
- 対象記事パネルは開閉式で、起動時は閉じている。
- Amazon URLは文字列表示せず、リンクアイコンから新しいタブで開ける。
- SEO名称変更画面はBlog Vercel標準の紫を使用する。
- JSX解析、対象テスト、既存関連テスト、Vercelビルド、差分検査が成功する。

## 進捗

- [x] 現行右クリックメニュー・予約投稿モーダル・一括置換・OGP・記事保存処理を調査
- [x] ヘルパー関数と状態管理を実装
- [x] 右クリック導線と3列UIを実装
- [x] 個別・選択・全件保存と復元を実装
- [x] 回帰テストを追加
- [x] ローカル検証
- [x] commit・push・本番一致確認

## 2026-08-28 UI追加修正

- [x] モーダル四辺・四隅のリサイズを実装
- [x] フォーム・記事ビューアー境界の横幅変更を実装
- [x] 対象記事パネルを初期閉鎖の開閉式へ変更
- [x] 記事行全体のプレビュー切り替えを実装
- [x] 目のアイコンをAmazonリンクアイコンへ変更
- [x] SEO名称変更画面をBlog Vercelの紫へ統一
- [x] 回帰テスト・Vercelビルド
- [ ] ブラウザ操作検証（環境側の接続情報不足により開始不可）
- [ ] commit・push・本番一致確認

## 検証記録

- JSX構文解析: 成功
- SEO名称変更UI契約テスト: 3件成功
- 既存関連テストを含む実行可能な単体テスト: 47件成功
- SEO補助関数の振る舞い確認: 9件成功
- Vercel実ビルド: 成功
- GitHub `main` push: 成功
- 本番 `public/index.html`: Git管理内容と432,927バイト・SHA-256 `36068b40171943e6566c79c56f995dd8d1f103206342a7199f97061c89c06db5`で一致
- 本番 `/api/ogp`: 指定Amazon URLから177文字の商品タイトルを取得
- UI追加修正後の関連単体テスト: 50件成功
- UI追加修正後のモーダルリサイズ計算: 5ケース成功
- UI追加修正後のJSX解析・Vercel実ビルド: 成功
- 全アクセサリーテスト80件も実行したが、隔離作業ツリーにGit管理外の既存fixtureが存在しないため30件は開始前に失敗した。今回の変更に関係するテスト失敗ではない。
- アプリ内ブラウザ検証: 接続情報不足により開始できず。独自ブラウザへ切り替えず、構文・契約・ビルド・本番配信ファイル一致で補完する。

## 再開手順

1. `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/docs/seo_name_change_implementation_plan.md` の進捗を確認する。
2. `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/public/index.html` の `SEO名称変更`、`seoRenameModal`、`findFirstAmazonUrl` を検索する。
3. `/Users/user/Library/CloudStorage/OneDrive-個人用/開発/Blog_Vercel/tests/accessories/test_seo_name_change_ui.py` を実行する。
