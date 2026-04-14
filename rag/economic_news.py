"""
오늘(한국 표준시) 기준, 주가·증시 관련 키워드가 포함된 뉴스를 RSS로 수집해 data/ 디렉터리에 저장합니다.
기본 설정에서는 같은 파일(`news_YYYYMMDD.txt`) 하단에 **세계 경제·정치·거시(영문 Google News) Top 10**을 이어 붙입니다.
vector_store.py는 파일명의 날짜와 'news' 등 키워드로 메타데이터를 구분할 수 있습니다.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv

load_dotenv()

KST = timezone(timedelta(hours=9))

# LLM 요약 목표 길이(한글 기준 문자 수)
SUMMARY_MIN_CHARS = 400
SUMMARY_MAX_CHARS = 500

# 증시 검색어 (OR 묶음, Google News 검색 길이 고려)
_STOCK_OR_QUERY = (
    "주가 OR 주식 OR 코스피 OR 코스닥 OR 나스닥 OR 전망 OR 증시 OR 환율 OR 금리 OR "
    "ETF OR 리츠 OR 공모주 OR 반도체 OR 2차전지 OR 바이오 OR 유상증자 OR 공시"
)

# Google News RSS — 단일 피드(하위 호환·수동 지정용)
DEFAULT_FEED_URL = (
    "https://news.google.com/rss/search?"
    f"q={quote_plus(_STOCK_OR_QUERY)}&hl=ko&gl=KR&ceid=KR:ko"
)

# 기본: 속보·상위 스토리(인기글에 가까운 묶음)·증시 검색을 순서대로 합침(중복 제거)
FEED_URL_BREAKING = (
    "https://news.google.com/rss/search?"
    f"q={quote_plus(f'(속보 OR [속보]) ({_STOCK_OR_QUERY})')}&hl=ko&gl=KR&ceid=KR:ko"
)
FEED_URL_TOP_STORIES_KR = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"

DEFAULT_FEED_URLS: tuple[str, ...] = (
    FEED_URL_BREAKING,
    FEED_URL_TOP_STORIES_KR,
    DEFAULT_FEED_URL,
)

# 세계 경제·거시·정치·지정학 (영문 Google News 검색) — 동일 파일 하단 섹션으로 병합
_WORLD_MACRO_OR_QUERY = (
    "world economy OR global economy OR IMF OR Federal Reserve OR ECB OR "
    "inflation OR trade tariffs OR recession OR OECD OR geopolitics OR "
    "central bank OR interest rates OR G7 OR G20 OR commodity OR oil price"
)
FEED_URL_WORLD_ECONOMY = (
    "https://news.google.com/rss/search?"
    f"q={quote_plus(_WORLD_MACRO_OR_QUERY)}&hl=en&gl=US&ceid=US:en"
)

# 영문 기사 제목·스니펫 매칭 (경제·정치·시장·통화정책 연관)
WORLD_ECON_PRIMARY_KEYWORDS: tuple[str, ...] = (
    "economy",
    "economic",
    "fed",
    "federal reserve",
    "imf",
    "ecb",
    "european central bank",
    "inflation",
    "deflation",
    "gdp",
    "trade",
    "tariff",
    "tariffs",
    "sanctions",
    "opec",
    "oil",
    "recession",
    "growth",
    "unemployment",
    "jobs",
    "interest rate",
    "rates",
    "central bank",
    "monetary",
    "fiscal",
    "policy",
    "election",
    "government",
    "congress",
    "senate",
    "parliament",
    "president",
    "minister",
    "geopolitical",
    "geopolitics",
    "conflict",
    "diplomacy",
    "stock market",
    "dow",
    "s&p",
    "nasdaq",
    "ftse",
    "yuan",
    "yen",
    "dollar",
    "euro",
    "pound",
    "stimulus",
    "budget",
    "debt",
    "default",
)

# 1차: 제목·요약에 포함되면 수집 (--no-listing-keywords 시 이 목록만)
PRIMARY_KEYWORDS: tuple[str, ...] = (
    "주가",
    "주식",
    "코스피",
    "코스닥",
    "나스닥",
    "주식 시장",
    "주식시장",
    "NASDAQ",
    "Nasdaq",
    "nasdaq",
    "다우",
    "S&P",
    "에스앤피",
    "증시",
    "미국증시",
    "증권",
    "리츠",
    "스팩",
    "공모주",
    "환율",
    "원달러",
    "유상증자",
    "무상증자",
    "공시",
    "2차전지",
    "바이오",
    "원유",
    "채권",
    "기관",
    "외국인",
)

_LISTING_PRIMARY_EXTRA: tuple[str, ...] | None = None


def _get_effective_primary_keywords(
    use_listing: bool,
    data_dir: str | Path,
) -> tuple[str, ...]:
    """기본 키워드 + (옵션) 코스피·코스닥 시총 상위·나스닥 대형주 종목명."""
    global _LISTING_PRIMARY_EXTRA
    if not use_listing:
        return PRIMARY_KEYWORDS
    if _LISTING_PRIMARY_EXTRA is None:
        try:
            from rag.stock_universe import get_listing_match_keywords

            names = get_listing_match_keywords(data_dir=data_dir)
            _LISTING_PRIMARY_EXTRA = tuple(sorted(names))
        except Exception as e:
            warnings.warn(
                f"상장 종목명 로드 실패, 기본 키워드만 사용: {e}",
                UserWarning,
            )
            _LISTING_PRIMARY_EXTRA = ()
    merged: list[str] = list(PRIMARY_KEYWORDS)
    seen = set(PRIMARY_KEYWORDS)
    for n in _LISTING_PRIMARY_EXTRA or ():
        if n not in seen:
            merged.append(n)
            seen.add(n)
    return tuple(merged)

# '전망' 단독은 정치 등 오탐이 많아, 아래 맥락 키워드가 함께 있을 때만 인정
FORECAST_KEYWORD = "전망"
FORECAST_CONTEXT_KEYWORDS: tuple[str, ...] = (
    "주가",
    "주식",
    "코스피",
    "코스닥",
    "나스닥",
    "증시",
    "증권",
    "지수",
    "매수",
    "매도",
    "투자",
    "외국인",
    "기관",
    "반도체",
    "금리",
    "환율",
    "배당",
    "실적",
    "선물",
    "옵션",
    "ETF",
    "etf",
    "나스닥",
    "NASDAQ",
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _strip_xml_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _localname_map(root: ET.Element) -> None:
    for el in root.iter():
        el.tag = _strip_xml_ns(el.tag)


def _parse_pub_date(text: str | None) -> datetime | None:
    if not text or not text.strip():
        return None
    try:
        dt = parsedate_to_datetime(text.strip())
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST)


def _clean_html(text: str) -> str:
    t = html.unescape(text or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _compact_for_match(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _keyword_hit(k: str, blob: str, blob_lower: str, compact: str) -> bool:
    k = k.strip()
    if not k:
        return False
    if k.isascii():
        return k.lower() in blob_lower
    kc = _compact_for_match(k)
    return k in blob or kc in compact


def item_matches_keywords(
    it: dict[str, str | None],
    primary: tuple[str, ...] = PRIMARY_KEYWORDS,
) -> bool:
    title = _clean_html(str(it.get("title") or ""))
    desc = _clean_html(str(it.get("description") or ""))
    blob = f"{title} {desc}"
    blob_lower = blob.lower()
    compact = _compact_for_match(blob)

    for kw in primary:
        if _keyword_hit(kw, blob, blob_lower, compact):
            return True

    if FORECAST_KEYWORD in blob or FORECAST_KEYWORD in compact:
        for kw in FORECAST_CONTEXT_KEYWORDS:
            if _keyword_hit(kw, blob, blob_lower, compact):
                return True
    return False


def _item_is_breaking(it: dict[str, str | None]) -> bool:
    """제목·설명에 속보 표기가 있으면 True."""
    t = _clean_html(str(it.get("title") or ""))
    d = _clean_html(str(it.get("description") or ""))
    blob = f"{t} {d}"
    if "[속보]" in blob or "(속보)" in blob:
        return True
    return "속보" in t


def _item_pub_ts(it: dict[str, str | None]) -> float:
    dt = _parse_pub_date(it.get("pubDate") if isinstance(it.get("pubDate"), str) else None)
    return float(dt.timestamp()) if dt is not None else 0.0


def _sort_stock_items(pool: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    """속보 우선, 같은 그룹에서는 최신순."""
    return sorted(
        pool,
        key=lambda it: (0 if _item_is_breaking(it) else 1, -_item_pub_ts(it)),
    )


def merge_items_from_feeds(feed_urls: Iterable[str]) -> list[dict[str, str | None]]:
    """여러 RSS를 순서대로 합치고, 링크(없으면 제목) 기준으로 중복 제거."""
    seen: set[str] = set()
    out: list[dict[str, str | None]] = []
    for url in feed_urls:
        try:
            xml_text = fetch_rss_xml(url)
        except Exception as e:
            warnings.warn(f"RSS 로드 실패(건너뜀): {url} — {e}", UserWarning)
            continue
        for it in parse_news_items(xml_text):
            link = (it.get("link") or "").strip()
            title = _clean_html(str(it.get("title") or ""))
            key = link if link else f"title:{title}"
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
    return out


def select_article_items(
    raw_items: list[dict[str, str | None]],
    *,
    now_kst: datetime,
    max_items: int,
    primary_keywords: tuple[str, ...] | None = None,
    filter_keywords: bool = True,
) -> tuple[list[dict[str, str | None]], str | None]:
    """
    키워드 필터 후, 오늘(KST) 게시분을 속보·최신순으로 먼저 채우고 부족하면 나머지 날짜에서 채움.
    최종 개수는 max_items 이하.
    filter_keywords=False 이면 raw_items를 그대로 풀(pool)로 사용(이미 선별된 경우·완화 모드).
    """
    pk = primary_keywords if primary_keywords is not None else PRIMARY_KEYWORDS
    if filter_keywords:
        keyword_items = [it for it in raw_items if item_matches_keywords(it, primary=pk)]
        if not keyword_items:
            return [], "피드에서 지정 키워드에 해당하는 기사를 찾지 못했습니다."
    else:
        keyword_items = list(raw_items)
        if not keyword_items:
            return [], "피드에서 기사를 찾지 못했습니다."

    today_d = now_kst.date()
    today_pool: list[dict[str, str | None]] = []
    rest_pool: list[dict[str, str | None]] = []
    for it in keyword_items:
        dt = _parse_pub_date(it.get("pubDate") if isinstance(it.get("pubDate"), str) else None)
        if dt is not None and dt.astimezone(KST).date() == today_d:
            today_pool.append(it)
        else:
            rest_pool.append(it)

    today_pool = _sort_stock_items(today_pool)
    rest_pool = _sort_stock_items(rest_pool)

    selected = today_pool[:max_items]
    if len(selected) < max_items:
        selected.extend(rest_pool[: max_items - len(selected)])

    note: str | None = None
    if not today_pool:
        note = (
            f"오늘({today_d.isoformat()}) 게시·키워드 일치 기사가 없어 "
            "최신 항목으로 채웠습니다."
        )
    elif len(keyword_items) < max_items:
        note = f"키워드 일치 기사가 총 {len(keyword_items)}건입니다(최대 {max_items}건 목표)."

    return selected[:max_items], note


def fetch_rss_xml(url: str, timeout: float = 20.0) -> str:
    resp = requests.get(
        url,
        headers={"User-Agent": DEFAULT_USER_AGENT},
        timeout=timeout,
    )
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def parse_news_items(xml_text: str) -> list[dict[str, str | None]]:
    root = ET.fromstring(xml_text)
    _localname_map(root)
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[dict[str, str | None]] = []
    for it in channel.findall("item"):
        title_el = it.find("title")
        link_el = it.find("link")
        pub_el = it.find("pubDate")
        desc_el = it.find("description")
        items.append(
            {
                "title": title_el.text if title_el is not None else None,
                "link": link_el.text if link_el is not None else None,
                "pubDate": pub_el.text if pub_el is not None else None,
                "description": desc_el.text if desc_el is not None else None,
            }
        )
    return items


def _rss_only_fallback_summary(title: str, description: str) -> str:
    """API 미사용 시 RSS 제목·설명을 한 줄로 묶음(제목·리드 중복 최소화)."""
    t = _clean_html(title)
    d = _clean_html(description)
    if not d:
        base = t
    elif t and (d.startswith(t[: min(len(t), 80)]) or _compact_for_match(t) == _compact_for_match(d)):
        base = d
    elif d and t.endswith(d[-min(len(d), 40) :]):
        base = t
    else:
        base = f"{t} {d}".strip() if d else t
    return re.sub(r"\s+", " ", base).strip()


def _split_into_sentences(blob: str) -> list[str]:
    """마침표·느낌표·물음표 등 뒤에서 문장을 나눈다(한글 본문 RSS용)."""
    s = re.sub(r"\s+", " ", (blob or "").strip())
    if not s:
        return []
    parts = re.split(r"(?<=[.!?。…])\s+", s)
    return [p.strip() for p in parts if p.strip()]


def _first_and_last_two_sentences(title: str, description: str) -> str:
    """
    RSS로 받은 제목+설명을 하나의 텍스트로 보고, 앞 2문장·뒤 2문장을 고른다.
    (원문 기사 전체가 아니라 피드에 실린 범위만 사용.)
    """
    t = _clean_html(title)
    d = _clean_html(description)
    blob = re.sub(r"\s+", " ", f"{t} {d}".strip())
    sents = _split_into_sentences(blob)
    if not sents:
        return t if t else ""
    if len(sents) <= 4:
        return " ".join(sents)
    return f"{' '.join(sents[:2])} … {' '.join(sents[-2:])}"


def _merge_without_redundant_tail(base: str, extra: str) -> str:
    """extra가 base와 문장 단위로 크게 겹치면 붙이지 않는다."""
    base_c = _compact_for_match(base)
    ex_c = _compact_for_match(extra)
    if not extra.strip():
        return base
    if ex_c and ex_c in base_c:
        return base
    if base_c and base_c in ex_c and len(ex_c) > len(base_c):
        return extra.strip()
    return re.sub(r"\s+", " ", f"{base} {extra}".strip())


# RSS만 있을 때·LLM 출력이 짧을 때 공백 포함 400~500자에 맞추기 위한 중립 문장(사실을 새로 만들지 않음)
_NEUTRAL_FILLERS: tuple[str, ...] = (
    " 본문은 수집 시점에 공개된 뉴스 스니펫에 기반하며, 이후 시세·지수는 변동될 수 있다.",
    " 투자·매매 판단은 원문 기사와 공시, 거래소 시세를 함께 확인하는 것이 바람직하다.",
    " 동일 이슈에 대한 후속 보도와 시장 반응을 교차 검토할 필요가 있다.",
    " 유동성·변동성 환경에 따라 해석이 달라질 수 있어 추가 뉴스를 점검하는 편이 안전하다.",
    " 해당 소식이 관련 업종·종목에 미칠 수 있는 영향은 개별 기업 실적과 거시 변수를 함께 보면서 판단해야 한다.",
    " 단기 뉴스 플로우만으로는 포지션을 확정하기 어려우므로 리스크 관리 관점에서 분할·한도를 검토할 수 있다.",
    " 공개 정보 외 비공개 사항은 본 요약 범위에 포함되지 않는다.",
)


def _expand_summary_to_char_range(
    text: str,
    min_c: int,
    max_c: int,
    *,
    title: str = "",
    description: str = "",
) -> str:
    """
    짧은 본문 뒤에 분량을 맞춘다.
    먼저 RSS 기준 앞 2문장·뒤 2문장을 덧붙이고, 그래도 부족하면 중립 문장을 이어 붙인다.
    """
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) > max_c:
        return t[: max_c - 1] + "…"
    if len(t) >= min_c:
        return t

    edge = _first_and_last_two_sentences(title, description)
    if edge:
        merged = _merge_without_redundant_tail(t, edge)
        merged = re.sub(r"\s+", " ", merged).strip()
        if len(merged) <= max_c:
            t = merged
        else:
            t = merged[: max_c - 1] + "…"

    idx = 0
    while len(t) < min_c and idx < 60:
        piece = _NEUTRAL_FILLERS[idx % len(_NEUTRAL_FILLERS)]
        if not piece.startswith(" "):
            piece = " " + piece
        if len(t) + len(piece) <= max_c:
            t = (t + piece).strip()
        else:
            room = max_c - len(t)
            if room >= 12:
                tail = piece.strip()
                t = (t + " " + tail[: room - 1] + "…").strip()
            break
        idx += 1
    if len(t) > max_c:
        return t[: max_c - 1] + "…"
    return t


def _clamp_summary_length(text: str) -> str:
    t = re.sub(r"\s+", " ", text.strip())
    if len(t) > SUMMARY_MAX_CHARS:
        return t[: SUMMARY_MAX_CHARS - 1] + "…"
    return t


def _summarize_news_with_llm(title: str, description: str) -> str:
    """제목·RSS 설명만으로 400~500자 한국어 요약(한 문단)."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

    model = os.getenv("NEWS_SUMMARY_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    title_c = _clean_html(title)
    desc_c = _clean_html(description)
    source_block = f"제목:\n{title_c}\n\nRSS 설명:\n{desc_c or '(없음)'}"

    system = (
        "당신은 증시·기업 뉴스를 다루는 편집자입니다. 주어진 제목과 RSS 설명만 근거로 작성합니다.\n"
        "제목·설명이 영어면 동일 내용을 한국어로 번역·요약합니다.\n"
        f"출력은 반드시 한 문단의 한국어 본문 하나뿐이며, 글자 수(공백 포함)가 {SUMMARY_MIN_CHARS}자 이상 "
        f"{SUMMARY_MAX_CHARS}자 이하여야 합니다. '요약:' 같은 접두어·번호·불릿·따옴표로 제목을 반복하지 마세요.\n"
        "RSS에 없는 구체 수치·인용·사실은 만들지 마세요. 정보가 적으면, 알려진 내용과 일반적인 시장 맥락만 "
        "조심스럽게 덧붙이되, 확인되지 않은 세부사실은 단정하지 마세요."
    )

    def _call(user_extra: str = "") -> str:
        user = source_block + user_extra
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.4,
            max_tokens=800,
        )
        return (resp.choices[0].message.content or "").strip()

    text = _call()
    text = re.sub(r"\s+", " ", text).strip()

    if not (SUMMARY_MIN_CHARS <= len(text) <= SUMMARY_MAX_CHARS):
        fix = (
            "\n\n다음은 방금 생성한 초안입니다:\n"
            + text
            + f"\n\n위 초안의 글자 수(공백 포함)는 {len(text)}자입니다. "
            f"{SUMMARY_MIN_CHARS}자 이상 {SUMMARY_MAX_CHARS}자 이하가 되도록 한 문단으로 전면 재작성하세요. "
            "근거는 제목·RSS 설명 범위 안에서만 유지하세요."
        )
        text = _call(fix)

    text = re.sub(r"\s+", " ", text).strip()
    text = _clamp_summary_length(text)
    if len(text) < SUMMARY_MIN_CHARS:
        text = _call(
            "\n\n다음 초안이 너무 짧습니다:\n"
            + text
            + f"\n\n{SUMMARY_MIN_CHARS}자 이상 {SUMMARY_MAX_CHARS}자 이하가 되도록 같은 근거 범위 안에서 보강하세요."
        )
        text = re.sub(r"\s+", " ", text).strip()
        text = _clamp_summary_length(text)
    if len(text) < SUMMARY_MIN_CHARS:
        text = _expand_summary_to_char_range(
            text,
            SUMMARY_MIN_CHARS,
            SUMMARY_MAX_CHARS,
            title=title_c,
            description=desc_c,
        )
    return text


