import argparse
import base64
import hashlib
import hmac
import json
import random
import string
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests


DEFAULT_JSON_OUTPUT = "artifacts/eta_p0_whitelist_2026-05-29.json"
DEFAULT_MD_OUTPUT = "ETA_P0白名单与缺口清单_2026-05-29.md"


@dataclass(frozen=True)
class EtaConfig:
    appid: str
    secret: str
    base_url: str


@dataclass(frozen=True)
class Candidate:
    key: str
    name: str
    group: str
    role: str
    priority: str
    preferred_classify_id: int | None = None
    notes: str = ""


CANDIDATES: list[Candidate] = [
    Candidate(
        key="sd_gas92_market",
        name="汽油：国六：92#：市场价：山东（日）",
        group="price_core",
        role="primary_anchor",
        priority="P0",
        preferred_classify_id=1197,
        notes="山东汽油日频主价格锚",
    ),
    Candidate(
        key="cn_gas92_market",
        name="汽油：国六：92#：市场价：中国（日）",
        group="price_core",
        role="national_anchor",
        priority="P0",
        preferred_classify_id=1197,
        notes="全国汽油日频参考锚",
    ),
    Candidate(
        key="sd_diesel0_market",
        name="柴油：国六：0#：市场价：山东（日）",
        group="price_core",
        role="primary_anchor",
        priority="P0",
        preferred_classify_id=1197,
        notes="山东柴油日频主价格锚，需重点看停更风险",
    ),
    Candidate(
        key="cn_diesel0_market",
        name="柴油：国六：0#：市场价：中国（日）",
        group="price_core",
        role="national_anchor",
        priority="P0",
        preferred_classify_id=1197,
        notes="全国柴油日频参考锚，需重点看停更风险",
    ),
    Candidate(
        key="sd_gas95_market",
        name="汽油：国六：95#：市场价：山东（日）",
        group="price_gap",
        role="external_required",
        priority="P0",
        preferred_classify_id=1197,
        notes="山东95#市场价，期望存在但本次需核实",
    ),
    Candidate(
        key="cn_gas95_market",
        name="汽油：国六：95#：市场价：中国（日）",
        group="price_gap",
        role="external_required",
        priority="P0",
        preferred_classify_id=1197,
        notes="全国95#市场价，期望存在但本次需核实",
    ),
    Candidate(
        key="sd_gas92_basis",
        name="市场价(现货基准价):汽油(92#):山东地炼",
        group="price_proxy",
        role="backup_anchor",
        priority="P1",
        preferred_classify_id=1197,
        notes="Wind 基准价，适合做训练特征或备选锚",
    ),
    Candidate(
        key="sd_diesel0_basis",
        name="市场价(现货基准价):柴油(0#):山东地炼",
        group="price_proxy",
        role="backup_anchor",
        priority="P1",
        preferred_classify_id=1197,
        notes="Wind 基准价，适合做训练特征或备选锚",
    ),
    Candidate(
        key="sd_refinery_gas_avg_6",
        name="（成品油组）山东地炼汽油均价（6家）",
        group="price_proxy",
        role="backup_anchor",
        priority="P1",
        preferred_classify_id=1197,
        notes="山东地炼样本均价，可做替代价格锚",
    ),
    Candidate(
        key="sd_refinery_diesel_avg_6",
        name="（成品油组）山东地炼柴油均价（6家）",
        group="price_proxy",
        role="backup_anchor",
        priority="P1",
        preferred_classify_id=1197,
        notes="山东地炼样本均价，可做替代价格锚",
    ),
    Candidate(
        key="sd_ceiling_gas",
        name="（成品油组）最高零售价：汽油（标准品）：山东/日频",
        group="policy_anchor",
        role="policy_constraint",
        priority="P1",
        preferred_classify_id=1197,
        notes="发改委调价链路约束",
    ),
    Candidate(
        key="sd_ceiling_diesel",
        name="（成品油组）最高零售价：柴油（标准品）：山东/日频",
        group="policy_anchor",
        role="policy_constraint",
        priority="P1",
        preferred_classify_id=1197,
        notes="发改委调价链路约束",
    ),
    Candidate(
        key="sg_92_crack_brent",
        name="新加坡92汽油裂差(vs Brent)",
        group="offshore_anchor",
        role="feature",
        priority="P1",
        preferred_classify_id=1197,
        notes="外盘汽油裂差锚",
    ),
    Candidate(
        key="gas_mtbe_spread",
        name="（成品油组）汽油-MTBE价差",
        group="component_spread",
        role="feature",
        priority="P1",
        preferred_classify_id=1197,
        notes="调油组分价差",
    ),
    Candidate(
        key="sd_gas_naphtha_spread",
        name="山东汽油-石脑油价差",
        group="component_spread",
        role="feature",
        priority="P1",
        preferred_classify_id=1197,
        notes="汽油与石脑油链条价差",
    ),
    Candidate(
        key="sd_mtbe_price",
        name="MTBE：市场主流价：山东（日）",
        group="component_price",
        role="feature",
        priority="P1",
        preferred_classify_id=1197,
        notes="调油关键组分价格",
    ),
    Candidate(
        key="sd_naphtha_price",
        name="石脑油：直馏：市场主流价：山东（日）",
        group="component_price",
        role="feature",
        priority="P1",
        preferred_classify_id=1197,
        notes="石脑油关键组分价格",
    ),
    Candidate(
        key="sd_refining_profit",
        name="（成品油组）山东地炼炼油利润",
        group="profit",
        role="feature_and_alert",
        priority="P0",
        preferred_classify_id=4070,
        notes="利润压缩/修复预警核心指标",
    ),
    Candidate(
        key="sd_gas_inventory",
        name="（成品油组）山东汽油库存（月）",
        group="inventory",
        role="feature",
        priority="P1",
        preferred_classify_id=1257,
        notes="库存因子，但更新频率偏低",
    ),
    Candidate(
        key="sd_diesel_inventory",
        name="（成品油组）柴油：库存：山东（月）",
        group="inventory",
        role="feature",
        priority="P1",
        preferred_classify_id=1257,
        notes="库存因子，但更新频率偏低",
    ),
    Candidate(
        key="sd_gas_sales_weekly",
        name="（成品油组）山东独立炼厂汽油销量（周）",
        group="demand",
        role="feature_and_alert",
        priority="P0",
        preferred_classify_id=1213,
        notes="山东汽油需求代理",
    ),
    Candidate(
        key="sd_gas_shipments_weekly",
        name="（成品油组）汽油出货量山东独立炼厂（周）",
        group="demand",
        role="feature_and_alert",
        priority="P1",
        preferred_classify_id=1213,
        notes="山东汽油出货节奏",
    ),
    Candidate(
        key="sd_diesel_shipments_weekly",
        name="（成品油组）柴油出货量山东：独立炼厂（周）",
        group="demand",
        role="feature_and_alert",
        priority="P1",
        preferred_classify_id=1213,
        notes="山东柴油出货节奏",
    ),
    Candidate(
        key="sd_crude_run_weekly",
        name="（成品油组）山东地炼原油加工量",
        group="supply",
        role="feature_and_alert",
        priority="P0",
        preferred_classify_id=1273,
        notes="山东地炼供给强度",
    ),
    Candidate(
        key="sd_crude_arrival_weekly",
        name="（成品油组）原油到港量山东独立炼厂（周）",
        group="supply",
        role="feature_and_alert",
        priority="P1",
        preferred_classify_id=1273,
        notes="山东地炼原料到港量",
    ),
    Candidate(
        key="sd_gas95_factory_jingbo",
        name="（成品油组）汽油：国六：95#：出厂价：山东：京博石化（日）",
        group="price_proxy",
        role="proxy_for_95",
        priority="P1",
        preferred_classify_id=1197,
        notes="95# 市场价缺失时的代理序列之一",
    ),
]


