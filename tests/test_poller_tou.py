"""Tests for TOU tier logic in the poller."""
import pytest
from datetime import date

from src.backend.poller import _get_tou_tier, _is_holiday

MOCK_TOU = {
    "rates": [
        {"name": "off_peak",  "rate_per_kwh": 0.0837},
        {"name": "peak",      "rate_per_kwh": 0.1674},
        {"name": "mid_peak",  "rate_per_kwh": 0.1465},
    ],
    "holidays": [
        {"month": 7,  "day": 4},   # Independence Day
        {"month": 12, "day": 25},  # Christmas
        {"month": 1,  "day": 1},   # New Year's
    ],
}

# Mon Apr 6 2026
MONDAY   = date(2026, 4, 6)
# Sat Apr 4 2026
SATURDAY = date(2026, 4, 4)
# Sun Apr 5 2026
SUNDAY   = date(2026, 4, 5)


class TestTOUTier:
    def test_off_peak_midnight_to_6am(self):
        for hour in range(6):
            tier, rate = _get_tou_tier(MONDAY, hour, MOCK_TOU)
            assert tier == "off_peak", f"hour {hour} should be off_peak"
            assert rate == pytest.approx(0.0837)

    def test_peak_monday_5pm_to_9pm(self):
        for hour in [17, 18, 19, 20]:
            tier, rate = _get_tou_tier(MONDAY, hour, MOCK_TOU)
            assert tier == "peak", f"hour {hour} Monday should be peak"
            assert rate == pytest.approx(0.1674)

    def test_mid_peak_monday_morning(self):
        for hour in [6, 7, 8, 9, 16]:
            tier, rate = _get_tou_tier(MONDAY, hour, MOCK_TOU)
            assert tier == "mid_peak", f"hour {hour} Monday should be mid_peak"

    def test_mid_peak_monday_after_peak(self):
        tier, rate = _get_tou_tier(MONDAY, 21, MOCK_TOU)
        assert tier == "mid_peak"
        tier, rate = _get_tou_tier(MONDAY, 23, MOCK_TOU)
        assert tier == "mid_peak"

    def test_saturday_has_peak(self):
        tier, _ = _get_tou_tier(SATURDAY, 18, MOCK_TOU)
        assert tier == "peak"

    def test_sunday_no_peak(self):
        """Sundays: 6AM-midnight is all mid-peak, no peak tier."""
        for hour in [17, 18, 19, 20]:
            tier, _ = _get_tou_tier(SUNDAY, hour, MOCK_TOU)
            assert tier == "mid_peak", f"Sunday hour {hour} should be mid_peak not peak"

    def test_sunday_off_peak_still_applies(self):
        for hour in range(6):
            tier, _ = _get_tou_tier(SUNDAY, hour, MOCK_TOU)
            assert tier == "off_peak"

    def test_fixed_holiday_no_peak(self):
        july_4_2026 = date(2026, 7, 4)  # Saturday — would normally be peak
        tier, _ = _get_tou_tier(july_4_2026, 18, MOCK_TOU)
        assert tier == "mid_peak", "July 4 should not have peak pricing"

    def test_non_holiday_saturday_has_peak(self):
        july_11_2026 = date(2026, 7, 11)  # Saturday, not a holiday
        tier, _ = _get_tou_tier(july_11_2026, 18, MOCK_TOU)
        assert tier == "peak"

    def test_boundary_hour_5pm_is_peak(self):
        tier, _ = _get_tou_tier(MONDAY, 17, MOCK_TOU)
        assert tier == "peak"

    def test_boundary_hour_9pm_is_mid_peak(self):
        tier, _ = _get_tou_tier(MONDAY, 21, MOCK_TOU)
        assert tier == "mid_peak"


class TestIsHoliday:
    def test_fixed_holiday(self):
        assert _is_holiday(date(2026, 7, 4), MOCK_TOU)
        assert _is_holiday(date(2026, 12, 25), MOCK_TOU)
        assert _is_holiday(date(2026, 1, 1), MOCK_TOU)

    def test_non_holiday(self):
        assert not _is_holiday(date(2026, 4, 6), MOCK_TOU)  # random Monday
        assert not _is_holiday(date(2026, 3, 15), MOCK_TOU)

    def test_floating_holiday_mlk(self):
        mlk_2026 = date(2026, 1, 19)  # 3rd Mon Jan 2026
        assert _is_holiday(mlk_2026, MOCK_TOU)

    def test_floating_holiday_labor_day(self):
        labor_2026 = date(2026, 9, 7)  # 1st Mon Sep 2026
        assert _is_holiday(labor_2026, MOCK_TOU)

    def test_floating_holiday_thanksgiving(self):
        thanksgiving_2026 = date(2026, 11, 26)  # 4th Thu Nov 2026
        assert _is_holiday(thanksgiving_2026, MOCK_TOU)
