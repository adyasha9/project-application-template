"""Evidence-based contributor analytics; no dashboard or database mutations.

CLI: python3 contributor_activity_analysis.py --data /path/to/issues.json
Optional --since/--until are inclusive UTC activity boundaries. --observed-at is
snapshot metadata; otherwise the latest valid recorded timestamp is used.

Activity counts describe participation, not fixes, effort, or productivity.
Snapshot ownership is intentionally independent of the activity window. A response
is a comment by someone other than the reporter, not necessarily a maintainer.
Unknown timeline completeness means no recorded response is not proof of neglect.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
import math
from statistics import median
from typing import Any
from urllib.parse import urlsplit

from analytics import timestamp

TRIAGE_EVENTS = frozenset({'labeled', 'unlabeled', 'assigned', 'unassigned',
                          'closed', 'reopened', 'milestoned', 'demilestoned',
                          'renamed', 'marked_as_duplicate', 'transferred'})
COMMENT_EVENTS = frozenset({'commented', 'comment'})
DEFAULT_BOTS = frozenset({'dependabot', 'github-actions'})


def _user(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    name = value.strip().casefold()
    return None if name == 'unknown' else name


def _distribution(values: list[float]) -> dict:
    ordered = sorted(values)
    return {'samples': len(values),
            'median_hours': round(median(values), 2) if values else None,
            'p90_hours': round(ordered[math.ceil(.9 * len(ordered)) - 1], 2) if values else None}


def _date(value: str | None, name: str) -> datetime | None:
    if value is None:
        return None
    parsed = timestamp(value)
    if parsed is None:
        raise ValueError(f'{name} must be an ISO-8601 date or timestamp')
    return parsed


def _analyze_base(issues: list[dict], *, observed_at: str | None = None,
                         since: str | None = None, until: str | None = None,
                         include_bots: bool = False, bot_accounts: tuple[str, ...] = (),
                         stale_days: int = 90) -> dict:
    """Analyze normalized issues returned by analytics.normalize.

    Contributor identities are case-insensitive GitHub logins. Recognized bots
    ([bot] suffix, defaults and explicit accounts) are excluded unless requested.
    Events with IDs are deduplicated per issue. No-ID records are not guessed to
    be duplicates. Named event actors receive participation credit, never inferred
    assignee/fix credit. Results are alphabetical, with evidence IDs for drilldown.
    """
    if isinstance(stale_days, bool) or not isinstance(stale_days, int) or stale_days < 0:
        raise ValueError('stale_days must be a nonnegative integer')
    start = _date(since, 'since')
    end = _date(until, 'until')
    supplied_observed = _date(observed_at, 'observed_at')
    dates = [timestamp(i.get(k)) for i in issues for k in ('created', 'updated', 'closed')]
    dates.extend(timestamp(e.get('date')) for i in issues for e in i.get('events', []))
    latest = max((d for d in dates if d), default=None)
    observed = supplied_observed or latest
    if observed is None:
        # No wall-clock fallback: an empty/undated dataset has no reference.
        observed = end or start
    if supplied_observed and latest and supplied_observed < latest:
        raise ValueError('observed_at precedes recorded activity; cannot treat this as an earlier snapshot')
    end = end or observed
    if start and end and start > end:
        raise ValueError('since must not be after until')
    if observed and end and end > observed:
        raise ValueError('until must not be after the snapshot reference')

    bots = DEFAULT_BOTS | frozenset(x.casefold() for x in bot_accounts)
    quality = Counter({key: 0 for key in ('duplicate_issues_skipped', 'issues_missing_creation_date',
        'issues_without_confirmed_timeline', 'issues_missing_reporter', 'duplicate_events_skipped',
        'events_without_ids', 'nonparticipation_events_excluded', 'participation_events_missing_date',
        'events_before_creation_excluded', 'participation_events_missing_actor', 'bot_participation_events_excluded')})
    people: dict[str, dict] = {}
    monthly: dict[str, dict] = defaultdict(lambda: {'actors': set(), 'issues': set(), 'comments': 0, 'triage_events': 0, 'reported': 0})
    response_delays: list[float] = []
    response_cohort: set[str] = set()
    no_response: set[str] = set()
    unassigned_open: set[str] = set()
    closed_without_date: set[str] = set()
    seen_issues: set[str] = set()

    def accepted(name):
        if not name:
            return False
        return include_bots or not (name.endswith('[bot]') or name in bots)

    def window(dt):
        return dt is not None and (start is None or dt >= start) and (end is None or dt <= end)

    def member(name):
        if name not in people:
            people[name] = {'reported': set(), 'commented': set(), 'triaged': set(),
                            'touched': set(), 'open_assigned': set(), 'old_open_assigned': set(),
                            'first_responses': set(), 'response_hours': [], 'comments': 0,
                            'triage_events': 0, 'active_days': set(), 'months': set(), 'areas': Counter(),
                            'last_activity': None}
        return people[name]

    def activity(name, issue_id, dt):
        p = member(name)
        p['touched'].add(issue_id)
        p['active_days'].add(dt.date().isoformat())
        p['months'].add(dt.strftime('%Y-%m'))
        if p['last_activity'] is None or dt > p['last_activity']:
            p['last_activity'] = dt
        bucket = monthly[dt.strftime('%Y-%m')]
        bucket['actors'].add(name)
        bucket['issues'].add(issue_id)
        return p, bucket

    for issue in issues:
        # Canonical GitHub repository/number; missing URLs mean one imported repository.
        url = urlsplit(issue.get('url') or '')
        parts = url.path.strip('/').split('/')
        if url.hostname == 'api.github.com' and parts[0] == 'repos': parts = parts[1:]
        if url.hostname in ('github.com', 'api.github.com') and len(parts) >= 2:
            issue_id = f"https://github.com/{parts[0].casefold()}/{parts[1].casefold()}/issues/{issue['number']}"
        else:
            issue_id = f"{issue.get('url') or 'import'}#{issue['number']}"
        if issue_id in seen_issues:
            quality['duplicate_issues_skipped'] += 1
            continue
        seen_issues.add(issue_id)
        created = timestamp(issue.get('created'))
        if created is None:
            quality['issues_missing_creation_date'] += 1
        if not issue.get('timeline_complete'):
            quality['issues_without_confirmed_timeline'] += 1
        if issue['state'] == 'closed' and not timestamp(issue.get('closed')):
            closed_without_date.add(issue_id)
        reporter = _user(issue.get('creator'))
        if reporter is None:
            quality['issues_missing_reporter'] += 1
        if accepted(reporter) and window(created):
            _, bucket = activity(reporter, issue_id, created)
            member(reporter)['reported'].add(issue_id)
            bucket['reported'] += 1
        if issue['state'] == 'open':
            owners = {_user(x) for x in issue.get('assignees', [])} - {None}
            if not owners:
                unassigned_open.add(issue_id)
            for owner in owners:
                if not accepted(owner):
                    continue
                p = member(owner)
                p['open_assigned'].add(issue_id)
                if created and observed and (observed-created).total_seconds() >= stale_days*86400:
                    p['old_open_assigned'].add(issue_id)
        response_candidates = []
        seen_events = set()
        discussion_actors = set()
        for event in issue.get('events', []):
            event_id = event.get('id')
            if event_id is not None:
                # JSON-serializable IDs need not be integers.
                token = json.dumps(event_id, sort_keys=True)
                if token in seen_events:
                    quality['duplicate_events_skipped'] += 1
                    continue
                seen_events.add(token)
            else:
                quality['events_without_ids'] += 1
            kind = event.get('type')
            if kind not in TRIAGE_EVENTS | COMMENT_EVENTS:
                quality['nonparticipation_events_excluded'] += 1
                continue
            dt, actor = timestamp(event.get('date')), _user(event.get('author'))
            if dt is None:
                quality['participation_events_missing_date'] += 1
                continue
            if created and dt < created:
                quality['events_before_creation_excluded'] += 1
                continue
            if actor is None:
                quality['participation_events_missing_actor'] += 1
                continue
            if not accepted(actor):
                quality['bot_participation_events_excluded'] += 1
                continue
            if kind in COMMENT_EVENTS and created and reporter and actor != reporter and (end is None or dt <= end):
                response_candidates.append((dt, actor))
            if not window(dt):
                continue
            p, bucket = activity(actor, issue_id, dt)
            if kind in COMMENT_EVENTS:
                p['comments'] += 1
                p['commented'].add(issue_id)
                discussion_actors.add(actor)
                bucket['comments'] += 1
            else:
                p['triage_events'] += 1
                p['triaged'].add(issue_id)
                bucket['triage_events'] += 1
        # Area breadth counts distinct discussed issues, not repeated comments.
        for actor in discussion_actors:
            for area in {x for x in issue.get('labels', []) if x.startswith('area/')}:
                member(actor)['areas'][area] += 1
        # Response cohort is issues created in the window with an eligible reporter.
        if window(created) and accepted(reporter):
            response_cohort.add(issue_id)
            if response_candidates:
                first = min(dt for dt, _ in response_candidates)
                hours = (first-created).total_seconds()/3600
                response_delays.append(hours)
                # Equal-timestamp first responders share credit; cohort is counted once.
                for actor in {actor for dt, actor in response_candidates if dt == first}:
                    p = member(actor)
                    p['first_responses'].add(issue_id)
                    p['response_hours'].append(hours)
            else:
                no_response.add(issue_id)

    rows = []
    for name, p in sorted(people.items()):
        rows.append({'login': name,
                     'activity': {'issues_reported': len(p['reported']), 'issues_commented_on': len(p['commented']),
                                  'comments': p['comments'], 'issues_triaged': len(p['triaged']),
                                  'triage_events': p['triage_events'], 'distinct_issues_touched': len(p['touched']),
                                  'active_days': len(p['active_days']), 'active_months': len(p['months']),
                                  'last_recorded_activity': p['last_activity'].isoformat() if p['last_activity'] else None},
                     'snapshot_ownership': {'open_issues': len(p['open_assigned']),
                                            'old_open_issues': len(p['old_open_assigned'])},
                     'first_external_responses': {'issues': len(p['first_responses']), **_distribution(p['response_hours'])},
                     'discussion_areas': dict(sorted(p['areas'].items())),
                     'evidence': {k: sorted(p[k]) for k in ('reported', 'commented', 'triaged', 'open_assigned', 'old_open_assigned', 'first_responses')}})

    def concentration(role):
        counts = sorted(((len(p[role]), name) for name, p in people.items() if p[role]), reverse=True)
        denominator = sum(n for n, _ in counts)
        top = counts[:3]
        return {'total_contributor_issue_pairs': denominator,
                'contributors': len(counts), 'top_three_logins': sorted(name for _, name in top),
                'top_three_share_percent': round(100*sum(n for n, _ in top)/denominator, 2) if denominator else None}

    return {'schema_version': 1,
            'scope': {'snapshot_reference': observed.isoformat() if observed else None,
                      'reference_basis': 'provided' if supplied_observed else 'latest_recorded_activity' if latest else 'window_boundary' if observed else 'unavailable',
                      'since_inclusive': start.isoformat() if start else None,
                      'until_inclusive': end.isoformat() if end else None,
                      'include_bots': include_bots, 'stale_days': stale_days,
                      'ownership_scope': 'current snapshot; not restricted by activity window'},
            'team': {'issues_analyzed': len(seen_issues), 'contributors': len(rows),
                     'response_cohort': len(response_cohort), 'recorded_external_response': _distribution(response_delays),
                     'without_recorded_external_response': len(no_response),
                     'open_without_current_owner': len(unassigned_open),
                     'discussion_concentration': concentration('commented'),
                     'open_ownership_concentration': concentration('open_assigned')},
            'monthly': {month: {'active_contributors': len(v['actors']), 'distinct_issues_touched': len(v['issues']),
                                'comments': v['comments'], 'triage_events': v['triage_events'], 'issues_reported': v['reported']}
                        for month, v in sorted(monthly.items())},
            'contributors': rows, 'data_quality': dict(sorted(quality.items())),
            'evidence': {'without_recorded_external_response': sorted(no_response),
                         'open_without_current_owner': sorted(unassigned_open),
                         'closed_without_usable_closure_date': sorted(closed_without_date)},
            'interpretation': [
                'Participation is not proof of fixes, effort, maintainer status, or productivity.',
                'First external response excludes the reporter; recognized bots are excluded by default.',
                'No recorded response is not proof of no response; timeline coverage may be incomplete.',
                'Current open ownership is a snapshot, not historical assignment or work-start evidence.',
                'Old open ownership measures issue age, not time assigned or inactivity.',
                'Concentration uses contributor-issue pairs; shared issues count once per participating contributor.',
                'Monthly series contains observed activity months only; absent months are not proof of inactivity.',
                'Date-only boundaries mean midnight UTC; use a full timestamp to include an entire ending day.',
                'No-ID events remain records; their uniqueness cannot be guaranteed.',
                'Equal-timestamp first responders share credit; response cohorts count each issue once.']}



def analyze_contributors(issues, *, response_target_hours=24, quiet_days=30, **options):
    """Return base and health metrics; the dashboard's public entry point."""
    from contributor_health_metrics import enrich_contributor_report
    report = _analyze_base(issues, **options)
    return enrich_contributor_report(
        issues, report, response_target_hours=response_target_hours,
        quiet_days=quiet_days, bot_accounts=options.get('bot_accounts', ()),
    )
