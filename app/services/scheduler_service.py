from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

from app.core.settings import SchedulerSettings
from app.services.market_dataset import MarketDatasetService
from app.services.workbench_service import WorkbenchService


logger = logging.getLogger(__name__)

JobMode = Literal["interval", "daily", "weekly"]


@dataclass
class SchedulerJobState:
    job_key: str
    label: str
    mode: JobMode
    schedule_value: str
    enabled: bool
    job_func: Callable[[], dict[str, Any]]
    next_run_at: datetime | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    last_summary: dict[str, Any] = field(default_factory=dict)
    running: bool = False


class SchedulerService:
    def __init__(
        self,
        settings: SchedulerSettings,
        dataset_service: MarketDatasetService,
        workbench_service: WorkbenchService,
    ) -> None:
        self.settings = settings
        self.dataset_service = dataset_service
        self.workbench_service = workbench_service
        self.tz = ZoneInfo(settings.timezone)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at: datetime | None = None
        self._jobs = self._build_jobs()

    def start(self) -> None:
        if not self.settings.enabled:
            logger.info("Scheduler disabled by config.")
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._started_at = self._now()
            self._prime_schedules()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="oil-research-scheduler",
                daemon=True,
            )
            self._thread.start()
        logger.info("Scheduler started with %s jobs.", len(self._jobs))

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)
        logger.info("Scheduler stopped.")

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            jobs = [
                {
                    "job_key": job.job_key,
                    "label": job.label,
                    "mode": job.mode,
                    "schedule_value": job.schedule_value,
                    "enabled": job.enabled,
                    "running": job.running,
                    "next_run_at": job.next_run_at,
                    "last_started_at": job.last_started_at,
                    "last_finished_at": job.last_finished_at,
                    "last_success_at": job.last_success_at,
                    "last_error": job.last_error,
                    "last_summary": job.last_summary,
                }
                for job in self._jobs.values()
            ]
        return {
            "enabled": self.settings.enabled,
            "timezone": self.settings.timezone,
            "started_at": self._started_at,
            "jobs": jobs,
        }

    def _build_jobs(self) -> dict[str, SchedulerJobState]:
        web_scraping_enabled = bool(getattr(self.dataset_service, "web_scraping_enabled", False))
        oilchem_scraping_enabled = bool(getattr(self.dataset_service, "oilchem_scraping_enabled", False))
        oilchem_spot_report_scraping_enabled = bool(
            getattr(self.dataset_service, "oilchem_spot_report_scraping_enabled", False)
        )
        oilchem_openapi_enabled = bool(
            getattr(getattr(self.dataset_service, "oilchem_openapi_client", None), "enabled", False)
        )
        competitor_price_enabled = bool(getattr(self.dataset_service, "competitor_price_client", None))
        return {
            "market_snapshot": SchedulerJobState(
                job_key="market_snapshot",
                label="价格快照抓取",
                mode="interval",
                schedule_value=f"{max(self.settings.snapshot_interval_seconds, 0)}秒",
                enabled=self.settings.snapshot_interval_seconds > 0,
                job_func=self._run_market_snapshot_job,
            ),
            "policy_event_refresh": SchedulerJobState(
                job_key="policy_event_refresh",
                label="政策与事件抓取",
                mode="interval",
                schedule_value=f"{max(self.settings.policy_event_interval_seconds, 0)}秒",
                enabled=web_scraping_enabled and self.settings.policy_event_interval_seconds > 0,
                job_func=self._run_policy_event_job,
            ),
            "brent_report_fetch": SchedulerJobState(
                job_key="brent_report_fetch",
                label="Brent日报抓取",
                mode="daily",
                schedule_value=self.settings.brent_report_fetch_time,
                enabled=bool(self.settings.brent_report_fetch_time.strip()),
                job_func=self._run_brent_report_job,
            ),
            "morning_briefing": SchedulerJobState(
                job_key="morning_briefing",
                label="晨报生成",
                mode="daily",
                schedule_value=self.settings.morning_briefing_time,
                enabled=self.settings.morning_briefing_enabled and bool(self.settings.morning_briefing_time.strip()),
                job_func=self._run_morning_briefing_job,
            ),
            "oilchem_spot_report_fetch": SchedulerJobState(
                job_key="oilchem_spot_report_fetch",
                label="隆众山东日评抓取",
                mode="daily",
                schedule_value=self.settings.oilchem_spot_report_fetch_time,
                enabled=oilchem_spot_report_scraping_enabled
                and bool(self.settings.oilchem_spot_report_fetch_time.strip()),
                job_func=self._run_oilchem_spot_report_job,
            ),
            "oilchem_price_fetch": SchedulerJobState(
                job_key="oilchem_price_fetch",
                label="隆众汽柴油市场价抓取",
                mode="daily",
                schedule_value=self.settings.oilchem_price_fetch_time,
                enabled=oilchem_scraping_enabled and bool(self.settings.oilchem_price_fetch_time.strip()),
                job_func=self._run_oilchem_price_job,
            ),
            "oilchem_production_sales_fetch": SchedulerJobState(
                job_key="oilchem_production_sales_fetch",
                label="隆众汽柴油产销率抓取",
                mode="daily",
                schedule_value=self.settings.oilchem_production_sales_fetch_time,
                enabled=oilchem_scraping_enabled and bool(self.settings.oilchem_production_sales_fetch_time.strip()),
                job_func=self._run_oilchem_production_sales_job,
            ),
            "oilchem_independent_maintenance_fetch": SchedulerJobState(
                job_key="oilchem_independent_maintenance_fetch",
                label="隆众地方炼厂检修计划抓取",
                mode="weekly",
                schedule_value=self.settings.oilchem_independent_maintenance_fetch_time,
                enabled=oilchem_scraping_enabled and bool(self.settings.oilchem_independent_maintenance_fetch_time.strip()),
                job_func=self._run_oilchem_independent_maintenance_job,
            ),
            "oilchem_main_maintenance_fetch": SchedulerJobState(
                job_key="oilchem_main_maintenance_fetch",
                label="隆众主营炼厂检修计划抓取",
                mode="weekly",
                schedule_value=self.settings.oilchem_main_maintenance_fetch_time,
                enabled=oilchem_scraping_enabled and bool(self.settings.oilchem_main_maintenance_fetch_time.strip()),
                job_func=self._run_oilchem_main_maintenance_job,
            ),
            "oilchem_daily_fetch": SchedulerJobState(
                job_key="oilchem_daily_fetch",
                label="隆众经营指标抓取",
                mode="daily",
                schedule_value=self.settings.oilchem_daily_fetch_time,
                enabled=oilchem_scraping_enabled and bool(self.settings.oilchem_daily_fetch_time.strip()),
                job_func=self._run_oilchem_daily_job,
            ),
            "competitor_price_fetch": SchedulerJobState(
                job_key="competitor_price_fetch",
                label="成品油询价市场均价入库",
                mode="daily",
                schedule_value=self.settings.competitor_price_fetch_time,
                enabled=competitor_price_enabled and bool(self.settings.competitor_price_fetch_time.strip()),
                job_func=self._run_competitor_price_job,
            ),
            "oilchem_openapi_inventory_fetch": SchedulerJobState(
                job_key="oilchem_openapi_inventory_fetch",
                label="隆众已购库存接口同步",
                mode="daily",
                schedule_value=self.settings.oilchem_openapi_inventory_fetch_time,
                enabled=oilchem_openapi_enabled and bool(self.settings.oilchem_openapi_inventory_fetch_time.strip()),
                job_func=self._run_oilchem_openapi_inventory_job,
            ),
            "sci99_price_adjustment_fetch": SchedulerJobState(
                job_key="sci99_price_adjustment_fetch",
                label="卓创调价预测抓取",
                mode="daily",
                schedule_value=self.settings.sci99_price_adjustment_fetch_time,
                enabled=web_scraping_enabled and bool(self.settings.sci99_price_adjustment_fetch_time.strip()),
                job_func=self._run_sci99_price_adjustment_job,
            ),
            "refined_news_fetch": SchedulerJobState(
                job_key="refined_news_fetch",
                label="多源成品油资讯低频抓取",
                mode="daily",
                schedule_value=self.settings.refined_news_fetch_time,
                enabled=web_scraping_enabled
                and bool(getattr(self.dataset_service, "refined_news_scraping_enabled", False))
                and bool(self.settings.refined_news_fetch_time.strip()),
                job_func=self._run_refined_news_job,
            ),
        }

    def _prime_schedules(self) -> None:
        now = self._now()
        for job in self._jobs.values():
            if not job.enabled:
                job.next_run_at = None
                continue
            if job.mode == "interval":
                interval_seconds = self._interval_seconds_for(job.job_key)
                job.next_run_at = now + timedelta(seconds=max(interval_seconds, 1))
                continue
            job.next_run_at = self._initial_daily_run(job=job, now=now)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            due_jobs = self._collect_due_jobs()
            if due_jobs:
                for job in due_jobs:
                    if self._stop_event.is_set():
                        break
                    self._run_job(job)
                continue
            wait_seconds = self._seconds_until_next_run()
            self._stop_event.wait(timeout=wait_seconds)

    def _collect_due_jobs(self) -> list[SchedulerJobState]:
        now = self._now()
        with self._lock:
            return sorted(
                [
                    job
                    for job in self._jobs.values()
                    if job.enabled and not job.running and job.next_run_at and job.next_run_at <= now
                ],
                key=lambda item: item.next_run_at or now,
            )

    def _seconds_until_next_run(self) -> float:
        now = self._now()
        with self._lock:
            next_runs = [
                job.next_run_at
                for job in self._jobs.values()
                if job.enabled and not job.running and job.next_run_at is not None
            ]
        if not next_runs:
            return 5.0
        wait_seconds = min((run_at - now).total_seconds() for run_at in next_runs)
        return max(0.5, min(wait_seconds, 30.0))

    def _run_job(self, job: SchedulerJobState) -> None:
        with self._lock:
            job.running = True
            job.last_started_at = self._now()
            job.last_error = None
        try:
            summary = job.job_func()
        except Exception as exc:
            logger.exception("Scheduled job failed: %s", job.job_key)
            with self._lock:
                job.last_error = str(exc)
                job.last_finished_at = self._now()
                job.last_summary = {}
                job.running = False
                job.next_run_at = self._compute_next_run(job=job, reference=job.last_finished_at)
            return

        with self._lock:
            finished_at = self._now()
            job.last_finished_at = finished_at
            job.last_success_at = finished_at
            job.last_summary = summary
            job.running = False
            job.next_run_at = self._compute_next_run(job=job, reference=finished_at)

    def _compute_next_run(self, *, job: SchedulerJobState, reference: datetime) -> datetime | None:
        if not job.enabled:
            return None
        if job.mode == "interval":
            interval_seconds = self._interval_seconds_for(job.job_key)
            return reference + timedelta(seconds=interval_seconds)
        if job.mode == "weekly":
            return self._next_weekly_time(after=reference, time_text=job.schedule_value, weekday=4)
        return self._next_daily_time(after=reference, time_text=job.schedule_value)

    def _initial_daily_run(self, *, job: SchedulerJobState, now: datetime) -> datetime:
        if job.mode == "weekly":
            return self._next_weekly_time(after=now, time_text=job.schedule_value, weekday=4)
        scheduled_today = self._combine_today(time_text=job.schedule_value, now=now)
        if now < scheduled_today:
            return scheduled_today
        return self._next_daily_time(after=now, time_text=job.schedule_value)

    def _run_market_snapshot_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_market_snapshot_archive(as_of_date=target_date)
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_brent_report_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_brent_report_archive(as_of_date=target_date)
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_policy_event_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_policy_event_archive(as_of_date=target_date)
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_morning_briefing_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        if self._has_today_briefing():
            latest = self.workbench_service.load_latest_briefing() or {}
            return {
                "status": "skipped",
                "reason": "briefing_already_exists",
                "briefing_id": latest.get("briefing_id"),
                "as_of_date": target_date.isoformat(),
            }
        payload = self.workbench_service.generate_morning_briefing(
            as_of_date=target_date,
            use_llm_writer=self.settings.morning_briefing_use_llm,
        )
        return {
            "status": "generated",
            "briefing_id": payload["briefing_id"],
            "title": payload["title"],
            "as_of_date": target_date.isoformat(),
        }

    def _run_oilchem_daily_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_oilchem_daily_archive(as_of_date=target_date)
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_oilchem_price_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_oilchem_price_archive(as_of_date=target_date)
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_competitor_price_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_competitor_price_archive(as_of_date=target_date)
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_oilchem_production_sales_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_oilchem_production_sales_archive(as_of_date=target_date)
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_oilchem_independent_maintenance_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_oilchem_maintenance_archive(
            as_of_date=target_date,
            refinery_scope="local",
        )
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_oilchem_main_maintenance_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_oilchem_maintenance_archive(
            as_of_date=target_date,
            refinery_scope="main",
        )
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_oilchem_openapi_inventory_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_oilchem_openapi_inventory_archive(as_of_date=target_date)
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_sci99_price_adjustment_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_sci99_price_adjustment_archive(as_of_date=target_date)
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_refined_news_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_refined_news_archive(as_of_date=target_date)
        return {"as_of_date": target_date.isoformat(), **payload}

    def _run_oilchem_spot_report_job(self) -> dict[str, Any]:
        target_date = self._local_today()
        payload = self.dataset_service.refresh_oilchem_spot_report_archive(as_of_date=target_date)
        return {"as_of_date": target_date.isoformat(), **payload}

    def _has_today_briefing(self) -> bool:
        latest = self.workbench_service.load_latest_briefing()
        if not latest:
            return False
        return str(latest.get("as_of_date") or "") == self._local_today().isoformat()

    def _has_today_oilchem_spot_report(self) -> bool:
        repository = getattr(self.dataset_service, "snapshot_repository", None)
        if not repository or not getattr(repository, "enabled", False):
            return False
        today = self._local_today()
        try:
            load_result = repository.load_refined_news_items(start_date=today, end_date=today)
        except Exception:
            return False
        if "oilchem_shandong_spot_daily_report" in getattr(load_result, "source_counts", {}):
            return True
        return any(
            str(item.get("source") or "") == "oilchem_shandong_spot_daily_report"
            for item in getattr(load_result, "items", [])
        )

    def _interval_seconds_for(self, job_key: str) -> int:
        if job_key == "market_snapshot":
            return max(self.settings.snapshot_interval_seconds, 1)
        if job_key == "policy_event_refresh":
            return max(self.settings.policy_event_interval_seconds, 1)
        return 86400

    def _combine_today(self, *, time_text: str, now: datetime) -> datetime:
        hour, minute = self._parse_daily_time(time_text)
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _next_daily_time(self, *, after: datetime, time_text: str) -> datetime:
        candidate = self._combine_today(time_text=time_text, now=after)
        if candidate <= after:
            candidate = candidate + timedelta(days=1)
        return candidate

    def _next_weekly_time(self, *, after: datetime, time_text: str, weekday: int) -> datetime:
        candidate = self._combine_today(time_text=time_text, now=after)
        days_ahead = (weekday - candidate.weekday()) % 7
        candidate = candidate + timedelta(days=days_ahead)
        if candidate <= after:
            candidate = candidate + timedelta(days=7)
        return candidate

    def _parse_daily_time(self, value: str) -> tuple[int, int]:
        normalized = value.strip()
        try:
            parsed = datetime.strptime(normalized, "%H:%M")
        except ValueError as exc:
            raise ValueError(f"Invalid scheduler time: {value}") from exc
        return parsed.hour, parsed.minute

    def _local_today(self) -> date:
        return self._now().date()

    def _now(self) -> datetime:
        return datetime.now(self.tz)
