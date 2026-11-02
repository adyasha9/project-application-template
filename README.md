# Poetry Issues

Tools for exploring Poetry’s GitHub issues: what remains open, where work is aging, and how discussion has changed over time.

Built from the ENPM611 project template, the project has two parts:

- **Dashboard:** an interactive web app for searching, filtering, and classifying issues.
- **Command-line analyses:** analyses run through `run.py` with a `--feature` flag.

## Contents

- [Dataset](#dataset)
- [Dashboard](#dashboard)
- [Command-Line Analyses](#command-line-analyses)
  - [Setup](#setup)
  - [Feature 2: Contributor Activity](#feature-2-contributor-activity)
  - [Feature 3: Discussion Trends](#feature-3-discussion-trends)
- [Interpreting the Data](#interpreting-the-data)
- [Architecture](#architecture)
- [Run the Dashboard](#run-the-dashboard)
- [Verification](#verification)
- [Next Steps](#next-steps)

## Dataset

Both parts use `poetry_issues_all.json`. The smaller export is retained for validation; the files are not combined because their issue numbers overlap.

| Metric | Count |
|---|---:|
| Total issues | 5,573 |
| Open / closed | 317 / 5,256 |
| Bug-labeled issues | 2,860 |
| Open bug-labeled issues | 164 |
| Recorded comment events | 29,461 |

## Dashboard

- **Overview:** open, closed, and bug-labeled totals.
- **Issue explorer:** search and filter by state, type, severity, ownership, and age.
- **Backlog aging:** clickable age bands reveal long-waiting issues.
- **Monthly trends:** compare issue creation and final recorded closures.
- **Calendar heat map:** explore daily creation activity by year.
- **Issue details:** descriptions, comments, recorded timelines, and GitHub links.
- **Manual severity:** save Critical, Major, Minor, or Unclassified locally.

All dashboard visualizations follow the dashboard filters. To start it, see [Run the Dashboard](#run-the-dashboard).

## Command-Line Analyses

Each analysis is selected with `python run.py --feature N`.

| Feature | Analysis | Details |
|---:|---|---|
| 2 | Contributor Activity and Backlog Health | [Feature 2](#feature-2-contributor-activity) |
| 3 | Monthly discussion trends | [Feature 3](#feature-3-discussion-trends) |

### Setup

Requires Python 3.10+. Run these once from the project folder:

```sh
python3 -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
```

Then point the program at the dataset, either with an environment variable:

```sh
export ENPM611_PROJECT_DATA_PATH="/path/to/poetry_issues_all.json"
```

or by setting `ENPM611_PROJECT_DATA_PATH` in `config.json`.

### Feature 2: Contributor Activity and Backlog Health

Shows who participates in Poetry’s issue tracker, how quickly issues receive responses, and where open work needs attention.

**What it does**

1. Filters contributor activity by an optional date range and excludes recognized bots by default.
2. Separately counts issues reported, issues discussed, comments, and recorded triage actions for each contributor.
3. Summarizes monthly participation and how concentrated discussion and current ownership are.
4. Calculates median and 90th-percentile first external response times and compares observed responses with a configurable review target.
5. Identifies aging assignments and quiet open issues, including those without a current owner.
6. Prints an analysis summary and saves contributor metrics to CSV and visualizations to PNG.

Date filters apply to activity; current ownership and quiet-backlog metrics describe the full snapshot. Incomplete timelines limit conclusions, and participation counts do not establish productivity or who fixed an issue.

**Run**

```sh
python run.py --feature 2
```

Optional date range (inclusive, `YYYY-MM-DD`):

```sh
python run.py --feature 2 \
  --start-date 2022-01-01 \
  --end-date 2023-12-31
```

### Feature 3: Discussion Trends

Shows how much discussion Poetry’s issue tracker generated over time.

**What it does**

1. Filters issues by an optional date range (a simple comparison on each issue’s `created_date`).
2. Buckets the remaining issues by creation month and counts them.
3. Counts comments (events of type `commented`) by the month in which each comment was posted.
4. Fills in months with no activity so the lines have no gaps.
5. Prints a summary and the monthly table, saves the table and chart, and opens the chart.

Resolution time is intentionally not part of this analysis.

**How to run**

After the [setup](#setup):

```sh
python run.py --feature 3
```

Optional date range (inclusive, `YYYY-MM-DD`):

```sh
python run.py --feature 3 --start-date 2022-01-01 --end-date 2023-12-31
```

If no issues fall inside the range, the program prints a message and exits without drawing a chart.

**Outputs**

| Output | Description |
|---|---|
| Terminal summary | Totals, busiest month for issues, busiest month for comments, average comments per issue |
| Terminal table | Issues and comments for every month in the range |
| `discussion_trends.png` | Line chart of issues created and comments posted per month, plus a second panel of comments per issue |
| `discussion_trends.csv` | The monthly table, for use in a spreadsheet |

The PNG and CSV are written to the directory you run the command from.

**Results on the full dataset**

Across 5,573 issues and 29,461 comments over 81 months (February 2018 to October 2024):

- Most issues created in one month: October 2020 (169).
- Most comments posted in one month: March 2024 (3,767).
- Average of 5.3 comments per issue.
- Comment volume spikes sharply in early 2024, far above the usual few hundred per month. This is unusually concentrated activity rather than a normal trend, and its cause has not been investigated.

**Edge cases and notes**

- Issues without a usable `created_date` are skipped.
- Comment events without a date are skipped.
- The date filter applies to issues, so the comments counted are those on the issues that pass the filter. A comment posted after the end date is still counted if its issue was created inside the range.
- Dates with and without time zones are compared in UTC.
- Comment counts reflect collected events; completeness is unverified.

## Interpreting the Data

**Issue type and severity answer different questions.** Type describes the work; severity describes its impact. Types come from explicit labels. The export contains no task/project or severity labels, so these classifications are not inferred.

Manual severity choices update the dashboard, persist across restarts, and remain separate from GitHub labels. They can be removed to restore the original classification.

Three distinctions matter:

- **Closed does not mean fixed.** Issues may be duplicates, invalid reports, or declined requests.
- **Current ownership does not prove who resolved an issue.** Historical assignment evidence is incomplete.
- **Missing dates are not zero durations.** Of the closed issues, 223 lack a usable closure date.

Open-issue age is measured at the historical reference. Closed duration runs from creation to the final recorded closure, including intervening closed periods. Comment counts reflect collected events; completeness is unverified.

## Architecture

| Component | Purpose |
|---|---|
| `analytics.py` | Normalize data, classify issues, and calculate metrics |
| `app.py` | Serve the dashboard and API; manage SQLite storage |
| `web/` | Dashboard interface, interactions, and styling |
| `run.py` | Command-line entry point; `--feature` selects the analysis to run |
| `discussion_trend_analysis.py` | Discussion trends analysis (feature 3) |
| `data_loader.py`, `model.py`, `config.py` | Template utilities that load the JSON into `Issue` and `Event` objects and read configuration |
| `tests/` | Metric, persistence, classification, and calendar checks |

For the dashboard, source JSON remains unchanged; SQLite stores the active snapshot and separate manual severity overrides. The command-line analyses read the JSON directly and do not use SQLite.

### Diagrams

> **Original template component diagram**  
> Asset: `team_5_component_diagram_before.svg.svg`

> **Proposed template extension**  
> Asset: `team_5_component_diagram_after.svg.svg`

> **Proposed contributor-analysis sequence**  
> Asset: `team_5_sequence_diagram.svg.svg`

The proposed diagrams reference planned command-line modules, not the current dashboard.

> **Current dashboard architecture**  
> JSON import → normalization → SQLite → API → dashboard

## Run the Dashboard

Requires Python 3.10+ and a modern browser. No third-party Python packages are needed.

```sh
python3 app.py \
  --data /path/to/poetry_issues_all.json \
  --observed-at 2024-10-20T17:19:04+00:00
```

Open **http://127.0.0.1:8765/**.

For later sessions, run `python3 app.py` to reuse stored data. Stop with `Ctrl+C`.

A new import replaces the active snapshot. Back up `issues.sqlite3` to preserve manual classifications.

**Historical reference:** October 20, 2024, the latest recorded activity—not a verified export timestamp. Results describe the exported snapshot, not current GitHub state.

## Verification

```sh
python3 -m unittest discover -s tests -v
node tests/test_calendar.cjs
node --check web/app.js
```

Thirteen Python tests and the JavaScript calendar checks passed during development. Browser visual and interaction verification remains pending.

The discussion trends analysis was checked by running it on `poetry_issues_all.json`: the totals (5,573 issues and 29,461 comments) match the dataset table above, and the date filter and empty-range cases behave as described. It has no automated tests yet.

## Next Steps

Live synchronization, stronger assignment-history coverage, contributor analysis, and production hosting with access control.

**Current scope:** a local, single-user historical analytics tool.