def build_article_summary(
    title: str,
    description: str,
    *,
    use_llm: bool = True,
) -> str:
    """
    기본: OpenAI로 400~500자 요약.
    API 없음·LLM 실패·--no-llm-summary: RSS 원문을 정리한 뒤, 부족하면 앞·뒤 문장을 덧붙이고 중립 문장으로 맞춘다.
    """
    if use_llm and os.getenv("OPENAI_API_KEY"):
        try:
            return _summarize_news_with_llm(title, description)
        except Exception as e:
            warnings.warn(f"LLM 요약 실패, RSS+중립 보강 사용: {e}", UserWarning, stacklevel=2)
            base = _rss_only_fallback_summary(title, description)
            return _expand_summary_to_char_range(
                base,
                SUMMARY_MIN_CHARS,
                SUMMARY_MAX_CHARS,
                title=title,
                description=description,
            )
    base = _rss_only_fallback_summary(title, description)
    return _expand_summary_to_char_range(
        base,
        SUMMARY_MIN_CHARS,
        SUMMARY_MAX_CHARS,
        title=title,
        description=description,
    )


def _format_article_lines(
    items: list[dict[str, str | None]],
    *,
    start_index: int = 1,
    use_llm_summary: bool = True,
) -> list[str]:
    lines: list[str] = []
    for i, it in enumerate(items, start=start_index):
        title = _clean_html(str(it.get("title") or ""))
        link = (it.get("link") or "").strip()
        desc_raw = str(it.get("description") or "")
        pub_raw = it.get("pubDate")
        dt = _parse_pub_date(pub_raw if isinstance(pub_raw, str) else None)
        pub_str = dt.strftime("%Y-%m-%d %H:%M KST") if dt else (pub_raw or "")

        summary = build_article_summary(title, desc_raw, use_llm=use_llm_summary)

        lines.append(f"[{i}] {title}")
        if link:
            lines.append(f"    URL: {link}")
        if pub_str:
            lines.append(f"    게시: {pub_str}")
        lines.append(f"    요약: {summary}")
        lines.append("")
    return lines


