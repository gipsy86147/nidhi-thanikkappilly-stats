#!/usr/bin/env python3
"""Scrape Nidhi Thanikkappilly stats from HiPenta and PentathlonScore."""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

HIPENTA_URLS = [
    "https://www.hipenta.com/live/events/46b72a21-cef6-4404-a527-6618600bf67f/categories/e6889cfc-828c-4792-82e2-c6fb8980b624/result",
    "https://www.hipenta.com/live/events/f14078fe-cd99-4f90-b2c2-994adeb4293e/categories/b2e43a82-0ae8-446c-a926-2f67312d4235/result",
]

PENTATHLONSCORE_HOME = "https://pentathlonscore.com/"
SUPABASE_URL = "https://cbwifmgrekugoljcaqoh.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNid2lmbWdyZWt1Z29samNhcW9oIiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3NjQ3MDcxODYsImV4cCI6MjA4MDI4MzE4Nn0."
    "Rp5MCWYQL9SxbnBEJ7e76gbbd95qsStaLE2Hkhpn47g"
)

TARGET_FIRST = "nidhi"
TARGET_LAST = "thanikkappilly"


@dataclass
class HiPentaEvent:
    source: str
    source_url: str
    event_name: str
    category: str
    location: str
    event_datetime_text: str
    overall_points: int | None
    overall_rank: int | None
    disciplines: dict[str, dict[str, str]]


@dataclass
class PentathlonScoreEvent:
    source: str
    source_url: str
    competition: str
    location: str
    start_date: str
    end_date: str
    status: str
    division: str
    age_group: str
    gender: str
    noc: str
    entry_rank: int | None
    total_points: int
    handicap_seconds: int | None
    tie_break_order: int | None
    disciplines: dict[str, dict[str, Any]]


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read().decode("utf-8", errors="ignore")


def clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_hipenta_event(source_url: str) -> HiPentaEvent:
    html = fetch_text(source_url)

    event_match = re.search(r'<h1[^>]*>\s*<a[^>]*>(.*?)</a>\s*</h1>', html)
    headers = re.findall(r'<h2[^>]*>(.*?)</h2>', html)

    marker = 'Nidhi<!-- --> <span class="font-medium">THANIKKAPPILLY</span>'
    marker_index = html.find(marker)
    if marker_index < 0:
        raise ValueError(f"Could not locate Nidhi row in HiPenta source: {source_url}")

    row_start = html.rfind("<tr", 0, marker_index)
    row_end = html.find("</tr>", marker_index)
    if row_start < 0 or row_end < 0:
        raise ValueError(f"Could not isolate Nidhi table row in: {source_url}")

    row_html = html[row_start : row_end + 5]

    overall_points = to_int(re.search(r"Overall Pts:\s*([0-9]+)", row_html).group(1))
    overall_rank = to_int(re.search(r"Overall Rank:\s*([0-9]+)", row_html).group(1))

    cell_html_list = re.findall(r'<td class="hidden sm:table-cell[^>]*>(.*?)</td>', row_html)
    if len(cell_html_list) < 5:
        raise ValueError(f"Unexpected HiPenta row shape for: {source_url}")

    def parse_cell(cell_html: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for div_html in re.findall(r"<div>(.*?)</div>", cell_html):
            label_match = re.search(r'<span class="text-gray-500 px-1">([^:<]+):</span>', div_html)
            if not label_match:
                continue
            label = clean_html_text(label_match.group(1))
            raw_value = div_html[label_match.end() :]
            value = clean_html_text(raw_value)
            values[label] = value
        return values

    disciplines = {
        "Obstacle": parse_cell(cell_html_list[0]),
        "Fencing": parse_cell(cell_html_list[1]),
        "Swimming": parse_cell(cell_html_list[2]),
        "Laser Run": parse_cell(cell_html_list[3]),
        "Overall": parse_cell(cell_html_list[4]),
    }

    return HiPentaEvent(
        source="hipenta",
        source_url=source_url,
        event_name=clean_html_text(event_match.group(1)) if event_match else "",
        category=clean_html_text(headers[0]) if len(headers) > 0 else "",
        location=clean_html_text(headers[1]) if len(headers) > 1 else "",
        event_datetime_text=clean_html_text(headers[2]) if len(headers) > 2 else "",
        overall_points=overall_points,
        overall_rank=overall_rank,
        disciplines=disciplines,
    )


def fetch_pentathlonscore_payload() -> list[dict[str, Any]]:
    select_clause = (
        "id,name,location,start_date,end_date,status,"
        "divisions(id,name,age_group,gender,order_index,"
        "entries(id,handicap,tie_break_order,athletes(first_name,last_name,noc),"
        "results(discipline,raw_value,points)))"
    )
    query = urllib.parse.urlencode(
        {
            "select": select_clause,
            "status": "in.(live,finished)",
            "order": "start_date.desc",
        }
    )

    api_url = f"{SUPABASE_URL}/rest/v1/competitions?{query}"
    req = urllib.request.Request(
        api_url,
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )

    with urllib.request.urlopen(req, timeout=35) as response:
        return json.loads(response.read().decode("utf-8"))


def compute_total_points(entry: dict[str, Any]) -> int:
    total = 0.0
    for result in entry.get("results", []) or []:
        points = result.get("points")
        try:
            if points is not None:
                total += float(points)
        except (TypeError, ValueError):
            continue
    return int(round(total))


def normalize_disciplines(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_discipline: dict[str, dict[str, Any]] = {}
    for result in results or []:
        discipline = str(result.get("discipline") or "").strip()
        if not discipline:
            continue
        by_discipline[discipline] = {
            "raw": result.get("raw_value"),
            "points": result.get("points"),
        }

    return {
        "Fencing": by_discipline.get("fence", {}),
        "Swimming": by_discipline.get("swim", {}),
        "Obstacle": by_discipline.get("obstacle", {}),
        "Laser Run": by_discipline.get("laser", {}),
    }


def compute_division_ranks(entries: list[dict[str, Any]]) -> dict[int, int]:
    enriched: list[dict[str, Any]] = []
    for entry in entries:
        results = entry.get("results", []) or []
        laser_points = None
        for result in results:
            if result.get("discipline") == "laser":
                laser_points = result.get("points")
                break

        enriched.append(
            {
                "id": entry.get("id"),
                "name": (
                    f"{(entry.get('athletes') or {}).get('first_name', '')} "
                    f"{(entry.get('athletes') or {}).get('last_name', '')}"
                ).strip(),
                "total": compute_total_points(entry),
                "has_laser": isinstance(laser_points, (int, float)),
                "tie_break_order": entry.get("tie_break_order"),
            }
        )

    division_has_laser = any(e["has_laser"] for e in enriched)

    def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
        tie_break = row["tie_break_order"]
        if tie_break is None:
            tie_break = 10**9
        return (-row["total"], tie_break, row["name"])

    enriched.sort(key=sort_key)

    rank_by_entry: dict[int, int] = {}
    if division_has_laser:
        for index, row in enumerate(enriched, start=1):
            rank_by_entry[row["id"]] = index
        return rank_by_entry

    last_total: int | None = None
    last_rank = 0
    for index, row in enumerate(enriched, start=1):
        total = row["total"]
        if index == 1:
            rank = 1
        elif total == last_total:
            rank = last_rank
        else:
            rank = index

        rank_by_entry[row["id"]] = rank
        last_total = total
        last_rank = rank

    return rank_by_entry


def parse_pentathlonscore_events(payload: list[dict[str, Any]]) -> list[PentathlonScoreEvent]:
    extracted: list[PentathlonScoreEvent] = []

    for competition in payload:
        for division in competition.get("divisions", []) or []:
            entries = division.get("entries", []) or []
            rank_by_entry = compute_division_ranks(entries)

            for entry in entries:
                athlete = entry.get("athletes") or {}
                first_name = str(athlete.get("first_name") or "").strip().lower()
                last_name = str(athlete.get("last_name") or "").strip().lower()
                if first_name != TARGET_FIRST or last_name != TARGET_LAST:
                    continue

                extracted.append(
                    PentathlonScoreEvent(
                        source="pentathlonscore",
                        source_url=PENTATHLONSCORE_HOME,
                        competition=str(competition.get("name") or ""),
                        location=str(competition.get("location") or ""),
                        start_date=str(competition.get("start_date") or ""),
                        end_date=str(competition.get("end_date") or ""),
                        status=str(competition.get("status") or ""),
                        division=str(division.get("name") or ""),
                        age_group=str(division.get("age_group") or ""),
                        gender=str(division.get("gender") or ""),
                        noc=str(athlete.get("noc") or ""),
                        entry_rank=rank_by_entry.get(entry.get("id")),
                        total_points=compute_total_points(entry),
                        handicap_seconds=entry.get("handicap"),
                        tie_break_order=entry.get("tie_break_order"),
                        disciplines=normalize_disciplines(entry.get("results", []) or []),
                    )
                )

    extracted.sort(key=lambda e: (e.start_date, e.competition), reverse=True)
    return extracted


def build_payload() -> dict[str, Any]:
    hipenta_events = [parse_hipenta_event(url) for url in HIPENTA_URLS]
    pentathlonscore_events = parse_pentathlonscore_events(fetch_pentathlonscore_payload())

    all_point_values: list[int] = []
    for event in hipenta_events:
        if isinstance(event.overall_points, int):
            all_point_values.append(event.overall_points)
    for event in pentathlonscore_events:
        all_point_values.append(event.total_points)

    summary = {
        "hipenta_event_count": len(hipenta_events),
        "pentathlonscore_event_count": len(pentathlonscore_events),
        "best_points": max(all_point_values) if all_point_values else None,
        "latest_event_date": pentathlonscore_events[0].start_date if pentathlonscore_events else None,
    }

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "athlete": {
            "first_name": "Nidhi",
            "last_name": "Thanikkappilly",
            "display_name": "Nidhi Thanikkappilly",
        },
        "sources": {
            "hipenta_urls": HIPENTA_URLS,
            "pentathlonscore_url": PENTATHLONSCORE_HOME,
        },
        "summary": summary,
        "hipenta_events": [event.__dict__ for event in hipenta_events],
        "pentathlonscore_events": [event.__dict__ for event in pentathlonscore_events],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Nidhi Thanikkappilly stats.")
    parser.add_argument(
        "--output",
        default="docs/data/nidhi_stats.json",
        help="Output JSON path (default: docs/data/nidhi_stats.json)",
    )
    args = parser.parse_args()

    payload = build_payload()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote {output_path}")
    print(
        "HiPenta events:",
        payload["summary"]["hipenta_event_count"],
        "| PentathlonScore events:",
        payload["summary"]["pentathlonscore_event_count"],
    )


if __name__ == "__main__":
    main()
