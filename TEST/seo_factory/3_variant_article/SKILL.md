---
name: 3_variant_article
description: SEO 記事量産ワークフローの第3フェーズ。個別記事ジョブ生成、個別記事本文作成、個別記事検証までを順番に実行したいときに使う。
---

# 3_variant_article スキル

## 概要

このスキルは、母艦記事から個別記事ジョブを作り、`variants/` 配下の記事を順番に完成させて検証を通すための実行手順をまとめる。

## 実行手順

1. `../output/<出力スラッグ>/memo/031_3_master_validation_report.md` が合格済みであることを確認する。
2. `../0_common/scripts/031_5_run_factory.py --resume-from-sheet` を実行し、`../output/<出力スラッグ>/memo/031_4_kobetsu_jobs.md` を生成する。
3. `prompts/031-4-kobetsu-writer-prompt.md` と `../0_common/promptreference.md` を確認し、対象キーワードごとの必須 H2 と禁止事項を揃える。
4. 各ジョブに従って `../output/<出力スラッグ>/variants/<target_keyword>.md` をこのチャットで執筆する。
5. 必要数を書いたら `../0_common/scripts/031_3_article_validator.py` を使って個別記事検証を行う。
6. `../output/<出力スラッグ>/memo/031_4_variant_validation_report.md` が合格するまで修正を繰り返す。

## 実行ルール

- 個別記事は母艦の丸写しではなく、対象キーワードで最初の1文から自然に答える。
- ジョブ生成ロジックの本体は `scripts/031_4_kobetsu_writer.py` とする。
- 個別記事の検証は `../0_common/scripts/031_3_article_validator.py` を使う。
- 母艦記事が未合格のまま個別記事フェーズへ進めてはいけない。

## 主要ファイル

- `scripts/031_4_kobetsu_writer.py`
- `prompts/031-4-kobetsu-writer-prompt.md`
- `../0_common/scripts/031_5_run_factory.py`
- `../0_common/scripts/031_3_article_validator.py`
- `../0_common/promptreference.md`
