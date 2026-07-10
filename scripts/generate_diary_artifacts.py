#!/usr/bin/env python3
"""
Generate diary/index.json from the per-entry notes in diary/entries/
and the series table in diary/series_overview.md.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

STAR = "⭐"

INT_RE = re.compile(r"^-?\d+$")
FLOAT_RE = re.compile(r"^-?\d+\.\d+$")
KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
LIST_ITEM_RE = re.compile(r"^\s*-\s*(.*)$")


def strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    for token in ("**", "__", "*", "_", "`"):
        text = text.replace(token, "")
    text = " ".join(text.split())
    return text.strip()


def split_flow_list(inner: str) -> list[str]:
    items: list[str] = []
    current = ""
    in_quote: str | None = None
    for ch in inner:
        if in_quote:
            current += ch
            if ch == in_quote:
                in_quote = None
            continue
        if ch in "\"'":
            in_quote = ch
            current += ch
            continue
        if ch == ",":
            items.append(current.strip())
            current = ""
            continue
        current += ch
    if current.strip():
        items.append(current.strip())
    return items


def parse_scalar(raw: str):
    raw = raw.strip()
    if raw == "":
        return None
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1].replace("''", "'")
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(item) for item in split_flow_list(inner)]
    if INT_RE.match(raw):
        return int(raw)
    if FLOAT_RE.match(raw):
        return float(raw)
    return raw


def parse_yaml_block(lines: list[str]) -> dict:
    data: dict = {}
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        match = KEY_RE.match(line)
        if not match:
            i += 1
            continue
        key, value = match.group(1), match.group(2)
        if value.strip() == "":
            items = []
            j = i + 1
            while j < n and LIST_ITEM_RE.match(lines[j]):
                item_match = LIST_ITEM_RE.match(lines[j])
                items.append(parse_scalar(item_match.group(1)))
                j += 1
            if items:
                data[key] = items
                i = j
                continue
            data[key] = None
            i += 1
            continue
        data[key] = parse_scalar(value)
        i += 1
    return data


WIKILINK_RE = re.compile(r"^\[\[([^\]|]*)(?:\|([^\]]+))?\]\]$")


def strip_wikilink(value):
    if not isinstance(value, str):
        return value
    match = WIKILINK_RE.match(value.strip())
    if not match:
        return value
    target, alias = match.groups()
    return (alias or target).strip()


def parse_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text
    data = parse_yaml_block(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :]).strip()
    return data, body


def load_entry(path: Path, entries_dir: Path, diary_dir: Path) -> dict | None:
    fm, _body = parse_frontmatter(path.read_text(encoding="utf-8"))
    title = fm.get("title")
    if not title:
        return None

    entry_id = str(path.relative_to(entries_dir).with_suffix("")).replace("\\", "/")
    entry: dict = {
        "id": entry_id,
        "title": str(title),
        "author": strip_wikilink(fm.get("author")),
        "path": str(path.relative_to(diary_dir)).replace("\\", "/"),
    }
    if fm.get("year") is not None:
        entry["year"] = fm["year"]
    if fm.get("month") is not None:
        entry["month"] = fm["month"]
    if fm.get("series"):
        entry["series"] = strip_wikilink(fm["series"])
        if fm.get("series_number") is not None:
            entry["seriesNumber"] = fm["series_number"]
        if fm.get("parent_series"):
            entry["parentSeries"] = strip_wikilink(fm["parent_series"])
            if fm.get("parent_series_number") is not None:
                entry["parentSeriesNumber"] = fm["parent_series_number"]
    if fm.get("rating") is not None:
        entry["rating"] = fm["rating"]
    if fm.get("started"):
        entry["started"] = fm["started"]
    if fm.get("finished"):
        entry["finished"] = fm["finished"]
    tags = fm.get("tags")
    if tags:
        entry["tags"] = tags
    return entry


def parse_series_overview(path: Path) -> list[dict]:
    if not path.exists():
        return []
    series: list[dict] = []
    in_table = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("| Book Series"):
            in_table = True
            continue
        if not in_table or not stripped.startswith("|"):
            continue
        if stripped.lstrip("|").strip().startswith("---"):
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


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "-", name)


def ensure_stub_notes(entries: list[dict], diary_dir: Path) -> list[str]:
    authors_dir = diary_dir / "authors"
    series_dir = diary_dir / "series"
    authors_dir.mkdir(exist_ok=True)
    series_dir.mkdir(exist_ok=True)

    author_names = {e["author"] for e in entries if e.get("author")}
    series_names = {e["series"] for e in entries if e.get("series")}
    series_names |= {e["parentSeries"] for e in entries if e.get("parentSeries")}

    created = []
    for name in sorted(author_names):
        path = authors_dir / f"{safe_filename(name)}.md"
        if not path.exists():
            path.write_text(f"# {name}\n", encoding="utf-8")
            created.append(str(path.relative_to(diary_dir)))
    for name in sorted(series_names):
        path = series_dir / f"{safe_filename(name)}.md"
        if not path.exists():
            path.write_text(f"# {name}\n", encoding="utf-8")
            created.append(str(path.relative_to(diary_dir)))
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate diary/index.json from per-entry notes.")
    parser.add_argument("--diary-dir", default="diary")
    args = parser.parse_args()

    diary_dir = Path(args.diary_dir)
    entries_dir = diary_dir / "entries"

    entries = []
    missing_author = []
    for path in sorted(entries_dir.glob("*/*.md")):
        entry = load_entry(path, entries_dir, diary_dir)
        if entry:
            entries.append(entry)
            if not entry["author"]:
                missing_author.append(str(path.relative_to(diary_dir)))
    if missing_author:
        raise SystemExit(
            "author is required but missing in:\n"
            + "\n".join(f"  - {p}" for p in missing_author)
        )
    entries.sort(key=lambda e: (e.get("year") or 0, e.get("month") or 0, e["title"]))

    created_stubs = ensure_stub_notes(entries, diary_dir)
    if created_stubs:
        print(f"Created {len(created_stubs)} new stub note(s):")
        for p in created_stubs:
            print(f"  - {p}")

    series_table = parse_series_overview(diary_dir / "series_overview.md")

    index = {
        "meta": {
            "entryCount": len(entries),
            "years": sorted({e["year"] for e in entries if "year" in e}),
        },
        "series_table": series_table,
        "entries": entries,
    }
    (diary_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(entries)} entries to {diary_dir / 'index.json'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
