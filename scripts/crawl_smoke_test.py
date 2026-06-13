import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch(url: str) -> tuple[requests.Response, BeautifulSoup]:
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    return response, BeautifulSoup(response.text, "html.parser")


def text_lines(node: BeautifulSoup | Any) -> list[str]:
    return [line.strip() for line in node.get_text("\n", strip=True).splitlines() if line.strip()]


def first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.S)
    return match.group(1).strip() if match else None


def ndrc_notice_test() -> dict[str, Any]:
    url = "https://www.ndrc.gov.cn/xwdt/xwfb/202404/t20240416_1365703_ext.html"
    response, soup = fetch(url)
    body = "\n".join(text_lines(soup))
    gas_raise = diesel_raise = None
    price_match = re.search(r"每吨\s*分别提高\s*([0-9]+)\s*元、\s*([0-9]+)\s*元", body)
    if price_match:
        gas_raise = int(price_match.group(1))
        diesel_raise = int(price_match.group(2))
    return {
        "source": "ndrc_notice",
        "url": url,
        "http_status": response.status_code,
        "access_level": "full",
        "title": soup.title.get_text(strip=True) if soup.title else None,
        "notice_title": first_match(r"新闻发布\s*(.*?)\s*2024/04/16", body),
        "publish_date": first_match(r"(\d{4}/\d{2}/\d{2})", body),
        "source_org": first_match(r"\d{4}/\d{2}/\d{2}\s+([^\n]+)", body),
        "gasoline_raise_yuan_per_ton": gas_raise,
        "diesel_raise_yuan_per_ton": diesel_raise,
        "content_preview": body[:260],
    }


def oilchem_list_test() -> dict[str, Any]:
    url = "https://oil.oilchem.net/oil/refinedoil.shtml"
    response, soup = fetch(url)
    sections: list[dict[str, Any]] = []
    for section in soup.select("div.channelmain3.left")[:4]:
        lines = text_lines(section)
        if not lines:
            continue
        name = lines[0]
        items = []
        seen = set()
        for a in section.find_all("a", href=True):
            headline = " ".join(a.get_text(" ", strip=True).split())
            href = urljoin(response.url, a["href"])
            if len(headline) < 8 or not href.endswith(".html"):
                continue
            key = (headline, href)
            if key in seen:
                continue
            seen.add(key)
            items.append({"headline": headline, "url": href})
            if len(items) >= 6:
                break
        sections.append(
            {
                "section_name": name,
                "item_count_sampled": len(items),
                "items": items,
            }
        )
    return {
        "source": "oilchem_refinedoil_channel",
        "url": url,
        "http_status": response.status_code,
        "access_level": "list_only",
        "title": soup.title.get_text(strip=True) if soup.title else None,
        "sections": sections,
    }


def oilchem_paywall_test() -> dict[str, Any]:
    url = "https://www.oilchem.net/26-0528-11-699687949b185102.html"
    response, soup = fetch(url)
    body = "\n".join(text_lines(soup))
    paywall_markers = [
        "会员登录",
        "免费开通",
        "15天的免费浏览权",
        "若需浏览此条信息",
    ]
    marker_hits = [marker for marker in paywall_markers if marker in body]
    return {
        "source": "oilchem_detail_paywall",
        "url": url,
        "http_status": response.status_code,
        "access_level": "metadata_only" if marker_hits else "full",
        "title": soup.title.get_text(strip=True) if soup.title else None,
        "publish_time": first_match(r"发布时间：\s*([0-9:\-\s]+)", body),
        "source_org": first_match(r"来源：\s*([^\s]+)", body),
        "paywall_markers": marker_hits,
        "content_preview": body[:260],
    }


def i315_home_test() -> dict[str, Any]:
    url = "https://oil.315i.com/"
    response, soup = fetch(url)
    table = soup.select_one("div#b2b1 table.sj_table")
    rows: list[dict[str, Any]] = []
    if table:
        for tr in table.find_all("tr"):
            cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")]
            if len(cells) != 6:
                continue
            rows.append(
                {
                    "product_name": cells[0],
                    "entity": cells[1],
                    "spec": cells[2],
                    "price": cells[3],
                    "unit": cells[4],
                    "change": cells[5],
                }
            )
            if len(rows) >= 12:
                break
    return {
        "source": "i315_home_snapshot",
        "url": url,
        "http_status": response.status_code,
        "access_level": "partial",
        "title": soup.title.get_text(strip=True) if soup.title else None,
        "sample_rows": rows,
    }


def i315_detail_test() -> dict[str, Any]:
    url = (
        "https://jiag.315i.com/price/main?"
        "productClassId=001002&columnClassId=001002004&timeType=0&finalNotColumn=1"
    )
    response, soup = fetch(url)
    tables = soup.find_all("table")
    header_row = []
    sample_items = []
    if len(tables) >= 2:
        headers = tables[1].find("tr")
        if headers:
            header_row = [
                " ".join(cell.get_text(" ", strip=True).split())
                for cell in headers.find_all(["th", "td"])
            ]
        for tr in tables[1].find_all("tr")[1:6]:
            cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")[:5]]
            if len(cells) >= 5:
                sample_items.append(
                    {
                        "refinery": cells[1],
                        "product_name": cells[2],
                        "spec": cells[3],
                        "standard": cells[4],
                    }
                )
    locked_cell_count = response.text.count("未登录")
    return {
        "source": "i315_local_refinery_detail",
        "url": url,
        "http_status": response.status_code,
        "access_level": "metadata_only" if locked_cell_count else "full",
        "title": soup.title.get_text(" ", strip=True) if soup.title else None,
        "table_headers": header_row,
        "sample_items": sample_items,
        "locked_cell_marker_count": locked_cell_count,
    }


def baiinfo_article_test() -> dict[str, Any]:
    url = "https://www.baiinfo.com/news/2073/35364596/s2"
    response, soup = fetch(url)
    article = soup.select_one("div.article-detail") or soup.select_one("div.content") or soup
    body = "\n".join(text_lines(article))
    return {
        "source": "baiinfo_article",
        "url": url,
        "http_status": response.status_code,
        "access_level": "full",
        "title": soup.title.get_text(strip=True) if soup.title else None,
        "source_org": first_match(r"来源：\s*([^\s]+)", body),
        "publish_date": first_match(r"更新时间：\s*([0-9年月日\-]+)", body),
        "content_preview": body[:320],
        "contains_brent": "布伦特" in body,
        "content_length": len(body),
    }


def run_tests() -> dict[str, Any]:
    tests = [
        ndrc_notice_test(),
        oilchem_list_test(),
        oilchem_paywall_test(),
        i315_home_test(),
        i315_detail_test(),
        baiinfo_article_test(),
    ]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "tests": tests,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run crawler smoke tests for refined-oil data sources.")
    parser.add_argument(
        "--output",
        default="artifacts/crawl_smoke_test_results.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    result = run_tests()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {output_path}")
    for item in result["tests"]:
        print(
            f"{item['source']}: status={item['http_status']} "
            f"access={item['access_level']} url={item['url']}"
        )


if __name__ == "__main__":
    main()
