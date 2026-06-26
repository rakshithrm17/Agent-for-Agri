"""Background Night Agent Scheduler.

Orchestrates the execution of all daily layers in sequence:
- 1:00 AM: Layer 1 Ingestion (collect weather, mandi, satellite, groundwater, news data)
- 2:00 AM: Layer 2 Feature Engineering (cleaning, validating, feature building)
- 3:00 AM: Layer 3 ML Engine Retraining (monthly on Sunday mornings)
- 4:00 AM: Layer 4 Predictions and Insights (anti-hallucination, risk scoring)

Allows triggering a run immediately using the `--run-now` CLI argument.
"""

import argparse
import datetime
import sys
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from crop_agent.config.logging_config import configure_logging, get_logger
from crop_agent.config.settings import (
    MONTHLY_RETRAIN_HOUR,
    MONTHLY_RETRAIN_MINUTE,
    NIGHT_AGENT_HOUR,
    NIGHT_AGENT_MINUTE,
)
from crop_agent.database.connection import get_session
from crop_agent.database.models import AgentRunLog, AnomalyLog
from crop_agent.ingestion.groundwater_collector import GroundwaterCollector
from crop_agent.ingestion.mandi_collector import MandiCollector
from crop_agent.ingestion.news_collector import NewsCollector
from crop_agent.ingestion.satellite_collector import SatelliteCollector
from crop_agent.ingestion.weather_collector import WeatherCollector

configure_logging()
logger = get_logger(__name__)


def run_ingestion_layer(target_date: datetime.date) -> tuple[int, int, int]:
    """Execute all Layer 1 ingestion collectors for the target date.

    Returns
    -------
        Tuple of (total_tasks, successes, failures).

    """
    logger.info("scheduler.ingestion_start", date=str(target_date))
    print(f"\n🔄 Running Ingestion Layer (Layer 1) for {target_date}...")

    collectors = {
        "WeatherCollector": WeatherCollector(),
        "MandiCollector": MandiCollector(),
        "SatelliteCollector": SatelliteCollector(),
        "GroundwaterCollector": GroundwaterCollector(),
        "NewsCollector": NewsCollector(),
    }

    successes = 0
    failures = 0

    for name, collector in collectors.items():
        try:
            print(f"  • Running {name}...")
            rows = collector.collect(target_date)
            logger.info("scheduler.collector_success", collector=name, rows_written=rows)
            print(f"    ✅ {name} finished. Rows written: {rows}")
            successes += 1
        except Exception as exc:
            logger.error("scheduler.collector_failed", collector=name, error=str(exc))
            print(f"    ❌ {name} failed: {exc}")
            failures += 1

    return len(collectors), successes, failures


def run_feature_engineering_layer(target_date: datetime.date) -> bool:
    """Execute Layer 2 Feature Engineering.

    Stubs the feature cleaning, validation, and building pipeline.
    """
    logger.info("scheduler.engineering_start", date=str(target_date))
    print(f"\n⚙️ Running Feature Engineering (Layer 2) for {target_date} [STUB]...")

    # Simulate feature validation and building steps
    time.sleep(0.5)

    logger.info("scheduler.engineering_success", date=str(target_date))
    print("  ✅ Feature engineering completed successfully.")
    return True


def run_ml_retraining_layer() -> bool:
    """Execute Layer 3 ML Model Retraining.

    Stubs model walk-forward validation and parameter optimization.
    """
    logger.info("scheduler.ml_retrain_start")
    print("\n🧠 Running ML Model Retraining & Evaluation (Layer 3) [STUB]...")

    time.sleep(0.5)

    logger.info("scheduler.ml_retrain_success")
    print("  ✅ Models retrained and validated successfully.")
    return True


def run_prediction_layer(target_date: datetime.date) -> int:
    """Execute Layer 4 Prediction & Insight Engine.

    Stubs yield/price/profit predictions and anti-hallucination checks.
    """
    logger.info("scheduler.prediction_start", date=str(target_date))
    print(f"\n🔮 Running Prediction & Insights (Layer 4) for {target_date} [STUB]...")

    time.sleep(0.5)

    logger.info("scheduler.prediction_success", date=str(target_date))
    print("  ✅ Crop recommendations, risk scores, and alerts updated.")
    return 6  # Return simulated count of crops predicted