def _summary_mode_lines(use_llm_summary: bool) -> list[str]:
    if use_llm_summary and os.getenv("OPENAI_API_KEY"):
        return [
            f"요약: OpenAI로 기사당 약 {SUMMARY_MIN_CHARS}~{SUMMARY_MAX_CHARS}자 생성 "
            f"(모델: {os.getenv('NEWS_SUMMARY_MODEL', 'gpt-4o-mini')})."
        ]
    if use_llm_summary:
        return [
            "요약: OPENAI_API_KEY가 없어 RSS 스니펫을 정리한 뒤 "
            f"{SUMMARY_MIN_CHARS}~{SUMMARY_MAX_CHARS}자가 되도록 중립 문장으로 분량을 맞췄습니다. "
            ".env에 키를 넣으면 AI가 본문형 요약을 생성합니다."
        ]
    return [
        f"요약: --no-llm-summary 로 RSS를 정리한 뒤 "
        f"{SUMMARY_MIN_CHARS}~{SUMMARY_MAX_CHARS}자가 되도록 중립 문장으로 맞췄습니다."
    ]


def build_document_text(
    items: list[dict[str, str | None]],
    *,
    source_note: str,
    collected_at_kst: datetime,
    note: str | None = None,
    use_llm_summary: bool = True,
) -> str:
    lines: list[str] = [
        "=== 주가·증시 키워드 뉴스 (RSS 수집) ===",
        f"수집 시각(KST): {collected_at_kst.strftime('%Y-%m-%d %H:%M:%S')}",
        source_note,
        "키워드 필터: "
        + ", ".join(PRIMARY_KEYWORDS)
        + f"; '{FORECAST_KEYWORD}'는 {', '.join(FORECAST_CONTEXT_KEYWORDS[:6])} 등 증시·투자 맥락 키워드와 함께 있을 때만",
    ]
    lines.extend(_summary_mode_lines(use_llm_summary))
    if note:
        lines.append(f"비고: {note}")
    lines.append("")
    lines.extend(_format_article_lines(items, start_index=1, use_llm_summary=use_llm_summary))
    return "\n".join(lines).rstrip() + "\n"


