"""CSV and PNG output only; calculations belong in contributor_metrics.py."""
import csv
import io
import json
from pathlib import Path

OUTPUT_CSV = 'contributor_activity.csv'
OUTPUT_PNG = 'contributor_activity.png'


def _csv_bytes(report):
    fields = ['login', 'issues_reported', 'issues_commented_on', 'comments', 'issues_triaged',
        'triage_events', 'distinct_issues_touched', 'active_days', 'active_months', 'last_recorded_activity',
        'current_open_assignments', 'old_open_assignments', 'first_response_issues', 'response_samples',
        'response_median_hours', 'response_p90_hours', 'first_observed_participation',
        'first_observed_in_selected_window', 'recorded_participation_before_window',
        'distinct_co_commenters', 'sole_external_commenter_issues', 'quiet_open_assignments',
        'open_age_samples', 'open_age_median_days', 'open_age_p90_days', 'triage_actions_json',
        'snapshot_reference', 'activity_since', 'activity_until', 'include_bots', 'old_issue_threshold_days',
        'quiet_days', 'response_target_hours', 'timeline_completeness_unconfirmed_issues']
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    scope, team = report['scope'], report['team']['health']
    for person in report['contributors']:
        login = person['login']
        if login.lstrip().startswith(('=', '+', '-', '@')):
            login = "'" + login
        ownership, response, health = person['snapshot_ownership'], person['first_external_responses'], person['health']
        writer.writerow({'login': login, **person['activity'],
            'current_open_assignments': ownership['open_issues'], 'old_open_assignments': ownership['old_open_issues'],
            'first_response_issues': response['issues'], 'response_samples': response['samples'],
            'response_median_hours': response['median_hours'], 'response_p90_hours': response['p90_hours'],
            **{key: health[key] for key in ('first_observed_participation', 'first_observed_in_selected_window',
                'recorded_participation_before_window', 'distinct_co_commenters',
                'sole_external_commenter_issues', 'quiet_open_assignments')},
            'open_age_samples': health['open_assignment_age']['samples'],
            'open_age_median_days': health['open_assignment_age']['median_days'],
            'open_age_p90_days': health['open_assignment_age']['p90_days'],
            'triage_actions_json': json.dumps(health['triage_actions'], sort_keys=True),
            'snapshot_reference': scope['snapshot_reference'], 'activity_since': scope['since_inclusive'],
            'activity_until': scope['until_inclusive'], 'include_bots': scope['include_bots'],
            'old_issue_threshold_days': scope['stale_days'],
            'quiet_days': team['quiet_open_backlog']['threshold_days'],
            'response_target_hours': team['response_target']['target_hours'],
            'timeline_completeness_unconfirmed_issues': report['data_quality']['issues_without_confirmed_timeline']})
    return output.getvalue().encode('utf-8-sig')


