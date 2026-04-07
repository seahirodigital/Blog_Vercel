---
name: 1_keyword_collect
description: SEO 記事量産ワークフローの第1フェーズ。ラッコキーワード収集、Google スプレッドシート保存、手動選別後の再開までを順番に実行したいときに使う。
---

# 1_keyword_collect スキル

## 概要

このスキルは、`1_keyword_collect/scripts/031_1_keyword_pipeline.py` と `0_common/scripts/031_5_run_factory.py` を使って、キーワード収集からスプシ再開までを1つのフェーズとして完了させる。

## 実行手順

1. ユーザーが `C:\Users\HCY\OneDrive\開発\Blog_Vercel\TEST\input\` に元記事を入れ、このチャットでラッコ検索キーワードを提示済みか確認する。未提示なら必ず確認してから進む。
2. ラッコ検索キーワードは記事本文から自動推測せず、必ずユーザー提示を正とする。
3. `../0_common/promptreference.md` を確認し、ラッコ検索キーワードと元記事有無を把握する。
4. 初回収集では `../0_common/scripts/031_5_run_factory.py` を `--resume-from-sheet` なしで実行し、ラッコキーワード収集と Google スプレッドシート保存まで進める。
5. スプレッドシートの `状況` 列を人手で編集し、採用・不要を確定する。
6. 再開時は同じ `../0_common/scripts/031_5_run_factory.py` を `--resume-from-sheet` つきで実行し、採用キーワードだけを次の母艦フェーズへ渡す。
7. 出力された `output/<出力スラッグ>/memo/current_keywords.json` と `output/<出力スラッグ>/memo/previous_keywords.json` を確認し、`2_base_article` フェーズへ進む。

## 実行ルール

- キーワード収集ロジックの本体は `scripts/031_1_keyword_pipeline.py` とする。
- 収集フェーズ単独の調査や修正では `scripts/031_1_keyword_pipeline.py` を読む。
- 実際の運用実行口は常に `../0_common/scripts/031_5_run_factory.py` を使う。
- ラッコ検索キーワードとスプレッドシートタブ名は空白版、出力フォルダは自動スラッグ版として扱う。
- 本フェーズでは本文を書かない。ここで行うのは収集、分類、スプシ連携、再開準備まで。

## 主要ファイル

- `scripts/031_1_keyword_pipeline.py`
- `../0_common/scripts/031_5_run_factory.py`
- `../0_common/promptreference.md`