def build_world_economy_document_text(
    items: list[dict[str, str | None]],
    *,
    source_note: str,
    collected_at_kst: datetime,
    note: str | None = None,
    use_llm_summary: bool = True,
) -> str:
    """세계 경제·정치·거시 이슈 섹션 (동일 news_YYYYMMDD.txt 하단에 병합)."""
    kw_preview = ", ".join(WORLD_ECON_PRIMARY_KEYWORDS[:24]) + ", …"
    lines: list[str] = [
        "=== 세계 경제·정치·거시 이슈 (글로벌 Top 10, 영문 RSS) ===",
        f"수집 시각(KST): {collected_at_kst.strftime('%Y-%m-%d %H:%M:%S')}",
        source_note,
        f"키워드 필터(영문·일부 축약 표기): {kw_preview}",
        "용도: 글로벌 거시·정책·지정학과 국내·해외 증시 상관관계를 함께 볼 때 참고.",
    ]
    lines.extend(_summary_mode_lines(use_llm_summary))
    if note:
        lines.append(f"비고: {note}")
    lines.append("")
    lines.extend(_format_article_lines(items, start_index=1, use_llm_summary=use_llm_summary))
    return "\n".join(lines).rstrip() + "\n"


def _article_dedupe_key(it: dict[str, str | None]) -> str:
    link = (it.get("link") or "").strip()
    if link:
        return link
    return f"title:{_clean_html(str(it.get('title') or ''))}"


