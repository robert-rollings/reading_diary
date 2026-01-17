#!/usr/bin/env python3
"""
Generate diary/index.json and diary/years/*.md from Reading_diary.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

STAR = "\u2b50"

MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}

FINISHED_RE = re.compile(r"finished\s*:\s*(.+)", re.IGNORECASE)
TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_-]+)")
YEAR_RE = re.compile(r"^##\s+(\d{4})\s*$")
MONTH_RE = re.compile(r"^###\s+(.+)$")
ENTRY_RE = re.compile(r"^####\s+")


def strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    for token in ("**", "__", "*", "_", "`"):
        text = text.replace(token, "")
    text = " ".join(text.split())
    return text.strip()


def normalize_series_name(name: str) -> str:
    text = strip_markdown(name)
    text = " ".join(text.split())
    if not text:
        return text
    for word in text.split():
        if re.search(r"[a-z][A-Z]", word):
            return text
    if text == text.lower() or all(word[1:].islower() for word in text.split() if len(word) > 1):
        return text.title()
    return text


def slugify(text: str, max_len: int = 50) -> str:
    text = strip_markdown(text)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not text:
        text = "entry"
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or "entry"


def extract_series_info(title: str) -> tuple[str | None, int | None]:
    clean = strip_markdown(title)
    for segment in re.findall(r"\(([^)]+)\)", clean):
        segment = segment.strip()
        if not segment:
            continue
        match = re.match(r"^\s*book\s+(\d+)\s+of\s+(.+?)\s*$", segment, re.IGNORECASE)
        if match:
            return normalize_series_name(match.group(2)), int(match.group(1))
        match = re.match(r"^\s*(.+?)\s+book\s+(\d+)\s*$", segment, re.IGNORECASE)
        if match:
            return normalize_series_name(match.group(1)), int(match.group(2))
        match = re.match(r"^\s*(.+?)\s+(\d+)\s*$", segment)
        if match:
            return normalize_series_name(match.group(1)), int(match.group(2))

    match = re.match(r"^\s*(.+?)\s+book\s+(\d+)\b", clean, re.IGNORECASE)
    if match:
        return normalize_series_name(match.group(1)), int(match.group(2))

    return None, None


def parse_heading(heading_line: str) -> tuple[str, str | None]:
    text = heading_line.lstrip("#").strip()
    text = strip_markdown(text)

    by_split = re.split(r"\s+by\s+", text, maxsplit=1, flags=re.IGNORECASE)
    if len(by_split) == 2:
        title = by_split[0].strip()
        author = by_split[1].strip()
        return title, author

    dash_split = re.split(r"\s+[\u2014\u2013-]\s+", text)
    if len(dash_split) >= 2:
        title = " ".join(dash_split[:-1]).strip()
        author = dash_split[-1].strip()
        return title, author

    return text.strip(), None


def parse_month_heading(text: str) -> tuple[str | None, int | None]:
    text = strip_markdown(text)
    match = re.match(r"^([A-Za-z]+)", text)
    if not match:
        return None, None
    month_name = match.group(1)
    month_num = MONTHS.get(month_name.capitalize())
    return month_name, month_num


def parse_date(raw: str) -> str | None:
    raw = strip_markdown(raw).replace(",", "").strip()
    if not raw:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    match = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$", raw)
    if match:
        day = int(match.group(1))
        month = MONTHS.get(match.group(2).capitalize())
        year = int(match.group(3))
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return raw


def extract_rating(lines: list[str]) -> int:
    for line in lines:
        if STAR in line:
            count = line.count(STAR)
            if count:
                return count
    return 0


def extract_tags(lines: list[str]) -> list[str]:
    tags: list[str] = []
    seen = set()
    for line in lines:
        for tag in TAG_RE.findall(line):
            token = f"#{tag}"
            if token not in seen:
                seen.add(token)
                tags.append(token)
    return tags


def extract_finished(lines: list[str]) -> str | None:
    for line in lines:
        match = FINISHED_RE.search(line)
        if match:
            return parse_date(match.group(1))
    return None


def make_entry_id(title: str, author: str | None, year: int, month_num: int | None) -> str:
    month_val = month_num or 0
    base = f"{title or ''}|{author or ''}|{year}|{month_val}"
    hash_part = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    slug = slugify(title)
    return f"{year}-{month_val:02d}-{slug}-{hash_part}"


def parse_series_table(lines: list[str]) -> list[dict]:
    series: list[dict] = []
    in_section = False
    in_table = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Other books or series of books"):
            in_section = True
            continue
        if in_section and stripped.startswith("## ") and "Other books or series of books" not in stripped:
            break
        if not in_section:
            continue

        if stripped.startswith("| Book Series"):
            in_table = True
            continue
        if in_table:
            if not stripped.startswith("|"):
                if series:
                    break
                continue
            if stripped.lstrip().startswith("|---"):
                continue
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) < 4:
                continue
            series_name = strip_markdown(cols[0])
            author = strip_markdown(cols[1])
            rating = cols[2]
            review = cols[3] if len(cols) == 4 else "|".join(cols[3:]).strip()
            series.append(
                {
                    "seriesName": series_name,
                    "author": author,
                    "ratingStars": rating.count(STAR),
                    "reviewText": review,
                }
            )

    return series


def parse_entries_and_years(lines: list[str]) -> tuple[list[dict], dict[int, list[str]]]:
    entries: list[dict] = []
    year_lines: dict[int, list[str]] = {}

    current_year: int | None = None
    current_month_name: str | None = None
    current_month_num: int | None = None
    current_entry: dict | None = None

    def flush_entry() -> None:
        nonlocal current_entry
        if not current_entry:
            return
        entry_lines = current_entry["lines"]
        rating = extract_rating(entry_lines[1:])
        tags = extract_tags(entry_lines[1:])
        finished = extract_finished(entry_lines[1:])

        entry = {
            "id": current_entry["id"],
            "title": current_entry["title"],
            "author": current_entry["author"],
            "year": current_entry["year"],
            "month": current_entry["month_num"],
            "monthName": current_entry["month_name"],
            "dateFinished": finished,
            "ratingStars": rating,
            "source": {
                "file": f"years/{current_entry['year']}.md",
                "anchor": f"entry-{current_entry['id']}",
            },
        }
        if current_entry.get("series_name"):
            series_obj = {"name": current_entry["series_name"]}
            if current_entry.get("series_number") is not None:
                series_obj["number"] = current_entry["series_number"]
            entry["series"] = series_obj
        if tags:
            entry["tags"] = tags
        entries.append(entry)
        current_entry = None

    for line in lines:
        line = line.rstrip("\n")

        year_match = YEAR_RE.match(line)
        if year_match:
            flush_entry()
            current_year = int(year_match.group(1))
            current_month_name = None
            current_month_num = None
            year_lines[current_year] = [line]
            continue

        if current_year is None:
            continue

        entry_match = ENTRY_RE.match(line)
        if entry_match:
            flush_entry()
            title, author = parse_heading(line)
            series_name, series_number = extract_series_info(title)
            entry_id = make_entry_id(title, author, current_year, current_month_num)
            current_entry = {
                "id": entry_id,
                "title": title,
                "author": author,
                "year": current_year,
                "month_name": current_month_name,
                "month_num": current_month_num,
                "series_name": series_name,
                "series_number": series_number,
                "lines": [line],
            }
            year_lines[current_year].append(f'<a id="entry-{entry_id}"></a>')
            year_lines[current_year].append(line)
            continue

        month_match = MONTH_RE.match(line)
        if month_match:
            flush_entry()
            month_text = month_match.group(1).strip()
            current_month_name, current_month_num = parse_month_heading(month_text)
            year_lines[current_year].append(line)
            continue

        if current_entry:
            current_entry["lines"].append(line)
        year_lines[current_year].append(line)

    flush_entry()
    return entries, year_lines


def write_year_files(output_dir: Path, year_lines: dict[int, list[str]]) -> None:
    years_dir = output_dir / "years"
    years_dir.mkdir(parents=True, exist_ok=True)
    for year, lines in year_lines.items():
        content = "\n".join(lines).rstrip() + "\n"
        (years_dir / f"{year}.md").write_text(content, encoding="utf-8")


def write_index(output_dir: Path, source: Path, entries: list[dict], series: list[dict]) -> None:
    index = {
        "meta": {
            "source": source.name,
            "entryCount": len(entries),
            "years": sorted({entry["year"] for entry in entries}),
        },
        "series_table": series,
        "entries": entries,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate diary artifacts.")
    parser.add_argument("--input", default="Reading_diary.md")
    parser.add_argument("--output-dir", default="diary")
    args = parser.parse_args()

    input_path = Path(args.input)
    lines = input_path.read_text(encoding="utf-8").splitlines()

    series = parse_series_table(lines)
    entries, year_lines = parse_entries_and_years(lines)

    output_dir = Path(args.output_dir)
    write_year_files(output_dir, year_lines)
    write_index(output_dir, input_path, entries, series)

    print(f"Wrote {len(entries)} entries across {len(year_lines)} years.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
