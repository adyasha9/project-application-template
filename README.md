# Poetry Issues

Tools for exploring Poetry’s GitHub issues: what remains open, where work is aging, and how discussion has changed over time.

Built from the ENPM611 project template, it provides three command-line analyses run through `run.py` with a `--feature` flag.

## Contents

- [Dataset](#dataset)
- [Command-Line Analyses](#command-line-analyses)
  - [Setup](#setup)
  - [Feature 1: Label Resolution](#feature-1-label-resolution)
  - [Feature 2: Contributor Activity](#feature-2-contributor-activity-and-backlog-health)
  - [Feature 3: Discussion Trends](#feature-3-discussion-trends)
- [Interpreting the Data](#interpreting-the-data)
- [Architecture](#architecture)
- [Verification](#verification)
- [Team Contributions](#team-contributions)
- [Next Steps](#next-steps)

## Dataset

The analyses use `poetry_issues_all.json`, downloaded from Canvas. The data file is not stored in this repository; see [Setup](#setup) for how to point the program at it.

| Metric | Count |
|---|---:|
| Total issues | 5,573 |
| Open / closed | 317 / 5,256 |
| Bug-labeled issues | 2,860 |
| Open bug-labeled issues | 164 |
| Recorded comment events | 29,461 |

## Command-Line Analyses

Each analysis is selected with `python run.py --feature N`.

| Feature | Analysis | Details |
|---:|---|---|
| 1 | Label resolution time | [Feature 1](#feature-1-label-resolution) |
| 2 | Contributor Activity and Backlog Health | [Feature 2](#feature-2-contributor-activity-and-backlog-health) |
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

### Feature 1: Label Resolution

Answers the question: **which kinds of issues (by label) take the longest to resolve, and how many are still open?**

**What it does**

1. Loads all issues through the template `DataLoader`.
2. For each closed issue, computes the resolution time: days from `created_date` to the **final** recorded `closed` event.
3. Groups issues by label. An issue with several labels counts toward each of them.
4. For each label, calculates the number of issues, the share still open, and the **median** and mean resolution time. The median is used for ranking because a few issues stayed open for years and would distort the average.
5. Keeps labels with at least 20 issues, ranks them from slowest to fastest, prints the 15 slowest, and opens a bar chart.

**How to run**

After the [setup](#setup):

```sh
python run.py --feature 1
```

Optional detail for one label (names must match the dataset exactly, for example `kind/bug`, `area/docs`, `status/triage`):

```sh
python run.py --feature 1 --label kind/bug
```

If the label is not found, the program prints a message and lists common labels instead of failing.

**Outputs**

| Output | Description |
|---|---|
| Terminal table | For the 15 slowest labels: number of issues, % still open, median days to close |
| Terminal finding | One sentence naming the slowest and fastest label in the table |
| Bar chart (window) | Median days from creation to close for each label; close the window to finish |
| Label detail (`--label`) | Issue count, open/closed split, % open, median and mean resolution days for that label |

No files are written; use the chart window's save button to keep a copy of the chart.

Example (`--label kind/bug`):

```text
Label: kind/bug
  Issues: 2860 (open 164, closed 2696, 5.7% open)
  Median resolution: 6.7 days
  Mean resolution:   141.9 days (based on 2581 closed issues)
```

**Results on the full dataset**

- Slowest labels (median days to close): `area/error-handling` (692), `area/ux` (503), `area/publishing` (376), `kind/enhancement` (363).
- Fastest labels in the chart: `kind/feature` (50) and `area/core` (53).
- `kind/bug` issues close faster than any label in the chart: a median of 6.7 days, with only 5.7% still open.
- Finding: defects are handled quickly, while improvements to error messages, user experience, and publishing wait one to two years.

**Edge cases and notes**

- Open issues count toward the open share but not toward resolution time.
- Closed issues with no recorded `closed` event or no creation date are excluded from resolution time.
- Labels with fewer than 20 issues are left out of the table and chart to avoid small-sample results; they can still be inspected with `--label`.
- "Closed" does not necessarily mean "fixed": duplicates and declined requests are also closed.

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

**Outputs**

| Output | Description |
|---|---|
| Terminal summary | Issues analyzed, eligible contributors, observed response sample count, rejected records, and saved file locations |
| `contributor_activity.png` | Summary cards and charts showing monthly participation, current ownership, response-target outcomes, and quiet open backlog |
| `contributor_activity.csv` | One row per contributor with reporting, discussion, triage, ownership, response timing, and health metrics, plus analysis settings |

Files are written to the directory you run the command from. If they already exist, the next run saves numbered copies (`contributor_activity_2.csv`, `contributor_activity_2.png`, and so on) instead of overwriting.

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

**Historical reference:** October 20, 2024, the latest recorded activity—not a verified export timestamp. Results describe the exported snapshot, not current GitHub state.

Three distinctions matter:

- **Closed does not mean fixed.** Issues may be duplicates, invalid reports, or declined requests.
- **Current ownership does not prove who resolved an issue.** Historical assignment evidence is incomplete.
- **Missing dates are not zero durations.** Of the closed issues, 223 lack a usable closure date.

Open-issue age is measured at the historical reference. Closed duration runs from creation to the final recorded closure, including intervening closed periods. Comment counts reflect collected events; completeness is unverified.

## Architecture

| Component | Purpose |
|---|---|
| `contributor_activity_analysis.py` | Coordinate configuration, data loading, analysis, and report exports |
| `contributor_metrics.py` | Calculate participation, response timing, monthly activity, and ownership concentration |
| `contributor_health_metrics.py` | Analyze response-target outcomes, observed assignment delays, quiet backlog, and contributor history |
| `contributor_activity_exports.py` | Generate the contributor CSV report and PNG charts |
| `analytics.py` | Normalize issue records and parse timestamps for shared analysis |
| `run.py` | Command-line entry point; `--feature` selects the analysis to run |
| `label_resolution_analysis.py` | Label resolution analysis (feature 1) |
| `discussion_trend_analysis.py` | Discussion trends analysis (feature 3) |
| `data_loader.py`, `model.py`, `config.py` | Template utilities that load the JSON into `Issue` and `Event` objects and read configuration |
| `tests/` | Unit tests for contributor report file numbering |

All analyses read the JSON data file directly; the source data is never modified.

### Diagrams

> **Original template component diagram**  
> Asset: `diagram/team_5_component_diagram_before.svg.svg`

> **Proposed template extension**  
> Asset: `diagram/team_5_component_diagram_after.svg.svg`

> **Proposed contributor-analysis sequence**  
> Asset: `diagram/team_5_sequence_diagram.svg.svg`

The diagrams were created in Milestone 1 and show the planned design; the final implementation adds supporting modules for feature 2.

## Verification

```sh
python3 -m unittest discover -s tests -v
```

Seven unit tests cover the contributor report file numbering and pass.

The discussion trends analysis was checked by running it on `poetry_issues_all.json`: the totals (5,573 issues and 29,461 comments) match the dataset table above, and the date filter and empty-range cases behave as described. It has no automated tests yet.

The label resolution analysis was checked by running it on `poetry_issues_all.json`, including the single-label view (`--label kind/bug`) and an unknown label (`--label xyz`), which prints a message instead of failing. It has no automated tests yet.

## Team Contributions

| Member | Contributions |
|---|---|
| Darsh Savani | Feature 1: label resolution analysis (`label_resolution_analysis.py`); connected Feature 1 to `run.py`; Feature 1 README section |
| Adyasha Mishra | Created the team fork; Feature 3: discussion trends analysis (`discussion_trend_analysis.py`); README revisions; reviewed and merged pull requests |
| Andrew Foday | Feature 2: contributor activity analysis (`contributor_activity_analysis.py` and supporting modules); repository restructuring; README updates |

## Next Steps

Automated tests for the label resolution and discussion trends analyses, and stronger assignment-history coverage.

**Current scope:** a local, command-line historical analytics tool.
