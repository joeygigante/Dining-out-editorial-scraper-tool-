"""Scheduling logic for automated pipeline runs.

Runs the weekly report Monday at 7am and mid-week alert Wednesday at noon.
Uses the `schedule` library for simplicity.
"""

from __future__ import annotations

import logging
import time

import schedule

from src.orchestrator import Pipeline

logger = logging.getLogger(__name__)


def setup_schedule(pipeline: Pipeline, config: dict):
    """Configure the weekly and mid-week schedules."""
    weekly_day = config.get("weekly_day", "monday")
    weekly_time = config.get("weekly_time", "07:00")
    midweek_day = config.get("midweek_day", "wednesday")
    midweek_time = config.get("midweek_time", "12:00")

    getattr(schedule.every(), weekly_day).at(weekly_time).do(_run_weekly, pipeline)
    getattr(schedule.every(), midweek_day).at(midweek_time).do(_run_midweek, pipeline)

    logger.info(
        "Scheduled: weekly report %s@%s, mid-week alert %s@%s",
        weekly_day,
        weekly_time,
        midweek_day,
        midweek_time,
    )


def run_loop():
    """Run the scheduling loop forever."""
    logger.info("Scheduler started — waiting for next scheduled run...")
    while True:
        schedule.run_pending()
        time.sleep(60)


def _run_weekly(pipeline: Pipeline):
    try:
        result = pipeline.run_weekly()
        logger.info("Weekly run completed: %s", result)
    except Exception:
        logger.exception("Weekly run failed")


def _run_midweek(pipeline: Pipeline):
    try:
        result = pipeline.run_midweek_alert()
        logger.info("Mid-week alert completed: %s", result)
    except Exception:
        logger.exception("Mid-week alert failed")
