import importlib.util
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "anna_itinerary.py"
SPEC = importlib.util.spec_from_file_location("anna_itinerary", SCRIPT)
ANNA_ITINERARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANNA_ITINERARY)


def good_data():
    days = []
    start = date(2026, 6, 26)
    for day in range(7):
        days.append(
            {
                "date": (start + timedelta(days=day)).isoformat(),
                "city": "杭州",
                "location": "西湖湖滨",
                "season_weather_basis": "六月末夏季，傍晚湿热，适合轻薄穿搭。",
                "time_slot": "傍晚",
                "activity": "旅行散步",
                "shoot_scene": "湖滨步道近景跟拍",
                "outfit_direction": "修身上衣与高腰半裙",
                "reference_keywords": ["旅行", "穿搭展示", "湖边散步"],
            }
        )
    return {
        "generated_at": "2026-06-26T09:00:00+08:00",
        "valid_from": "2026-06-26",
        "valid_to": "2026-07-02",
        "status": "active",
        "days": days,
    }


class AnnaItineraryTest(unittest.TestCase):
    def write_json(self, data):
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "itinerary.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.addCleanup(temp.cleanup)
        return path

    def test_active_itinerary_passes_for_active_day(self):
        path = self.write_json(good_data())
        result = ANNA_ITINERARY.status(path, date(2026, 6, 27))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["decision"], "pass")
        self.assertEqual(result["active_day"]["date"], "2026-06-27")

    def test_missing_file_blocks(self):
        result = ANNA_ITINERARY.status(Path("/tmp/not-a-real-itinerary.json"), date(2026, 6, 27))
        self.assertFalse(result["ok"])
        self.assertEqual(result["decision"], "missing")

    def test_draft_itinerary_blocks(self):
        data = good_data()
        data["status"] = "draft"
        path = self.write_json(data)
        result = ANNA_ITINERARY.status(path, date(2026, 6, 27))
        self.assertFalse(result["ok"])
        self.assertEqual(result["decision"], "invalid")
        self.assertTrue(any("status must be active" in item for item in result["errors"]))

    def test_expired_itinerary_blocks(self):
        path = self.write_json(good_data())
        result = ANNA_ITINERARY.status(path, date(2026, 7, 3))
        self.assertFalse(result["ok"])
        self.assertEqual(result["decision"], "expired")

    def test_non_consecutive_dates_block(self):
        data = good_data()
        data["days"][3]["date"] = "2026-07-10"
        path = self.write_json(data)
        result = ANNA_ITINERARY.status(path, date(2026, 6, 27))
        self.assertFalse(result["ok"])
        self.assertTrue(any("days[3].date" in item for item in result["errors"]))

    def test_confirmed_itinerary_blocks(self):
        data = good_data()
        data["status"] = "confirmed"
        path = self.write_json(data)
        result = ANNA_ITINERARY.status(path, date(2026, 6, 27))
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["decision"], "invalid")
        self.assertTrue(any("status must be active" in item for item in result["errors"]))


if __name__ == "__main__":
    unittest.main()
