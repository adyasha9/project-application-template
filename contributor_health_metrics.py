"""Response, assignment, discussion and snapshot backlog health.

Targets are review policies, not contractual service levels. Missing timeline
history prevents claims about true unanswered issues or first assignments.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import json
import math
from statistics import median
from urllib.parse import urlsplit

from analytics import timestamp
from contributor_metrics import COMMENT_EVENTS, DEFAULT_BOTS, TRIAGE_EVENTS


def _login(value):
    if not isinstance(value, str) or not value.strip():
        return None
    name = value.strip().casefold()
    return None if name == 'unknown' else name


def _identity(issue):
    url = urlsplit(issue.get('url') or '')
    parts = url.path.strip('/').split('/')
    if url.hostname == 'api.github.com' and parts[0] == 'repos':
        parts = parts[1:]
    if url.hostname in ('github.com', 'api.github.com') and len(parts) >= 2:
        return f"https://github.com/{parts[0].casefold()}/{parts[1].casefold()}/issues/{issue['number']}"
    return f"{issue.get('url') or 'import'}#{issue['number']}"


def _distribution(values, unit):
    ordered = sorted(values)
    return {'samples': len(ordered),
            f'median_{unit}': round(median(ordered), 2) if ordered else None,
            f'p90_{unit}': round(ordered[math.ceil(.9 * len(ordered)) - 1], 2) if ordered else None}


def enrich_contributor_report(issues, report, *, response_target_hours=24,
                              quiet_days=30, bot_accounts=()):
    """Return a separate report with richer metrics and role-specific evidence."""
    if (isinstance(response_target_hours, bool)
            or not isinstance(response_target_hours, (int, float))
            or not math.isfinite(response_target_hours) or response_target_hours <= 0):
        raise ValueError('response_target_hours must be positive and finite')
    if isinstance(quiet_days, bool) or not isinstance(quiet_days, int) or quiet_days < 0:
        raise ValueError('quiet_days must be a nonnegative integer')
    result = deepcopy(report)
    scope = result['scope']
    start, end = timestamp(scope['since_inclusive']), timestamp(scope['until_inclusive'])
    observed = timestamp(scope['snapshot_reference'])
    bots = DEFAULT_BOTS | frozenset(x.strip().casefold() for x in bot_accounts if isinstance(x, str))

    def eligible(name):
        return bool(name) and (scope['include_bots'] or not (name.endswith('[bot]') or name in bots))

    def in_window(value):
        return value is not None and (start is None or value >= start) and (end is None or value <= end)

    profiles = defaultdict(lambda: {'first_seen': None, 'co_commenters': set(),
        'sole_external_commenter_issues': set(), 'quiet_open_assignments': set(),
        'open_age_days': [], 'triage_actions': Counter()})
    targets = {key: [] for key in ('recorded_within_target', 'recorded_after_target',
                                  'no_recorded_response_mature', 'still_in_observation')}
    assignment_delays, quiet_open, quiet_unassigned, no_activity_reference = [], [], [], []
    assignment_cohort = assignments_without_target = 0
    seen_issues = set()

    def observe(name, when):
        if eligible(name) and when is not None:
            first = profiles[name]['first_seen']
            if first is None or when < first:
                profiles[name]['first_seen'] = when

    for issue in issues:
        key = _identity(issue)
        if key in seen_issues:
            continue
        seen_issues.add(key)
        created, reporter = timestamp(issue.get('created')), _login(issue.get('creator'))
        if created and (end is None or created <= end):
            observe(reporter, created)
        events, seen_events = [], set()
        for event in issue.get('events', []):
            event_id = event.get('id')
            if event_id is not None:
                token = json.dumps(event_id, sort_keys=True)
                if token in seen_events:
                    continue
                seen_events.add(token)
            when = timestamp(event.get('date'))
            if when is None or (created and when < created) or (observed and when > observed):
                continue
            events.append((when, _login(event.get('author')), event))
        responses, assignment_dates = [], []
        commenters, external_commenters = set(), set()
        last_participation = created
        for when, actor, event in events:
            kind = event.get('type')
            if kind == 'assigned' and (end is None or when <= end):
                assignment_dates.append(when)
                assignments_without_target += not bool(event.get('assignee'))
            if kind not in COMMENT_EVENTS | TRIAGE_EVENTS or not eligible(actor):
                continue
            if last_participation is None or when > last_participation:
                last_participation = when
            if end is None or when <= end:
                observe(actor, when)
            if kind in COMMENT_EVENTS and created and reporter and actor != reporter and (end is None or when <= end):
                responses.append(when)
            if not in_window(when):
                continue
            if kind in COMMENT_EVENTS:
                commenters.add(actor)
                if reporter and actor != reporter:
                    external_commenters.add(actor)
            else:
                profiles[actor]['triage_actions'][kind] += 1
        for actor in commenters:
            profiles[actor]['co_commenters'].update(commenters - {actor})
        if len(external_commenters) == 1:
            profiles[next(iter(external_commenters))]['sole_external_commenter_issues'].add(key)
        if in_window(created):
            assignment_cohort += 1
            if assignment_dates:
                assignment_delays.append((min(assignment_dates) - created).total_seconds()/3600)
            if eligible(reporter):
                if responses:
                    delay = (min(responses) - created).total_seconds()/3600
                    bucket = 'recorded_within_target' if delay <= response_target_hours else 'recorded_after_target'
                elif end and (end - created).total_seconds() >= response_target_hours * 3600:
                    bucket = 'no_recorded_response_mature'
                else:
                    bucket = 'still_in_observation'
                targets[bucket].append(key)
        if issue['state'] != 'open':
            continue
        owners = {_login(x) for x in issue.get('assignees', [])} - {None}
        for owner in owners:
            if eligible(owner) and created and observed and observed >= created:
                profiles[owner]['open_age_days'].append((observed-created).total_seconds()/86400)
        if last_participation is None or observed is None:
            no_activity_reference.append(key)
        elif (observed-last_participation).total_seconds()/86400 >= quiet_days:
            quiet_open.append(key)
            if not owners:
                quiet_unassigned.append(key)
            for owner in owners:
                if eligible(owner):
                    profiles[owner]['quiet_open_assignments'].add(key)
    for contributor in result['contributors']:
        profile = profiles[contributor['login']]
        first = profile['first_seen']
        contributor['health'] = {
            'first_observed_participation': first.isoformat() if first else None,
            'first_observed_in_selected_window': in_window(first) if start and first else None,
            'recorded_participation_before_window': first < start if start and first else None,
            'distinct_co_commenters': len(profile['co_commenters']),
            'sole_external_commenter_issues': len(profile['sole_external_commenter_issues']),
            'quiet_open_assignments': len(profile['quiet_open_assignments']),
            'open_assignment_age': _distribution(profile['open_age_days'], 'days'),
            'triage_actions': dict(sorted(profile['triage_actions'].items())),
        }
        contributor['evidence'].update({key: sorted(profile[key]) for key in
            ('sole_external_commenter_issues', 'quiet_open_assignments')})
    result['team']['health'] = {
        'response_target': {'target_hours': response_target_hours,
            'cohort': sum(map(len, targets.values())), **{key: len(values) for key, values in targets.items()}},
        'first_observed_assignment': {'creation_cohort': assignment_cohort,
            **_distribution(assignment_delays, 'hours'),
            'without_observed_assignment': assignment_cohort-len(assignment_delays),
            'observed_assignment_events_missing_target': assignments_without_target},
        'quiet_open_backlog': {'threshold_days': quiet_days, 'issues': len(quiet_open),
            'without_current_owner': len(quiet_unassigned), 'without_activity_reference': len(no_activity_reference)},
    }
    result['evidence'].update({'response_target': {key: sorted(values) for key, values in targets.items()},
        'quiet_open_issues': sorted(quiet_open), 'quiet_open_without_owner': sorted(quiet_unassigned)})
    result['interpretation'].extend([
        'Targets are observational review policies, not contractual SLA measurements.',
        'Still-in-observation issues have not had a complete target interval by the period end.',
        'First observed assignment is not necessarily the first actual assignment or work start.',
        'Quiet backlog uses snapshot-wide recorded eligible participation, falling back to creation.',
        'First observed participation is not a real join date; earlier history may be absent.',
        'Co-commenters shared a discussion; direct collaboration is not established.',
        'Sole external commenter counts apply only to collected comments in the selected window.',
    ])
    return result
