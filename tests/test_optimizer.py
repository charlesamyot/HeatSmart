"""Tests for the schedule optimizer."""
import pytest
from datetime import date

from src.backend.optimizer import ScheduleOptimizer, _deduplicate_slots, _mode_heat_rate


MOCK_TOU = {
    "rates": [
        {"name": "off_peak",  "rate_per_kwh": 0.0837},
        {"name": "peak",      "rate_per_kwh": 0.1674},
        {"name": "mid_peak",  "rate_per_kwh": 0.1465},
    ],
    "holidays": [],
}

# Monday (peak pricing applies)
WEEKDAY = date(2026, 4, 6)
# Sunday (no peak pricing)
SUNDAY = date(2026, 4, 5)


class TestScheduleOptimizer:
    def setup_method(self):
        self.optimizer = ScheduleOptimizer(
            preferred_setpoint=120.0,
            min_acceptable_temp=110.0,
            max_recovery_minutes=60,
            tou_config=MOCK_TOU,
        )

    def test_optimize_returns_result(self):
        usage = {7: 10.0, 8: 12.0, 18: 8.0, 19: 9.0}
        result = self.optimizer.optimize(usage, WEEKDAY)
        assert result is not None
        assert result.estimated_daily_cost >= 0
        assert len(result.schedule) <= 4

    def test_optimize_no_usage_data_returns_fallback(self):
        result = self.optimizer.optimize({}, WEEKDAY)
        assert result is not None
        assert len(result.schedule) >= 1

    def test_setpoint_bounds_respected(self):
        usage = {7: 10.0}
        result = self.optimizer.optimize(usage, WEEKDAY)
        for slot in result.schedule:
            assert 110.0 <= slot.setpoint <= 140.0

    def test_schedule_entries_in_order(self):
        usage = {7: 10.0, 8: 8.0}
        result = self.optimizer.optimize(usage, WEEKDAY)
        hours = [s.hour for s in result.schedule]
        assert hours == sorted(hours)

    def test_sunday_no_peak_tier(self):
        """On Sunday there should be no peak tier — all mid-peak or off-peak."""
        rates = self.optimizer._hourly_rates(SUNDAY)
        tiers = [tier for _, tier, _ in rates]
        assert "peak" not in tiers

    def test_weekday_has_peak_tier(self):
        rates = self.optimizer._hourly_rates(WEEKDAY)
        tiers = {tier for _, tier, _ in rates}
        assert "peak" in tiers

    def test_cost_estimate_positive(self):
        usage = {7: 10.0, 18: 8.0}
        result = self.optimizer.optimize(usage, WEEKDAY)
        assert result.estimated_daily_cost > 0

    def test_savings_computed_when_current_available(self):
        usage = {7: 10.0, 18: 8.0}
        result = self.optimizer.optimize(usage, WEEKDAY)
        assert result.current_daily_cost is not None
        # savings_pct may be negative if optimized is worse (edge case), just check it's computed
        assert result.savings_pct is not None

    def test_max_schedule_entries(self):
        usage = {h: 5.0 for h in range(24)}
        result = self.optimizer.optimize(usage, WEEKDAY)
        assert len(result.schedule) <= 4

    def test_explanation_not_empty(self):
        result = self.optimizer.optimize({7: 5.0}, WEEKDAY)
        assert len(result.explanation) > 0


class TestHelpers:
    def test_deduplicate_keeps_last(self):
        from src.backend.optimizer import ScheduleSlot
        slots = [
            ScheduleSlot(hour=6, minute=0, setpoint=120, mode="ENERGY_SAVING"),
            ScheduleSlot(hour=6, minute=0, setpoint=130, mode="HEAT_PUMP_ONLY"),
        ]
        result = _deduplicate_slots(slots)
        assert len(result) == 1
        assert result[0].setpoint == 130

    def test_mode_heat_rate_electric_faster(self):
        assert _mode_heat_rate("ELECTRIC_MODE") > _mode_heat_rate("ENERGY_SAVING")
        assert _mode_heat_rate("HIGH_DEMAND") > _mode_heat_rate("HEAT_PUMP_ONLY")
