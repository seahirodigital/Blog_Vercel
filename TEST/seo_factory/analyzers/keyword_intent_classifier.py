"""サジェストキーワードのクエリタイプ分類。

`C:\\Users\\HCY\\OneDrive\\開発\\Blog_Vercel\\reference\\suggest_keywords.js`
にある分類語彙と判定順を流用し、分類は `Know / Do / Buy` の3種類に固定する。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Mapping

INTENT_BUY = "Buy"
INTENT_DO = "Do"
INTENT_KNOW = "Know"

INTENT_ORDER: Mapping[str, int] = {
    INTENT_BUY: 0,
    INTENT_KNOW: 1,
    INTENT_DO: 2,
}

VOLUME_ORDER: Mapping[str, int] = {
    "大": 0,
    "中": 1,
    "小": 2,
    "極小": 3,
}

PRIORITY_BUCKET_ORDER: Mapping[tuple[str, str], int] = {
    (INTENT_BUY, "大"): 0,
    (INTENT_KNOW, "大"): 1,
    (INTENT_BUY, "中"): 2,
    (INTENT_KNOW, "中"): 3,
    (INTENT_BUY, "小"): 4,
}

# `suggest_keywords.js` の語彙群と判定順を継承する。
# ただし今回の方針に合わせて、
# - 比較系は Buy
# - トラブル系は Know
# として扱う。
BUY_KEYWORDS = (
    "価格", "値段", "料金", "金額", "費用", "相場", "定価", "値引き", "割引",
    "安い", "高い", "格安", "激安", "特価", "最安値", "割安", "お得",
    "コスパ", "セール価格", "キャンペーン価格",
    "購入", "買う", "買いたい", "注文", "予約", "予約販売", "発売日",
    "販売開始", "再販", "入手", "手に入れる", "契約", "申し込み",
    "お取り寄せ", "発注",
    "在庫", "在庫あり", "在庫なし", "在庫確認",
    "入荷", "入荷予定", "再入荷",
    "即納", "即日発送", "当日発送",
    "納期", "お届け", "配送", "発送", "到着", "いつ届く",
    "セール", "タイムセール", "初売り", "福袋", "限定セール",
    "数量限定", "初回限定", "期間限定",
    "特典付き", "クーポン", "クーポンコード",
    "ポイント還元", "ポイントアップ", "キャッシュバック",
    "キャンペーン", "ノベルティ", "おまけ付き",
    "公式サイト", "正規", "正規品", "正規代理店", "直販",
    "販売店", "取扱店", "取り扱い", "店舗", "実店舗",
    "どこで買える", "どこで売ってる", "販売先",
    "公式ショップ", "ショップ限定", "アウトレット",
    "純正", "本物", "偽物",
    "新品", "中古", "リユース", "リサイクル", "リファービッシュ", "再生品",
    "型落ち", "旧型", "新型", "新作", "最新モデル",
    "限定モデル", "特別仕様", "限定カラー",
    "支払い方法", "分割払い", "月額", "月々", "一括払い",
    "分割手数料", "無金利",
    "クレジット対応", "代引き", "後払い",
    "サブスク", "定期購入", "定期便",
    "Amazon限定", "Amazonベーシック",
    "プライム限定", "プライムデー",
    "ブラックフライデー", "サイバーマンデー",
    "タイムセール祭り", "初売りセール", "ポイント祭り",
    "通販", "ネット通販", "オンライン購入", "ネット購入",
    "宅配", "送料無料",
    "レビュー", "口コミ", "評判", "評価",
    "感想", "経験談", "実際どう", "実際に使ってみた",
    "体験談", "本音", "ユーザーの声", "利用者の声",
    "使用感", "比較", "違い",
    "おすすめ", "ランキング", "人気",
    "満足度", "採点", "どっちがいい",
    "au", "docomo", "softbank", "rakuten", "ahamo", "linemo",
    "uq", "ymobile", "amazon", "sim", "case", "qi", "qi2",
    "magsafe", "usb", "pencil", "charger", "ケーブル", "cable",
)

KNOW_HINT_KEYWORDS = (
    "やめとけ", "買うな", "やめたほうがいい",
    "使えない", "付いてない",
    "不具合", "故障しやすい", "壊れやすい",
    "返品", "失敗した", "後悔",
    "最悪", "ダメ", "微妙",
    "デメリット", "不便", "不満",
    "注意点", "問題点", "良くない",
    "気をつけろ", "向いてない", "いらない",
)

DO_KEYWORDS = (
    "ログイン", "登録", "ダウンロード", "インストール", "解約", "計算", "変換",
    "アクセス", "地図", "やり方", "アップデート", "update", "設定",
    "修理", "交換", "再起動", "電源off", "引き継ぎ",
)


def _normalize_for_match(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("\u3000", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.lower()


def classify_intent(keyword: str) -> str:
    """既存JSと同じ優先順で3分類する。"""
    normalized = _normalize_for_match(keyword)

    if any(token.lower() in normalized for token in BUY_KEYWORDS):
        return INTENT_BUY
    if any(token.lower() in normalized for token in DO_KEYWORDS):
        return INTENT_DO
    if any(token.lower() in normalized for token in KNOW_HINT_KEYWORDS):
        return INTENT_KNOW
    return INTENT_KNOW


def should_mark_article_candidate(query_type: str, volume_label: str) -> bool:
    """内部優先度の目安として、既存JSの Buy×大/中 を維持する。"""
    return query_type == INTENT_BUY and volume_label in {"大", "中"}


def article_status_label(query_type: str, volume_label: str) -> str:
    """記事化対象はユーザーがシート上で手動選択するため、初期値は空欄。"""
    _ = query_type
    _ = volume_label
    return ""


def make_intent_sort_key(
    query_type: str,
    volume_label: str,
    suggest_keyword: str = "",
    article_candidate: bool | None = None,
) -> tuple[int, int, int, str]:
    """ユーザー需要順に寄せた並び順キーを返す。"""
    _ = article_candidate

    return (
        PRIORITY_BUCKET_ORDER.get((query_type, volume_label), 99),
        VOLUME_ORDER.get(volume_label, 99),
        INTENT_ORDER.get(query_type, 99),
        _normalize_for_match(suggest_keyword),
    )
