"""Coordinate contributor analysis, template loading and optional CSV/PNG exports.

Metric definitions: contributor_metrics.py and contributor_health_metrics.py.
Output formatting: contributor_activity_exports.py. The re-export below preserves
existing dashboard imports. No optional plotting/template imports run on import.
"""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path

from analytics import normalize, timestamp
from contributor_metrics import analyze_contributors
from contributor_activity_exports import OUTPUT_CSV, OUTPUT_PNG, export_report


class ContributorActivityAnalysis:
    """Load data, calculate results, and coordinate exports; no metric formulas."""
    def __init__(self, data_path=None, **options):
        config = None
        if data_path is None:
            try:
                import config
            except ModuleNotFoundError as exc:
                if exc.name != 'config': raise
                raise ValueError('Provide --data or use the original template configuration.') from exc
        def setting(name, default=None):
            if options.get(name) is not None: return options[name]
            value = config.get_parameter(name) if config else None
            return default if value is None else value
        self.data_path = Path(data_path) if data_path else None
        self.start_date, self.end_date = setting('start_date'), setting('end_date')
        self.observed_at = setting('observed_at')
        self.include_bots, self.bot_accounts = setting('include_bots', False), setting('bot_accounts', ())
        self.stale_days = setting('stale_days', 90)
        self.response_target_hours, self.quiet_days = setting('response_target_hours', 24), setting('quiet_days', 30)
        self.user, self.output_dir = setting('user'), Path(setting('output_dir', '.'))
        if not isinstance(self.include_bots, bool): raise ValueError('include_bots must be true or false')

    @staticmethod
    def _iso(value):
        return value.isoformat() if isinstance(value, datetime) else value

    def _load_issues(self):
        if self.data_path:
            records = json.loads(self.data_path.read_text(encoding='utf-8'))
        else:
            from data_loader import DataLoader
            records = []
            for issue in DataLoader().get_issues():
                records.append({'number': issue.number, 'url': issue.url, 'creator': issue.creator,
                    'title': issue.title, 'text': issue.text, 'labels': issue.labels,
                    'state': getattr(issue.state, 'value', issue.state), 'assignees': issue.assignees,
                    'created_date': self._iso(issue.created_date), 'updated_date': self._iso(issue.updated_date),
                    'timeline_complete': False, 'events': [{'event_type': e.event_type, 'author': e.author,
                    'event_date': self._iso(e.event_date), 'label': e.label, 'comment': e.comment}
                    for e in issue.events or []]})
        issues, errors = normalize(records)
        if records and not issues: raise ValueError('No valid issues to analyze: ' + '; '.join(errors[:3]))
        return issues, {'accepted': len(issues), 'rejected': len(errors), 'errors': errors}

    def _period(self, issues):
        def parse(value, name):
            if value is None: return None
            parsed = timestamp(value)
            if parsed is None: raise ValueError(f'{name} must be an ISO-8601 date or timestamp')
            return parsed
        start, end = parse(self.start_date, 'start_date'), parse(self.end_date, 'end_date')
        if isinstance(self.end_date, str) and len(self.end_date) == 10:
            end += timedelta(days=1)-timedelta(microseconds=1)
            reference = parse(self.observed_at, 'observed_at')
            if reference is None:
                dates = [timestamp(i.get(k)) for i in issues for k in ('created', 'updated', 'closed')]
                dates.extend(timestamp(e.get('date')) for i in issues for e in i.get('events', []))
                reference = max((d for d in dates if d), default=None)
            if reference and reference.date() == end.date(): end = min(end, reference)
        return self._iso(start), self._iso(end)

    def build_report(self):
        issues, imported = self._load_issues()
        since, until = self._period(issues)
        report = analyze_contributors(issues, since=since, until=until, observed_at=self.observed_at,
            include_bots=self.include_bots, bot_accounts=self.bot_accounts, stale_days=self.stale_days,
            response_target_hours=self.response_target_hours, quiet_days=self.quiet_days)
        report['import'] = imported
        if self.user:
            login = str(self.user).strip().casefold()
            rows = [p for p in report['contributors'] if p['login'] == login]
            if not rows: raise ValueError(f'No eligible contributor found: {self.user}')
            report['contributors'], report['contributor_filter'] = rows, login
        return report

    def run(self, *, csv_path=OUTPUT_CSV, png_path=OUTPUT_PNG, print_summary=True):
        report = self.build_report()
        written = export_report(report,
            csv_path=self.output_dir / csv_path if csv_path is not None else None,
            png_path=self.output_dir / png_path if png_path is not None else None)
        if print_summary:
            team = report['team']
            print(f"Analyzed {team['issues_analyzed']:,} issues; {team['contributors']:,} eligible contributors.")
            print(f"Response observations: {team['recorded_external_response']['samples']:,}; rejected records: {report['import']['rejected']:,}.")
            print('Participation is not productivity. Timeline completeness is unverified.')
            for path in written: print(f'Saved: {path}')
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--since', '--start-date', dest='start_date')
    parser.add_argument('--until', '--end-date', dest='end_date', help='Date-only end dates include that entire day, capped at the reference.')
    parser.add_argument('--observed-at')
    parser.add_argument('--include-bots', action='store_true')
    parser.add_argument('--bot', action='append', default=[])
    parser.add_argument('--stale-days', type=int, default=90)
    parser.add_argument('--response-target-hours', type=float, default=24)
    parser.add_argument('--quiet-days', type=int, default=30)
    parser.add_argument('--user')
    parser.add_argument('--output-dir', type=Path, default=Path('.'))
    parser.add_argument('--csv', type=Path, nargs='?', const=Path(OUTPUT_CSV))
    parser.add_argument('--png', type=Path, nargs='?', const=Path(OUTPUT_PNG))
    parser.add_argument('--summary', action='store_true', help='Print a concise summary instead of the full JSON report')
    args = parser.parse_args(argv)
    options = vars(args).copy()
    data = options.pop('data')
    csv_path, png_path, summary = (options.pop(k) for k in ('csv', 'png', 'summary'))
    options['bot_accounts'] = tuple(options.pop('bot'))
    try:
        report = ContributorActivityAnalysis(data, **options).run(
            csv_path=csv_path, png_path=png_path, print_summary=summary)
    except (OSError, ValueError, TypeError, AttributeError, ImportError, RuntimeError) as exc:
        parser.error(str(exc))
    if not summary: print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
