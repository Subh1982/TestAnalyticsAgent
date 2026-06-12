#!/usr/bin/env python3
"""
Accor Plus homepage analytics agent.

Usage:
  python accorplus_homepage_agent.py /path/to/raw_data.xlsx
  python accorplus_homepage_agent.py /path/to/raw_data.csv --output outputs/report.md
"""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


CANONICAL_COLUMNS = {
    "date": ["date"],
    "page_path": ["page path", "page_path", "page", "path"],
    "users": ["users"],
    "sessions": ["sessions"],
    "engaged_sessions": ["engaged sessions", "engaged_sessions"],
    "engagement_rate": ["engagement rate", "engagement_rate"],
    "avg_engagement_time_sec": [
        "average engagement time",
        "avg engagement time",
        "avg engagement time (sec)",
        "average engagement time (sec)",
        "average engagement time seconds",
    ],
    "conversions": ["conversions"],
    "revenue_aud": ["revenue (aud)", "revenue aud", "revenue_aud", "revenue"],
}


@dataclass(frozen=True)
class Insight:
    title: str
    detail: str


def normalize_column_name(value: object) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("_", " ")
    return text


def canonicalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized_to_original = {normalize_column_name(col): col for col in df.columns}
    rename_map = {}

    for canonical, aliases in CANONICAL_COLUMNS.items():
        for alias in aliases:
            original = normalized_to_original.get(normalize_column_name(alias))
            if original is not None:
                rename_map[original] = canonical
                break

    cleaned = df.rename(columns=rename_map).copy()
    missing = [col for col in CANONICAL_COLUMNS if col not in cleaned.columns]
    if missing:
        expected = ", ".join(CANONICAL_COLUMNS)
        found = ", ".join(map(str, df.columns))
        raise ValueError(
            f"Missing required columns: {', '.join(missing)}.\n"
            f"Expected columns like: {expected}.\n"
            f"Found: {found}"
        )

    return cleaned[list(CANONICAL_COLUMNS.keys())]


def read_source(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        df = pd.read_excel(path)
    elif suffix == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError("Use an Excel workbook (.xlsx/.xls) or CSV file.")

    return canonicalize_columns(df)


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")

    numeric_cols = [
        "users",
        "sessions",
        "engaged_sessions",
        "engagement_rate",
        "avg_engagement_time_sec",
        "conversions",
        "revenue_aud",
    ]
    for col in numeric_cols:
        prepared[col] = pd.to_numeric(prepared[col], errors="coerce")

    if prepared["date"].isna().any():
        raise ValueError("Some Date values could not be parsed.")
    if prepared[numeric_cols].isna().any().any():
        bad_cols = prepared[numeric_cols].columns[prepared[numeric_cols].isna().any()].tolist()
        raise ValueError(f"Some metric values could not be parsed: {', '.join(bad_cols)}")

    prepared = prepared.sort_values("date").reset_index(drop=True)
    prepared["weekday"] = prepared["date"].dt.day_name()
    prepared["conversion_rate"] = prepared["conversions"] / prepared["sessions"]
    prepared["revenue_per_session"] = prepared["revenue_aud"] / prepared["sessions"]
    prepared["revenue_per_conversion"] = prepared["revenue_aud"] / prepared["conversions"]
    prepared["sessions_per_user"] = prepared["sessions"] / prepared["users"]
    prepared["unengaged_sessions"] = prepared["sessions"] - prepared["engaged_sessions"]
    return prepared


def pct_change(new: float, old: float) -> float:
    if old == 0 or math.isnan(old):
        return 0.0
    return (new - old) / old


def money(value: float) -> str:
    return f"AUD {value:,.0f}"


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def num(value: float) -> str:
    return f"{value:,.0f}"


def signed_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100:.1f}%"


def weighted_average(values: Iterable[float], weights: Iterable[float]) -> float:
    series_values = pd.Series(values, dtype="float64")
    series_weights = pd.Series(weights, dtype="float64")
    weight_sum = series_weights.sum()
    if weight_sum == 0:
        return 0.0
    return float((series_values * series_weights).sum() / weight_sum)


