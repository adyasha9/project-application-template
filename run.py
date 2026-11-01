"""
Application entry point.

Features:
    0: Original example analysis
    1: Reserved for the first project analysis
    2: Contributor activity analysis
    3: Discussion trends analysis

Contributor activity generates CSV and PNG reports by default.
"""

import argparse

import config


def parse_args(argv=None):
    """Parse feature selection and optional analysis settings."""
    ap = argparse.ArgumentParser(
        prog="run.py",
        description="Run GitHub issue analyses.",
    )

    ap.add_argument(
        "--feature", "-f",
        type=int,
        choices=(0, 1, 2, 3),
        required=True,
        help="0: example; 1: reserved; 2: contributors; 3: discussion trends",
    )

    ap.add_argument(
        "--user", "-u",
        help="Limit contributor rows to a GitHub login",
    )
    ap.add_argument(
        "--label", "-l",
        help="Optional label for analyses that support label filtering",
    )
    ap.add_argument(
        "--data",
        help="JSON dataset path; otherwise use the template DataLoader",
    )

    ap.add_argument(
        "--start-date", "--since",
        dest="start_date",
        help="Activity start date or timestamp, inclusive",
    )
    ap.add_argument(
        "--end-date", "--until",
        dest="end_date",
        help="Activity end; date-only values include the whole day",
    )
    ap.add_argument(
        "--observed-at",
        dest="observed_at",
        help="Historical snapshot reference timestamp",
    )

    ap.add_argument(
        "--include-bots",
        dest="include_bots",
        action="store_true",
        default=None,
        help="Include recognized bot accounts",
    )
    ap.add_argument(
        "--bot",
        dest="bot_accounts",
        action="append",
        default=None,
        help="Additional bot login to exclude; repeatable",
    )

    ap.add_argument(
        "--stale-days",
        dest="stale_days",
        type=int,
        help="Issue-age threshold for old open assignments; default: 90",
    )
    ap.add_argument(
        "--response-target-hours",
        dest="response_target_hours",
        type=float,
        help="Observed response review target; default: 24 hours",
    )
    ap.add_argument(
        "--quiet-days",
        dest="quiet_days",
        type=int,
        help="Recorded participation gap for quiet issues; default: 30 days",
    )

    ap.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Existing output directory; default: current directory",
    )

    csv_options = ap.add_mutually_exclusive_group()
    csv_options.add_argument(
        "--csv",
        dest="csv_path",
        default="contributor_activity.csv",
        metavar="FILENAME",
        help="CSV filename or absolute destination",
    )
    csv_options.add_argument(
        "--no-csv",
        dest="csv_path",
        action="store_const",
        const=None,
        help="Disable CSV export",
    )

    png_options = ap.add_mutually_exclusive_group()
    png_options.add_argument(
        "--png",
        dest="png_path",
        default="contributor_activity.png",
        metavar="FILENAME",
        help="PNG filename or absolute destination",
    )
    png_options.add_argument(
        "--no-png",
        dest="png_path",
        action="store_const",
        const=None,
        help="Disable PNG export",
    )

    return ap.parse_args(argv)


def run_contributor_analysis(args):
    """Resolve contributor settings and run feature 2."""
    from contributor_activity_analysis import ContributorActivityAnalysis

    if args.label is not None:
        raise ValueError(
            "--label is not currently supported by contributor activity."
        )

    setting_names = (
        "user",
        "start_date",
        "end_date",
        "observed_at",
        "include_bots",
        "bot_accounts",
        "stale_days",
        "response_target_hours",
        "quiet_days",
        "output_dir",
    )

    settings = {
        name: config.get_parameter(name)
        for name in setting_names
    }

    analysis = ContributorActivityAnalysis(
        data_path=args.data,
        **settings,
    )

    return analysis.run(
        csv_path=args.csv_path,
        png_path=args.png_path,
    )


def main(argv=None):
    args = parse_args(argv)

    # Preserve the template's configuration flow.
    # Non-None command-line values override existing settings.
    config.overwrite_from_args(args)

    try:
        if args.feature == 0:
            # Import only when needed so feature 2 does not load
            # the example analysis and its plotting dependencies.
            from example_analysis import ExampleAnalysis

            ExampleAnalysis().run()

        elif args.feature == 1:
            raise ValueError(
                "Feature 1 is not implemented. "
                "Connect its analysis module before using it."
            )

        elif args.feature == 2:
            run_contributor_analysis(args)

        elif args.feature == 3:
            from discussion_trend_analysis import DiscussionTrends

            DiscussionTrends().run()

    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        raise SystemExit(f"Analysis failed: {exc}") from exc


if __name__ == "__main__":
    main()