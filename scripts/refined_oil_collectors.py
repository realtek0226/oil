import argparse
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup, Tag


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def fetch(url: str) -> tuple[requests.Response, BeautifulSoup]:
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    return response, BeautifulSoup(response.text, "html.parser")


def write_json(payload: dict[str, Any], output_path: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_float_maybe(value: str | None) -> float | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate or candidate in {"-", "--", "/"}:
        return None
    try:
        return float(candidate)
    except ValueError:
        return None


def parse_int_maybe(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"-?\d+", value)
    return int(match.group(0)) if match else None


def soup_text(soup: BeautifulSoup | Tag) -> str:
    return "\n".join(clean_lines(soup.get_text("\n", strip=True)))


def find_latest_ndrc_notice(list_url: str) -> dict[str, Any]:
    response, soup = fetch(list_url)
    items = []
    for a in soup.find_all("a", href=True):
        title = clean_text(a.get_text(" ", strip=True))
        href = urljoin(response.url, a["href"])
        if "成品油" not in title:
            continue
        if not href.startswith("https://www.ndrc.gov.cn/"):
            continue
        items.append({"title": title, "url": href})
    deduped = []
    seen = set()
    for item in items:
        key = (item["title"], item["url"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    if not deduped:
        raise RuntimeError("No NDRC refined-oil notice found in listing page.")
    return {
        "list_url": list_url,
        "discovered_at_utc": now_utc_iso(),
        "latest_notice": deduped[0],
        "candidates": deduped[:10],
    }


def parse_ndrc_notice(notice_url: str) -> dict[str, Any]:
    response, soup = fetch(notice_url)
    body = soup_text(soup)
    lines = clean_lines(body)

    title = None
    publish_date = None
    source_org = None
    gasoline_change_yuan_per_ton = None
    diesel_change_yuan_per_ton = None
    effective_time = None

    for line in lines:
        if "成品油价格" in line and "国家发展和改革委员会" not in line:
            title = clean_text(line)
            break

    publish_match = re.search(r"(\d{4}/\d{2}/\d{2})", body)
    if publish_match:
        publish_date = publish_match.group(1)

    org_match = re.search(r"来源[:：]?\s*\n?\s*([^\n\[]+)", body)
    if org_match:
        source_org = clean_text(org_match.group(1))

    change_match = re.search(
        r"(?:每吨|价格每吨)\s*分别(?:提高|上调|下调|降低)\s*([0-9]+)\s*元[、和]\s*([0-9]+)\s*元",
        body,
    )
    if change_match:
        gasoline_change_yuan_per_ton = int(change_match.group(1))
        diesel_change_yuan_per_ton = int(change_match.group(2))
        if "下调" in body or "降低" in body:
            gasoline_change_yuan_per_ton *= -1
            diesel_change_yuan_per_ton *= -1

    effective_match = re.search(r"自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日24时起", body)
    if effective_match:
        effective_time = (
            f"{effective_match.group(1)}-"
            f"{int(effective_match.group(2)):02d}-"
            f"{int(effective_match.group(3)):02d} 24:00"
        )
    elif publish_date:
        short_effective_match = re.search(r"自\s*(\d{1,2})月(\d{1,2})日24时起", body)
        if short_effective_match:
            publish_year = publish_date[:4]
            effective_time = (
                f"{publish_year}-{int(short_effective_match.group(1)):02d}-"
                f"{int(short_effective_match.group(2)):02d} 24:00"
            )

    return {
        "source": "ndrc_notice",
        "url": response.url,
        "fetched_at_utc": now_utc_iso(),
        "title": title or (soup.title.get_text(strip=True) if soup.title else None),
        "publish_date": publish_date,
        "source_org": source_org,
        "gasoline_change_yuan_per_ton": gasoline_change_yuan_per_ton,
        "diesel_change_yuan_per_ton": diesel_change_yuan_per_ton,
        "effective_time": effective_time,
        "content_preview": body[:400],
    }


def find_best_price_table(soup: BeautifulSoup) -> Tag | None:
    best_table = None
    best_score = -1
    for table in soup.find_all("table"):
        text = clean_text(table.get_text(" ", strip=True))
        score = 0
        for token in ["汽油", "柴油", "元/吨", "元/升", "零售价", "批发价", "标号", "型号"]:
            if token in text:
                score += 1
        if score > best_score:
            best_score = score
            best_table = table
    return best_table if best_score > 0 else None


def table_to_rows(table: Tag) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["th", "td"])]
        if any(cells):
            rows.append(cells)
    return rows


def extract_price_rows(rows: list[list[str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    # Template A: Shanghai style, two-row per product, one with 元/吨 and one with 元/升.
    if rows and rows[0][:3] == ["标 号", "单 位", "最高零售价"]:
        current_item: dict[str, Any] | None = None
        for row in rows[1:]:
            if len(row) >= 3 and any(keyword in row[0] for keyword in ["汽油", "柴油"]):
                current_item = {
                    "oil_name": row[0],
                    "price_ton": parse_float_maybe(row[2]) if row[1] == "元/吨" else None,
                    "price_liter": parse_float_maybe(row[2]) if row[1] == "元/升" else None,
                    "wholesale_ton": None,
                }
                results.append(current_item)
            elif current_item and len(row) >= 2 and row[0] == "元/升":
                current_item["price_liter"] = parse_float_maybe(row[1])
        return results

    # Template B: Zhejiang style, one row per product.
    if rows and any("零售价" in cell for cell in rows[0]) and any("批发价" in cell for cell in rows[0]):
        header = rows[0]
        for row in rows[1:]:
            if len(row) < 5:
                continue
            if row[0] not in {"汽油", "柴油"}:
                continue
            oil_name = f"{row[1]}{row[0]}"
            results.append(
                {
                    "oil_name": oil_name,
                    "price_ton": parse_float_maybe(row[2]),
                    "price_liter": parse_float_maybe(row[3]),
                    "wholesale_ton": parse_float_maybe(row[4]),
                }
            )
        return results

    return results


def parse_local_fgw_notice(region_code: str, url: str, province_name: str) -> dict[str, Any]:
    response, soup = fetch(url)
    body = soup_text(soup)
    table = find_best_price_table(soup)
    rows = table_to_rows(table) if table else []
    prices = extract_price_rows(rows)

    title = clean_text(soup.title.get_text(strip=True)) if soup.title else None
    publish_date = None
    for pattern in [
        r"发布日期[:：]?\s*(\d{4}[-年/]\d{1,2}[-月/]\d{1,2}日?)",
        r"成文日期[:：]?\s*(\d{4}[-年/]\d{1,2}[-月/]\d{1,2}日?)",
        r"(\d{4}年\d{1,2}月\d{1,2}日)",
    ]:
        match = re.search(pattern, body)
        if match:
            publish_date = clean_text(match.group(1))
            break

    effective_time = None
    effective_match = re.search(r"自(\d{4}年\d{1,2}月\d{1,2}日)24时起", body)
    if effective_match:
        effective_time = clean_text(effective_match.group(1)) + " 24:00"

    return {
        "source": "local_fgw_notice",
        "region_code": region_code,
        "province_name": province_name,
        "url": response.url,
        "fetched_at_utc": now_utc_iso(),
        "title": title,
        "publish_date": publish_date,
        "effective_time": effective_time,
        "price_items": prices,
        "raw_table_rows": rows,
        "content_preview": body[:400],
    }


@dataclass
class EjiayouConfig:
    base_url: str
    platform_name: str
    before_key: str
    after_key: str
    page_size: int = 100
    station_pages_path_template: str = (
        "/oreo/ejiayou_open_api/stations/v2/getStationPages/"
        "{currentPage}/{pageSize}/{platformName}/{sign}/{timestamp}"
    )


def build_ejiayou_sign(before_key: str, timestamp_seconds: int, after_key: str) -> str:
    source = f"{before_key}{timestamp_seconds}{after_key}"
    return hashlib.md5(source.encode("utf-8")).hexdigest().upper()


def load_ejiayou_config() -> EjiayouConfig:
    base_url = os.getenv("EJIAYOU_BASE_URL", "https://pre.ejiayou.com").rstrip("/")
    platform_name = os.getenv("EJIAYOU_PLATFORM_NAME")
    before_key = os.getenv("EJIAYOU_BEFORE_KEY")
    after_key = os.getenv("EJIAYOU_AFTER_KEY")
    page_size = int(os.getenv("EJIAYOU_PAGE_SIZE", "100"))
    path_template = os.getenv(
        "EJIAYOU_STATION_PAGES_PATH_TEMPLATE",
        (
            "/oreo/ejiayou_open_api/stations/v2/getStationPages/"
            "{currentPage}/{pageSize}/{platformName}/{sign}/{timestamp}"
        ),
    )
    if not platform_name or not before_key or not after_key:
        raise RuntimeError(
            "Missing EJIAYOU credentials. Set EJIAYOU_PLATFORM_NAME, "
            "EJIAYOU_BEFORE_KEY, EJIAYOU_AFTER_KEY."
        )
    return EjiayouConfig(
        base_url=base_url,
        platform_name=platform_name,
        before_key=before_key,
        after_key=after_key,
        page_size=page_size,
        station_pages_path_template=path_template,
    )


def build_ejiayou_station_page_url(config: EjiayouConfig, current_page: int) -> tuple[str, int, str]:
    timestamp_seconds = int(time.time())
    sign = build_ejiayou_sign(config.before_key, timestamp_seconds, config.after_key)
    path = config.station_pages_path_template.format(
        currentPage=current_page,
        pageSize=config.page_size,
        platformName=config.platform_name,
        sign=sign,
        timestamp=timestamp_seconds,
    )
    return f"{config.base_url}{path}", timestamp_seconds, sign


def normalize_ejiayou_station(record: dict[str, Any]) -> dict[str, Any]:
    prices = []
    for item in record.get("prices", []) or []:
        prices.append(
            {
                "oil_code": item.get("oilCode"),
                "oil_type": item.get("oilType"),
                "country_price": parse_float_maybe(str(item.get("countryPrice", ""))),
                "station_price": parse_float_maybe(str(item.get("stationPrice", ""))),
                "discount_price": parse_float_maybe(str(item.get("discountPrice", ""))),
                "oilgun_codes": item.get("oilgunCodes") or [],
            }
        )
    return {
        "station_id": str(record.get("stationId", "")),
        "station_name": record.get("stationName"),
        "province_name": clean_text(str(record.get("provinceName", ""))),
        "city_name": clean_text(str(record.get("cityName", ""))),
        "district": clean_text(str(record.get("district", ""))),
        "province_id": record.get("provinceId"),
        "city_id": record.get("cityId"),
        "latitude_bd": parse_float_maybe(str(record.get("latitude", ""))),
        "longitude_bd": parse_float_maybe(str(record.get("longitude", ""))),
        "location": record.get("location"),
        "station_type": record.get("stationType"),
        "phone": record.get("phone"),
        "prices": prices,
        "raw_adverts": record.get("adverts") or record.get("Adverts") or [],
    }


def collect_ejiayou_station_page(current_page: int) -> dict[str, Any]:
    config = load_ejiayou_config()
    url, timestamp_seconds, sign = build_ejiayou_station_page_url(config, current_page=current_page)
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    payload = response.json()
    raw_items = payload.get("data") or []
    normalized_items = [normalize_ejiayou_station(item) for item in raw_items]
    return {
        "source": "ejiayou_station_pages",
        "base_url": config.base_url,
        "request_url": url,
        "platform_name": config.platform_name,
        "timestamp_seconds": timestamp_seconds,
        "sign": sign,
        "current_page": current_page,
        "page_size": config.page_size,
        "fetched_at_utc": now_utc_iso(),
        "api_code": payload.get("code"),
        "api_msg": payload.get("msg"),
        "station_count": len(normalized_items),
        "stations": normalized_items,
    }


def normalize_ejiayou_sample(sample_path: str) -> dict[str, Any]:
    with open(sample_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    raw_items = payload.get("data") or []
    normalized_items = [normalize_ejiayou_station(item) for item in raw_items]
    return {
        "source": "ejiayou_sample_normalized",
        "sample_path": sample_path,
        "generated_at_utc": now_utc_iso(),
        "station_count": len(normalized_items),
        "stations": normalized_items,
    }


def load_province_templates(config_path: str) -> dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run_ndrc_latest(output_path: str) -> Path:
    listing = find_latest_ndrc_notice("https://www.ndrc.gov.cn/xwdt/xwfb/")
    notice = parse_ndrc_notice(listing["latest_notice"]["url"])
    payload = {"generated_at_utc": now_utc_iso(), "listing": listing, "notice": notice}
    return write_json(payload, output_path)


def run_local_templates(config_path: str, output_path: str) -> Path:
    config = load_province_templates(config_path)
    results = []
    for item in config.get("templates", []):
        if not item.get("sample_url"):
            continue
        results.append(
            parse_local_fgw_notice(
                region_code=item["region_code"],
                url=item["sample_url"],
                province_name=item["province_name"],
            )
        )
    payload = {
        "generated_at_utc": now_utc_iso(),
        "config_path": config_path,
        "results": results,
    }
    return write_json(payload, output_path)


def run_ejiayou(current_page: int, output_path: str) -> Path:
    payload = collect_ejiayou_station_page(current_page=current_page)
    return write_json(payload, output_path)


def run_ejiayou_sample(sample_path: str, output_path: str) -> Path:
    payload = normalize_ejiayou_sample(sample_path)
    return write_json(payload, output_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refined-oil data collectors")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ndrc_parser = subparsers.add_parser("ndrc-latest", help="Collect latest NDRC refined-oil notice")
    ndrc_parser.add_argument(
        "--output",
        default="artifacts/ndrc_latest_notice.json",
        help="Output JSON path",
    )

    local_parser = subparsers.add_parser("local-fgw-samples", help="Collect sample local FGW notices")
    local_parser.add_argument(
        "--config",
        default="configs/province_price_templates.yaml",
        help="Province template config path",
    )
    local_parser.add_argument(
        "--output",
        default="artifacts/local_fgw_samples.json",
        help="Output JSON path",
    )

    ejiayou_parser = subparsers.add_parser("ejiayou-stations", help="Call Ejiayou station pages API")
    ejiayou_parser.add_argument("--page", type=int, default=1, help="Current page")
    ejiayou_parser.add_argument(
        "--output",
        default="artifacts/ejiayou_station_page.json",
        help="Output JSON path",
    )

    ejiayou_sample_parser = subparsers.add_parser(
        "ejiayou-sample",
        help="Normalize documented Ejiayou sample response",
    )
    ejiayou_sample_parser.add_argument(
        "--sample",
        default="artifacts/ejiayou_station_pages_sample.json",
        help="Sample response JSON path",
    )
    ejiayou_sample_parser.add_argument(
        "--output",
        default="artifacts/ejiayou_station_pages_sample_normalized.json",
        help="Output JSON path",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ndrc-latest":
        path = run_ndrc_latest(args.output)
    elif args.command == "local-fgw-samples":
        path = run_local_templates(args.config, args.output)
    elif args.command == "ejiayou-stations":
        path = run_ejiayou(args.page, args.output)
    elif args.command == "ejiayou-sample":
        path = run_ejiayou_sample(args.sample, args.output)
    else:
        raise RuntimeError(f"Unsupported command: {args.command}")

    print(f"wrote {path}")


if __name__ == "__main__":
    main()
