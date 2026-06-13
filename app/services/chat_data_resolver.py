from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd

from app.services.market_dataset import MarketDatasetService


@dataclass(frozen=True)
class ChatDataResult:
    answered: bool
    source: str = "database"
    title: str = ""
    summary: str = ""
    fields: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "answered": self.answered,
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "fields": self.fields,
            "rows": self.rows,
            "metadata": self.metadata,
        }


class ChatDataResolver:
    FIELD_SPECS: dict[str, tuple[str, str, tuple[str, ...]]] = {
        "brent_active_settlement": ("Brent 结算价", "美元/桶", ("brent", "布伦特", "原油")),
        "sd_gas92_market": ("山东 92# 汽油", "元/吨", ("山东92", "山东 92", "山东汽油", "山东油价")),
        "cn_gas92_market": ("全国 92# 汽油", "元/吨", ("全国92", "全国 92", "全国汽油")),
        "east_china_gas92_market": ("华东 92# 汽油", "元/吨", ("华东",)),
        "north_china_gas92_market": ("华北 92# 汽油", "元/吨", ("华北",)),
        "south_china_gas92_market": ("华南 92# 汽油", "元/吨", ("华南",)),
        "central_china_gas92_market": ("华中 92# 汽油", "元/吨", ("华中",)),
        "northwest_gas92_market": ("西北 92# 汽油", "元/吨", ("西北",)),
        "southwest_gas92_market": ("西南 92# 汽油", "元/吨", ("西南",)),
        "northeast_gas92_market": ("东北 92# 汽油", "元/吨", ("东北",)),
        "sales_production_ratio_d1": ("山东地炼产销率", "%", ("产销率",)),
        "sales_production_ratio_d3_avg": ("山东地炼产销率 3日均值", "%", ("3日产销率", "三日产销率")),
        "sales_production_ratio_w1_avg": ("山东地炼产销率 7日均值", "%", ("7日产销率", "周度产销率")),
        "sd_crude_run_weekly": ("山东地炼常减压开工率", "%", ("开工率", "产能利用率")),
        "sd_refining_profit": ("山东炼油利润", "元/吨", ("炼油利润", "利润")),
        "shandong_product_inventory_total_formal": ("库存合计：贸易商+主营+独立炼厂", "万吨", ("库存合计", "总库存")),
        "shandong_trader_inventory": ("贸易商库存", "万吨", ("贸易商库存",)),
        "shandong_main_company_inventory": ("主营库存", "万吨", ("主营库存",)),
        "shandong_independent_refinery_inventory": ("独立炼厂库存", "万吨", ("独立炼厂库存", "炼厂库存")),
        "price_adjustment_expected_yuan": ("发改委调价预测金额", "元/吨", ("调价预测", "调价金额", "发改委")),
        "sd_gas_crack": ("山东 92# 汽油裂解价差", "元/吨", ("裂解价差",)),
    }

    DATA_KEYWORDS = (
        "价格",
        "油价",
        "数据",
        "多少",
        "走势",
        "历史",
        "产销率",
        "开工率",
        "产能利用率",
        "利润",
        "库存",
        "调价",
        "价差",
        "裂解",
        "运费",
        "新闻",
        "资讯",
        "政策",
        "事件",
    )
    PREDICTION_KEYWORDS = ("预测", "研判", "点位", "区间", "趋势", "经营建议", "怎么看", "D1", "D3", "W1", "M1")

    def __init__(self, dataset_service: MarketDatasetService) -> None:
        self.dataset_service = dataset_service

    def resolve(self, *, message: str, as_of_date: date) -> ChatDataResult:
        text = message.strip()
        if not text:
            return ChatDataResult(answered=False)
        if self._looks_like_prediction_request(text):
            return ChatDataResult(answered=False)
        if any(keyword in text for keyword in ("新闻", "资讯", "政策", "事件")):
            return self._resolve_policy_events(text=text, as_of_date=as_of_date)
        if not any(keyword in text for keyword in self.DATA_KEYWORDS):
            return ChatDataResult(answered=False)

        fields = self._match_fields(text)
        if not fields:
            return ChatDataResult(answered=False)
        start_date, end_date = self._parse_date_range(text=text, as_of_date=as_of_date)
        if self._should_use_realtime_brent(text=text, fields=fields, start_date=start_date, end_date=end_date, as_of_date=as_of_date):
            return self._resolve_realtime_brent(as_of_date=as_of_date)
        try:
            frame = self.dataset_service.build_feature_frame(start_date=start_date, end_date=end_date)
        except Exception as exc:
            return ChatDataResult(
                answered=False,
                metadata={"error": str(exc), "reason": "database_query_failed"},
            )
        if frame.empty:
            if start_date == end_date:
                rows = self._latest_available_rows(fields=fields, end_date=end_date)
                if rows:
                    latest_date = rows[-1].get("date")
                    fallback_prefix = (
                        f"{start_date.isoformat()} 已返回系统最新价格口径："
                        if latest_date == start_date.isoformat()
                        else f"{start_date.isoformat()} 没有查到当日有效值，已返回最新可用日期 {latest_date}："
                    )
                    return ChatDataResult(
                        answered=True,
                        title="数据库查询结果",
                        summary=fallback_prefix
                        + self._build_summary(
                            rows=rows,
                            fields=fields,
                            start_date=start_date,
                            end_date=end_date,
                        ).split("：", 1)[-1],
                        fields=fields,
                        rows=rows,
                        metadata={
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "field_labels": {field: self.FIELD_SPECS[field][0] for field in fields},
                            "units": {field: self.FIELD_SPECS[field][1] for field in fields},
                            "latest_fallback": True,
                        },
                    )
            return ChatDataResult(
                answered=True,
                title="数据库查询结果",
                summary=f"{start_date.isoformat()} 至 {end_date.isoformat()} 没有查到可用数据。",
                fields=fields,
                rows=[],
                metadata={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            )

        rows = self._frame_rows(frame=frame, fields=fields, start_date=start_date, end_date=end_date)
        latest_fallback = False
        if not rows and start_date == end_date:
            rows = self._latest_available_rows(fields=fields, end_date=end_date)
            latest_fallback = bool(rows)
        summary = self._build_summary(rows=rows, fields=fields, start_date=start_date, end_date=end_date)
        if latest_fallback:
            latest_date = rows[-1].get("date")
            fallback_prefix = (
                f"{start_date.isoformat()} 已返回系统最新价格口径："
                if latest_date == start_date.isoformat()
                else f"{start_date.isoformat()} 没有查到当日有效值，已返回最新可用日期 {latest_date}："
            )
            summary = fallback_prefix + summary.split("：", 1)[-1]
        return ChatDataResult(
            answered=True,
            title="数据库查询结果",
            summary=summary,
            fields=fields,
            rows=rows,
            metadata={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "field_labels": {field: self.FIELD_SPECS[field][0] for field in fields},
                "units": {field: self.FIELD_SPECS[field][1] for field in fields},
                "latest_fallback": latest_fallback,
            },
        )

    def _looks_like_prediction_request(self, text: str) -> bool:
        lowered = text.upper()
        return any(keyword in text or keyword in lowered for keyword in self.PREDICTION_KEYWORDS)

    def _match_fields(self, text: str) -> list[str]:
        matched: list[str] = []
        normalized = re.sub(r"\s+", "", text.lower())
        for field, (_label, _unit, keywords) in self.FIELD_SPECS.items():
            if any(re.sub(r"\s+", "", keyword.lower()) in normalized for keyword in keywords):
                matched.append(field)
        if "区域" in text or "各区域" in text:
            for field in (
                "east_china_gas92_market",
                "north_china_gas92_market",
                "south_china_gas92_market",
                "central_china_gas92_market",
                "northwest_gas92_market",
                "southwest_gas92_market",
                "northeast_gas92_market",
            ):
                if field not in matched:
                    matched.append(field)
        return matched[:12]

    def _should_use_realtime_brent(
        self,
        *,
        text: str,
        fields: list[str],
        start_date: date,
        end_date: date,
        as_of_date: date,
    ) -> bool:
        if fields != ["brent_active_settlement"]:
            return False
        if start_date != end_date or end_date != as_of_date:
            return False
        return any(keyword in text for keyword in ("实时", "当前", "现在", "今天", "最新"))

    def _resolve_realtime_brent(self, *, as_of_date: date) -> ChatDataResult:
        try:
            payload = self.dataset_service.get_brent_realtime_snapshot(as_of_date=as_of_date)
        except Exception as exc:
            return ChatDataResult(answered=False, metadata={"error": str(exc), "reason": "brent_realtime_failed"})
        value = payload.get("latest_price")
        generated_at = payload.get("generated_at")
        row = {
            "date": as_of_date.isoformat(),
            "brent_active_settlement": value,
            "generated_at": generated_at.isoformat() if hasattr(generated_at, "isoformat") else generated_at,
        }
        return ChatDataResult(
            answered=True,
            title="Brent 实时价格",
            summary=f"Brent 最新价格 {value}美元/桶，更新时间 {row['generated_at'] or '-'}。",
            fields=["brent_active_settlement"],
            rows=[row],
            metadata={
                "start_date": as_of_date.isoformat(),
                "end_date": as_of_date.isoformat(),
                "field_labels": {"brent_active_settlement": "Brent 最新价格"},
                "units": {"brent_active_settlement": "美元/桶"},
                "source": "brent_realtime_snapshot",
                "raw_metadata": payload.get("metadata") or {},
            },
        )

    def _parse_date_range(self, *, text: str, as_of_date: date) -> tuple[date, date]:
        iso_dates = [date.fromisoformat(item) for item in re.findall(r"20\d{2}-\d{1,2}-\d{1,2}", text)]
        if len(iso_dates) >= 2:
            return min(iso_dates), max(iso_dates)
        if len(iso_dates) == 1:
            return iso_dates[0], iso_dates[0]

        month_day_matches = re.findall(r"(\d{1,2})月(\d{1,2})日?", text)
        month_days = []
        for month_raw, day_raw in month_day_matches:
            try:
                month_days.append(date(as_of_date.year, int(month_raw), int(day_raw)))
            except ValueError:
                continue
        if len(month_days) >= 2:
            return min(month_days), max(month_days)
        if len(month_days) == 1:
            return month_days[0], month_days[0]

        recent_match = re.search(r"最近\s*(\d{1,3})\s*天", text)
        if recent_match:
            days = max(1, min(int(recent_match.group(1)), 365))
            return as_of_date - timedelta(days=days - 1), as_of_date
        if "昨天" in text:
            target = as_of_date - timedelta(days=1)
            return target, target
        if "前天" in text:
            target = as_of_date - timedelta(days=2)
            return target, target
        if "本周" in text:
            return as_of_date - timedelta(days=as_of_date.weekday()), as_of_date
        if "本月" in text:
            return as_of_date.replace(day=1), as_of_date
        if "历史" in text or "走势" in text:
            return as_of_date - timedelta(days=29), as_of_date
        return as_of_date, as_of_date

    def _frame_rows(
        self,
        *,
        frame: pd.DataFrame,
        fields: list[str],
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        working = frame.copy()
        working["date"] = pd.to_datetime(working["date"]).dt.date
        working = working[(working["date"] >= start_date) & (working["date"] <= end_date)].sort_values("date")
        rows: list[dict[str, Any]] = []
        for _, item in working.iterrows():
            row: dict[str, Any] = {"date": item["date"].isoformat()}
            has_value = False
            for field in fields:
                value = self._round_or_none(item.get(field))
                row[field] = value
                has_value = has_value or value is not None
            if has_value:
                rows.append(row)
        return rows[-60:]

    def _latest_available_rows(self, *, fields: list[str], end_date: date) -> list[dict[str, Any]]:
        try:
            frame = self.dataset_service.build_feature_frame(start_date=end_date - timedelta(days=30), end_date=end_date)
        except Exception:
            return []
        rows = self._frame_rows(
            frame=frame,
            fields=fields,
            start_date=end_date - timedelta(days=30),
            end_date=end_date,
        )
        return rows[-1:] if rows else []

    def _build_summary(self, *, rows: list[dict[str, Any]], fields: list[str], start_date: date, end_date: date) -> str:
        if not rows:
            return f"{start_date.isoformat()} 至 {end_date.isoformat()} 没有查到这些字段的有效值。"
        latest = rows[-1]
        parts = []
        for field in fields[:6]:
            label, unit, _keywords = self.FIELD_SPECS[field]
            value = latest.get(field)
            if value is not None:
                parts.append(f"{label} {value}{unit}")
        return f"数据库命中 {len(rows)} 条记录，最新日期 {latest.get('date')}：" + "；".join(parts)

    def _resolve_policy_events(self, *, text: str, as_of_date: date) -> ChatDataResult:
        try:
            feed = self.dataset_service.build_policy_event_feed(
                news_date=as_of_date,
                policy_date=as_of_date,
                sort_mode="importance",
            )
        except Exception as exc:
            return ChatDataResult(answered=False, metadata={"error": str(exc), "reason": "policy_feed_failed"})
        items: list[dict[str, Any]] = []
        if "政策" in text:
            items.extend(feed.get("policy_items") or [])
        if "新闻" in text or "资讯" in text:
            items.extend(feed.get("refined_news_items") or [])
        if "事件" in text or "快讯" in text:
            items.extend(feed.get("event_news_items") or [])
        if not items:
            items = [
                *(feed.get("policy_items") or [])[:3],
                *(feed.get("refined_news_items") or [])[:3],
                *(feed.get("event_news_items") or [])[:3],
            ]
        rows = [
            {
                "time": item.get("publish_time") or item.get("effective_time") or item.get("publish_date") or item.get("_item_date"),
                "title": item.get("title") or item.get("headline"),
                "source": item.get("source"),
                "importance": item.get("_importance_score") or item.get("importance_score") or item.get("relevance_score"),
                "summary": item.get("summary") or item.get("content") or item.get("impact"),
            }
            for item in items[:12]
        ]
        return ChatDataResult(
            answered=True,
            title="政策与事件归档",
            summary=f"数据库归档命中 {len(rows)} 条政策/资讯/事件记录。",
            fields=["time", "title", "source", "importance", "summary"],
            rows=rows,
            metadata={"as_of_date": as_of_date.isoformat()},
        )

    def _round_or_none(self, value: Any) -> float | None:
        try:
            if value is None or pd.isna(value):
                return None
            return round(float(value), 4)
        except Exception:
            return None
