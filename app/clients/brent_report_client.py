from __future__ import annotations

import os
import re
from datetime import date
from typing import Any

import requests


REPORT_URL = os.getenv("BRENT_REPORT_URL", "")


class BrentReportClient:
    def fetch_latest(self) -> dict[str, Any]:
        if not REPORT_URL:
            raise RuntimeError("Brent report API URL is not configured")
        response = requests.get(REPORT_URL, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Brent report API returned invalid payload: {payload}")
        data = payload["data"]
        markdown = data.get("markdownReport", "")
        return {
            "report_date": data.get("reportDate"),
            "title": data.get("title"),
            "markdown": markdown,
            "signals": self._extract_signals(markdown),
        }

    def normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload or {})
        markdown = str(normalized.get("markdown") or "")
        if markdown:
            normalized["signals"] = self._extract_signals(markdown)
        return normalized

    def _extract_signals(self, markdown: str) -> dict[str, Any]:
        brent_settlement = None
        brent_close = None
        brent_settlement_change_usd = None
        brent_settlement_change_pct = None
        market_snapshot = self._extract_brent_market_snapshot(markdown)
        if market_snapshot:
            brent_close = market_snapshot.get("close")
            brent_settlement = market_snapshot.get("settlement")
            brent_settlement_change_usd = market_snapshot.get("settlement_change_usd")
            brent_settlement_change_pct = market_snapshot.get("settlement_change_pct")
        for cells in self._iter_markdown_rows(markdown):
            if market_snapshot:
                break
            if (
                len(cells) >= 5
                and cells[0].startswith("Brent ")
                and self._parse_money(cells[1]) is not None
                and self._parse_money(cells[3]) is not None
            ):
                brent_close = self._parse_money(cells[1])
                brent_settlement = self._parse_money(cells[3])
                brent_settlement_change_usd = self._parse_signed_money(cells[4])
                brent_settlement_change_pct = self._parse_signed_percent(cells[4])
                break
            if len(cells) >= 5 and cells[0] == "Brent" and "M1" in cells[1]:
                brent_close = self._parse_money(cells[2])
                if len(cells) >= 6 and self._parse_signed_percent(cells[3]) is not None:
                    brent_settlement = self._parse_money(cells[4])
                    brent_settlement_change_usd = self._parse_signed_money(cells[5])
                    brent_settlement_change_pct = self._parse_signed_percent(cells[5])
                else:
                    brent_settlement = self._parse_money(cells[3])
                    brent_settlement_change_usd = self._parse_signed_money(cells[4])
                    brent_settlement_change_pct = self._parse_signed_percent(cells[4])
                break
            if len(cells) >= 6 and cells[0] == "Brent" and self._parse_money(cells[4]) is not None:
                brent_close = self._parse_money(cells[2])
                brent_settlement = self._parse_money(cells[4])
                brent_settlement_change_usd = self._parse_signed_money(cells[5])
                brent_settlement_change_pct = self._parse_signed_percent(cells[5])
                break
        realtime_context = self._extract_realtime_context(markdown)
        if brent_settlement is not None:
            realtime_context["brent_settlement"] = brent_settlement
        if brent_close is not None:
            realtime_context["brent_close"] = brent_close
        if brent_settlement_change_usd is not None:
            realtime_context["brent_settlement_change_usd"] = brent_settlement_change_usd
        if brent_settlement_change_pct is not None:
            realtime_context["brent_settlement_change_pct"] = brent_settlement_change_pct
        if brent_settlement is not None and brent_settlement_change_usd is not None:
            realtime_context["previous_settlement"] = round(
                float(brent_settlement) - float(brent_settlement_change_usd),
                4,
            )

        bullish_keywords = ["减产", "地缘", "供应中断", "库存下降", "强势"]
        bearish_keywords = ["增产", "需求走弱", "累库", "衰退", "疲弱"]
        bullish_hits = sum(1 for keyword in bullish_keywords if keyword in markdown)
        bearish_hits = sum(1 for keyword in bearish_keywords if keyword in markdown)

        forecast_anchor_close = (
            brent_settlement if brent_settlement is not None else self._forecast_anchor_close(markdown, realtime_context)
        )
        daily_forecast = self._extract_daily_forecast(
            markdown,
            realtime_context,
            anchor_close=forecast_anchor_close,
        )
        horizon_forecasts = self._extract_horizon_forecasts(markdown, anchor_close=forecast_anchor_close)
        return {
            "brent_settlement": brent_settlement,
            "brent_settlement_change_usd": brent_settlement_change_usd,
            "brent_settlement_change_pct": brent_settlement_change_pct,
            "daily_forecast": daily_forecast,
            "realtime_context": realtime_context,
            "bullish_hits": bullish_hits,
            "bearish_hits": bearish_hits,
            "supported_horizons": list(horizon_forecasts.keys()),
            "horizon_forecasts": horizon_forecasts,
        }

    def _extract_realtime_context(self, markdown: str) -> dict[str, Any]:
        context: dict[str, Any] = {}
        realtime_reference_match = re.search(
            r"实时参考价（北京时间\s*(?P<time>[^）]+)）：Brent\s*M1\s*\$(?P<realtime>[0-9]+(?:\.[0-9]+)?)",
            markdown,
        )
        if realtime_reference_match:
            context.update(
                {
                    "realtime_price": float(realtime_reference_match.group("realtime")),
                    "realtime_text_time": realtime_reference_match.group("time").strip(),
                    "source_text": realtime_reference_match.group(0)[:220],
                }
            )
        realtime_match = re.search(
            r"当前实时\s*B\.IPE\s*约\s*\$(?P<realtime>[0-9]+(?:\.[0-9]+)?)"
            r".*?较\s*[^$]*收盘(?:回吐|下跌|走低)约\s*\$(?P<retrace>[0-9]+(?:\.[0-9]+)?)",
            markdown,
            flags=re.S,
        )
        if realtime_match:
            realtime_price = float(realtime_match.group("realtime"))
            retrace = float(realtime_match.group("retrace"))
            context.update(
                {
                    "realtime_price": realtime_price,
                    "retrace_from_close_usd": retrace,
                    "rebound_to_close_usd": retrace,
                    "source_text": realtime_match.group(0)[:220],
                }
            )
        return context

    def _extract_daily_forecast(
        self,
        markdown: str,
        realtime_context: dict[str, Any],
        anchor_close: float | None = None,
    ) -> dict[str, Any]:
        anchor_close = anchor_close or self._forecast_anchor_close(markdown, realtime_context)
        vertical_forecast = self._extract_vertical_daily_forecast(
            markdown=markdown,
            anchor_close=anchor_close,
            realtime_context=realtime_context,
        )
        if vertical_forecast:
            return self._with_daily_forecast_date(vertical_forecast, markdown)

        for cells in self._iter_markdown_rows(markdown):
            if len(cells) < 3 or not cells[0].startswith("当日"):
                continue
            range_values = self._parse_money_range(cells[2])
            if self._parse_money(cells[1]) is not None and range_values is not None:
                point_value = self._parse_money(cells[1])
                lower, upper = range_values
                direction_text = cells[3] if len(cells) > 3 else None
                trading_rhythm = cells[4] if len(cells) > 4 else None
                core_driver = cells[5] if len(cells) > 5 else None
                confidence = None
            else:
                point_value = self._parse_money(cells[2]) if len(cells) > 2 else None
                lower = self._parse_money(cells[3]) if len(cells) > 3 else None
                upper = self._parse_money(cells[4]) if len(cells) > 4 else None
                direction_text = cells[1] if len(cells) > 1 else None
                trading_rhythm = None
                core_driver = None
                confidence = cells[5] if len(cells) > 5 else None
            if point_value is None:
                continue
            forecast: dict[str, Any] = {
                "window": cells[0],
                "point_value": point_value,
                "range_lower": lower,
                "range_upper": upper,
                "direction_text": direction_text,
                "confidence": confidence,
            }
            if trading_rhythm:
                forecast["trading_rhythm"] = trading_rhythm
            if core_driver:
                forecast["core_driver"] = core_driver
            if anchor_close is not None:
                forecast["change_usd"] = round(point_value - float(anchor_close), 4)
                forecast["change_source"] = self._change_source_label(
                    "daily",
                    anchor_close=anchor_close,
                    realtime_context=realtime_context,
                )
                forecast["anchor_close"] = float(anchor_close)
                realtime_price = realtime_context.get("realtime_price")
                if realtime_price is not None:
                    forecast["change_vs_realtime_usd"] = round(point_value - float(realtime_price), 4)
            else:
                realtime_price = realtime_context.get("realtime_price")
                if realtime_price is not None:
                    forecast["change_vs_realtime_usd"] = round(point_value - float(realtime_price), 4)
                    forecast["change_usd"] = forecast["change_vs_realtime_usd"]
                    forecast["change_source"] = "daily_point_minus_realtime"
            return self._with_daily_forecast_date(forecast, markdown)

        bullet_forecast = self._extract_bullet_daily_forecast(
            markdown=markdown,
            anchor_close=anchor_close,
            realtime_context=realtime_context,
        )
        if bullet_forecast:
            return self._with_daily_forecast_date(bullet_forecast, markdown)

        row_pattern = re.compile(
            r"\|\s*当日\s*Brent\s*M1\s*\([^)]*\)\s*\|\s*(?P<emoji>[^\s|]+)\$(?P<point>[0-9]+(?:\.[0-9]+)?)\s*"
            r"\|\s*\$(?P<lower>[0-9]+(?:\.[0-9]+)?)\s*[–-]\s*\$(?P<upper>[0-9]+(?:\.[0-9]+)?)\s*"
            r"\|\s*(?P<direction>[^|]+)\|",
        )
        match = row_pattern.search(markdown)
        forecast: dict[str, Any] = {}
        if match:
            point_value = float(match.group("point"))
            forecast.update(
                {
                    "point_value": point_value,
                    "range_lower": float(match.group("lower")),
                    "range_upper": float(match.group("upper")),
                    "direction_text": match.group("direction").strip(),
                    "direction_emoji": match.group("emoji").strip(),
                }
            )
            realtime_price = realtime_context.get("realtime_price")
            if anchor_close is not None:
                forecast["change_usd"] = round(point_value - float(anchor_close), 4)
                forecast["change_source"] = self._change_source_label(
                    "daily",
                    anchor_close=anchor_close,
                    realtime_context=realtime_context,
                )
                forecast["anchor_close"] = float(anchor_close)
            if realtime_price is not None:
                forecast["change_vs_realtime_usd"] = round(point_value - float(realtime_price), 4)
        if forecast.get("change_usd") is not None:
            return self._with_daily_forecast_date(forecast, markdown)
        if realtime_context.get("rebound_to_close_usd") is not None:
            forecast["change_usd"] = float(realtime_context["rebound_to_close_usd"])
            forecast["change_source"] = "rebound_to_previous_close"
        elif forecast.get("change_vs_realtime_usd") is not None:
            forecast["change_usd"] = forecast["change_vs_realtime_usd"]
            forecast["change_source"] = "daily_point_minus_realtime"
        return self._with_daily_forecast_date(forecast, markdown)

    def _extract_horizon_forecasts(
        self,
        markdown: str,
        anchor_close: float | None = None,
    ) -> dict[str, Any]:
        forecasts: dict[str, Any] = {}
        anchor_close = anchor_close if anchor_close is not None else self._extract_anchor_close(markdown)
        for cells in self._iter_markdown_rows(markdown):
            if len(cells) < 5:
                continue
            week_match = re.match(
                rf"{chr(0x7b2c)}(?P<week_no>[1-4]){chr(0x5468)}\s*[{chr(0xff08)}(](?P<window>[^{chr(0xff09)})]+)[{chr(0xff09)})]",
                cells[0],
            )
            is_w_row = False
            if not week_match:
                week_match = re.match(r"W(?P<week_no>[1-4])\b", self._clean_markdown_cell(cells[0]), re.IGNORECASE)
                is_w_row = week_match is not None
            if not week_match:
                continue
            if is_w_row:
                range_values = self._parse_money_range_flexible(cells[3])
                point_value = self._parse_money(cells[2])
                lower, upper = range_values if range_values is not None else (None, None)
                direction_text = cells[4] if len(cells) > 4 else None
                core_driver = None
                confidence = cells[5] if len(cells) > 5 else None
            else:
                range_values = self._parse_money_range(cells[2])
                if self._parse_money(cells[1]) is not None and range_values is not None:
                    point_value = self._parse_money(cells[1])
                    lower, upper = range_values
                    direction_text = cells[3] if len(cells) > 3 else None
                    core_driver = cells[4] if len(cells) > 4 else None
                    confidence = None
                else:
                    point_value = self._parse_money(cells[2])
                    lower = self._parse_money(cells[3])
                    upper = self._parse_money(cells[4])
                    direction_text = cells[1]
                    core_driver = None
                    confidence = cells[5] if len(cells) > 5 else None
            if point_value is None:
                continue
            horizon = f"W{week_match.group('week_no')}"
            forecasts[horizon] = {
                "window": week_match.groupdict().get("window", "") and week_match.group("window").strip(),
                "point_value": point_value,
                "range_lower": lower,
                "range_upper": upper,
                "direction_text": direction_text,
                "confidence": confidence,
            }
            if core_driver:
                forecasts[horizon]["core_driver"] = core_driver
            if anchor_close is not None:
                forecasts[horizon]["change_usd"] = round(point_value - float(anchor_close), 4)
                forecasts[horizon]["change_source"] = (
                    f"{horizon}_point_minus_report_settlement"
                    if anchor_close is not None and self._settlement_in_markdown(markdown, anchor_close)
                    else f"{horizon}_point_minus_anchor_close"
                )
                forecasts[horizon]["anchor_close"] = float(anchor_close)

        if forecasts:
            return forecasts

        bullet_forecasts = self._extract_bullet_horizon_forecasts(markdown, anchor_close=anchor_close)
        if bullet_forecasts:
            return bullet_forecasts

        row_pattern = re.compile(
            r"\| 第(?P<week_no>[1-4])周 \((?P<window>[^)]+)\) \| (?P<emoji>[^\s|]+)\$(?P<point>[0-9]+\.[0-9]+) "
            r"\| \$(?P<lower>[0-9]+\.[0-9]+)\s*[–-]\s*\$(?P<upper>[0-9]+\.[0-9]+) "
            r"\| (?P<direction>[^|]+) \| (?P<driver>[^|]+) \|",
        )
        for match in row_pattern.finditer(markdown):
            horizon = f"W{match.group('week_no')}"
            forecasts[horizon] = {
                "window": match.group("window").strip(),
                "point_value": float(match.group("point")),
                "range_lower": float(match.group("lower")),
                "range_upper": float(match.group("upper")),
                "direction_text": match.group("direction").strip(),
                "direction_emoji": match.group("emoji").strip(),
                "core_driver": match.group("driver").strip(),
            }
            delta_match = re.search(r"delta=([+-]?[0-9]+(?:\.[0-9]+)?)", match.group("driver"))
            if delta_match:
                forecasts[horizon]["change_usd"] = float(delta_match.group(1))
                forecasts[horizon]["change_source"] = "weekly_delta"
        return forecasts

    def _extract_bullet_daily_forecast(
        self,
        *,
        markdown: str,
        anchor_close: float | None,
        realtime_context: dict[str, Any],
    ) -> dict[str, Any]:
        point_match = re.search(r"-\s*\*\*point_usd\*\*\s*:\s*\$(?P<point>[0-9]+(?:\.[0-9]+)?)", markdown)
        if not point_match:
            return {}
        point_value = float(point_match.group("point"))
        range_match = re.search(
            r"-\s*\*\*range\*\*\s*:\s*\$(?P<lower>[0-9]+(?:\.[0-9]+)?)\s*[–—-]\s*\$(?P<upper>[0-9]+(?:\.[0-9]+)?)",
            markdown,
        )
        direction_match = re.search(r"-\s*\*\*direction\*\*\s*:\s*(?P<direction>[^\n]+)", markdown)
        confidence_match = re.search(r"-\s*\*\*confidence\*\*\s*:\s*(?P<confidence>[^\n]+)", markdown)
        driver_match = re.search(r"-\s*\*\*driver\*\*\s*:\s*(?P<driver>[^\n]+)", markdown)
        forecast: dict[str, Any] = {
            "window": "当日",
            "point_value": point_value,
            "range_lower": float(range_match.group("lower")) if range_match else None,
            "range_upper": float(range_match.group("upper")) if range_match else None,
            "direction_text": direction_match.group("direction").strip() if direction_match else None,
            "confidence": confidence_match.group("confidence").strip() if confidence_match else None,
        }
        if driver_match:
            forecast["core_driver"] = driver_match.group("driver").strip()
        if anchor_close is not None:
            forecast["change_usd"] = round(point_value - float(anchor_close), 4)
            forecast["change_source"] = self._change_source_label("daily", anchor_close=anchor_close, realtime_context=realtime_context)
            forecast["anchor_close"] = float(anchor_close)
        realtime_price = realtime_context.get("realtime_price") or realtime_context.get("brent_settlement")
        if realtime_price is not None:
            forecast["change_vs_realtime_usd"] = round(point_value - float(realtime_price), 4)
            if forecast.get("change_usd") is None:
                forecast["change_usd"] = forecast["change_vs_realtime_usd"]
                forecast["change_source"] = "daily_point_minus_realtime"
        return forecast

    def _extract_bullet_horizon_forecasts(self, markdown: str, anchor_close: float | None) -> dict[str, Any]:
        forecasts: dict[str, Any] = {}
        pattern = re.compile(
            r"-\s*\*\*(?P<horizon>W[1-4])\s*\((?P<window>[^)]+)\)\*\*\s*:\s*"
            r"\$(?P<point>[0-9]+(?:\.[0-9]+)?)\s*"
            r"\[\$(?P<lower>[0-9]+(?:\.[0-9]+)?),\s*\$(?P<upper>[0-9]+(?:\.[0-9]+)?)\]\s*"
            r"(?P<direction>[^\s—-]+)\s*[—-]\s*(?P<driver>[^\n]+)"
        )
        for match in pattern.finditer(markdown):
            horizon = match.group("horizon")
            point_value = float(match.group("point"))
            forecasts[horizon] = {
                "window": match.group("window").strip(),
                "point_value": point_value,
                "range_lower": float(match.group("lower")),
                "range_upper": float(match.group("upper")),
                "direction_text": match.group("direction").strip(),
                "confidence": None,
                "core_driver": match.group("driver").strip(),
            }
            if anchor_close is not None:
                forecasts[horizon]["change_usd"] = round(point_value - float(anchor_close), 4)
                forecasts[horizon]["change_source"] = f"{horizon}_point_minus_anchor_close"
                forecasts[horizon]["anchor_close"] = float(anchor_close)
        return forecasts

    def _iter_markdown_rows(self, markdown: str) -> list[list[str]]:
        rows: list[list[str]] = []
        for line in markdown.splitlines():
            normalized = line.strip()
            if not normalized.startswith("|") or "---" in normalized:
                continue
            cells = [cell.strip() for cell in normalized.strip("|").split("|")]
            if cells:
                rows.append(cells)
        return rows

    def _parse_money(self, value: str) -> float | None:
        match = re.search(r"\$?\s*([0-9]+(?:\.[0-9]+)?)", value)
        return float(match.group(1)) if match else None

    def _parse_money_range(self, value: str) -> tuple[float, float] | None:
        match = re.search(
            r"\$?\s*(?P<lower>[0-9]+(?:\.[0-9]+)?)\s*[–—-]\s*\$?\s*(?P<upper>[0-9]+(?:\.[0-9]+)?)",
            value,
        )
        if not match:
            return None
        return float(match.group("lower")), float(match.group("upper"))

    def _parse_signed_money(self, value: str) -> float | None:
        match = re.search(r"(?P<sign1>[+-])?\s*\$?\s*(?P<sign2>[+-])?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)", value)
        if not match:
            return None
        numeric_value = float(match.group("value"))
        sign = match.group("sign1") or match.group("sign2")
        return -numeric_value if sign == "-" else numeric_value

    def _parse_signed_percent(self, value: str) -> float | None:
        match = re.search(r"\((?P<sign>[+-])?(?P<value>[0-9]+(?:\.[0-9]+)?)%\)", value)
        if not match:
            match = re.search(r"/\s*(?P<sign>[+-])?(?P<value>[0-9]+(?:\.[0-9]+)?)%", value)
        if not match:
            match = re.search(r"(?P<sign>[+-])(?P<value>[0-9]+(?:\.[0-9]+)?)%", value)
        if not match:
            return None
        numeric_value = float(match.group("value"))
        return -numeric_value if match.group("sign") == "-" else numeric_value

    def _extract_anchor_close(self, markdown: str) -> float | None:
        explicit_anchor = self._extract_explicit_anchor_close(markdown)
        if explicit_anchor is not None:
            return explicit_anchor
        market_snapshot = self._extract_brent_market_snapshot(markdown)
        if market_snapshot.get("settlement") is not None:
            return market_snapshot.get("settlement")
        for cells in self._iter_markdown_rows(markdown):
            if (
                len(cells) >= 5
                and cells[0].startswith("Brent ")
                and self._parse_money(cells[3]) is not None
            ):
                return self._parse_money(cells[3])
            if len(cells) >= 4 and cells[0] == "Brent" and "M1" in cells[1]:
                return self._parse_money(cells[3])
        return None

    def _extract_explicit_anchor_close(self, markdown: str) -> float | None:
        match = re.search(
            r"当日预测锚定\s*(?:[0-9]+/[0-9]+\s*)?Brent\s*M1\s*(?:收盘价|settle|settlement)\s*\$(?P<value>[0-9]+(?:\.[0-9]+)?)",
            markdown,
        )
        return float(match.group("value")) if match else None

    def _forecast_anchor_close(self, markdown: str, realtime_context: dict[str, Any]) -> float | None:
        return (
            realtime_context.get("brent_settlement")
            or self._extract_explicit_anchor_close(markdown)
            or self._extract_anchor_close(markdown)
        )

    def _settlement_in_markdown(self, markdown: str, anchor_close: float | None) -> bool:
        if anchor_close is None:
            return False
        settlement = self._extract_brent_market_snapshot(markdown).get("settlement") if self._extract_brent_market_snapshot(markdown) else None
        if settlement is None:
            return False
        return abs(float(settlement) - float(anchor_close)) < 1e-6

    def _change_source_label(
        self,
        prefix: str,
        *,
        anchor_close: float | None,
        realtime_context: dict[str, Any],
    ) -> str:
        settlement = realtime_context.get("brent_settlement")
        if anchor_close is not None and settlement is not None and abs(float(anchor_close) - float(settlement)) < 1e-6:
            return f"{prefix}_point_minus_report_settlement"
        return f"{prefix}_point_minus_anchor_close"

    def _extract_brent_market_snapshot(self, markdown: str) -> dict[str, float | None]:
        rows = self._iter_markdown_rows(markdown)
        for header_index, header in enumerate(rows):
            column_map = self._brent_market_column_map(header)
            if not column_map:
                continue
            for cells in rows[header_index + 1 :]:
                if len(cells) < 2:
                    continue
                if self._brent_market_column_map(cells):
                    break
                if not self._is_front_brent_row(cells):
                    continue
                return {
                    "close": self._parse_money(cells[column_map["close"]])
                    if column_map.get("close", -1) < len(cells)
                    else None,
                    "settlement": self._parse_money(cells[column_map["settlement"]])
                    if column_map.get("settlement", -1) < len(cells)
                    else None,
                    "settlement_change_usd": self._parse_signed_money(cells[column_map["settlement_change"]])
                    if column_map.get("settlement_change", -1) < len(cells)
                    else None,
                    "settlement_change_pct": self._parse_signed_percent(cells[column_map["settlement_change"]])
                    if column_map.get("settlement_change", -1) < len(cells)
                    else None,
                }
        return {}

    def _brent_market_column_map(self, header: list[str]) -> dict[str, int]:
        lower_cells = [cell.lower().replace(" ", "") for cell in header]
        has_product = any("品种" in cell or "鍝佺" in cell for cell in header)
        has_settlement = any("settlement" in cell for cell in lower_cells)
        if not has_product or not has_settlement:
            return {}
        result: dict[str, int] = {}
        for index, cell in enumerate(header):
            lower = lower_cells[index]
            is_change = self._is_change_header(cell)
            if "settlement" in lower and is_change:
                result["settlement_change"] = index
            elif "settlement" in lower:
                result["settlement"] = index
            elif self._is_close_price_header(cell):
                result["close"] = index
        if "settlement" not in result or "settlement_change" not in result:
            return {}
        return result

    def _is_close_price_header(self, value: str) -> bool:
        if self._is_change_header(value):
            return False
        return "收盘价" in value or "鏀剁洏浠" in value or value.strip().lower() == "close"

    def _is_change_header(self, value: str) -> bool:
        lower = value.lower()
        return any(
            marker in lower
            for marker in (
                "较",
                "昨日",
                "vs",
                "change",
                "涨跌",
                "杈",
                "娑ㄨ穼",
            )
        )

    def _is_front_brent_row(self, cells: list[str]) -> bool:
        first = cells[0]
        contract = cells[1] if len(cells) > 1 else ""
        if "Brent" not in first:
            return False
        combined = f"{first} {contract}".upper()
        if "M1" in combined:
            return True
        return first.strip().lower() == "brent"

    def _extract_daily_forecast_date(self, markdown: str) -> date | None:
        pattern = re.compile(
            rf"{chr(0x5f53)}{chr(0x65e5)}{chr(0x9884)}{chr(0x6d4b)}\s*[{chr(0xff08)}(](?P<date>\d{{4}}-\d{{2}}-\d{{2}})[{chr(0xff09)})]"
        )
        match = pattern.search(markdown)
        if not match:
            return None
        try:
            return date.fromisoformat(match.group("date"))
        except ValueError:
            return None

    def _with_daily_forecast_date(self, forecast: dict[str, Any], markdown: str) -> dict[str, Any]:
        if forecast and forecast.get("forecast_date") is None:
            forecast_date = self._extract_daily_forecast_date(markdown)
            if forecast_date is not None:
                forecast["forecast_date"] = forecast_date.isoformat()
        return forecast

    def _extract_vertical_daily_forecast(
        self,
        *,
        markdown: str,
        anchor_close: float | None,
        realtime_context: dict[str, Any],
    ) -> dict[str, Any]:
        fields: dict[str, str] = {}
        for cells in self._iter_markdown_rows(markdown):
            if len(cells) != 2:
                continue
            key = self._clean_markdown_cell(cells[0])
            value = cells[1]
            if key in {"点估计", "鐐逛及璁?", "point_usd", "point"}:
                fields["point"] = value
            elif key in {"区间", "浠锋牸棰勬祴鍖洪棿", "range"}:
                fields["range"] = value
            elif key in {"方向", "鏂瑰悜", "direction"}:
                fields["direction"] = value
            elif key in {"置信度", "confidence"}:
                fields["confidence"] = value
            elif key in {"交易节奏", "浜ゆ槗鑺傚"}:
                fields["trading_rhythm"] = value
            elif key in {"核心驱动", "鏍稿績椹卞姩", "driver"}:
                fields["core_driver"] = value
        point_value = self._parse_money(fields.get("point", ""))
        if point_value is None:
            return {}
        range_values = self._parse_money_range_flexible(fields.get("range", ""))
        forecast_date = self._extract_daily_forecast_date(markdown)
        forecast: dict[str, Any] = {
            "window": "当日",
            "point_value": point_value,
            "range_lower": range_values[0] if range_values else None,
            "range_upper": range_values[1] if range_values else None,
            "direction_text": self._clean_markdown_cell(fields.get("direction", "")) or None,
            "confidence": self._clean_markdown_cell(fields.get("confidence", "")) or None,
        }
        if fields.get("trading_rhythm"):
            forecast["trading_rhythm"] = self._clean_markdown_cell(fields["trading_rhythm"])
        if fields.get("core_driver"):
            forecast["core_driver"] = self._clean_markdown_cell(fields["core_driver"])
        if anchor_close is not None:
            forecast["change_usd"] = round(point_value - float(anchor_close), 4)
            forecast["change_source"] = self._change_source_label("daily", anchor_close=anchor_close, realtime_context=realtime_context)
            forecast["anchor_close"] = float(anchor_close)
        realtime_price = realtime_context.get("realtime_price")
        if realtime_price is not None:
            forecast["change_vs_realtime_usd"] = round(point_value - float(realtime_price), 4)
            if forecast.get("change_usd") is None:
                forecast["change_usd"] = forecast["change_vs_realtime_usd"]
                forecast["change_source"] = "daily_point_minus_realtime"
        return forecast

    def _parse_money_range_flexible(self, value: str) -> tuple[float, float] | None:
        values = re.findall(r"\$?\s*([0-9]+(?:\.[0-9]+)?)", str(value or ""))
        if len(values) < 2:
            return None
        return float(values[0]), float(values[1])

    def _clean_markdown_cell(self, value: str) -> str:
        return re.sub(r"[*`]+", "", str(value or "")).replace("/桶", "").strip()
