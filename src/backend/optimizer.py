"""
TOU-aware schedule optimizer for Rheem EcoNet water heater.

Strategy: rule-based pre-heat/coast with thermal simulation.
1. Build hourly usage profile from historical data.
2. Identify high-demand windows.
3. Generate candidate schedule using pre-heat-before-peak + coast-during-peak.
4. Simulate 24-hour tank temperature to verify comfort constraints.
5. Score by total cost; return best passing schedule.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, time

from .config import load_tou_rates
from .poller import _get_tou_tier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thermal model constants (typical 50-gal heat pump water heater)
# ---------------------------------------------------------------------------
_STANDBY_LOSS_PER_HOUR = 0.75      # °F/hr average tank temperature drop when idle
_HEAT_PUMP_RATE_PER_HOUR = 9.0     # °F/hr heating rate in HEAT_PUMP_ONLY mode
_ELECTRIC_RATE_PER_HOUR = 22.0     # °F/hr in ELECTRIC_MODE / HIGH_DEMAND
_ENERGY_SAVING_RATE = 9.0          # °F/hr (uses heat pump preferentially)
_DEFAULT_SETPOINT = 120.0
_MAX_SCHEDULE_ENTRIES = 4


@dataclass
class ScheduleSlot:
    hour: int          # 0-23
    minute: int        # usually 0
    setpoint: float
    mode: str


@dataclass
class OptimizationResult:
    schedule: list
    estimated_daily_cost: float
    explanation: str
    comfort_violations: int
    current_daily_cost: float = None
    savings_pct: float = None
    savings_monthly_low: float = None   # conservative monthly savings ($)
    savings_monthly_high: float = None
    savings_yearly_low: float = None
    savings_yearly_high: float = None


class ScheduleOptimizer:
    """
    Generates an optimized water heater schedule for a single weekday or weekend day.
    """

    def __init__(
        self,
        preferred_setpoint: float = _DEFAULT_SETPOINT,
        min_acceptable_temp: float = 110.0,
        max_recovery_minutes: int = 60,
        tou_config: dict | None = None,
    ) -> None:
        self.preferred_setpoint = preferred_setpoint
        self.min_acceptable_temp = min_acceptable_temp
        self.max_recovery_minutes = max_recovery_minutes
        self._tou = tou_config or load_tou_rates()

    def optimize(
        self,
        usage_by_hour: dict[int, float],   # hour→avg gallons used
        target_date: date,
    ) -> OptimizationResult:
        """
        Generate an optimized schedule for target_date.

        usage_by_hour: historical average water draw per hour (gallons).
        """
        rates = self._hourly_rates(target_date)
        high_demand = self._find_demand_windows(usage_by_hour)
        candidates = self._generate_candidates(rates, high_demand, target_date, usage_by_hour)

        best: OptimizationResult | None = None
        for candidate in candidates:
            result = self._evaluate(candidate, rates, usage_by_hour)
            if best is None or (
                result.comfort_violations <= best.comfort_violations
                and result.estimated_daily_cost < best.estimated_daily_cost
            ):
                best = result

        if best is None:
            # Fallback: always-on at preferred setpoint
            best = self._fallback(rates)

        # Compute current cost (no optimization — heater runs on demand all day)
        current_cost = self._estimate_unoptimized_cost(usage_by_hour, rates)
        best.current_daily_cost = current_cost
        if current_cost and current_cost > 0:
            daily_savings = current_cost - best.estimated_daily_cost
            best.savings_pct = round(daily_savings / current_cost * 100, 1)

            # Conservative range: 60-90% of theoretical daily savings
            # (accounts for weather, usage variation, thermal model inaccuracy)
            low_factor, high_factor = 0.6, 0.9
            best.savings_monthly_low = round(daily_savings * low_factor * 30, 2)
            best.savings_monthly_high = round(daily_savings * high_factor * 30, 2)
            best.savings_yearly_low = round(daily_savings * low_factor * 365, 2)
            best.savings_yearly_high = round(daily_savings * high_factor * 365, 2)

        return best

    # ------------------------------------------------------------------
    # Private: candidate generation
    # ------------------------------------------------------------------

    def _generate_candidates(
        self,
        rates: list[tuple[int, str, float]],
        high_demand: list[int],
        target_date: date,
        usage_by_hour: dict = None,
    ) -> list[list[ScheduleSlot]]:
        """Generate 3 candidate schedules to evaluate."""
        peak_hours = [h for h, tier, _ in rates if tier == "peak"]
        off_peak_hours = [h for h, tier, _ in rates if tier == "off_peak"]
        mid_peak_hours = [h for h, tier, _ in rates if tier == "mid_peak"]

        candidates = []

        # --- Candidate 1: Pre-heat before peak, coast during peak ---
        slots: list[ScheduleSlot] = []
        if off_peak_hours:
            # Start pre-heat 2h before first demand window, during off-peak
            for demand_hour in sorted(high_demand):
                pre_heat_hour = max(0, demand_hour - 2)
                # Find the last off-peak hour before pre_heat_hour
                valid_off = [h for h in off_peak_hours if h <= pre_heat_hour]
                start_hour = valid_off[-1] if valid_off else (off_peak_hours[0] if off_peak_hours else 3)
                slots.append(ScheduleSlot(
                    hour=start_hour, minute=0,
                    setpoint=min(self.preferred_setpoint + 10, 130.0),
                    mode="HEAT_PUMP_ONLY"
                ))
                if len(slots) >= 2:
                    break

        if peak_hours:
            # Drop setpoint at peak start to coast
            slots.append(ScheduleSlot(
                hour=min(peak_hours), minute=0,
                setpoint=max(self.min_acceptable_temp + 5, self.preferred_setpoint - 10),
                mode="ENERGY_SAVING"
            ))
            # Recover after peak ends
            post_peak = min(peak_hours) + (max(peak_hours) - min(peak_hours) + 2)
            if post_peak < 24:
                slots.append(ScheduleSlot(
                    hour=post_peak, minute=0,
                    setpoint=self.preferred_setpoint,
                    mode="ENERGY_SAVING"
                ))

        slots = _deduplicate_slots(slots)[:_MAX_SCHEDULE_ENTRIES]
        if slots:
            candidates.append(slots)

        # --- Candidate 2: Maximize off-peak heating ---
        slots2: list[ScheduleSlot] = []
        if off_peak_hours:
            slots2.append(ScheduleSlot(
                hour=3, minute=0,
                setpoint=min(self.preferred_setpoint + 12, 130.0),
                mode="HEAT_PUMP_ONLY"
            ))
        slots2.append(ScheduleSlot(
            hour=6, minute=0,
            setpoint=self.preferred_setpoint,
            mode="ENERGY_SAVING"
        ))
        if peak_hours:
            slots2.append(ScheduleSlot(
                hour=min(peak_hours), minute=0,
                setpoint=self.min_acceptable_temp + 5,
                mode="ENERGY_SAVING"
            ))
            slots2.append(ScheduleSlot(
                hour=max(peak_hours) + 1, minute=0,
                setpoint=self.preferred_setpoint,
                mode="ENERGY_SAVING"
            ))
        slots2 = _deduplicate_slots(slots2)[:_MAX_SCHEDULE_ENTRIES]
        candidates.append(slots2)

        # --- Candidate 3: OFF overnight, ON morning, OFF peak, ON evening ---
        # Pattern: OFF → heat pump pre-heat → OFF during peak → recover after peak
        # This is the most aggressive savings pattern within 4 setpoints
        if peak_hours:
            slots3 = [
                ScheduleSlot(hour=0, minute=0, setpoint=self.min_acceptable_temp, mode="OFF"),           # OFF overnight
                ScheduleSlot(hour=4, minute=0,                                       # Pre-heat before morning
                    setpoint=min(self.preferred_setpoint + 10, 130.0), mode="HEAT_PUMP_ONLY"),
                ScheduleSlot(hour=min(peak_hours), minute=0, setpoint=self.min_acceptable_temp, mode="OFF"),  # OFF during peak
                ScheduleSlot(hour=max(peak_hours) + 1, minute=0,                     # Recover after peak
                    setpoint=self.preferred_setpoint, mode="HEAT_PUMP_ONLY"),
            ]
        else:
            slots3 = [
                ScheduleSlot(hour=0, minute=0, setpoint=self.min_acceptable_temp, mode="OFF"),
                ScheduleSlot(hour=5, minute=0, setpoint=min(self.preferred_setpoint + 10, 130.0), mode="HEAT_PUMP_ONLY"),
                ScheduleSlot(hour=10, minute=0, setpoint=self.preferred_setpoint, mode="ENERGY_SAVING"),
                ScheduleSlot(hour=22, minute=0, setpoint=self.min_acceptable_temp, mode="OFF"),
            ]
        candidates.append(slots3)

        # --- Candidate 4: OFF late night + peak, ON morning + evening ---
        # For users who mainly use hot water morning and evening
        first_demand = sorted(high_demand)[0] if high_demand else 7
        last_demand = sorted(high_demand)[-1] if high_demand else 21
        slots4 = [
            ScheduleSlot(hour=max(0, first_demand - 2), minute=0,
                setpoint=min(self.preferred_setpoint + 8, 130.0), mode="HEAT_PUMP_ONLY"),
            ScheduleSlot(hour=min(first_demand + 3, 12), minute=0, setpoint=self.min_acceptable_temp, mode="OFF"),
        ]
        if peak_hours:
            slots4.append(ScheduleSlot(
                hour=max(peak_hours) + 1, minute=0,
                setpoint=self.preferred_setpoint, mode="HEAT_PUMP_ONLY"))
            slots4.append(ScheduleSlot(
                hour=min(last_demand + 2, 23), minute=0, setpoint=self.min_acceptable_temp, mode="OFF"))
        else:
            slots4.append(ScheduleSlot(hour=16, minute=0, setpoint=self.preferred_setpoint, mode="ENERGY_SAVING"))
            slots4.append(ScheduleSlot(hour=22, minute=0, setpoint=self.min_acceptable_temp, mode="OFF"))
        slots4 = _deduplicate_slots(slots4)[:_MAX_SCHEDULE_ENTRIES]
        candidates.append(slots4)

        # --- Candidate 5: Conservative — lower setpoint during peak, no OFF ---
        slots5 = [
            ScheduleSlot(hour=4, minute=0, setpoint=self.preferred_setpoint, mode="ENERGY_SAVING"),
            ScheduleSlot(hour=17, minute=0, setpoint=self.preferred_setpoint - 8, mode="ENERGY_SAVING"),
            ScheduleSlot(hour=21, minute=0, setpoint=self.preferred_setpoint, mode="ENERGY_SAVING"),
        ]
        candidates.append(slots5)

        return candidates

    # ------------------------------------------------------------------
    # Private: evaluation
    # ------------------------------------------------------------------

    def _evaluate(
        self,
        slots: list[ScheduleSlot],
        rates: list[tuple[int, str, float]],
        usage_by_hour: dict[int, float],
    ) -> OptimizationResult:
        """Simulate 24h and compute cost + comfort violations."""
        # Build hour→(setpoint, mode, rate) from schedule
        schedule_map: dict[int, ScheduleSlot] = {}
        active_slot = slots[0] if slots else ScheduleSlot(0, 0, self.preferred_setpoint, "ENERGY_SAVING")
        for hour in range(24):
            for slot in slots:
                if slot.hour <= hour:
                    active_slot = slot
            schedule_map[hour] = active_slot

        tank_temp = self.preferred_setpoint
        total_cost = 0.0
        violations = 0

        for hour, tier, rate in rates:
            slot = schedule_map[hour]
            target = slot.setpoint
            gallons_drawn = usage_by_hour.get(hour, 0.0)
            heat_rate = _mode_heat_rate(slot.mode)
            tank_vol = 50.0   # gallons (typical tank) — constant for all hour calculations

            # Hot water draw cools the tank (incoming cold water ~55°F mixes in)
            if gallons_drawn > 0:
                cold_temp = 55.0
                mix_ratio = min(gallons_drawn / tank_vol, 0.8)
                tank_temp = tank_temp * (1 - mix_ratio) + cold_temp * mix_ratio

            # Standby heat loss
            tank_temp -= _STANDBY_LOSS_PER_HOUR

            # Heating needed (OFF/VACATION = no heating, just losses)
            kwh_this_hour = 0.0
            if slot.mode not in ("OFF", "VACATION") and tank_temp < target:
                degrees_needed = min(target - tank_temp, heat_rate)
                tank_temp += degrees_needed
                cop = 3.5 if slot.mode in ("HEAT_PUMP_ONLY", "ENERGY_SAVING") else 1.0
                kwh_this_hour = (degrees_needed * tank_vol * 8.33 / 3412) / cop

            total_cost += kwh_this_hour * rate

            if tank_temp < self.min_acceptable_temp:
                violations += 1

        explanation = self._build_explanation(slots, total_cost, violations)
        return OptimizationResult(
            schedule=slots,
            estimated_daily_cost=round(total_cost, 4),
            current_daily_cost=None,
            savings_pct=None,
            explanation=explanation,
            comfort_violations=violations,
        )

    def _fallback(self, rates: list[tuple[int, str, float]]) -> OptimizationResult:
        slots = [ScheduleSlot(hour=0, minute=0, setpoint=self.preferred_setpoint, mode="ENERGY_SAVING")]
        avg_rate = sum(r for _, _, r in rates) / len(rates) if rates else 0.12
        est_cost = round(3.0 * avg_rate, 4)   # rough 3 kWh/day estimate
        return OptimizationResult(
            schedule=slots,
            estimated_daily_cost=est_cost,
            current_daily_cost=None,
            savings_pct=None,
            explanation="Using default always-on schedule (insufficient historical data for optimization).",
            comfort_violations=0,
        )

    def _estimate_unoptimized_cost(
        self, usage_by_hour: dict[int, float], rates: list[tuple[int, str, float]]
    ) -> float:
        """Estimate cost with no schedule optimization (heater responds on demand)."""
        tank_temp = self.preferred_setpoint
        total_cost = 0.0
        for hour, tier, rate in rates:
            gallons = usage_by_hour.get(hour, 0.0)
            if gallons > 0:
                tank_vol = 50.0
                cold_temp = 55.0
                mix_ratio = min(gallons / tank_vol, 0.8)
                tank_temp = tank_temp * (1 - mix_ratio) + cold_temp * mix_ratio
            tank_temp -= _STANDBY_LOSS_PER_HOUR
            if tank_temp < self.preferred_setpoint:
                degrees_needed = min(self.preferred_setpoint - tank_temp, _ENERGY_SAVING_RATE)
                tank_temp += degrees_needed
                cop = 3.5
                kwh = (degrees_needed * 50.0 * 8.33 / 3412) / cop
                total_cost += kwh * rate
        return round(total_cost, 4)

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _hourly_rates(self, d: date) -> list[tuple[int, str, float]]:
        return [(h, *_get_tou_tier(d, h, self._tou)) for h in range(24)]

    def _find_demand_windows(self, usage_by_hour: dict[int, float]) -> list[int]:
        """Return hours where usage is above the 75th percentile."""
        if not usage_by_hour:
            return [7, 8, 18, 19]  # sensible defaults
        values = sorted(usage_by_hour.values())
        if len(values) < 4:
            return list(usage_by_hour.keys())
        threshold = values[int(len(values) * 0.75)]
        return [h for h, g in usage_by_hour.items() if g >= threshold]

    def _find_idle_windows(self, high_demand: list, usage_by_hour: dict) -> list:
        """Find windows of 3+ consecutive hours with zero or near-zero usage.

        Returns list of (start_hour, end_hour) tuples, sorted by length descending.
        """
        # Build hourly usage, defaulting to 0 for hours without data
        hourly = [usage_by_hour.get(h, 0.0) for h in range(24)]

        # Find consecutive runs of zero/near-zero usage
        threshold = 0.5  # gallons — below this is "idle"
        windows = []
        start = None
        for h in range(24):
            if hourly[h] <= threshold and h not in high_demand:
                if start is None:
                    start = h
            else:
                if start is not None and (h - start) >= 3:
                    windows.append((start, h))
                start = None
        if start is not None and (24 - start) >= 3:
            windows.append((start, 24))

        # Sort by length descending (longest idle window first)
        windows.sort(key=lambda w: w[1] - w[0], reverse=True)
        return windows

    def _build_explanation(
        self, slots: list[ScheduleSlot], cost: float, violations: int
    ) -> str:
        mode_labels = {
            "OFF": "Off (no heating)", "ENERGY_SAVING": "Energy Saving",
            "HEAT_PUMP_ONLY": "Heat Pump Only (cheapest)", "HIGH_DEMAND": "High Demand",
            "ELECTRIC_MODE": "Electric (expensive)", "VACATION": "Vacation",
        }
        lines = [f"Estimated daily cost: ${cost:.3f}\n"]
        for i, slot in enumerate(slots):
            t = f"{slot.hour:02d}:{slot.minute:02d}"
            mode_desc = mode_labels.get(slot.mode, slot.mode)
            next_slot = slots[i + 1] if i + 1 < len(slots) else None
            end_t = f"{next_slot.hour:02d}:00" if next_slot else "midnight"
            if slot.mode == "OFF":
                lines.append(f"  {t}–{end_t}  OFF — heater idle, zero energy cost")
            else:
                lines.append(f"  {t}–{end_t}  {slot.setpoint}°F — {mode_desc}")
        lines.append("")
        if violations:
            lines.append(f"⚠ {violations} hour(s) may drop below {self.min_acceptable_temp}°F minimum.")
        else:
            lines.append("✓ All comfort constraints met.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mode_heat_rate(mode: str) -> float:
    if mode in ("ELECTRIC_MODE", "HIGH_DEMAND", "PERFORMANCE"):
        return _ELECTRIC_RATE_PER_HOUR
    return _HEAT_PUMP_RATE_PER_HOUR


def _deduplicate_slots(slots: list[ScheduleSlot]) -> list[ScheduleSlot]:
    """Remove duplicate hours, keeping last occurrence."""
    seen: dict[int, ScheduleSlot] = {}
    for slot in slots:
        seen[slot.hour] = slot
    return sorted(seen.values(), key=lambda s: s.hour)
