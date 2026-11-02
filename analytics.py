"""Normalize template exports and GitHub API records; calculate evidence-based metrics."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import median
import math

SEVERITY = {'critical': {'critical', 'severity:critical', 'severity: critical'},
            'major': {'major', 'severity:major', 'severity: major'},
            'minor': {'minor', 'severity:minor', 'severity: minor'}}
TYPES = {'bug': {'bug', 'kind/bug', 'type:bug', 'type: bug'},
         'task': {'task', 'kind/task', 'type:task', 'type: task'},
         'project': {'project', 'kind/project', 'type:project', 'type: project'},
         'release': {'kind/release', 'type:release', 'type: release'},
         'refactor': {'kind/refactor', 'type:refactor', 'type: refactor'},
         'feature': {'feature', 'kind/feature'},
         'enhancement': {'enhancement', 'kind/enhancement', 'type:enhancement', 'type: enhancement'},
         'question': {'question', 'kind/question'}}

def timestamp(value):
    if not isinstance(value, str): return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except ValueError: return None

def person(value):
    return value.get('login') if isinstance(value, dict) else value if isinstance(value, str) else None

def label(value):
    return value.get('name', '') if isinstance(value, dict) else str(value)

def classify(labels, mapping):
    keys = {x.lower().strip() for x in labels}
    hits = [name for name, aliases in mapping.items() if keys & aliases]
    return hits[0] if len(hits) == 1 else 'conflict' if hits else 'unknown'

def days(start, end):
    return round((end-start).total_seconds()/86400, 3) if start and end and end >= start else None

def normalize(records):
    if not isinstance(records, list): raise ValueError('Expected a JSON array of issue objects.')
    result, errors, seen = [], [], set()
    for index, raw in enumerate(records):
        if not isinstance(raw, dict): errors.append(f'Record {index+1}: not an object'); continue
        if 'pull_request' in raw: continue
        if any(raw.get(k) is not None and not isinstance(raw[k], list) for k in ('labels','events','assignees')):
            errors.append(f'Record {index+1}: labels, events and assignees must be arrays'); continue
        try: number = int(raw.get('number'))
        except (ValueError, TypeError, OverflowError): number = 0
        state = raw.get('state')
        if number <= 0 or state not in ('open', 'closed'):
            errors.append(f'Record {index+1}: invalid issue number or state'); continue
        url = raw.get('html_url') or raw.get('url') or ''
        # API URLs retain repository scope; exports without URLs are single-repository imports.
        key = (url.rsplit('/', 1)[0], number)
        if key in seen: errors.append(f'Record {index+1}: duplicate issue #{number}'); continue
        seen.add(key)
        labels = [label(x) for x in raw.get('labels') or []]
        events = []
        for e in raw.get('events') or []:
            if not isinstance(e, dict): continue
            events.append({'type': e.get('event_type') or e.get('event'),
                           'author': person(e.get('author') or e.get('actor') or e.get('user')),
                           'date': e.get('event_date') or e.get('created_at'),
                           'assignee': person(e.get('assignee')), 'comment': str(e.get('comment') or e.get('body') or ''),
                           'id': e.get('id')})
        # Exact duplicate event IDs are excluded; events without IDs remain observable records.
        event_ids, unique = set(), []
        for e in events:
            if e['id'] is not None and e['id'] in event_ids: continue
            if e['id'] is not None: event_ids.add(e['id'])
            unique.append(e)
        events = sorted(unique, key=lambda e: timestamp(e['date']) or datetime.min.replace(tzinfo=timezone.utc))
        created = raw.get('created_date') or raw.get('created_at')
        closed = raw.get('closed_at') or raw.get('closed_date')
        if state == 'closed' and not timestamp(closed):
            closures = [e['date'] for e in events if e['type'] == 'closed' and timestamp(e['date'])]
            closed = closures[-1] if closures else None
        if state == 'open': closed = None
        result.append({'key': len(result), 'number': number, 'url': url, 'title': str(raw.get('title') or '(untitled)'),
                       'body': str(raw.get('text') or raw.get('body') or ''), 'creator': person(raw.get('creator') or raw.get('user')) or 'unknown',
                       'state': state, 'labels': labels, 'type': classify(labels, TYPES), 'severity': classify(labels, SEVERITY),
                       'assignees': [p for p in (person(x) for x in raw.get('assignees') or []) if p],
                       'created': created, 'updated': raw.get('updated_date') or raw.get('updated_at'), 'closed': closed,
                       'closure_reason': raw.get('state_reason'), 'events': events,
                       'timeline_complete': raw.get('timeline_complete') is True})
    return result, errors

def enrich(issue, observed):
    item = {k:v for k,v in issue.items() if k not in ('body', 'events')}
    created = timestamp(issue['created'])
    item['age'] = days(created, timestamp(issue['closed']) if issue['state']=='closed' else observed)
    assignments = [timestamp(e['date']) for e in issue['events'] if e['type']=='assigned' and timestamp(e['date']) and created and timestamp(e['date']) >= created]
    item['assignment_days'] = days(created, min(assignments)) if assignments else None
    comments = [e for e in issue['events'] if e['type'] in ('commented', 'comment')]
    item['comments'] = len(comments)
    item['reopened'] = sum(e['type']=='reopened' for e in issue['events'])
    return item

def select(issues, observed, query):
    result = [enrich(i, observed) for i in issues]
    for field in ('state', 'type', 'severity'):
        if query.get(field):
            if field == 'type' and query[field] in TYPES:
                aliases = TYPES[query[field]]
                result = [i for i in result if {x.lower().strip() for x in i['labels']} & aliases]
            else: result = [i for i in result if i[field] == query[field]]
    if query.get('unassigned') == 'true': result = [i for i in result if not i['assignees']]
    if query.get('age_band'):
        bands = {'0–7d': (0,7), '8–30d': (7,30), '31–90d': (30,90), '90+d': (90,float('inf'))}
        band = query['age_band']
        if band == 'unknown': result = [i for i in result if i['state']=='open' and i['age'] is None]
        elif band in bands:
            lo, hi = bands[band]
            result = [i for i in result if i['state']=='open' and i['age'] is not None and (i['age'] >= lo if lo == 0 else i['age'] > lo) and i['age'] <= hi]
    if query.get('q'):
        q = query['q'].lower()
        result = [i for i in result if q in ' '.join([str(i['number']),i['title'], i['creator'], *i['assignees'], *i['labels']]).lower()]
    return result

def summary(items, issues, observed):
    ids = {i['key'] for i in items}
    raw = [i for i in issues if i['key'] in ids]
    opened = [i for i in items if i['state']=='open']
    assigned = [i['assignment_days'] for i in items if i['assignment_days'] is not None]
    closed = [i['age'] for i in items if i['state']=='closed' and i['age'] is not None]
    def stats(values):
        ordered = sorted(values)
        return {'median': round(median(values),2) if values else None, 'p90': ordered[max(0,math.ceil(len(ordered)*.9)-1)] if values else None, 'n': len(values)}
    aging = Counter()
    for i in opened:
        n = i['age']; aging['unknown' if n is None else '0–7d' if n <= 7 else '8–30d' if n <= 30 else '31–90d' if n <= 90 else '90+d'] += 1
    months = defaultdict(lambda: {'created':0,'closed':0})
    heat = Counter()
    people = defaultdict(lambda: {'reported':set(), 'assigned':set(), 'commented':set()})
    for i in raw:
        created, closure = timestamp(i['created']), timestamp(i['closed'])
        if created: months[created.strftime('%Y-%m')]['created'] += 1; heat[created.strftime('%Y-%m-%d')] += 1
        if closure: months[closure.strftime('%Y-%m')]['closed'] += 1
        people[i['creator']]['reported'].add(i['key'])
        for name in i['assignees']: people[name]['assigned'].add(i['key'])
        for e in i['events']:
            if e['type'] in ('commented','comment') and e['author']: people[e['author']]['commented'].add(i['key'])
    contributors = [{'name':name, **{k:len(v) for k,v in roles.items()}} for name,roles in people.items()]
    contributors.sort(key=lambda p: (-p['commented'], -p['assigned'], p['name']))
    return {'total':len(items),'open':len(opened),'closed':len(items)-len(opened),
            'unassigned':sum(not i['assignees'] for i in opened),
            'critical_unassigned':sum(i['severity']=='critical' and not i['assignees'] for i in opened),
            'assignment':stats(assigned),'closure':stats(closed),
            'bugs':sum('kind/bug' in i['labels'] or 'bug' in i['labels'] for i in items),
            'type_labels':{name:sum(bool({x.lower().strip() for x in i['labels']} & aliases) for i in items) for name,aliases in TYPES.items()},
            'severity_sources':dict(Counter(i.get('severity_source','unclassified') for i in items)),
            'severity':dict(Counter(i['severity'] for i in items)), 'types':dict(Counter(i['type'] for i in items)),
            'aging':dict(aging), 'months':dict(sorted(months.items())), 'heat':dict(sorted(heat.items())),
            'contributors':contributors[:30], 'timeline_complete':sum(i['timeline_complete'] for i in raw),
            'missing_created':sum(timestamp(i['created']) is None for i in raw),
            'missing_closed':sum(i['state']=='closed' and timestamp(i['closed']) is None for i in raw)}