def build_observations(df: pd.DataFrame) -> list[Insight]:
    first_7 = df.head(7)
    last_7 = df.tail(7)
    best_revenue = df.loc[df["revenue_aud"].idxmax()]
    worst_revenue = df.loc[df["revenue_aud"].idxmin()]
    best_conversion_rate = df.loc[df["conversion_rate"].idxmax()]
    weekday = (
        df.groupby("weekday", sort=False)
        .agg(
            sessions=("sessions", "mean"),
            conversions=("conversions", "mean"),
            revenue_aud=("revenue_aud", "mean"),
            conversion_rate=("conversion_rate", "mean"),
        )
        .sort_values("revenue_aud", ascending=False)
    )
    top_weekday_name = weekday.index[0]
    bottom_weekday_name = weekday.index[-1]

    revenue_lift = pct_change(last_7["revenue_aud"].sum(), first_7["revenue_aud"].sum())
    conversion_lift = pct_change(last_7["conversions"].sum(), first_7["conversions"].sum())
    session_lift = pct_change(last_7["sessions"].sum(), first_7["sessions"].sum())
    engagement_lift = pct_change(last_7["avg_engagement_time_sec"].mean(), first_7["avg_engagement_time_sec"].mean())

    corr = df[["sessions", "avg_engagement_time_sec", "engagement_rate", "conversions", "revenue_aud"]].corr()
    revenue_session_corr = corr.loc["sessions", "revenue_aud"]
    conversion_session_corr = corr.loc["sessions", "conversions"]
    revenue_engagement_time_corr = corr.loc["avg_engagement_time_sec", "revenue_aud"]

    return [
        Insight(
            "Volume and revenue improved through the month",
            (
                f"The final 7 days produced {money(last_7['revenue_aud'].sum())}, "
                f"{signed_pct(revenue_lift)} vs the first 7 days. Sessions moved "
                f"{signed_pct(session_lift)} and conversions moved {signed_pct(conversion_lift)}."
            ),
        ),
        Insight(
            "Engagement is steady but not the main growth lever",
            (
                f"Engagement rate stayed in a narrow {pct(df['engagement_rate'].min())}-"
                f"{pct(df['engagement_rate'].max())} band. Average engagement time rose "
                f"{signed_pct(engagement_lift)} from the first week to the final week."
            ),
        ),
        Insight(
            "Conversions and revenue mostly follow traffic",
            (
                f"The correlation between sessions and revenue is {revenue_session_corr:.2f}, "
                f"and between sessions and conversions is {conversion_session_corr:.2f}. "
                f"Revenue also tracks engagement time closely at {revenue_engagement_time_corr:.2f}."
            ),
        ),
        Insight(
            "Best and weakest days are clear",
            (
                f"Best revenue day: {best_revenue['date'].date()} with "
                f"{money(best_revenue['revenue_aud'])} and {num(best_revenue['conversions'])} conversions. "
                f"Weakest revenue day: {worst_revenue['date'].date()} with "
                f"{money(worst_revenue['revenue_aud'])} and {num(worst_revenue['conversions'])} conversions. "
                f"Best conversion-rate day: {best_conversion_rate['date'].date()} at "
                f"{pct(best_conversion_rate['conversion_rate'])}."
            ),
        ),
        Insight(
            "Weekday mix deserves closer campaign review",
            (
                f"{top_weekday_name} had the strongest average daily revenue "
                f"({money(weekday.iloc[0]['revenue_aud'])}), while {bottom_weekday_name} was lowest "
                f"({money(weekday.iloc[-1]['revenue_aud'])}). This may reflect media pacing, email sends, "
                "offer timing, or natural travel-planning behavior."
            ),
        ),
    ]


def build_recommendations(df: pd.DataFrame) -> list[Insight]:
    unengaged_rate = df["unengaged_sessions"].sum() / df["sessions"].sum()
    weighted_conversion_rate = df["conversions"].sum() / df["sessions"].sum()

    return [
        Insight(
            "Make the membership value proposition sharper above the fold",
            (
                "The homepage has several strong benefits to choose from: sign-up bonus points, free nights, "
                "hotel discounts, dining discounts, status nights, member offers, and events. Test hero variants "
                "that lead with one primary promise and a direct Join Now path instead of asking users to process "
                "many benefits at once."
            ),
        ),
        Insight(
            "Reduce conversion friction between homepage and checkout",
            (
                f"The sample conversion rate is {pct(weighted_conversion_rate)} per session. Add or test sticky "
                "Join Now CTAs, price/value anchors near benefit sections, and a short comparison block showing "
                "annual fee vs likely savings from free nights, dining, and hotel discounts."
            ),
        ),
        Insight(
            "Use engagement depth to route users to the next best action",
            (
                f"About {pct(unengaged_rate)} of sessions are not engaged. For shallow sessions, prioritize a "
                "fast benefit summary and country-specific offer. For deeper sessions, surface proof points, FAQs, "
                "terms clarity, and checkout reassurance close to the CTA."
            ),
        ),
        Insight(
            "Personalize by market and intent",
            (
                "Because the homepage redirects by country, report and optimize each country path separately. "
                "Different markets may need different hero offers, currency framing, local hotel examples, dining "
                "examples, and checkout messaging."
            ),
        ),
        Insight(
            "Improve GA4 event coverage before large redesign decisions",
            (
                "Track country selection, Join Now clicks, checkout starts, offer clicks, benefit-card clicks, FAQ "
                "expands, scroll depth, outbound booking clicks, and errors. The current file can show outcomes, "
                "but event-level data will explain which homepage modules create or lose intent."
            ),
        ),
    ]


