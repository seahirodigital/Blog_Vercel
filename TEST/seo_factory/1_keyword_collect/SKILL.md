---
name: 1_keyword_collect
description: SEO 記事量産ワークフローの第1フェーズ。ラッコキーワード収集、Google スプレッドシート保存、手動選別後の再開までを順番に実行したいときに使う。
---

# 1_keyword_collect スキル

## 概要

このスキルは、`1_keyword_collect/scripts/031_1_keyword_pipeline.py` と `0_common/scripts/031_5_run_factory.py` を使って、キーワード収集からスプシ再開までを1つのフェーズとして完了させる。

## 実行手順

1. `../0_common/promptreference.md` を確認し、対象シードキーワードと `output/<seed>/reference/` の有無を把握する。
2. 初回収集では `../0_common/scripts/031_5_run_factory.py` を `--resume-from-sheet` なしで実行し、ラッコキーワード収集と Google スプレッドシート保存まで進める。
3. スプレッドシートの `状況` 列を人手で編集し、採用・不要を確定する。
4. 再開時は同じ `../0_common/scripts/031_5_run_factory.py` を `--resume-from-sheet` つきで実行し、採用キーワードだけを次の母艦フェーズへ渡す。
5. 出力された `output/<seed>/memo/current_keywords.json` と `output/<seed>/memo/previous_keywords.json` を確認し、`2_base_article` フェーズへ進む。

## 実行ルール

- キーワード収集ロジックの本体は `scripts/031_1_keyword_pipeline.py` とする。
- 収集フェーズ単独の調査や修正では `scripts/031_1_keyword_pipeline.py` を読む。
- 実際の運用実行口は常に `../0_common/scripts/031_5_run_factory.py` を使う。
- 本フェーズでは本文を書かない。ここで行うのは収集、分類、スプシ連携、再開準備まで。

## 主要ファイル

- `scripts/031_1_keyword_pipeline.py`
- `../0_common/scripts/031_5_run_factory.py`
- `../0_common/promptreference.md`
