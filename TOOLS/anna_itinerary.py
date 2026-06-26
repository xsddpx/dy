#!/usr/bin/env python3
"""Validate the active Anna weekly itinerary asset."""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


REQUIRED_DAY_FIELDS = [
    "date",
    "city",
    "location",
    "season_weather_basis",
    "time_slot",
    "activity",
    "shoot_scene",
    "outfit_direction",
    "reference_keywords",
]
ACTIVE_STATUSES = {"active"}


def parse_iso_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def today_in_shanghai():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def non_empty(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(isinstance(item, str) and item.strip() for item in value)
    return False


def validate_itinerary(data):
    errors = []
    if not isinstance(data, dict):
        return None, ["itinerary must be a JSON object"]

    status = data.get("status")
    if status not in ACTIVE_STATUSES:
        errors.append("status must be active before use")

    try:
        valid_from = parse_iso_date(data.get("valid_from"), "valid_from")
        valid_to = parse_iso_date(data.get("valid_to"), "valid_to")
    except ValueError as exc:
        return None, [str(exc)]

    days = data.get("days")
    if not isinstance(days, list):
        return None, ["days must be a list"]
    if len(days) != 7:
        errors.append("days must contain exactly 7 entries")

    expected_to = valid_from + timedelta(days=6)
    if valid_to != expected_to:
        errors.append("valid_to must be valid_from + 6 days")

    for index, item in enumerate(days):
        if not isinstance(item, dict):
            errors.append(f"days[{index}] must be an object")
            continue
        expected_date = valid_from + timedelta(days=index)
        try:
            item_date = parse_iso_date(item.get("date"), f"days[{index}].date")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if item_date != expected_date:
            errors.append(f"days[{index}].date must be {expected_date.isoformat()}")
        for field in REQUIRED_DAY_FIELDS:
            if field == "date":
                continue
            if not non_empty(item.get(field)):
                errors.append(f"days[{index}].{field} must be non-empty")

    return {"valid_from": valid_from, "valid_to": valid_to, "days": days}, errors


def load_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def status(path, current_date):
    if not path.exists():
        return {
            "decision": "missing",
            "ok": False,
            "message": f"{path} is missing; generate and save a 7-day itinerary before continuing.",
        }
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "decision": "invalid",
            "ok": False,
            "message": f"{path} cannot be read as valid JSON: {exc}",
        }

    validated, errors = validate_itinerary(data)
    if errors:
        return {
            "decision": "invalid",
            "ok": False,
            "message": "itinerary asset is not usable",
            "errors": errors,
        }

    valid_from = validated["valid_from"]
    valid_to = validated["valid_to"]
    if current_date < valid_from:
        return {
            "decision": "not_started",
            "ok": False,
            "message": f"itinerary starts on {valid_from.isoformat()}; generate and save today's 7-day itinerary.",
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat(),
        }
    if current_date > valid_to:
        return {
            "decision": "expired",
            "ok": False,
            "message": f"itinerary expired on {valid_to.isoformat()}; regenerate and save a new 7-day itinerary.",
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat(),
        }

    offset = (current_date - valid_from).days
    active_day = validated["days"][offset]
    return {
        "decision": "pass",
        "ok": True,
        "message": f"use active itinerary for {current_date.isoformat()}",
        "valid_from": valid_from.isoformat(),
        "valid_to": valid_to.isoformat(),
        "active_day": active_day,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="检查 Anna 一周行程资产是否可用于当天任务。")
    parser.add_argument("--path", default="MATERIAL/anna-weekly-itinerary.json", help="行程 JSON 资产路径")
    parser.add_argument("--date", default=None, help="按 YYYY-MM-DD 指定任务日期；默认使用 Asia/Shanghai 今天")
    args = parser.parse_args(argv)

    current_date = parse_iso_date(args.date, "--date") if args.date else today_in_shanghai()
    result = status(Path(args.path), current_date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