def build_report(df: pd.DataFrame, source: Path) -> str:
    totals = {
        "users": df["users"].sum(),
        "sessions": df["sessions"].sum(),
        "engaged_sessions": df["engaged_sessions"].sum(),
        "conversions": df["conversions"].sum(),
        "revenue_aud": df["revenue_aud"].sum(),
    }

    weighted_engagement_rate = totals["engaged_sessions"] / totals["sessions"]
    weighted_conversion_rate = totals["conversions"] / totals["sessions"]
    avg_time_weighted = weighted_average(df["avg_engagement_time_sec"], df["sessions"])
    revenue_per_session = totals["revenue_aud"] / totals["sessions"]
    revenue_per_user = totals["revenue_aud"] / totals["users"]
    revenue_per_conversion = totals["revenue_aud"] / totals["conversions"]
    date_min = df["date"].min().date()
    date_max = df["date"].max().date()
    paths = ", ".join(sorted(df["page_path"].astype(str).unique()))

    observations = build_observations(df)
    recommendations = build_recommendations(df)

    lines = [
        "# Accor Plus Homepage Analytics Report",
        "",
        f"Source file: `{source.name}`",
        f"Period: {date_min} to {date_max}",
        f"Page path(s): {paths}",
        "",
        "## Executive Summary",
        "",
        (
            f"The homepage generated {num(totals['sessions'])} sessions from {num(totals['users'])} users, "
            f"with {num(totals['conversions'])} conversions and {money(totals['revenue_aud'])} revenue. "
            f"Weighted engagement rate was {pct(weighted_engagement_rate)}, average engagement time was "
            f"{avg_time_weighted:.0f} seconds, and conversion rate was {pct(weighted_conversion_rate)}."
        ),
        "",
        "## KPI Snapshot",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Users | {num(totals['users'])} |",
        f"| Sessions | {num(totals['sessions'])} |",
        f"| Engaged sessions | {num(totals['engaged_sessions'])} |",
        f"| Engagement rate | {pct(weighted_engagement_rate)} |",
        f"| Avg engagement time | {avg_time_weighted:.0f} sec |",
        f"| Conversions | {num(totals['conversions'])} |",
        f"| Conversion rate | {pct(weighted_conversion_rate)} |",
        f"| Revenue | {money(totals['revenue_aud'])} |",
        f"| Revenue / session | {money(revenue_per_session)} |",
        f"| Revenue / user | {money(revenue_per_user)} |",
        f"| Revenue / conversion | {money(revenue_per_conversion)} |",
        "",
        "## Observations",
        "",
    ]

    for item in observations:
        lines.append(f"### {item.title}")
        lines.append(item.detail)
        lines.append("")

    lines.extend(
        [
            "## Recommended Improvements for www.accorplus.com",
            "",
        ]
    )
    for item in recommendations:
        lines.append(f"### {item.title}")
        lines.append(item.detail)
        lines.append("")

    lines.extend(
        [
            "## Suggested Test Backlog",
            "",
            "1. A/B test hero messages: sign-up bonus vs free nights vs dining savings vs status nights.",
            "2. A/B test sticky Join Now CTA on mobile and desktop.",
            "3. Add a membership value calculator or savings explainer near the first CTA.",
            "4. Segment homepage reporting by country path and compare conversion rates by market.",
            "5. Build a GA4 funnel from homepage view to Join Now click to checkout start to purchase.",
            "",
            "## Data Notes",
            "",
            "- Engagement rate in the report is recalculated as engaged sessions divided by sessions.",
            "- Revenue efficiency metrics use total revenue divided by the relevant total volume.",
            "- Recommendations are based on the provided GA4 sample plus current homepage positioning.",
        ]
    )

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Accor Plus homepage GA4 raw data.")
    parser.add_argument("source", type=Path, help="Path to the raw GA4 Excel or CSV file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/accorplus_homepage_report.md"),
        help="Markdown report path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = prepare_data(read_source(args.source))
    report = build_report(df, args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
