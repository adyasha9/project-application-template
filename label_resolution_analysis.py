"""
Feature 1 - Label Resolution Analysis

Question: How long do issues with different labels take to get resolved,
and what share of them is still open?

Method: For every closed issue, resolution time = days between creation
and the final 'closed' event. Issues are grouped by label and the median
resolution time, open share and issue count are computed per label.

Optional input: --label <name> prints a detailed breakdown for one label.
"""

from typing import List, Dict
import statistics

import matplotlib.pyplot as plt

import config
from data_loader import DataLoader
from model import Issue, State


def get_resolution_days(issue: Issue):
    """
    Days between an issue's creation and its final 'closed' event.
    Returns None if the issue is open or a date is missing.
    """
    if issue.state != State.closed or issue.created_date is None:
        return None
    closed_dates = [e.event_date for e in issue.events
                    if e.event_type == 'closed' and e.event_date is not None]
    if not closed_dates:
        return None
    return (max(closed_dates) - issue.created_date).total_seconds() / 86400


class LabelResolutionAnalysis:

    def __init__(self, min_issues: int = 20, top_n: int = 15):
        # Optional --label parameter from the command line
        self.LABEL: str = config.get_parameter('label')
        self.min_issues = min_issues   # ignore labels with too few issues
        self.top_n = top_n             # number of labels shown in the chart

    def run(self):
        issues: List[Issue] = DataLoader().get_issues()
        stats = self.compute_label_stats(issues)

        if self.LABEL is not None:
            self.print_label_detail(self.LABEL, stats)
            return

        self.print_summary(stats)
        self.plot(stats)

    # ---------------- processing ----------------

    def compute_label_stats(self, issues: List[Issue]) -> Dict[str, dict]:
        """
        Groups issues by label and returns, per label:
        count, open, closed, median_days, mean_days.
        """
        grouped: Dict[str, dict] = {}
        for issue in issues:
            for label in issue.labels:
                entry = grouped.setdefault(label, {'count': 0, 'open': 0, 'closed': 0, 'days': []})
                entry['count'] += 1
                if issue.state == State.open:
                    entry['open'] += 1
                else:
                    entry['closed'] += 1
                    days = get_resolution_days(issue)
                    if days is not None:
                        entry['days'].append(days)

        stats = {}
        for label, entry in grouped.items():
            days = entry['days']
            stats[label] = {
                'count': entry['count'],
                'open': entry['open'],
                'closed': entry['closed'],
                'open_pct': 100 * entry['open'] / entry['count'],
                'median_days': statistics.median(days) if days else None,
                'mean_days': statistics.mean(days) if days else None,
                'resolved_with_date': len(days),
            }
        return stats

    def ranked_labels(self, stats: Dict[str, dict]) -> List[str]:
        """Labels with enough data, slowest median resolution first."""
        eligible = [l for l, s in stats.items()
                    if s['count'] >= self.min_issues and s['median_days'] is not None]
        eligible.sort(key=lambda l: stats[l]['median_days'], reverse=True)
        return eligible[:self.top_n]

    # ---------------- output ----------------

    def print_summary(self, stats: Dict[str, dict]):
        labels = self.ranked_labels(stats)
        print('\nQuestion: Which issue labels take the longest to resolve?\n')
        print(f'{"Label":<28}{"Issues":>8}{"Open %":>9}{"Median days":>14}')
        print('-' * 59)
        for l in labels:
            s = stats[l]
            print(f'{l:<28}{s["count"]:>8}{s["open_pct"]:>8.1f}%{s["median_days"]:>14.1f}')
        if labels:
            slow, fast = labels[0], labels[-1]
            print(f'\nFinding: "{slow}" issues take the longest (median '
                  f'{stats[slow]["median_days"]:.1f} days); "{fast}" are resolved fastest '
                  f'(median {stats[fast]["median_days"]:.1f} days).')
        print(f'(Only labels with at least {self.min_issues} issues are shown.)\n')

    def print_label_detail(self, label: str, stats: Dict[str, dict]):
        if label not in stats:
            print(f'\nLabel "{label}" was not found in the dataset.')
            common = sorted(stats, key=lambda l: stats[l]['count'], reverse=True)[:10]
            print('Some available labels: ' + ', '.join(common) + '\n')
            return
        s = stats[label]
        print(f'\nLabel: {label}')
        print(f'  Issues: {s["count"]} (open {s["open"]}, closed {s["closed"]}, {s["open_pct"]:.1f}% open)')
        if s['median_days'] is None:
            print('  No closed issues with a recorded closing date.\n')
        else:
            print(f'  Median resolution: {s["median_days"]:.1f} days')
            print(f'  Mean resolution:   {s["mean_days"]:.1f} days '
                  f'(based on {s["resolved_with_date"]} closed issues)\n')

    def plot(self, stats: Dict[str, dict]):
        labels = self.ranked_labels(stats)
        if not labels:
            print('Not enough data to plot.')
            return
        medians = [stats[l]['median_days'] for l in labels]
        fig, ax = plt.subplots(figsize=(12, 7))
        ax.barh(labels[::-1], medians[::-1], color='steelblue')
        ax.set_title(f'Median resolution time by label (labels with ≥{self.min_issues} issues)')
        ax.set_xlabel('Median days from creation to close')
        ax.set_ylabel('Label')
        plt.tight_layout()
        plt.show()


if __name__ == '__main__':
    LabelResolutionAnalysis().run()
