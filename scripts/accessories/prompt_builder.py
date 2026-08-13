"""LLMに限定JSONだけを返させる入力と応答検査。"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .affiliate_group import AffiliateGroup


def build_prompt_input(
    *,
    template_path: str | Path | None = None,
    template_content: str = "",
    product_name: str,
    category_name: str,
    evidence: str,
    affiliate_group: AffiliateGroup,
) -> tuple[str, str]:
    prompt = str(template_content or "").strip()
    if not prompt and template_path is not None:
        prompt = Path(template_path).read_text(encoding="utf-8-sig").strip()
    if not prompt:
        raise ValueError("生成プロンプトが空です")
    blocks = "\n\n".join(
        f"【商品{product.index}】\n{product.text}" for product in affiliate_group.products
    )
    input_text = (
        f"親製品名: {product_name}\n"
        f"対象周辺機器: {category_name}\n\n"
        f"【カテゴリ共通説明文】\n{affiliate_group.section_intro}\n\n"
        f"【おすすめ商品ブロック】\n{blocks}"
    )
    return prompt, input_text


def _normalize_newlines(value: str) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _fact_tokens(value: str) -> set[str]:
    without_urls = re.sub(r"https?://\S+", "", value)
    return set(re.findall(r"(?i)[A-Z]+[A-Z0-9.+-]*|\d+(?:[.,]\d+)*(?:mAh|W|GB|TB|Hz|mm|cm|m|%|インチ)?", without_urls))


def _validate_adapted_product(source: str, adapted: str, product_name: str, product_title: str) -> str:
    source_text = _normalize_newlines(source)
    adapted_text = _normalize_newlines(adapted)
    if not adapted_text.startswith(f"▼{product_title}"):
        raise ValueError(f"商品名行が変更されています: {product_title}")
    if re.search(r"<br\s*/?>", adapted_text, re.I):
        raise ValueError(f"商品紹介文にHTML改行が含まれています: {product_title}")
    source_urls = re.findall(r"https?://[^\s)\]]+", source_text)
    adapted_urls = re.findall(r"https?://[^\s)\]]+", adapted_text)
    if adapted_urls != source_urls:
        raise ValueError(f"商品URLが変更されています: {product_title}")
    source_lines = source_text.split("\n")
    adapted_lines = adapted_text.split("\n")
    if len(adapted_lines) < len(source_lines):
        raise ValueError(
            f"商品紹介文の行数が減少しています: {product_title} "
            f"原文{len(source_lines)}行 / 生成{len(adapted_lines)}行"
        )
    if sum(not line.strip() for line in adapted_lines) < sum(not line.strip() for line in source_lines):
        raise ValueError(f"商品紹介文の空行が削除されています: {product_title}")
    adapted_cursor = 0
    for line_number, source_line in enumerate(source_lines, start=1):
        if not source_line.strip():
            continue
        matched = False
        while adapted_cursor < len(adapted_lines):
            adapted_line = adapted_lines[adapted_cursor]
            adapted_cursor += 1
            if adapted_line == source_line:
                matched = True
                break
            subject_only_change = (
                not source_line.startswith("▼")
                and not re.search(r"https?://", source_line)
                and product_name in adapted_line
                and not (_fact_tokens(source_line) - _fact_tokens(adapted_line))
                and not (_fact_tokens(adapted_line) - (_fact_tokens(source_line) | _fact_tokens(product_name)))
                and SequenceMatcher(None, source_line, adapted_line).ratio() >= 0.45
            )
            if subject_only_change:
                matched = True
                break
        if not matched:
            raise ValueError(
                f"商品紹介文{line_number}行目が削除または大きく書き換えられています: {product_title}"
            )
    allowed_tokens = _fact_tokens(source_text) | _fact_tokens(product_name)
    added_tokens = _fact_tokens(adapted_text) - allowed_tokens
    if added_tokens:
        raise ValueError(f"入力にない数値・英数字仕様があります: {product_title}")
    return adapted_text


def _validate_adapted_section_intro(source: str, adapted: str, product_name: str) -> str:
    source_text = _normalize_newlines(source)
    adapted_text = _normalize_newlines(adapted)
    if not source_text:
        if adapted_text:
            raise ValueError("元文のないカテゴリ共通説明文は追加できません")
        return ""
    if not adapted_text:
        raise ValueError("カテゴリ共通説明文が空です")
    if re.search(r"<br\s*/?>", adapted_text, re.I):
        raise ValueError("カテゴリ共通説明文にHTML改行が含まれています")
    source_lines = source_text.split("\n")
    adapted_lines = adapted_text.split("\n")
    if len(adapted_lines) < len(source_lines):
        raise ValueError(
            f"カテゴリ共通説明文の行数が減少しています: "
            f"原文{len(source_lines)}行 / 生成{len(adapted_lines)}行"
        )
    if sum(not line.strip() for line in adapted_lines) < sum(not line.strip() for line in source_lines):
        raise ValueError("カテゴリ共通説明文の空行が削除されています")

    adapted_cursor = 0
    for line_number, source_line in enumerate(source_lines, start=1):
        if not source_line.strip():
            continue
        matched = False
        while adapted_cursor < len(adapted_lines):
            adapted_line = adapted_lines[adapted_cursor]
            adapted_cursor += 1
            if adapted_line == source_line:
                matched = True
                break
            subject_only_change = (
                "おすすめ" in source_line
                and product_name in adapted_line
                and not (_fact_tokens(source_line) - _fact_tokens(adapted_line))
                and not (_fact_tokens(adapted_line) - (_fact_tokens(source_line) | _fact_tokens(product_name)))
                and SequenceMatcher(None, source_line, adapted_line).ratio() >= 0.45
            )
            if subject_only_change:
                matched = True
                break
        if not matched:
            raise ValueError(
                f"カテゴリ共通説明文{line_number}行目が削除または大きく書き換えられています"
            )
    source_urls = re.findall(r"https?://[^\s)\]]+", source_text)
    adapted_urls = re.findall(r"https?://[^\s)\]]+", adapted_text)
    if adapted_urls != source_urls:
        raise ValueError("カテゴリ共通説明文のURLが変更されています")
    source_tokens = _fact_tokens(source_text)
    adapted_tokens = _fact_tokens(adapted_text)
    missing_tokens = source_tokens - adapted_tokens
    if missing_tokens:
        raise ValueError("カテゴリ共通説明文の数値・英数字が削除されています")
    added_tokens = adapted_tokens - (source_tokens | _fact_tokens(product_name))
    if added_tokens:
        raise ValueError("カテゴリ共通説明文に入力にない数値・英数字があります")
    return adapted_text


def _parse_json_object(text: str) -> dict[str, Any]:
    """JSON本体と、前後に説明が付いたJSON応答を安全に読み取る。"""
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("LLM応答が空です")
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[-1].strip() == "```":
            raw = "\n".join(lines[1:-1]).strip()
            if raw.casefold().startswith("json"):
                raw = raw[4:].lstrip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as original_error:
        decoder = json.JSONDecoder()
        data = None
        for match in re.finditer(r"\{", raw):
            try:
                candidate, _ = decoder.raw_decode(raw[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                data = candidate
                break
        if data is None:
            detail = (
                f"{original_error.msg}、"
                f"{original_error.lineno}行{original_error.colno}列"
            )
            raise ValueError(f"LLM応答のJSON解析に失敗しました（{detail}）") from original_error
    if not isinstance(data, dict):
        raise ValueError("LLM応答のJSONルートはオブジェクトである必要があります")
    return data


def parse_engine_result(
    text: str,
    *,
    product_name: str,
    category_name: str,
    affiliate_group: AffiliateGroup,
) -> dict[str, Any]:
    data = _parse_json_object(text)
    if set(data) != {"intro_sentence", "adapted_section_intro", "products"}:
        raise ValueError("LLM応答のキーが指定と一致しません")
    intro = str(data.get("intro_sentence", "")).strip()
    products = data.get("products")
    adapted_section_intro = _validate_adapted_section_intro(
        affiliate_group.section_intro,
        str(data.get("adapted_section_intro", "")),
        product_name,
    )
    if not intro or product_name not in intro or category_name not in intro:
        raise ValueError("冒頭案内文に親製品名または周辺機器名がありません")
    if any(token in intro for token in ("http://", "https://", "\n", "<think>", "job_id", "<br>")) or re.search(r"<br\s*/?>", intro, re.I):
        raise ValueError("冒頭案内文に禁止値があります")
    if not isinstance(products, list) or len(products) != len(affiliate_group.products):
        raise ValueError("LLM応答の商品ブロック件数が不正です")
    ordered: list[str] = []
    for expected_index, (item, source_product) in enumerate(zip(products, affiliate_group.products), start=1):
        if not isinstance(item, dict) or item.get("index") != expected_index:
            raise ValueError(f"商品{expected_index}の参照番号が不正です")
        adapted = str(item.get("adapted_text", "")).strip()
        if any(token in adapted for token in ("<think>", "job_id", "Amazonのアソシエイトとして", "AIの整形・編集", "おすすめ商品のリンクまとめ")):
            raise ValueError(f"商品{expected_index}の調整文に禁止値があります")
        ordered.append(
            _validate_adapted_product(
                source_product.text,
                adapted,
                product_name,
                source_product.title,
            )
        )
    return {
        "intro_sentence": intro,
        "adapted_section_intro": adapted_section_intro,
        "adapted_product_texts": ordered,
    }
