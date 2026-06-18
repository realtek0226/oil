from __future__ import annotations

from functools import lru_cache

from app.clients.brent_report_client import BrentReportClient
from app.clients.china_money_client import ChinaMoneyCnyMidClient
from app.clients.cnenergy_refined_oil_client import CnEnergyRefinedOilClient
from app.clients.competitor_price_client import CompetitorPriceClient
from app.clients.eta_client import EtaClient
from app.clients.jinshi_client import JinshiClient
from app.clients.jlc_refined_oil_client import JlcRefinedOilClient
from app.clients.llm_client import LlmClient
from app.clients.oilchem_openapi_client import OilchemOpenApiClient
from app.clients.oilchem_price_client import OilchemPriceClient
from app.clients.oilchem_production_sales_client import OilchemProductionSalesClient
from app.clients.refined_oil_news_client import RefinedOilNewsClient
from app.clients.refined_oil_policy_client import RefinedOilPolicyClient
from app.clients.sci99_refinery_dynamic_client import Sci99RefineryDynamicClient
from app.clients.wind_price_client import WindPriceClient
from app.core.settings import get_settings
from app.services.agent_control import AgentControlService
from app.services.auth_service import AuthService
from app.services.backtest.service import BacktestService
from app.services.indicator_catalog import IndicatorCatalog
from app.services.market_dataset import MarketDatasetService
from app.services.postgres_snapshot_repository import PostgresSnapshotRepository
from app.services.predictors.shandong_gas92 import ShandongGas92Predictor
from app.services.predictors.shandong_regional_spreads import ShandongRegionalSpreadPredictor
from app.services.run_repository import FileRunRepository
from app.services.scheduler_service import SchedulerService
from app.services.workbench_service import WorkbenchService


@lru_cache(maxsize=1)
def get_catalog() -> IndicatorCatalog:
    return IndicatorCatalog()


@lru_cache(maxsize=1)
def get_eta_client() -> EtaClient:
    return EtaClient(get_settings().eta)


@lru_cache(maxsize=1)
def get_wind_price_client() -> WindPriceClient:
    settings = get_settings().wind
    return WindPriceClient(
        base_url=settings.base_url,
        default_code=settings.brent_code,
        default_fields=settings.brent_fields,
        timeout_seconds=settings.timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_llm_client() -> LlmClient:
    return LlmClient(get_settings().llm)


@lru_cache(maxsize=1)
def get_oilchem_openapi_client() -> OilchemOpenApiClient:
    return OilchemOpenApiClient(get_settings().oilchem_openapi)


@lru_cache(maxsize=1)
def get_competitor_price_client() -> CompetitorPriceClient:
    settings = get_settings().competitor_price
    return CompetitorPriceClient(base_url=settings.base_url, timeout_seconds=settings.timeout_seconds)


@lru_cache(maxsize=1)
def get_repository() -> FileRunRepository:
    return FileRunRepository()


@lru_cache(maxsize=1)
def get_snapshot_repository() -> PostgresSnapshotRepository | None:
    settings = get_settings().database
    if not settings.url.strip():
        return None
    return PostgresSnapshotRepository(settings)


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    repository = get_snapshot_repository()
    if repository is None:
        raise RuntimeError("Authentication requires a configured PostgreSQL database.")
    return AuthService(repository=repository, settings=get_settings().auth)


@lru_cache(maxsize=1)
def get_dataset_service() -> MarketDatasetService:
    collector_settings = get_settings().collectors
    return MarketDatasetService(
        eta_client=get_eta_client(),
        catalog=get_catalog(),
        china_money_client=ChinaMoneyCnyMidClient(),
        wind_price_client=get_wind_price_client(),
        brent_report_client=BrentReportClient(get_settings().brent_report),
        jinshi_client=JinshiClient(get_settings().jinshi),
        refined_oil_news_client=RefinedOilNewsClient(),
        oilchem_openapi_client=get_oilchem_openapi_client(),
        competitor_price_client=get_competitor_price_client(),
        oilchem_price_client=OilchemPriceClient(),
        oilchem_production_sales_client=OilchemProductionSalesClient(),
        cnenergy_refined_oil_client=CnEnergyRefinedOilClient(),
        jlc_refined_oil_client=JlcRefinedOilClient(),
        sci99_refinery_dynamic_client=Sci99RefineryDynamicClient(get_settings().sci99),
        policy_client=RefinedOilPolicyClient(),
        snapshot_repository=get_snapshot_repository(),
        web_scraping_enabled=collector_settings.web_scraping_enabled,
        refined_news_scraping_enabled=collector_settings.refined_news_scraping_enabled,
        policy_scraping_enabled=collector_settings.policy_scraping_enabled,
        oilchem_spot_report_scraping_enabled=collector_settings.oilchem_spot_report_scraping_enabled,
        oilchem_scraping_enabled=collector_settings.oilchem_scraping_enabled,
    )


@lru_cache(maxsize=1)
def get_agent_control_service() -> AgentControlService:
    return AgentControlService(get_repository())


@lru_cache(maxsize=1)
def get_predictor() -> ShandongGas92Predictor:
    return ShandongGas92Predictor(
        dataset_service=get_dataset_service(),
        llm_client=get_llm_client(),
        agent_control_service=get_agent_control_service(),
        scorecard_path=get_settings().research.scorecard_path,
    )


@lru_cache(maxsize=1)
def get_regional_spread_predictor() -> ShandongRegionalSpreadPredictor:
    return ShandongRegionalSpreadPredictor(
        dataset_service=get_dataset_service(),
        llm_client=get_llm_client(),
        agent_control_service=get_agent_control_service(),
        snapshot_repository=get_snapshot_repository(),
        outright_predictor=get_predictor(),
    )


@lru_cache(maxsize=1)
def get_backtest_service() -> BacktestService:
    return BacktestService(get_predictor())


@lru_cache(maxsize=1)
def get_workbench_service() -> WorkbenchService:
    return WorkbenchService(
        dataset_service=get_dataset_service(),
        predictor=get_predictor(),
        spread_predictor=get_regional_spread_predictor(),
        llm_client=get_llm_client(),
        repository=get_repository(),
    )


@lru_cache(maxsize=1)
def get_scheduler_service() -> SchedulerService:
    return SchedulerService(
        settings=get_settings().scheduler,
        dataset_service=get_dataset_service(),
        workbench_service=get_workbench_service(),
    )