def collect_world_economy_section(
    kr_items: list[dict[str, str | None]],
    *,
    now_kst: datetime,
    max_world_articles: int = 10,
    use_llm_summary: bool = True,
) -> tuple[str, str | None]:
    """
    영문 Google News(거시·정치·지정학) RSS로 글로벌 기사를 고르고, 문서 하단 섹션 문자열만 반환합니다.
    반환: (섹션 전체 텍스트, 비고 또는 None). 기사가 없으면 ("", None).
    """
    raw = merge_items_from_feeds((FEED_URL_WORLD_ECONOMY,))
    seen_kr = {_article_dedupe_key(it) for it in kr_items}
    raw = [it for it in raw if _article_dedupe_key(it) not in seen_kr]

    if not raw:
        return "", "세계 경제 RSS에서 항목을 가져오지 못했습니다."

    kw_hits = [it for it in raw if item_matches_keywords(it, primary=WORLD_ECON_PRIMARY_KEYWORDS)]
    pool = kw_hits if kw_hits else raw
    use_keyword_filter = bool(kw_hits)

    world_selected, wnote = select_article_items(
        pool,
        now_kst=now_kst,
        max_items=max_world_articles,
        primary_keywords=WORLD_ECON_PRIMARY_KEYWORDS,
        filter_keywords=use_keyword_filter,
    )
    if not world_selected:
        return "", wnote or "세계 경제 섹션에 포함할 기사가 없습니다."

    extra_note = wnote
    if not use_keyword_filter:
        extra_note = (
            (extra_note + " ") if extra_note else ""
        ) + "영문 키워드 일치가 적어 피드 상위·최신 항목으로 채웠습니다."

    source_note = (
        "수집: Google 뉴스 영문 검색 RSS — "
        f"질의 요약: world economy / Fed·IMF·ECB·거시·무역·지정학 등 (최대 {max_world_articles}건, "
        "앞선 국내 섹션과 URL·제목 중복 제거)."
    )

    body = build_world_economy_document_text(
        world_selected,
        source_note=source_note,
        collected_at_kst=now_kst,
        note=extra_note,
        use_llm_summary=use_llm_summary,
    )
    return body, None