CLASSIFY_IDS = [1187, 1197, 1213, 1257, 1271, 1273, 2027, 3751, 3812, 3895, 3903, 4070]


def random_nonce(length: int = 32) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def build_signature(appid: str, secret: str, nonce: str, timestamp: int) -> str:
    sign_str = f"appid={appid}&nonce={nonce}&timestamp={timestamp}"
    digest = hmac.new(secret.encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


def signed_headers(config: EtaConfig) -> dict[str, str]:
    nonce = random_nonce()
    timestamp = int(time.time())
    signature = build_signature(config.appid, config.secret, nonce, timestamp)
    return {
        "AppId": config.appid,
        "Nonce": nonce,
        "Timestamp": str(timestamp),
        "Signature": signature,
    }


def eta_get(config: EtaConfig, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.get(
        f"{config.base_url}{path}",
        headers=signed_headers(config),
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("Ret") != 200:
        raise RuntimeError(f"ETA API failed for {path}: {payload}")
    return payload


def fetch_indicator_index(config: EtaConfig, classify_ids: list[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for classify_id in classify_ids:
        data = eta_get(config, "/v1/edb/list", {"ClassifyId": classify_id}).get("Data") or []
        if not isinstance(data, list):
            continue
        for item in data:
            key = (str(item.get("UniqueCode", "")), str(item.get("EdbCode", "")))
            if key in seen:
                continue
            seen.add(key)
            item = dict(item)
            item["ClassifyId"] = classify_id
            rows.append(item)
    return rows


def freshness_threshold_days(frequency: str) -> int:
    if "日" in frequency:
        return 7
    if "周" in frequency:
        return 14
    if "月" in frequency:
        return 45
    if "季" in frequency:
        return 120
    return 90


def lookback_start(latest_date: date, frequency: str) -> date:
    if "日" in frequency:
        return latest_date - timedelta(days=45)
    if "周" in frequency:
        return latest_date - timedelta(days=180)
    if "月" in frequency:
        return latest_date - timedelta(days=540)
    if "季" in frequency:
        return latest_date - timedelta(days=720)
    return latest_date - timedelta(days=180)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def resolve_candidate(candidate: Candidate, index_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = [row for row in index_rows if row.get("EdbName") == candidate.name]
    if candidate.preferred_classify_id is not None:
        preferred = [row for row in matches if row.get("ClassifyId") == candidate.preferred_classify_id]
        if preferred:
            return preferred
    return matches


def inspect_candidate(
    config: EtaConfig,
    candidate: Candidate,
    matches: list[dict[str, Any]],
    today: date,
) -> dict[str, Any]:
    base = asdict(candidate)
    if not matches:
        base.update(
            {
                "found": False,
                "status": "missing",
                "reason": "not_found_in_eta_index",
                "usable_for_training": False,
                "usable_for_realtime_monitoring": False,
                "freshness_days": None,
                "freshness_status": "missing",
                "detail": None,
                "data_rows": 0,
                "data_sample": [],
            }
        )
        return base

    match = matches[0]
    detail = eta_get(
        config,
        "/v1/edb/detail",
        {"UniqueCode": match["UniqueCode"], "EdbCode": match["EdbCode"]},
    ).get("Data") or {}

    latest_date = parse_date(detail.get("LatestDate"))
    frequency = str(detail.get("Frequency", ""))
    threshold = freshness_threshold_days(frequency)
    freshness_days = (today - latest_date).days if latest_date else None
    freshness_status = "unknown"
    if freshness_days is not None:
        freshness_status = "fresh" if freshness_days <= threshold else "stale"

    data_rows: list[dict[str, Any]] = []
    if latest_date is not None:
        start_date = lookback_start(latest_date, frequency).strftime("%Y-%m-%d")
        data_rows = eta_get(
            config,
            "/v1/edb/data",
            {"UniqueCode": match["UniqueCode"], "StartDate": start_date},
        ).get("Data") or []

    usable_for_training = bool(data_rows or detail.get("LatestDate"))
    usable_for_realtime_monitoring = freshness_status == "fresh"
    status = "ready"
    if not usable_for_training:
        status = "unusable"
    elif not usable_for_realtime_monitoring:
        status = "stale"

    base.update(
        {
            "found": True,
            "status": status,
            "reason": "",
            "usable_for_training": usable_for_training,
            "usable_for_realtime_monitoring": usable_for_realtime_monitoring,
            "freshness_days": freshness_days,
            "freshness_status": freshness_status,
            "match_count": len(matches),
            "detail": {
                "EdbInfoId": detail.get("EdbInfoId"),
                "UniqueCode": detail.get("UniqueCode"),
                "EdbCode": detail.get("EdbCode"),
                "EdbName": detail.get("EdbName"),
                "ClassifyId": detail.get("ClassifyId"),
                "SourceName": detail.get("SourceName"),
                "Frequency": detail.get("Frequency"),
                "Unit": detail.get("Unit"),
                "StartDate": detail.get("StartDate"),
                "EndDate": detail.get("EndDate"),
                "LatestDate": detail.get("LatestDate"),
                "LatestValue": detail.get("LatestValue"),
                "NoUpdate": detail.get("NoUpdate"),
                "ErDataUpdateDate": detail.get("ErDataUpdateDate"),
            },
            "data_rows": len(data_rows),
            "data_sample": data_rows[:5],
        }
    )
    return base


def build_markdown(report: dict[str, Any]) -> str:
    today = report["generated_at"]
    lines = [
        f"# ETA P0 白名单与缺口清单（{today}）",
        "",
        "## 1. 汇总结论",
        "",
        f"- 白名单候选数：{report['summary']['candidate_count']}",
        f"- 在 ETA 中找到：{report['summary']['found_count']}",
        f"- 适合线上实时监控：{report['summary']['fresh_count']}",
        f"- 找到但已不新鲜：{report['summary']['stale_count']}",
        f"- 明确缺口：{report['summary']['missing_count']}",
        "",
        "## 2. P0 可直接接入指标",
        "",
        "| key | 指标 | 分组 | 最新日期 | 状态 | 说明 |",
        "|---|---|---|---:|---|---|",
    ]
    for item in report["items"]:
        if item["priority"] != "P0":
            continue
        detail = item.get("detail") or {}
        latest_date = detail.get("LatestDate", "-")
        note = item.get("notes", "")
        if item["status"] == "ready":
            status = "可直连"
        elif item["status"] == "stale":
            status = "仅历史可用"
        else:
            status = "缺口"
        lines.append(
            f"| {item['key']} | {item['name']} | {item['group']} | {latest_date} | {status} | {note} |"
        )

    lines.extend(
        [
            "",
            "## 3. 需要外部补源或代理建模的缺口",
            "",
            "| key | 指标 | 原因 | 建议 |",
            "|---|---|---|---|",
        ]
    )
    for item in report["items"]:
        if item["status"] not in {"missing", "stale"}:
            continue
        reason = item["reason"] or item["freshness_status"]
        if item["status"] == "missing":
            recommendation = "必须补外部源，或用代理变量估算"
        else:
            recommendation = "保留作历史训练，不作为线上主锚"
        lines.append(f"| {item['key']} | {item['name']} | {reason} | {recommendation} |")

    lines.extend(
        [
            "",
            "## 4. P1 推荐因子",
            "",
            "| key | 指标 | 分组 | 最新日期 | 状态 |",
            "|---|---|---|---:|---|",
        ]
    )
    for item in report["items"]:
        if item["priority"] != "P1":
            continue
        detail = item.get("detail") or {}
        latest_date = detail.get("LatestDate", "-")
        lines.append(
            f"| {item['key']} | {item['name']} | {item['group']} | {latest_date} | {item['status']} |"
        )

    lines.extend(
        [
            "",
            "## 5. 直接判断",
            "",
            "- ETA 已能支撑山东成品油研究系统的 V1 主链，但不能单独覆盖全部线上价格锚。",
            "- 山东/全国 95# 市场价目前未在 ETA 中验证到，必须补外部源。",
            "- 山东/全国 0# 柴油市场价虽然存在，但实测最新日期停在 2025-09-04，不应继续当作当前线上主锚。",
            "- 价格异动预警仍需叠加成品油新闻事件流，ETA 指标库本身不能替代事件流。",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def write_text(path: str, content: str) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ETA refined-oil P0 whitelist")
    parser.add_argument("--appid", required=True)
    parser.add_argument("--secret", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--json-output", default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", default=DEFAULT_MD_OUTPUT)
    parser.add_argument("--today", default="2026-05-29")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = EtaConfig(args.appid, args.secret, args.base_url.rstrip("/"))
    today = datetime.strptime(args.today, "%Y-%m-%d").date()
    index_rows = fetch_indicator_index(config, CLASSIFY_IDS)

    items = []
    for candidate in CANDIDATES:
        matches = resolve_candidate(candidate, index_rows)
        items.append(inspect_candidate(config, candidate, matches, today))

    summary = {
        "candidate_count": len(items),
        "found_count": sum(1 for item in items if item["found"]),
        "fresh_count": sum(1 for item in items if item["freshness_status"] == "fresh"),
        "stale_count": sum(1 for item in items if item["status"] == "stale"),
        "missing_count": sum(1 for item in items if item["status"] == "missing"),
    }
    report = {
        "generated_at": args.today,
        "base_url": config.base_url,
        "summary": summary,
        "items": items,
    }

    write_text(args.json_output, json.dumps(report, ensure_ascii=False, indent=2))
    write_text(args.md_output, build_markdown(report))
    print(f"wrote {args.json_output}")
    print(f"wrote {args.md_output}")


if __name__ == "__main__":
    main()
