```markdown
# Codex Instructions: Make Literary Companion scale with a large GitHub reading diary (Custom GPT Actions)

## Context
We have a Custom GPT called **“Literary Companion”** that relies on a GitHub-hosted reading diary Markdown file. The diary has grown large enough that fetching it in one action call fails with a “too big” / tool-output/context ingestion style error.

The solution must continue to work for the **foreseeable future** as the diary accumulates entries across **many years**. That means the design must scale without periodic manual intervention.

The diary format (important for parsing/indexing):
- A top section: “Other books or series of books I have read and enjoyed” with a Markdown table (Series, Author, Rating, Review).
- Year headings like `## 2024`, `## 2025`, etc.
- Month headings like `### January 2024`
- Book entries typically like `#### <Title> by <Author>`
- Rating lines with star emojis like `⭐️⭐️⭐️⭐️`
- Review prose until the next entry heading
- Occasional tags like `#bookclub`, blockquotes, and subheadings
- Formatting is not perfectly consistent; parsing must tolerate small drift.

## Problem
Current action fetches the entire diary from GitHub Raw, e.g.:
- `GET https://raw.githubusercontent.com/robert-rollings/reading_diary/main/Reading_diary.md`

This is no longer viable because the response is too large.

## Objective
Redesign the repo artifacts + action interface so Literary Companion can:
1) Load a **small index/metadata** first
2) Fetch **only the relevant chunk(s)** of content for the user’s question
3) Avoid ever ingesting the full diary by default
4) Keep working as the diary grows across many years (no recurring manual split work)

## Hard requirements (Codex must produce)
Codex must produce:
1) A **repo artifact plan** (what files exist in the GitHub repo after the change)
2) **Code for Custom GPT Actions**: a complete **OpenAPI schema** ready to paste into the Actions editor (operationIds, parameters, response types)
3) If applicable, **generator code** + **GitHub Actions workflow** that builds the new artifacts from the single source diary
4) An update to the **Literary Companion Instructions** markdown so it uses the new actions correctly

## Priority: Keep the diary as one authoring file
Codex must first attempt solutions that preserve:
- `Reading_diary.md` as the **single source of truth** for editing

Only fall back to manual splitting if absolutely necessary. The preferred approach must scale automatically as years accumulate.

---

## Solution options Codex must consider (in this order)

### Option 1 (preferred): One source file + generated index + generated scalable chunks/extracts
Keep editing `Reading_diary.md` only, but generate *derived artifacts* for the GPT:

**Must generate (always):**
- `diary/index.json` — small metadata-only index; always safe to fetch

**Must generate one scalable content strategy:**
Choose the most robust for long-term growth:

**A) Year chunk files (recommended default)**
- `diary/years/2024.md`, `diary/years/2025.md`, ...  
Generated automatically from the single source file. This naturally scales year by year.

**OR B) Per-review extracts (best precision, more files)**
- `diary/extracts/<id>.md` per review  
Still generated automatically, so it scales indefinitely.

**Avoid** “compact-only” summaries as the sole source, because review critique needs actual review text.

#### Index requirements (must support most queries without extra fetch)
`diary/index.json` must include enough info to answer:
- “Have I read X?”
- “What do I generally like?”
- “Recommend me a book based on my diary”
…using index only, 90%+ of the time.

Minimum per-entry fields:
- `id` (stable, deterministic)
- `title`
- `author`
- `year`
- `month` (string or number)
- `dateFinished` (if present; else null)
- `ratingStars` (integer 0–5 derived from ⭐ count)
- `tags` (array; optional)
- `source` pointer:
  - if year chunks: `{ "file": "years/2025.md", "anchor": "..." }`
  - if extracts: `{ "file": "extracts/<id>.md" }`

Also include `series_table` parsed from the top Markdown table:
- `seriesName`, `author`, `ratingStars`, `reviewText`

