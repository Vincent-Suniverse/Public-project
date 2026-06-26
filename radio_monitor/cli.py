from __future__ import annotations

import argparse
import logging
import signal
import sys

from .config import Config
from .pipeline import Pipeline


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def cmd_run(args: argparse.Namespace) -> None:
    config = Config.from_env()
    _configure_logging(config.log_level)

    pipeline = Pipeline(config)

    if args.once:
        success = pipeline.run_once()
        pipeline.close()
        sys.exit(0 if success else 1)

    def _shutdown(signum: int, _frame: object) -> None:
        logging.getLogger(__name__).info("Received signal %d, shutting down", signum)
        pipeline.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    pipeline.run_continuous()


def cmd_stats(args: argparse.Namespace) -> None:
    config = Config.from_env()
    _configure_logging(config.log_level)

    pipeline = Pipeline(config)
    stats = pipeline.stats()
    pipeline.close()

    print(f"Total transmissions:  {stats['total_transmissions']:>10,}")
    print(f"Unique aircraft:      {stats['unique_aircraft']:>10,}")
    print(f"Completed poll runs:  {stats['completed_poll_runs']:>10,}")
    print(f"Failed poll runs:     {stats['failed_poll_runs']:>10,}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="radio-monitor",
        description="ADS-B radio transmission monitoring pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run the monitoring pipeline")
    run_parser.add_argument(
        "--once",
        action="store_true",
        help="Execute a single poll cycle and exit",
    )
    run_parser.set_defaults(func=cmd_run)

    stats_parser = sub.add_parser("stats", help="Show pipeline statistics")
    stats_parser.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)
