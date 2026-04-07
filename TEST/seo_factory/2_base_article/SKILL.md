---
name: 2_base_article
description: SEO 記事量産ワークフローの第2フェーズ。母艦アウトライン生成、材料束作成、参照記事を土台にした母艦記事執筆、母艦検証までを順番に実行したいときに使う。
---

# 2_base_article スキル

## 概要

このスキルは、`2_base_article/scripts/031_2_master_article_generator.py` と母艦用プロンプト群を使って、母艦記事の材料生成から検証通過までを一続きで進める。

## 実行手順

1. `../0_common/promptreference.md` を確認し、参照記事は `../output/<seed>/reference/` 配下の最新 Markdown を使う前提を共有する。
2. `../0_common/scripts/031_5_run_factory.py --resume-from-sheet` を実行し、`outline.md` と `031_2_master_research_bundle.md` を出力する。
3. `prompts/031-1-best-outline-prompt.md` と `prompts/031-2-best-article-enhancer-prompt.md` を確認し、H2 構造と参照記事維持条件を揃える。
4. このチャットで `../output/<seed>/reference/<任意の参照記事>.md` を土台に `../output/<seed>/master_article.md` を作成する。
5. 再度 `../0_common/scripts/031_5_run_factory.py --resume-from-sheet` を実行し、母艦検証と個別記事ジョブ生成まで進める。
6. `../output/<seed>/memo/031_3_master_validation_report.md` が NG の場合は、母艦記事を修正して再検証する。
7. 合格したら `3_variant_article` フェーズへ進む。

## 実行ルール

- 母艦本文は Python が自動生成しない。本文の仕上げはこのチャットで行う。
- `scripts/031_2_master_article_generator.py` は、アウトライン、材料束、参照記事構造ルールの材料生成に専念する。
- 母艦検証は `../0_common/scripts/031_3_article_validator.py` を使う。
- 参照記事の章立て、章内説明量、箇条書き、Q&A 密度を壊してはいけない。

## 主要ファイル

- `scripts/031_2_master_article_generator.py`
- `prompts/031-1-best-outline-prompt.md`
- `prompts/031-2-best-article-enhancer-prompt.md`
- `../0_common/scripts/031_5_run_factory.py`
- `../0_common/scripts/031_3_article_validator.py`
- `../0_common/promptreference.md`