#### Generator behavior (must be robust)
Parser/generator must:
- Be deterministic
- Tolerate formatting drift (extra spaces, missing blank lines, minor heading variations)
- Parse:
  - Year headings `## 2024`
  - Month headings `### January 2024`
  - Book headings `#### Title by Author` (tolerate variations; handle edge cases gracefully)
  - Rating lines containing star emojis
  - Tags like `#bookclub` near rating or first lines of the entry
  - Review body until next `####`/`###`/`##`

#### Scalability requirement (must satisfy)
The generator must keep working as the diary grows across many years:
- No manual editing needed to create new year files or extracts
- Index stays small enough for the action payload
- Year chunks/extracts remain fetchable individually

#### Deliverables for Option 1
Codex must output:
- Parser script (Python or Node) that reads `Reading_diary.md` and writes:
  - `diary/index.json`
  - `diary/years/<year>.md` OR `diary/extracts/<id>.md`
- GitHub Actions workflow YAML that:
  - Runs on push to `main`
  - Regenerates the derived artifacts
  - Commits changes back to repo (or otherwise ensures the derived files exist in-repo on main)

### Option 2 (fallback): Split diary into year files as primary (avoid if possible)
If Option 1 is not viable, restructure repo into:
- `diary/index.json`
- `diary/2024.md`, `diary/2025.md`, ...

But this is less preferred because it risks recurring maintenance. Only choose if absolutely necessary.

### Option 3 (avoid unless proven): HTTP Range requests
Only consider if Custom GPT Actions reliably support headers and byte-range requests. Usually brittle.

---

## Custom GPT Actions: required endpoints
Codex must output a paste-ready OpenAPI schema supporting:

### 1) `getDiaryIndex`
- `GET /robert-rollings/reading_diary/main/diary/index.json`
- Returns `application/json`

### 2) Content fetch (choose based on strategy)
**If using year chunks:**
- `getDiaryYear`
  - `GET /robert-rollings/reading_diary/main/diary/years/{year}.md`
  - `year` is a path param (e.g., `2025`)
  - Returns `text/plain`

**If using extracts:**
- `getDiaryExtract`
  - `GET /robert-rollings/reading_diary/main/diary/extracts/{id}.md`
  - Returns `text/plain`

### Optional legacy endpoint (do not use by default)
- `getReadingDiaryFull`
  - `GET /robert-rollings/reading_diary/main/Reading_diary.md`
  - For debugging only; GPT instructions must strongly discourage use.

---

## Required update: Literary Companion Instructions must change
Current instructions say:
- “Before answering diary-dependent questions, you must call `getReadingDiary`.”

This must be changed.

Codex must update the instructions so the GPT does:
1) Call `getDiaryIndex` first for diary-dependent queries
2) Call `getDiaryYear`/`getDiaryExtract` only when it needs review prose or detailed quotes

Update the “Source of Truth” section to say:
- Index is authoritative for read history, ratings, dates, and high-level preference signals
- Full review text is authoritative only when fetched via the year/extract endpoint
- Do not infer missing facts; if it’s not in index or fetched content, say so explicitly

Also add tool-usage guidance:
- “Have I read X?” → index only
- “What did I think of X?” → index → then fetch only the relevant year/extract
- Recommendations → index only (optionally sample 1–2 extracts if the user explicitly wants deep evidence)

---

## Acceptance criteria
- `getDiaryIndex` never triggers the “too big” error.
- 90%+ of queries use **index only**.
- Deep review critique fetches **at most one** year chunk or one extract by default.
- The approach continues to work as the diary accumulates entries for many years (no manual splitting required).

---

## Deliverables checklist (Codex output must include)
1) Final recommended approach (Option 1 preferred; Option 2 only if necessary)
2) Repo file layout after change
3) Generator script code + GitHub Actions workflow (if Option 1)
4) Paste-ready OpenAPI schema for Custom GPT Actions
5) Patch/update to Literary Companion Instructions markdown reflecting the new action calls and “source of truth” logic
```
