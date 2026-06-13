from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


CONFIG_PATH = Path("app/config/app_config.json")


@dataclass(frozen=True)
class LlmSettings:
    model_name: str
    base_url: str
    api_key: str
    timeout_seconds: int = 60


@dataclass(frozen=True)
class EtaSettings:
    appid: str
    secret: str
    base_url: str


@dataclass(frozen=True)
class WindSettings:
    base_url: str = ""
    brent_code: str = "B.IPE"
    brent_fields: str = "rt_latest,rt_chg,rt_pct_chg"
    timeout_seconds: float = 5.0


@dataclass(frozen=True)
class JinshiSettings:
    api_url: str = ""
    auth_token: str = ""
    secret_key_b64: str = ""


@dataclass(frozen=True)
class OilchemOpenApiSettings:
    enabled: bool = False
    base_url: str = ""
    username: str = ""
    password: str = ""
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class ResearchSettings:
    default_entity_code: str
    default_region_code: str
    default_product_code: str
    scorecard_path: str


@dataclass(frozen=True)
class DatabaseSettings:
    url: str = ""
    schema: str = "oil_research"
    echo: bool = False


@dataclass(frozen=True)
class SchedulerSettings:
    enabled: bool = False
    timezone: str = "Asia/Shanghai"
    snapshot_interval_seconds: int = 300
    policy_event_interval_seconds: int = 900
    morning_briefing_time: str = "08:05"
    brent_report_fetch_time: str = "08:00"
    morning_briefing_use_llm: bool = True
    oilchem_price_fetch_time: str = "19:00"
    oilchem_production_sales_fetch_time: str = "20:00"
    oilchem_independent_maintenance_fetch_time: str = "23:00"
    oilchem_main_maintenance_fetch_time: str = "01:00"
    oilchem_spot_report_fetch_time: str = "02:00"
    oilchem_daily_fetch_time: str = "18:10"
    oilchem_openapi_inventory_fetch_time: str = "22:00"


@dataclass(frozen=True)
class CollectorSettings:
    web_scraping_enabled: bool = False
    refined_news_scraping_enabled: bool = False
    policy_scraping_enabled: bool = False
    oilchem_spot_report_scraping_enabled: bool = False
    oilchem_scraping_enabled: bool = False


@dataclass(frozen=True)
class AuthSettings:
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "CHANGE_ME"
    bootstrap_admin_display_name: str = "System Administrator"
    session_ttl_hours: int = 12
    remember_me_ttl_hours: int = 24 * 14
    cookie_name: str = "oil_research_session"
    cookie_secure: bool = False


@dataclass(frozen=True)
class AppSettings:
    llm: LlmSettings
    eta: EtaSettings
    wind: WindSettings
    jinshi: JinshiSettings
    oilchem_openapi: OilchemOpenApiSettings
    research: ResearchSettings
    database: DatabaseSettings
    scheduler: SchedulerSettings
    collectors: CollectorSettings
    auth: AuthSettings


def _load_json_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing config file: {path}. Copy app/config/app_config.example.json to app/config/app_config.json and fill it."
        )
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    payload = _load_json_config(CONFIG_PATH)
    return AppSettings(
        llm=LlmSettings(**payload["llm"]),
        eta=EtaSettings(**payload["eta"]),
        wind=WindSettings(**payload.get("wind", {})),
        jinshi=JinshiSettings(**payload.get("jinshi", {})),
        oilchem_openapi=OilchemOpenApiSettings(**payload.get("oilchem_openapi", {})),
        research=ResearchSettings(**payload["research"]),
        database=DatabaseSettings(**payload.get("database", {})),
        scheduler=SchedulerSettings(**payload.get("scheduler", {})),
        collectors=CollectorSettings(**payload.get("collectors", {})),
        auth=AuthSettings(**payload.get("auth", {})),
    )