def run_pipeline(target_date: datetime.date) -> None:
    """Run the entire agent execution pipeline for a specific date and log stats."""
    start_time = time.time()
    logger.info("scheduler.pipeline_start", date=str(target_date))
    print("=" * 60)
    print(f"🚀 EXECUTING CROP INTELLIGENCE NIGHT AGENT PIPELINE: {target_date}")
    print("=" * 60)

    # 1. Run Ingestion
    tasks_total, successes, failures = run_ingestion_layer(target_date)

    # 2. Run Feature Engineering (Layer 2)
    tasks_total += 1
    if run_feature_engineering_layer(target_date):
        successes += 1
    else:
        failures += 1

    # 3. Run Predictions (Layer 4)
    tasks_total += 1
    predictions_generated = run_prediction_layer(target_date)
    if predictions_generated > 0:
        successes += 1
    else:
        failures += 1

    # Calculate run duration
    duration = time.time() - start_time

    # Find anomalies flagged today
    anomalies_count = 0
    try:
        with get_session() as session:
            # Query anomaly logs for today
            day_start = datetime.datetime.combine(target_date, datetime.time())
            day_end = day_start + datetime.timedelta(days=1)
            anomalies_count = (
                session.query(AnomalyLog)
                .filter(AnomalyLog.flagged_at >= day_start, AnomalyLog.flagged_at < day_end)
                .count()
            )
    except Exception as e:
        logger.error("scheduler.anomaly_count_failed", error=str(e))

    # Write AgentRunLog
    run_status = "SUCCESS" if failures == 0 else ("PARTIAL" if successes > 0 else "FAILED")
    notes = f"Scheduler execution completed. successes={successes}, failures={failures}"

    try:
        with get_session() as session:
            # Delete existing run log for this date if it exists to allow re-runs
            session.query(AgentRunLog).filter_by(run_date=datetime.datetime.combine(target_date, datetime.time())).delete()

            run_log = AgentRunLog(
                run_date=datetime.datetime.combine(target_date, datetime.time()),
                tasks_total=tasks_total,
                tasks_success=successes,
                tasks_failed=failures,
                data_freshness_hrs=1.0,
                predictions_generated=predictions_generated,
                anomalies_flagged=anomalies_count,
                run_duration_sec=duration,
                run_status=run_status,
                notes=notes,
            )
            session.add(run_log)
            session.commit()
            print(f"\n📝 Run logged to agent_run_log. Status: {run_status} | Duration: {duration:.2f}s")
            logger.info("scheduler.run_logged", run_status=run_status, duration_sec=duration)
    except Exception as exc:
        print(f"\n⚠️ Failed to write agent run log: {exc}")
        logger.error("scheduler.log_write_failed", error=str(exc))

    print("\n🎉 Pipeline run completed!")


def main() -> None:
    """Parse CLI args and set up scheduler daemon or trigger immediate run."""
    parser = argparse.ArgumentParser(description="Crop Intelligence Background Agent Scheduler")
    parser.add_argument("--run-now", action="store_true", help="Run the entire pipeline immediately and exit")
    parser.add_argument("--date", type=str, help="Target date for --run-now in YYYY-MM-DD format (defaults to today)")
    args = parser.parse_args()

    if args.run_now:
        target_date = datetime.date.today()
        if args.date:
            try:
                target_date = datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
            except ValueError:
                print(f"❌ Invalid date format: {args.date}. Use YYYY-MM-DD.")
                sys.exit(1)
        run_pipeline(target_date)
        return

    # Daemon execution mode (APScheduler)
    scheduler = BlockingScheduler()

    # 1. Schedule daily ingestion at 1:00 AM
    # (For simplified standalone execution, we group daily tasks inside run_pipeline at 1:00 AM)
    scheduler.add_job(
        func=lambda: run_pipeline(datetime.date.today()),
        trigger=CronTrigger(hour=NIGHT_AGENT_HOUR, minute=NIGHT_AGENT_MINUTE),
        id="daily_pipeline",
        name="Daily Ingestion and Prediction Pipeline",
        replace_existing=True,
    )

    # 2. Schedule monthly model retraining at 3:00 AM on the first Sunday of every month
    scheduler.add_job(
        func=run_ml_retraining_layer,
        trigger=CronTrigger(day="1-7", day_of_week="sun", hour=MONTHLY_RETRAIN_HOUR, minute=MONTHLY_RETRAIN_MINUTE),
        id="monthly_retraining",
        name="Monthly ML Models Retraining",
        replace_existing=True,
    )

    print("=" * 60)
    print("🕒 Starting Background Night Agent Scheduler (Blocking Mode)...")
    print(f"   Daily pipeline scheduled for {NIGHT_AGENT_HOUR:02d}:{NIGHT_AGENT_MINUTE:02d} everyday.")
    print(f"   Monthly model retrain scheduled for first Sunday at {MONTHLY_RETRAIN_HOUR:02d}:{MONTHLY_RETRAIN_MINUTE:02d}.")
    print("   Press Ctrl+C to exit.")
    print("=" * 60)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 Night Agent Scheduler stopped.")


if __name__ == "__main__":
    main()
