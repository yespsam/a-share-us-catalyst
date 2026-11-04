from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Union


@dataclass(frozen=True)
class UsTicker:
    ticker: str
    name: str
    weight: float = 1.0


@dataclass(frozen=True)
class Candidate:
    code: str
    name: str
    industry: str
    rationale: str


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    logic: str
    us_tickers: list[UsTicker]
    candidates: list[Candidate]
    policy_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class AppConfig:
    report: dict[str, Any]
    themes: list[Theme]


def load_config(path: Union[str, Path]) -> AppConfig:
    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    themes: list[Theme] = []
    for theme in raw["themes"]:
        themes.append(
            Theme(
                id=theme["id"],
                name=theme["name"],
                logic=theme["logic"],
                us_tickers=[
                    UsTicker(
                        ticker=str(item["ticker"]).upper(),
                        name=item.get("name", str(item["ticker"]).upper()),
                        weight=float(item.get("weight", 1.0)),
                    )
                    for item in theme.get("us_tickers", [])
                ],
                candidates=[
                    Candidate(
                        code=str(item["code"]).zfill(6),
                        name=item["name"],
                        industry=item.get("industry", ""),
                        rationale=item.get("rationale", ""),
                    )
                    for item in theme.get("candidates", [])
                ],
                policy_keywords=tuple(str(word).strip() for word in theme.get("policy_keywords", []) if str(word).strip()),
            )
        )
    return AppConfig(report=raw.get("report", {}), themes=themes)
