"""
코스피·코스닥·나스닥 상장 종목명을 불러와 뉴스 키워드 매칭에 보조로 쓴다.
FinanceDataReader StockListing 사용. 결과는 캐시 파일로 재사용한다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import FrozenSet

KST = timezone(timedelta(hours=9))

# 나스닥: 시총 순위가 API에 없어 대형 기술주 위주 심볼로 필터(종목명 매칭용)
NASDAQ_FOCUS_SYMBOLS: frozenset[str] = frozenset(
    {
        "NVDA",
        "AAPL",
        "MSFT",
        "GOOGL",
        "GOOG",
        "AMZN",
        "META",
        "TSLA",
        "AVGO",
        "COST",
        "NFLX",
        "AMD",
        "INTC",
        "QCOM",
        "ADBE",
        "CSCO",
        "PEP",
        "KO",
        "DIS",
        "ABNB",
        "PYPL",
        "BKNG",
        "GILD",
        "MU",
        "LRCX",
        "SNPS",
        "CDNS",
        "MRVL",
        "PANW",
        "CRWD",
        "ORCL",
        "IBM",
        "AMAT",
        "TXN",
        "HON",
        "SBUX",
        "MDLZ",
        "ISRG",
        "ADP",
        "VRTX",
    }
)


def _cache_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / ".cache" / "listing_names.json"


def _load_cache(path: Path, max_age_hours: int) -> FrozenSet[str] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(raw["saved_at"])
        if datetime.now(KST) - saved.replace(tzinfo=KST) > timedelta(hours=max_age_hours):
            return None
        return frozenset(raw["names"])
    except Exception:
        return None


def _save_cache(path: Path, names: FrozenSet[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "saved_at": datetime.now(KST).isoformat(),
                "count": len(names),
                "names": sorted(names),
            },
            ensure_ascii=False,
            indent=0,
        ),
        encoding="utf-8",
    )


def fetch_listing_names(
    *,
    kospi_top: int = 45,
    kosdaq_top: int = 45,
) -> FrozenSet[str]:
    """KOSPI·KOSDAQ 시총 상위 + 나스닥 대형주 심볼에 해당하는 종목명 집합."""
    import FinanceDataReader as fdr

    names: set[str] = set()

    kospi = fdr.StockListing("KOSPI")
    if "Marcap" in kospi.columns and "Name" in kospi.columns:
        top = kospi.sort_values("Marcap", ascending=False).head(kospi_top)
        names.update(top["Name"].astype(str).str.strip())

    kosdaq = fdr.StockListing("KOSDAQ")
    if "Marcap" in kosdaq.columns and "Name" in kosdaq.columns:
        top = kosdaq.sort_values("Marcap", ascending=False).head(kosdaq_top)
        names.update(top["Name"].astype(str).str.strip())

    nas = fdr.StockListing("NASDAQ")
    if "Symbol" in nas.columns and "Name" in nas.columns:
        sub = nas[nas["Symbol"].isin(NASDAQ_FOCUS_SYMBOLS)]
        names.update(sub["Name"].astype(str).str.strip())

    # 너무 짧은 토큰·숫자만 이름 제외
    cleaned = {n for n in names if len(n) >= 2 and not n.isdigit()}
    return frozenset(cleaned)


def get_listing_match_keywords(
    data_dir: str | Path | None = None,
    *,
    max_age_hours: int = 24,
    refresh: bool = False,
) -> FrozenSet[str]:
    """
    캐시가 있으면 사용, 없거나 만료·refresh 시 API로 갱신.
    data_dir 기본: 환경변수 DATA_PATH 또는 ./data
    """
    base = Path(data_dir or os.getenv("DATA_PATH", "data"))
    path = _cache_path(base)
    if not refresh:
        cached = _load_cache(path, max_age_hours)
        if cached is not None:
            return cached
    names = fetch_listing_names()
    try:
        _save_cache(path, names)
    except OSError:
        pass
    return names


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="상장 종목명 캐시 갱신 (KOSPI/KOSDAQ/NASDAQ)")
    p.add_argument("--data-dir", default=os.getenv("DATA_PATH", "data"))
    args = p.parse_args()
    n = get_listing_match_keywords(data_dir=args.data_dir, refresh=True)
    print(f"저장 완료: {len(n)}개 종목명 (캐시: {_cache_path(args.data_dir)})")


if __name__ == "__main__":
    main()
