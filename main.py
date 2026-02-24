#!/usr/bin/env python3
"""DiningOut Editorial Scraper Tool — CLI entry point.

Usage:
    python main.py run-weekly          Full weekly pipeline
    python main.py run-alert           Mid-week breaking news check
    python main.py collect             Collect data only (no report)
    python main.py report [RUN_ID]     Generate report from existing data
    python main.py health              Check all source health
    python main.py schedule            Start automated scheduler
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv

from src.orchestrator import Pipeline
from src.scheduler import run_loop, setup_schedule

# Load environment variables from .env file
load_dotenv()


def _load_config(config_path: str) -> dict:
    """Load config from YAML, with env vars overriding."""
    import os

    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    # Environment variables override config file
    env_overrides = {
        "reddit_client_id": os.getenv("REDDIT_CLIENT_ID"),
        "reddit_client_secret": os.getenv("REDDIT_CLIENT_SECRET"),
        "yelp_api_key": os.getenv("YELP_API_KEY"),
        "sendgrid_api_key": os.getenv("SENDGRID_API_KEY"),
        "smtp_user": os.getenv("SMTP_USER"),
        "smtp_password": os.getenv("SMTP_PASSWORD"),
        "smtp_host": os.getenv("SMTP_HOST"),
    }
    for key, val in env_overrides.items():
        if val is not None:
            config[key] = val

    return config


def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@click.group()
@click.option("--config", default="config/config.yaml", help="Path to config file")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, config, verbose):
    """DiningOut Editorial Scraper Tool"""
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config"] = _load_config(config)


@cli.command("run-weekly")
@click.pass_context
def run_weekly(ctx):
    """Run the full weekly pipeline: collect, analyze, report, email."""
    pipeline = Pipeline(ctx.obj["config"])
    result = pipeline.run_weekly()
    click.echo(f"Weekly run complete: {result['items_collected']} items, email sent: {result['email_sent']}")


@cli.command("run-alert")
@click.pass_context
def run_alert(ctx):
    """Run mid-week breaking news check."""
    pipeline = Pipeline(ctx.obj["config"])
    result = pipeline.run_midweek_alert()
    click.echo(f"Alert check complete: {result['items_collected']} items, alert sent: {result['alert_sent']}")


@cli.command("collect")
@click.pass_context
def collect_only(ctx):
    """Collect data from all sources without generating a report."""
    pipeline = Pipeline(ctx.obj["config"])
    result = pipeline.run_collect_only()
    click.echo(f"Collection complete: {result['items_collected']} items saved as run {result['run_id']}")


@cli.command("report")
@click.argument("run_id", required=False)
@click.option("-o", "--output", default=None, help="Save HTML to file instead of stdout")
@click.pass_context
def generate_report(ctx, run_id, output):
    """Generate report from stored data. Optionally specify a RUN_ID."""
    pipeline = Pipeline(ctx.obj["config"])
    html = pipeline.generate_report_only(run_id)
    if output:
        Path(output).write_text(html)
        click.echo(f"Report saved to {output}")
    else:
        click.echo(html)


@cli.command("health")
@click.pass_context
def health_check(ctx):
    """Check health of all configured data sources."""
    pipeline = Pipeline(ctx.obj["config"])
    results = pipeline.health_check()
    for name, status in results.items():
        if isinstance(status, dict):
            click.echo(f"  {name}: {status}")
        else:
            icon = "OK" if status else "FAIL"
            click.echo(f"  {name}: {icon}")


@cli.command("schedule")
@click.pass_context
def start_scheduler(ctx):
    """Start the automated scheduler (runs indefinitely)."""
    pipeline = Pipeline(ctx.obj["config"])
    setup_schedule(pipeline, ctx.obj["config"])
    click.echo("Scheduler started. Press Ctrl+C to stop.")
    try:
        run_loop()
    except KeyboardInterrupt:
        click.echo("\nScheduler stopped.")


if __name__ == "__main__":
    cli()
