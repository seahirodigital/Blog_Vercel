"""既存affiliate_links.txtから名前付き商品群を安全に取り出す。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SECTION_RE = re.compile(r"^===([^=\r\n]+)===$", re.MULTILINE)
URL_RE = re.compile(r"https?://[^\s)\]]+")

SECTION_LABELS = {
    "battery": "バッテリー",
    "adapter": "充電器",
    "cable": "ケーブル",
    "case": "ケース",
    "film": "保護フィルム",
    "keyboard": "キーボード",
    "mouse": "マウス",
    "stand": "スタンド",
    "hub": "ハブ",
    "earphone": "イヤホン",
    "headphone": "ヘッドホン",
    "speaker": "スピーカー",
    "storage": "ストレージ",
    "monitor": "モニター",
}
SECTION_EXTRA_ALIASES = {"adapter": ("アダプター",)}


@dataclass(frozen=True)
class AffiliateProduct:
    index: int
    title: str
    text: str
    urls: tuple[str, ...]


@dataclass(frozen=True)
class AffiliateGroup:
    name: str
    raw_text: str
    section_intro: str
    products: tuple[AffiliateProduct, ...]


def _normalized_text(value: str) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


def _normalized_section_name(value: str) -> str:
    return str(value or "").strip().casefold()


def _canonical_section_name(value: str) -> str:
    normalized = _normalized_section_name(value)
    for section_id, label in SECTION_LABELS.items():
        aliases = (section_id, label, *SECTION_EXTRA_ALIASES.get(section_id, ()))
        if normalized in {_normalized_section_name(alias) for alias in aliases}:
            return label
    return str(value or "").strip()


def _section_names_equal(left: str, right: str) -> bool:
    return _normalized_section_name(_canonical_section_name(left)) == _normalized_section_name(
        _canonical_section_name(right)
    )


def list_sections(text: str) -> tuple[str, ...]:
    """名前付きセクションを記載順で返す。"""
    return tuple(match.group(1) for match in SECTION_RE.finditer(_normalized_text(text)))


def extract_group(text: str, section_name: str) -> AffiliateGroup:
    """指定セクション内の全「▼」商品を原文順で返す。"""
    normalized = _normalized_text(text)
    matches = list(SECTION_RE.finditer(normalized))
    target_index = next((index for index, match in enumerate(matches) if match.group(1) == section_name), None)
    if target_index is None:
        target_index = next(
            (index for index, match in enumerate(matches) if _section_names_equal(match.group(1), section_name)),
            None,
        )
    if target_index is None:
        raise ValueError(f"アフィリエイトセクションがありません: {section_name}")

    start = matches[target_index].end()
    end = matches[target_index + 1].start() if target_index + 1 < len(matches) else len(normalized)
    raw = normalized[start:end].strip("\n")
    if not raw.strip():
        raise ValueError(f"アフィリエイトセクションが空です: {section_name}")

    block_starts = [match.start() for match in re.finditer(r"(?m)^▼", raw)]
    if not block_starts:
        raise ValueError(f"商品ブロックの先頭「▼」がありません: {section_name}")
    section_intro = raw[: block_starts[0]].strip()

    products: list[AffiliateProduct] = []
    for index, block_start in enumerate(block_starts):
        block_end = block_starts[index + 1] if index + 1 < len(block_starts) else len(raw)
        block = raw[block_start:block_end].strip()
        first_line = block.splitlines()[0].removeprefix("▼").strip()
        urls = tuple(URL_RE.findall(block))
        if not first_line:
            raise ValueError(f"商品名が空です: {section_name} #{index + 1}")
        products.append(
            AffiliateProduct(index=index + 1, title=first_line, text=block, urls=urls)
        )

    return AffiliateGroup(
        name=section_name,
        raw_text=raw,
        section_intro=section_intro,
        products=tuple(products),
    )


def load_group(path: str | Path, section_name: str) -> AffiliateGroup:
    return extract_group(Path(path).read_text(encoding="utf-8-sig"), section_name)