def _png_bytes(report):
    """Render a shareable briefing with explicit scope, direct counts and units."""
    try:
        from matplotlib.figure import Figure
        from matplotlib.patches import FancyBboxPatch
        from matplotlib.ticker import MaxNLocator, FuncFormatter
    except ImportError as exc:
        raise RuntimeError('PNG export requires matplotlib: install requirements.txt or use --csv only.') from exc
    from datetime import datetime
    import textwrap

    ink, muted, blue = '#1d3047', '#62748a', '#2479c4'
    light, line = '#c8deef', '#e6edf4'
    scope, team = report['scope'], report['team']
    health, response = team['health'], team['recorded_external_response']
    backlog, target = health['quiet_open_backlog'], health['response_target']
    figure = Figure(figsize=(16, 12), facecolor='#f3f6fa')

    def text(x, y, content, size=10, color=ink, weight='normal', **options):
        return figure.text(x, y, content, fontsize=size, color=color, weight=weight,
                           fontfamily='DejaVu Sans', **options)

    def box(x, y, width, height, color='white', border='#e0e8f1'):
        patch = FancyBboxPatch((x, y), width, height, boxstyle='round,pad=0.006,rounding_size=0.012',
                              transform=figure.transFigure, linewidth=.8, edgecolor=border,
                              facecolor=color, zorder=-1)
        figure.add_artist(patch)

    def short_date(value, fallback='Unavailable'):
        if not value: return fallback
        try: return datetime.fromisoformat(value.replace('Z', '+00:00')).strftime('%d %b %Y')
        except (ValueError, TypeError): return 'Unavailable'

    def duration(hours):
        if hours is None: return 'Unavailable'
        if hours >= 48: return f'{hours / 24:,.1f} days'
        return f'{hours:,.1f} hours'

    def style(axis, orientation='y'):
        axis.set_facecolor('white')
        for spine in axis.spines.values(): spine.set_visible(False)
        axis.tick_params(axis='both', length=0, labelsize=9, colors=muted, pad=7)
        axis.set_axisbelow(True)
        axis.grid(axis=orientation, color=line, linewidth=.8)
        numeric = axis.yaxis if orientation == 'y' else axis.xaxis
        numeric.set_major_locator(MaxNLocator(integer=True, nbins=4))
        numeric.set_major_formatter(FuncFormatter(lambda n, _: f'{n:,.0f}'))

    def card(x, label, value, note, primary=False):
        box(x, .79, .215, .105, '#1767ae' if primary else 'white', '#1767ae' if primary else '#e0e8f1')
        color, secondary = ('white', '#daebfa') if primary else (ink, muted)
        text(x+.014, .872, label.upper(), 8.5, secondary, 'bold')
        text(x+.014, .826, value, 27, color, 'bold')
        text(x+.014, .801, note, 8.2, secondary)

    text(.045, .961, 'CONTRIBUTOR INTELLIGENCE', 9, blue, 'bold')
    text(.045, .924, 'Participation, response & backlog health', 25, ink, 'bold')
    text(.045, .910, f"ACTIVITY  {short_date(scope['since_inclusive'], 'Earliest recorded')} – {short_date(scope['until_inclusive'])}  ·  UTC", 9, muted)
    text(.955, .959, f"SNAPSHOT  {short_date(scope['snapshot_reference'])}", 9, muted, ha='right')
    bot_note = 'Recognized bots included' if scope['include_bots'] else 'Recognized bots excluded'
    text(.955, .940, bot_note, 9, muted, ha='right')
    card(.045, 'Contributors represented', f"{team['contributors']:,}", 'Activity participants + current owners', True)
    card(.280, 'Median first response', duration(response['median_hours']), f"{response['samples']:,} observed external responses")
    card(.515, '90th-percentile response', duration(response['p90_hours']), '90% of observed times fall at or below this')
    card(.750, 'Quiet + no current owner', f"{backlog['without_current_owner']:,}", f"Of {backlog['issues']:,} quiet open issues · snapshot")

    # Top row: selected-period activity and snapshot-wide ownership.
    box(.045, .445, .44, .305)
    box(.515, .445, .44, .305)
    text(.061, .726, '01  /  PARTICIPATION OVER TIME', 9, muted, 'bold')
    text(.061, .701, 'How many people are participating?', 14, ink, 'bold')
    text(.061, .681, 'Distinct active contributors · last 12 observed months', 9, muted)
    activity = figure.add_axes([.085, .522, .375, .128])
    style(activity)
    months = list(report['monthly'].items())[-12:]
    if months:
        values = [v['active_contributors'] for _, v in months]
        activity.bar(range(len(months)), values, width=.65, color=blue, zorder=3)
        labels = [datetime.strptime(m, '%Y-%m').strftime('%b %y') for m, _ in months]
        activity.set_xticks(range(len(months)), labels, rotation=40, ha='right')
        activity.set_ylim(0, max(1, max(values))*1.24)
        for index, value in enumerate(values):
            activity.text(index, value+max(1,max(values))*.025, f'{value:,}', ha='center', fontsize=8, color=ink)
    else:
        activity.set_xticks([]);activity.set_yticks([])
        activity.text(.5, .5, 'No eligible recorded activity', transform=activity.transAxes, ha='center', color=muted)
    text(.061, .461, 'Observed months only; a boundary month may be partial.', 8.5, muted)

    text(.531, .726, '02  /  CURRENT OWNERSHIP', 9, muted, 'bold')
    text(.531, .701, 'Where is open work concentrated?', 14, ink, 'bold')
    selected = report.get('contributor_filter')
    label = 'Selected contributor' if selected else 'Up to 10 contributors with the most open assignments'
    text(.531, .681, label, 9, muted)
    ownership = figure.add_axes([.635, .505, .295, .145])
    style(ownership, 'x')
    owners = sorted((p for p in report['contributors'] if p['snapshot_ownership']['open_issues']),
                    key=lambda p: (-p['snapshot_ownership']['open_issues'], p['login']))[:10]
    if owners:
        old = [p['snapshot_ownership']['old_open_issues'] for p in owners]
        total = [p['snapshot_ownership']['open_issues'] for p in owners]
        newer = [n-aged for n, aged in zip(total,old)]
        ownership.barh(range(len(owners)), newer, color=light, height=.58, zorder=3)
        ownership.barh(range(len(owners)), old, left=newer, color=blue, height=.58, zorder=3)
        ownership.set_yticks(range(len(owners)), [textwrap.shorten(p['login'], width=21, placeholder='…') for p in owners])
        ownership.invert_yaxis();ownership.set_xlim(0,max(total)*1.17)
        for index, count in enumerate(total):
            ownership.text(count+max(total)*.025,index,f'{count:,}',va='center',fontsize=9,color=ink,weight='bold')
    else:
        ownership.set_xticks([]);ownership.set_yticks([])
        ownership.text(.5,.5,'No eligible current open assignments',ha='center',transform=ownership.transAxes,color=muted)
    text(.531,.477,'■',10,blue)
    text(.543,.477,f"Issue age {scope['stale_days']}+ days",8.5,muted)
    text(.705,.477,'■',10,light)
    text(.717,.477,'Younger or age unavailable',8.5,muted)
    text(.531,.461,'Assignments are not fixes completed or time spent working.',8.5,muted)

    # Bottom row: denominator-labeled response outcomes and quiet backlog share.
    box(.045,.105,.44,.305)
    box(.515,.105,.44,.305)
    text(.061,.386,'03  /  OBSERVED RESPONSE COVERAGE',9,muted,'bold')
    text(.061,.361,f"A {target['target_hours']:g}-hour response review target",14,ink,'bold')
    text(.061,.341,f"Cohort: {target['cohort']:,} issues created in the activity period",9,muted)
    response_axis = figure.add_axes([.218,.178,.235,.130])
    style(response_axis,'x')
    keys=['recorded_within_target','recorded_after_target','no_recorded_response_mature','still_in_observation']
    labels=['Within target','After target','No response recorded¹','Still observing²']
    values=[target[k] for k in keys]
    response_axis.barh(range(4),values,color=['#4d9980','#c4a464','#ae7d84','#b2bdcb'],height=.55,zorder=3)
    response_axis.set_yticks(range(4),labels)
    response_axis.invert_yaxis(); response_axis.set_xlim(0,max(1,max(values))*1.60)
    for index,value in enumerate(values):
        share=f"{value/target['cohort']:.1%}" if target['cohort'] else 'n/a'
        response_axis.text(value+max(1,max(values))*.025,index,f'{value:,}  ({share})',va='center',fontsize=8.5,color=ink)
    text(.061,.138,'¹ Full target interval elapsed; incomplete history may hide a response.',8,muted)
    text(.061,.121,'² Not yet observed for a full target interval. A target is not an SLA.',8,muted)

    text(.531,.386,'04  /  QUIET OPEN BACKLOG',9,muted,'bold')
    text(.531,.361,'Which quiet issues have no owner?',14,ink,'bold')
    text(.531,.341,f"No recorded eligible participation for {backlog['threshold_days']}+ days · snapshot",9,muted)
    quiet = figure.add_axes([.537,.162,.140,.153])
    owned=backlog['issues']-backlog['without_current_owner']
    unowned=backlog['without_current_owner']
    if backlog['issues']:
        quiet.pie([unowned,owned],colors=[blue,light],startangle=90,counterclock=False,
                  wedgeprops={'width':.22,'edgecolor':'white','linewidth':2})
    else:
        quiet.pie([1],colors=[line],wedgeprops={'width':.22,'edgecolor':'white'})
    quiet.text(0,.08,f"{backlog['issues']:,}",ha='center',va='center',fontsize=28,weight='bold',color=ink)
    quiet.text(0,-.27,'quiet issues',ha='center',fontsize=9,color=muted)
    quiet.set_aspect('equal')
    def quiet_row(y,label,count,color):
        share=f"{count/backlog['issues']:.1%}" if backlog['issues'] else 'n/a'
        text(.705,y,'■',11,color)
        text(.721,y,label,10,muted)
        text(.721,y-.027,f'{count:,}  ·  {share}',19,ink,'bold')
    quiet_row(.287,'No current owner',unowned,blue)
    quiet_row(.215,'Has a current owner',owned,light)
    text(.531,.138,'Quiet time falls back to issue creation if no participation is recorded.',8,muted)
    text(.531,.121,f"Missing activity reference: {backlog['without_activity_reference']:,} issues.",8,muted)

    unverified=report['data_quality']['issues_without_confirmed_timeline']
    text(.045,.070,f"EVIDENCE NOTE  Timeline completeness unconfirmed for {unverified:,} of {team['issues_analyzed']:,} issues.",9,muted,'bold')
    text(.045,.051,'Response timings exclude unobserved responses. Participation does not establish productivity, fixes, or maintainer status.',8.5,muted)
    text(.045,.032,'Period charts follow the selected activity window; ownership and quiet backlog use the snapshot. '+('Contributor rows filtered; team metrics retain the full cohort.' if selected else bot_note+'.'),8.5,muted)
    output=io.BytesIO()
    figure.savefig(output,format='png',dpi=180)
    return output.getvalue()


def export_report(report, *, csv_path=None, png_path=None):
    """Render first, then exclusively create outputs. Writes are not a multi-file transaction."""
    requests = []
    if csv_path is not None: requests.append((Path(csv_path), _csv_bytes))
    if png_path is not None: requests.append((Path(png_path), _png_bytes))
    paths = [path.resolve() for path, _ in requests]
    if len(paths) != len(set(paths)):
        raise ValueError('CSV and PNG destinations must be different')
    for path in paths:
        if path.exists(): raise FileExistsError(f'Output already exists: {path}')
        if not path.parent.is_dir(): raise FileNotFoundError(f'Output directory does not exist: {path.parent}')
    rendered = [(path, render(report)) for path, render in requests]
    written = []
    for path, content in rendered:
        with path.open('xb') as stream:
            stream.write(content)
        written.append(str(path))
    return written
