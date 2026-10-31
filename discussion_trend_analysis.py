"""
Discussion trends analysis.

Buckets issues by month, counts how many issues were created and how many
comments were posted in each month, and plots both as a line chart.

Optional date filter (simple comparison on Issue.created_date):
    --start-date YYYY-MM-DD   keep issues created on/after this date
    --end-date   YYYY-MM-DD   keep issues created on/before this date
"""

from datetime import datetime, timezone
from typing import List, Optional

import matplotlib.pyplot as plt
import pandas as pd
from dateutil import parser

import config
from data_loader import DataLoader
from model import Issue

COMMENT_EVENT_TYPE = 'commented'
OUTPUT_PNG = 'discussion_trends.png'
OUTPUT_CSV = 'discussion_trends.csv'


class DiscussionTrends:
    """
    Implements the discussion trends analysis and plots the result.
    """

    def __init__(self):
        self.start_date: Optional[datetime] = self._parse_date(config.get_parameter('start_date'))
        self.end_date: Optional[datetime] = self._parse_date(config.get_parameter('end_date'))

    @staticmethod
    def _parse_date(value) -> Optional[datetime]:
        """Parses a date string from the command line; returns None if not given."""
        if value is None:
            return None
        parsed = parser.parse(str(value))
        # Compare in UTC so naive and timezone-aware dates can be mixed safely
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    def _filter_issues(self, issues: List[Issue]) -> List[Issue]:
        """Simple comparison on created_date. Issues without a date are skipped."""
        kept = []
        for issue in issues:
            if issue.created_date is None:
                continue
            created = self._as_utc(issue.created_date)
            if self.start_date is not None and created < self.start_date:
                continue
            if self.end_date is not None and created > self.end_date:
                continue
            kept.append(issue)
        return kept

    def compute_monthly_counts(self, issues: List[Issue]) -> pd.DataFrame:
        """
        Returns a DataFrame indexed by month with columns 'issues' and 'comments'.
        Issues are bucketed by created_date, comments by the comment's event_date.
        """
        issue_months = []
        comment_months = []
        for issue in self._filter_issues(issues):
            issue_months.append(self._month(issue.created_date))
            for event in issue.events:
                if event.event_type == COMMENT_EVENT_TYPE and event.event_date is not None:
                    comment_months.append(self._month(event.event_date))

        issues_per_month = pd.Series(issue_months, dtype='object').value_counts()
        comments_per_month = pd.Series(comment_months, dtype='object').value_counts()

        df = pd.DataFrame({'issues': issues_per_month, 'comments': comments_per_month})
        if df.empty:
            return df
        df = df.fillna(0).astype(int)
        # Fill in months with no activity so the line chart has no gaps
        all_months = pd.period_range(df.index.min(), df.index.max(), freq='M')
        return df.reindex(all_months, fill_value=0)

    @staticmethod
    def _month(dt: datetime) -> pd.Period:
        return pd.Period(year=dt.year, month=dt.month, freq='M')

    @staticmethod
    def _summary(df: pd.DataFrame) -> str:
        """Short text summary of the monthly counts."""
        total_issues = int(df['issues'].sum())
        total_comments = int(df['comments'].sum())
        busiest_issues = df['issues'].idxmax()
        busiest_comments = df['comments'].idxmax()
        avg = total_comments / total_issues if total_issues else 0
        return (
            f'Discussion trends: {total_issues} issues, {total_comments} comments '
            f'over {len(df)} months.\n'
            f'  Most issues created:   {busiest_issues} ({int(df["issues"].max())})\n'
            f'  Most comments posted:  {busiest_comments} ({int(df["comments"].max())})\n'
            f'  Average comments per issue: {avg:.1f}'
        )

    def run(self):
        issues: List[Issue] = DataLoader().get_issues()
        df = self.compute_monthly_counts(issues)

        if df.empty:
            print('No issues found for the given date range.')
            return

        print('\n' + self._summary(df) + '\n')
        print(df.to_string())

        # Save the monthly table as CSV
        df.to_csv(OUTPUT_CSV, index_label='month')

        # Comments per issue (discussion intensity); months without issues -> 0
        ratio = (df['comments'] / df['issues'].where(df['issues'] > 0)).fillna(0)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True,
                                       gridspec_kw={'height_ratios': [3, 2]})
        months = df.index.to_timestamp()

        ax1.plot(months, df['issues'], marker='o', label='Issues created')
        ax1.plot(months, df['comments'], marker='o', label='Comments posted')
        ax1.set_title('Discussion trends per month')
        ax1.set_ylabel('Count')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        ax2.plot(months, ratio, marker='o', color='tab:green')
        ax2.set_title('Comments per issue created (same month)')
        ax2.set_xlabel('Month')
        ax2.set_ylabel('Comments / issue')
        ax2.grid(True, alpha=0.3)

        fig.tight_layout()
        # Save the chart as an image
        fig.savefig(OUTPUT_PNG, dpi=150)
        print(f'\nSaved chart to {OUTPUT_PNG} and table to {OUTPUT_CSV}.')
        plt.show()


if __name__ == '__main__':
    DiscussionTrends().run()