import argparse
import base64
import hashlib
import hmac
import json
import random
import string
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


DEFAULT_OUTPUT = "artifacts/eta_edb_scan.json"


@dataclass
class EtaConfig:
    appid: str
    secret: str
    base_url: str


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
    ret = payload.get("Ret")
    if ret != 200:
        raise RuntimeError(f"ETA API failed for {path}: {payload}")
    return payload


def walk_classify_tree(
    nodes: list[dict[str, Any]],
    path: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_path = path or []
    for node in nodes:
        name = node.get("ClassifyName", "")
        next_path = current_path + [name]
        rows.append(
            {
                "classify_id": node.get("ClassifyId"),
                "classify_name": name,
                "unique_code": node.get("UniqueCode"),
                "path": " / ".join(next_path),
                "parent_id": node.get("ParentId"),
            }
        )
        rows.extend(walk_classify_tree(node.get("Child") or [], next_path))
    return rows


def match_keywords(value: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in value]


def fetch_indicator_list(config: EtaConfig, classify_id: int) -> list[dict[str, Any]]:
    payload = eta_get(config, "/v1/edb/list", params={"ClassifyId": classify_id})
    data = payload.get("Data") or []
    if not isinstance(data, list):
        return []
    return data


def summarize_indicators(
    classify_rows: list[dict[str, Any]],
    classify_keywords: list[str],
    indicator_keywords: list[str],
) -> dict[str, Any]:
    matched_classifies = []
    for row in classify_rows:
        hits = match_keywords(row["path"], classify_keywords)
        if hits:
            matched = dict(row)
            matched["hits"] = hits
            matched_classifies.append(matched)

    return {
        "matched_classifies": matched_classifies,
        "indicator_keywords": indicator_keywords,
    }


def scan_eta_edb(
    config: EtaConfig,
    classify_keywords: list[str],
    indicator_keywords: list[str],
    per_class_limit: int = 0,
) -> dict[str, Any]:
    source_list = eta_get(config, "/v1/edb/source/list").get("Data") or []
    classify_tree = eta_get(config, "/v1/edb/classify/tree", params={"ClassifyType": 0}).get("Data") or []
    classify_rows = walk_classify_tree(classify_tree)
    summary = summarize_indicators(classify_rows, classify_keywords, indicator_keywords)

    classify_indicator_hits = []
    unmatched_classifies = []
    for row in summary["matched_classifies"]:
        classify_id = row["classify_id"]
        indicators = fetch_indicator_list(config, int(classify_id))
        matches = []
        for indicator in indicators:
            name = indicator.get("EdbName", "")
            hits = match_keywords(name, indicator_keywords)
            if hits:
                matches.append(
                    {
                        "hits": hits,
                        "edb_info_id": indicator.get("EdbInfoId"),
                        "unique_code": indicator.get("UniqueCode"),
                        "edb_code": indicator.get("EdbCode"),
                        "edb_name": name,
                        "source_name": indicator.get("SourceName"),
                        "frequency": indicator.get("Frequency"),
                        "unit": indicator.get("Unit"),
                        "latest_date": indicator.get("LatestDate"),
                        "latest_value": indicator.get("LatestValue"),
                    }
                )

        classify_payload = {
            "classify_id": classify_id,
            "classify_name": row["classify_name"],
            "path": row["path"],
            "classify_hits": row["hits"],
            "indicator_count": len(indicators),
            "matched_indicator_count": len(matches),
            "matches": matches if per_class_limit <= 0 else matches[:per_class_limit],
        }
        classify_indicator_hits.append(classify_payload)
        if not matches:
            unmatched_classifies.append(classify_payload)

    keyword_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for classify_item in classify_indicator_hits:
        for match in classify_item["matches"]:
            for hit in match["hits"]:
                keyword_buckets[hit].append(
                    {
                        "classify_path": classify_item["path"],
                        "edb_info_id": match["edb_info_id"],
                        "unique_code": match["unique_code"],
                        "edb_code": match["edb_code"],
                        "edb_name": match["edb_name"],
                        "source_name": match["source_name"],
                        "frequency": match["frequency"],
                        "unit": match["unit"],
                        "latest_date": match["latest_date"],
                        "latest_value": match["latest_value"],
                    }
                )

    return {
        "base_url": config.base_url,
        "source_count": len(source_list),
        "sources": source_list,
        "classify_count": len(classify_rows),
        "matched_classify_count": len(summary["matched_classifies"]),
        "matched_classifies": summary["matched_classifies"],
        "classify_indicator_hits": classify_indicator_hits,
        "unmatched_classifies": unmatched_classifies,
        "keyword_buckets": dict(keyword_buckets),
    }


def write_json(payload: dict[str, Any], output: str) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan ETA EDB classify tree and indicator list")
    parser.add_argument("--appid", required=True)
    parser.add_argument("--secret", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--classify-keywords",
        default="能源化工,油,汽油,柴油,山东,地炼,炼厂,燃料,石脑油,MTBE,PX,原油,石油",
    )
    parser.add_argument(
        "--indicator-keywords",
        default="成品油,汽油,柴油,山东,地炼,炼厂,92,95,0#,0号,国六,石脑油,燃料油,MTBE,PX,原油,布伦特",
    )
    parser.add_argument(
        "--per-class-limit",
        type=int,
        default=0,
        help="Maximum matched indicators to keep per classify. Use 0 to keep all matches.",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = EtaConfig(appid=args.appid, secret=args.secret, base_url=args.base_url.rstrip("/"))
    classify_keywords = [item.strip() for item in args.classify_keywords.split(",") if item.strip()]
    indicator_keywords = [item.strip() for item in args.indicator_keywords.split(",") if item.strip()]
    payload = scan_eta_edb(
        config,
        classify_keywords,
        indicator_keywords,
        per_class_limit=args.per_class_limit,
    )
    path = write_json(payload, args.output)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