def collect_todays_economic_news(
    data_dir: str | Path = "data",
    *,
    feed_url: str | None = None,
    feed_urls: Sequence[str] | None = None,
    max_articles: int = 20,
    max_world_articles: int = 10,
    use_llm_summary: bool = True,
    use_listing_keywords: bool | None = None,
    include_world_macro: bool | None = None,
) -> Path:
    """
    주가·증시 키워드 뉴스 RSS를 받아 data/news_YYYYMMDD.txt 로 저장합니다.
    기본은 속보 검색·한국 상위 스토리·증시 검색 피드를 합친 뒤 최대 max_articles건만 남깁니다.
    기본 피드 사용 시 같은 파일 하단에 **세계 경제·정치·거시(영문) Top 10** 섹션을 이어 붙입니다.
    """
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    if use_listing_keywords is None:
        use_listing_keywords = os.getenv("NEWS_INCLUDE_LISTING", "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )

    primary_kw = _get_effective_primary_keywords(use_listing_keywords, data_path)

    if include_world_macro is None:
        include_world_macro = os.getenv("NEWS_INCLUDE_WORLD_MACRO", "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )

    now_kst = datetime.now(KST)
    date_tag = now_kst.strftime("%Y%m%d")
    out_file = data_path / f"news_{date_tag}.txt"

    if feed_urls is not None:
        urls: tuple[str, ...] = tuple(feed_urls)
    elif feed_url is not None:
        urls = (feed_url,)
    else:
        urls = DEFAULT_FEED_URLS

    raw_items = merge_items_from_feeds(urls)
    items, note = select_article_items(
        raw_items,
        now_kst=now_kst,
        max_items=max_articles,
        primary_keywords=primary_kw,
    )

    if urls == DEFAULT_FEED_URLS:
        source_note = (
            "수집: 「속보·증시」검색 RSS + Google 뉴스 한국 상위 스토리(주목·많이 읽는 흐름에 가까운 묶음) + "
            f"「{_STOCK_OR_QUERY}」검색 RSS를 순서대로 합쳐 중복 제거 후, 키워드 일치 기사 중 "
            f"[속보] 우선·최신순으로 최대 {max_articles}건."
        )
        if use_listing_keywords:
            source_note += (
                " 키워드 매칭에 코스피·코스닥 시총 상위 종목명과 나스닥 대형주 종목명을 포함합니다 "
                "(FinanceDataReader, data/.cache/listing_names.json 캐시)."
            )
    else:
        source_note = f"수집: 사용자 지정 RSS {len(urls)}개, 최대 {max_articles}건(속보 우선·최신순)."

    body = build_document_text(
        items,
        source_note=source_note,
        collected_at_kst=now_kst,
        note=note,
        use_llm_summary=use_llm_summary,
    )

    use_default_bundle = feed_urls is None and feed_url is None
    if include_world_macro and use_default_bundle:
        world_body, _ = collect_world_economy_section(
            items,
            now_kst=now_kst,
            max_world_articles=max_world_articles,
            use_llm_summary=use_llm_summary,
        )
        if world_body.strip():
            body = body.rstrip() + "\n\n" + world_body.strip() + "\n"

    out_file.write_text(body, encoding="utf-8")
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="data/ 폴더에 오늘의 주가·증시 키워드 뉴스 텍스트를 저장합니다."
    )
    parser.add_argument(
        "--data-dir",
        default=os.getenv("DATA_PATH", "data"),
        help="저장 디렉터리 (기본: data 또는 환경변수 DATA_PATH)",
    )
    parser.add_argument(
        "--feed-url",
        default=None,
        help="이 URL 하나만 사용(미지정 시 속보+상위스토리+증시 검색 3종 병합)",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=20,
        help="저장할 기사 최대 개수(기본 20, 주가·증시 키워드 뉴스 구간)",
    )
    parser.add_argument(
        "--no-llm-summary",
        action="store_true",
        help="OpenAI 요약 없이 RSS 제목·설명만 요약 필드에 넣습니다.",
    )
    parser.add_argument(
        "--no-listing-keywords",
        action="store_true",
        help="코스피·코스닥·나스닥 종목명 매칭 없이 고정 키워드만 사용합니다.",
    )
    parser.add_argument(
        "--max-world-articles",
        type=int,
        default=10,
        help="세계 경제·거시(영문 RSS) 섹션에 넣을 최대 기사 수(기본 10).",
    )
    parser.add_argument(
        "--no-world-macro",
        action="store_true",
        help="같은 파일 하단의 세계 경제(영문) 섹션을 생략합니다.",
    )
    args = parser.parse_args()

    path = collect_todays_economic_news(
        args.data_dir,
        feed_url=args.feed_url,
        max_articles=args.max_articles,
        max_world_articles=args.max_world_articles,
        use_llm_summary=not args.no_llm_summary,
        use_listing_keywords=not args.no_listing_keywords,
        include_world_macro=not args.no_world_macro,
    )
    print(f"저장 완료: {path.resolve()}")


if __name__ == "__main__":
    main()
