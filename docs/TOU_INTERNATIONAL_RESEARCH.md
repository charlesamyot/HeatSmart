# International Time-of-Use (TOU) Electricity Rate Research

> **Purpose**: Server-side default TOU rate definitions for WattWise energy savings app.
> **Scope**: Canada and Europe.
> **Date**: April 2026 (rates should be verified against current utility publications).
> **Status**: Research document -- rates are based on published utility schedules as of
> early-to-mid 2025. All CAD/EUR/GBP amounts are in local currency unless noted.

---

## Table of Contents

1. [Canada](#1-canada)
   - [Ontario (OEB Regulated TOU)](#11-ontario-oeb-regulated-tou)
   - [British Columbia (BC Hydro)](#12-british-columbia-bc-hydro)
   - [Alberta (Deregulated)](#13-alberta-deregulated)
   - [Quebec (Hydro-Quebec)](#14-quebec-hydro-quebec)
   - [Other Canadian Provinces](#15-other-canadian-provinces)
2. [Europe](#2-europe)
   - [United Kingdom](#21-united-kingdom)
   - [Germany](#22-germany)
   - [France](#23-france)
   - [Netherlands](#24-netherlands)
   - [Nordics (Nord Pool)](#25-nordics-nord-pool)
   - [Spain](#26-spain)
   - [Italy](#27-italy)
3. [Key Architectural Questions](#3-key-architectural-questions)
4. [Proposed Schema Design](#4-proposed-schema-design)
5. [API Reference Summary](#5-api-reference-summary)

---

## 1. Canada

### 1.1 Ontario (OEB Regulated TOU)

**Regulator**: Ontario Energy Board (OEB)
**Applies to**: All regulated-price-plan (RPP) customers of local distribution companies
(Toronto Hydro, Hydro One, Alectra, etc.)

Ontario has the most mature fixed-block TOU system in Canada. The OEB sets province-wide
TOU prices that are updated May 1 and November 1 each year.

#### Rate Tiers (as of November 2024 -- verify for current period)

| Tier     | Winter (Nov 1 - Apr 30) | Summer (May 1 - Oct 31) |
|----------|------------------------|------------------------|
| Off-Peak | 7.6 cents/kWh          | 7.6 cents/kWh          |
| Mid-Peak | 12.2 cents/kWh         | 12.2 cents/kWh         |
| On-Peak  | 15.8 cents/kWh         | 15.8 cents/kWh         |

Note: The per-kWh prices are the same across seasons; what changes is which hours
are classified as mid-peak vs. on-peak.

#### Time Blocks

**Winter (November 1 -- April 30)**

| Period    | Weekdays            | Weekends/Holidays |
|-----------|---------------------|-------------------|
| Off-Peak  | 7:00 PM -- 7:00 AM  | All day           |
| Mid-Peak  | 11:00 AM -- 5:00 PM | --                |
| On-Peak   | 7:00 AM -- 11:00 AM, 5:00 PM -- 7:00 PM | -- |

**Summer (May 1 -- October 31)**

| Period    | Weekdays            | Weekends/Holidays |
|-----------|---------------------|-------------------|
| Off-Peak  | 7:00 PM -- 7:00 AM  | All day           |
| Mid-Peak  | 7:00 AM -- 11:00 AM, 5:00 PM -- 7:00 PM | -- |
| On-Peak   | 11:00 AM -- 5:00 PM | --                |

Key points:
- Summer and winter swap the on-peak and mid-peak blocks.
- Weekends and Ontario statutory holidays are always off-peak (all day).
- Ontario statutory holidays: New Year's, Family Day (3rd Mon Feb), Good Friday,
  Victoria Day (Mon before May 25), Canada Day, Civic Holiday (1st Mon Aug),
  Labour Day, Thanksgiving (2nd Mon Oct), Christmas, Boxing Day.

#### Data Source

- OEB publishes rates at: `https://www.oeb.ca/consumer-information-and-protection/electricity-rates`
- No public API. Rates are published as PDF/HTML tables on the OEB website.
- Rates change on a fixed schedule (May 1 / Nov 1), making static defaults practical.
- The time block structure has been stable since ~2015. Only the per-kWh prices change.

#### Default YAML for WattWise

```yaml
utility: Ontario Energy Board (RPP)
region: ON
country: CA
currency: CAD
base_service_charge_per_day: 0.00  # varies by LDC, not part of TOU
season_schedule:
  winter: { start_month: 11, end_month: 4 }
  summer: { start_month: 5, end_month: 10 }
rates:
  winter:
    - name: on_peak
      rate_per_kwh: 0.158
      periods:
        - days: [0,1,2,3,4]
          ranges: [[7,11], [17,19]]
    - name: mid_peak
      rate_per_kwh: 0.122
      periods:
        - days: [0,1,2,3,4]
          ranges: [[11,17]]
    - name: off_peak
      rate_per_kwh: 0.076
      periods:
        - days: [0,1,2,3,4]
          ranges: [[19,24], [0,7]]
        - days: [5,6]
          ranges: [[0,24]]
  summer:
    - name: on_peak
      rate_per_kwh: 0.158
      periods:
        - days: [0,1,2,3,4]
          ranges: [[11,17]]
    - name: mid_peak
      rate_per_kwh: 0.122
      periods:
        - days: [0,1,2,3,4]
          ranges: [[7,11], [17,19]]
    - name: off_peak
      rate_per_kwh: 0.076
      periods:
        - days: [0,1,2,3,4]
          ranges: [[19,24], [0,7]]
        - days: [5,6]
          ranges: [[0,24]]
holidays:
  fixed:
    - { month: 1, day: 1 }    # New Year's
    - { month: 7, day: 1 }    # Canada Day
    - { month: 12, day: 25 }  # Christmas
    - { month: 12, day: 26 }  # Boxing Day
  floating:
    - family_day      # 3rd Mon Feb
    - good_friday     # varies
    - victoria_day    # Mon before May 25
    - civic_holiday   # 1st Mon Aug
    - labour_day      # 1st Mon Sep
    - thanksgiving_ca # 2nd Mon Oct
holiday_treatment: off_peak  # all holidays treated as off-peak (all day)
```

---

### 1.2 British Columbia (BC Hydro)

**Utility**: BC Hydro (Crown corporation)
**Structure**: Two-tier inclining block rate (NOT time-of-use by default), plus
an optional TOU pilot.

#### Standard Residential Rate (Step 1 / Step 2)

BC Hydro uses a two-step conservation rate, not TOU:

| Step       | Rate (approx.)   | Threshold                   |
|------------|-------------------|-----------------------------|
| Step 1     | ~10.05 cents/kWh  | First 1,350 kWh/billing period (approx 22.19 kWh/day) |
| Step 2     | ~15.07 cents/kWh  | All additional kWh           |

This is a volumetric tiered rate, not time-dependent. There is no peak/off-peak
distinction in the standard rate.

#### Optional TOU Pilot

BC Hydro ran a voluntary TOU pilot program. As of 2024-2025, this was still in
pilot phase with limited enrollment. The pilot structure was:

| Period    | Rate (approx.)   | Hours                    |
|-----------|-------------------|--------------------------|
| Off-Peak  | ~7.0 cents/kWh    | 11:00 PM -- 7:00 AM      |
| On-Peak   | ~14.4 cents/kWh   | 4:00 PM -- 9:00 PM       |
| Mid-Peak  | ~10.7 cents/kWh   | All other hours           |

The pilot was seasonal (winter-focused, Oct-Mar had sharper peak pricing).

#### Data Source

- `https://www.bchydro.com/accounts-billing/rates-energy-use/electricity-rates.html`
- No public API for rates.
- For WattWise: offer the standard 2-step rate as default (not TOU), with optional
  TOU pilot rates as an alternative selection.

#### Default YAML for WattWise

```yaml
utility: BC Hydro
region: BC
country: CA
currency: CAD
rate_type: tiered_block  # NOT time-of-use
tiers:
  - name: step_1
    rate_per_kwh: 0.1005
    threshold_kwh_per_day: 22.19
  - name: step_2
    rate_per_kwh: 0.1507
    threshold_kwh_per_day: null  # unlimited above step 1
# Optional TOU pilot (if user opts in):
tou_pilot:
  rates:
    - name: off_peak
      rate_per_kwh: 0.070
      periods:
        - days: [0,1,2,3,4,5,6]
          ranges: [[23,24],[0,7]]
    - name: on_peak
      rate_per_kwh: 0.144
      periods:
        - days: [0,1,2,3,4,5,6]
          ranges: [[16,21]]
    - name: mid_peak
      rate_per_kwh: 0.107
      periods:
        - days: [0,1,2,3,4,5,6]
          ranges: [[7,16],[21,23]]
```

---

### 1.3 Alberta (Deregulated)

**Structure**: Deregulated market. No government-mandated TOU blocks.
**How pricing works**: Customers choose between:

1. **Regulated Rate Option (RRO)**: A monthly variable rate set by the default
   utility (ENMAX in Calgary, EPCOR in Edmonton, others elsewhere). This is a
   single flat rate per kWh that changes monthly. NOT time-of-use.

2. **Competitive retailers**: Fixed-price contracts (flat rate per kWh for a term),
   or floating/spot-indexed plans. Some retailers offer time-differentiated products
   but these are not standardized.

3. **Real-time pricing**: The Alberta Electric System Operator (AESO) publishes
   the wholesale pool price hourly. Some retailers pass through pool price + adder.

#### AESO Pool Price

The wholesale pool price is set hourly and can vary from $0/MWh to over $999/MWh
(the market cap). Typical range is $30-$150/MWh ($0.03-$0.15/kWh).

Peak patterns in Alberta (not formalized but observable):
- Morning peak: ~7:00 AM -- 10:00 AM
- Evening peak: ~5:00 PM -- 9:00 PM (especially winter)
- Off-peak: overnight and midday (solar generation suppresses midday in summer)

#### AESO Data API

AESO provides real-time and historical pool price data:
- **Real-time**: `http://ets.aeso.ca/ets_web/ip/Market/Reports/SMPriceReportServlet`
- **API**: AESO ETS (Energy Trading System) public reports
- **Format**: CSV/HTML reports, updated every few minutes
- **Historical**: Available through AESO reporting portal

For WattWise, Alberta support should either:
- Use the monthly RRO rate as a flat rate (simplest)
- Optionally pull AESO pool prices for power users who want real-time optimization

#### Default YAML for WattWise

```yaml
utility: Alberta RRO (ENMAX/EPCOR)
region: AB
country: CA
currency: CAD
rate_type: flat_variable  # single rate, changes monthly
flat_rate_per_kwh: 0.0872  # sample RRO rate -- varies monthly
# Alternative: AESO pool price integration
aeso_pool_price:
  api_url: "http://ets.aeso.ca/ets_web/ip/Market/Reports/SMPriceReportServlet"
  format: html_table
  update_frequency: 5_minutes
  note: "Pool price in $/MWh, divide by 1000 for $/kWh. Add retailer markup."
```

---

### 1.4 Quebec (Hydro-Quebec)

**Utility**: Hydro-Quebec (Crown corporation)
**Structure**: Historically flat-rate (tiered block), but introduced dynamic
pricing in 2019 with the "Flex D" (Winter Credit) option, expanded over time.

#### Standard Rate D (Domestic)

Two-tier inclining block rate (not time-of-use):

| Tier    | Rate (approx.)    | Threshold                    |
|---------|-------------------|------------------------------|
| First   | ~7.59 cents/kWh   | First 40 kWh/day             |
| Second  | ~10.49 cents/kWh  | All additional kWh            |

Note: Quebec has among the lowest electricity rates in North America due to
extensive hydroelectric generation.

#### Flex D (Dynamic Pricing Option)

Hydro-Quebec's "Flex D" rate is an opt-in dynamic pricing option focused on
winter peak events. It is NOT traditional fixed-block TOU -- it is event-driven:

- **Winter critical peak events**: Hydro-Quebec sends signals on cold winter days
  (typically December-March) when demand is very high. During these events
  (typically 6:00 AM - 9:00 AM and 4:00 PM - 8:00 PM), the rate increases to
  ~50 cents/kWh.
- **Off-peak credits**: In exchange, customers get a credit (~3 cents/kWh discount)
  on all non-event consumption.
- **Events**: Maximum ~30 events per winter season, announced day-ahead via app/email.
- **Summer**: No events -- standard rate applies year-round outside winter.

The Flex D API/notification system:
- Hydro-Quebec publishes event alerts via their app and website
- No documented public API for event signals
- Events typically announced by 3:00 PM the day before

#### Default YAML for WattWise

```yaml
utility: Hydro-Quebec
region: QC
country: CA
currency: CAD
rate_type: tiered_block  # base rate is tiered, not TOU
tiers:
  - name: first_tier
    rate_per_kwh: 0.0759
    threshold_kwh_per_day: 40
  - name: second_tier
    rate_per_kwh: 0.1049
    threshold_kwh_per_day: null
# Flex D dynamic pricing overlay (opt-in)
flex_d:
  enabled: false  # user opts in
  winter_event_rate_per_kwh: 0.50
  off_peak_credit_per_kwh: 0.03
  event_hours_morning: [6, 9]     # 6 AM - 9 AM
  event_hours_evening: [16, 20]   # 4 PM - 8 PM
  event_season: { start_month: 12, end_month: 3 }
  max_events_per_season: 30
  notification: day_ahead
  api: null  # no public API -- manual or push notification
```

---

### 1.5 Other Canadian Provinces

#### Nova Scotia (Nova Scotia Power)

Two-tier inclining block rate. No TOU program.
- First 10,000 kWh/year: ~17.48 cents/kWh
- Above 10,000 kWh/year: ~18.21 cents/kWh

#### New Brunswick (NB Power)

Two-tier inclining block rate. No residential TOU.
- First 1,400 kWh/month: ~12.96 cents/kWh
- Above 1,400 kWh/month: ~16.35 cents/kWh

#### Manitoba (Manitoba Hydro)

Flat rate, no TOU:
- ~9.94 cents/kWh (all consumption)
- Very low rates due to hydroelectric generation.

#### Saskatchewan (SaskPower)

Two-tier rate, no TOU:
- First 1,000 kWh/month: ~15.87 cents/kWh
- Above: ~17.77 cents/kWh

#### Prince Edward Island (Maritime Electric)

Flat residential rate: ~17.9 cents/kWh. No TOU.

**Summary**: Ontario is the only Canadian province with a mandatory/standard TOU
rate structure. BC has a pilot. Quebec has event-based dynamic pricing (Flex D).
All other provinces use flat or tiered-block rates with no time differentiation.

---

## 2. Europe

### 2.1 United Kingdom

The UK has a diverse and competitive retail electricity market with several
TOU and dynamic tariff options.

#### Economy 7 / Economy 10 (Legacy TOU)

The traditional UK TOU tariffs, available from most suppliers:

**Economy 7** (most common legacy TOU):
- 7 hours of cheaper off-peak electricity overnight
- Exact hours vary by region and meter, but typically:

| Period   | Hours (typical)     | Rate (approx.)     |
|----------|--------------------|--------------------|
| Off-Peak | 12:00 AM -- 7:00 AM | ~15-18p/kWh        |
| Peak     | 7:00 AM -- 12:00 AM | ~30-38p/kWh        |

Note: Hours vary by electricity region (14 regions in UK). Some meters use
1:00 AM -- 8:00 AM. The meter hardware determines the exact hours.

**Economy 10**: 10 hours of off-peak across three windows:
- Overnight: ~12:00 AM -- 5:00 AM (5 hours)
- Afternoon: ~1:00 PM -- 4:00 PM (3 hours)
- Evening: ~8:00 PM -- 10:00 PM (2 hours)

#### Octopus Energy Agile Tariff

The most prominent dynamic/TOU tariff in the UK. Prices change every 30 minutes
based on wholesale market conditions.

**Structure**:
- 48 half-hourly price slots per day
- Prices published day-ahead at ~4:00 PM for the following day (4:00 PM - 4:00 PM)
- Prices can go negative (customer is paid to use electricity) during low-demand/high-wind
- Price cap: 100p/kWh (was 78p, may be adjusted)
- Typical range: 5p-35p/kWh, with occasional negative prices or spikes

**Octopus Agile API** (public, well-documented):
```
GET https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25/electricity-tariffs/E-1R-AGILE-FLEX-22-11-25-{REGION}/standard-unit-rates/

Query params:
  period_from: ISO 8601 datetime
  period_to: ISO 8601 datetime
  page_size: integer

Response format (JSON):
{
  "count": 48,
  "results": [
    {
      "value_exc_vat": 15.32,     // p/kWh excluding VAT
      "value_inc_vat": 16.09,     // p/kWh including VAT (5% domestic)
      "valid_from": "2025-01-15T00:00:00Z",
      "valid_to": "2025-01-15T00:30:00Z"
    },
    ...
  ]
}
```

Region codes (GSP Groups): A through P (14 regions).
- A = East England, B = East Midlands, C = London, etc.
- Product codes change periodically (AGILE-FLEX-22-11-25 is one version).

**Authentication**: API key required (free, obtained from Octopus account).
Public product listing available without auth.

**Octopus Go Tariff** (simpler TOU):

| Period   | Hours              | Rate (approx.)     |
|----------|--------------------|---------------------|
| Off-Peak | 12:30 AM -- 4:30 AM | ~12p/kWh           |
| Peak     | 4:30 AM -- 12:30 AM | ~27p/kWh           |

Octopus Go is designed for EV owners but works for any flexible load.

#### British Gas / EDF Energy / Other Big Six

Most large UK suppliers offer Economy 7 meters but not dynamic tariffs.
No public APIs from British Gas or EDF UK.

- British Gas: Standard variable tariff or fixed-price. Economy 7 available.
- EDF Energy: Standard or fixed. Economy 7/10 available where meters exist.
- No real-time or day-ahead price APIs from these suppliers.

#### Default YAML for WattWise (UK)

```yaml
utility: UK Default (Economy 7)
region: UK
country: GB
currency: GBP
rate_type: fixed_tou
rates:
  - name: off_peak
    rate_per_kwh: 0.17  # 17p/kWh
    periods:
      - days: [0,1,2,3,4,5,6]
        ranges: [[0,7]]  # midnight to 7 AM
  - name: peak
    rate_per_kwh: 0.34   # 34p/kWh
    periods:
      - days: [0,1,2,3,4,5,6]
        ranges: [[7,24]]
# Dynamic option:
dynamic_tariff:
  provider: octopus_agile
  api_base: "https://api.octopus.energy/v1/products/"
  product_code: "AGILE-FLEX-22-11-25"
  resolution_minutes: 30
  auth_required: true  # API key from Octopus account
  price_unit: pence_per_kwh
  vat_rate: 0.05
  day_ahead_publish_time: "16:00"
  price_cap_pence: 100
```

---

### 2.2 Germany

Germany has moved aggressively toward dynamic tariffs since the EU Electricity
Market Directive (2019/944) requirement that all suppliers offer dynamic contracts.

#### Traditional Rate Structure

Most German households are on flat-rate contracts:
- Typical residential rate: ~30-40 cents/kWh (EUR) -- among the highest in Europe
- No government-mandated TOU blocks

Some older installations have "Nachtstrom" (night electricity) with a two-tariff
meter (HT/NT -- Hochtarif/Niedertarif):

| Period   | Hours (typical)      | Rate (approx.)     |
|----------|---------------------|---------------------|
| HT (day) | 6:00 AM -- 10:00 PM | ~35-42 cents/kWh   |
| NT (night)| 10:00 PM -- 6:00 AM| ~25-30 cents/kWh   |

#### Tibber (Dynamic Tariff)

Tibber is a pan-European energy company offering hourly spot-price pass-through.

**Structure**:
- Hourly prices based on EPEX Spot day-ahead auction
- Prices published ~1:00 PM for the next day (noon-noon)
- Customer pays: spot price + Tibber margin (~1-2 cents) + grid fees + taxes
- Prices can go negative

**Tibber API** (GraphQL):
```
POST https://api.tibber.com/v1-beta/gql

Headers:
  Authorization: Bearer {PERSONAL_ACCESS_TOKEN}

Query:
{
  viewer {
    homes {
      currentSubscription {
        priceInfo {
          current { total currency level startsAt }
          today { total startsAt level }
          tomorrow { total startsAt level }
        }
      }
    }
  }
}

Response:
{
  "data": {
    "viewer": {
      "homes": [{
        "currentSubscription": {
          "priceInfo": {
            "current": {
              "total": 0.2931,      // EUR/kWh (all-in)
              "currency": "EUR",
              "level": "NORMAL",    // VERY_CHEAP, CHEAP, NORMAL, EXPENSIVE, VERY_EXPENSIVE
              "startsAt": "2025-01-15T13:00:00+01:00"
            },
            "today": [...],         // 24 hourly entries
            "tomorrow": [...]       // available after ~1 PM
          }
        }
      }]
    }
  }
}
```

**Authentication**: Personal access token required (free from Tibber account).
A demo token is available for testing: `5K4MVS-OjfWhK_4yrjOlFe1F6kJXPVf7eQYggo8ebAE`

#### aWATTar (Dynamic Tariff)

Austrian/German dynamic electricity provider. Offers an hourly tariff.

**aWATTar API** (public, no auth required):
```
GET https://api.awattar.de/v1/marketdata

Query params:
  start: Unix timestamp (ms) -- optional
  end: Unix timestamp (ms) -- optional

Response (JSON):
{
  "object": "list",
  "data": [
    {
      "start_timestamp": 1705276800000,
      "end_timestamp": 1705280400000,
      "marketprice": 85.23,        // EUR/MWh (divide by 10 for cents/kWh)
      "unit": "Eur/MWh"
    },
    ...
  ]
}
```

This is the EPEX Spot Day-Ahead auction price. No authentication required.
Returns 24 hourly entries. Grid fees, taxes, and margin are NOT included --
those must be added based on the customer's specific situation.

#### Default YAML for WattWise (Germany)

```yaml
utility: Germany Default
region: DE
country: DE
currency: EUR
rate_type: dynamic_spot
spot_source: epex_day_ahead
# Fallback static HT/NT rates:
static_fallback:
  - name: day_ht
    rate_per_kwh: 0.38
    periods:
      - days: [0,1,2,3,4,5,6]
        ranges: [[6,22]]
  - name: night_nt
    rate_per_kwh: 0.27
    periods:
      - days: [0,1,2,3,4,5,6]
        ranges: [[22,24],[0,6]]
dynamic_tariffs:
  tibber:
    api_url: "https://api.tibber.com/v1-beta/gql"
    auth_required: true
    format: graphql
    resolution_minutes: 60
    price_includes: all_in  # spot + margin + grid + taxes
  awattar:
    api_url: "https://api.awattar.de/v1/marketdata"
    auth_required: false
    format: json_rest
    resolution_minutes: 60
    price_includes: spot_only  # must add grid fees + taxes
    price_unit: eur_per_mwh   # divide by 10 for cents/kWh
```

---

### 2.3 France

France has the most structured fixed-TOU system in Europe, operated by EDF
(the dominant supplier, ~75% market share).

#### Heures Pleines / Heures Creuses (HP/HC -- Peak/Off-Peak)

The standard French TOU option, available to all residential customers:

| Period         | Hours (typical)                | Rate (approx.)     |
|----------------|-------------------------------|---------------------|
| Heures Creuses | 8 hours, varies by commune     | ~20.68 cents/kWh   |
| Heures Pleines | 16 hours                       | ~27.00 cents/kWh   |

**Critical detail**: The exact HC hours vary by commune/distribution point. Common
patterns include:
- 10:00 PM -- 6:00 AM (single night block)
- 11:00 PM -- 7:00 AM (single night block)
- 11:30 PM -- 7:30 AM (single night block)
- 1:00 PM -- 3:00 PM + 2:00 AM -- 8:00 AM (split block with midday off-peak)

The HC hours are determined by the local grid operator (Enedis) and are printed
on the meter or available via the Enedis Linky portal. There is no national
standard set of hours -- it varies by distribution point.

**No seasonal variation** in HP/HC -- same hours year-round.
**No weekend/holiday exception** -- same schedule every day.

#### EDF Tempo Tariff

A more complex dynamic-ish tariff with 6 price levels based on day color:

**Day Colors** (announced day-ahead at 5:00 PM):
- **Blue days** (Jours Bleus): 300 days/year -- cheapest
- **White days** (Jours Blancs): 43 days/year -- moderate
- **Red days** (Jours Rouges): 22 days/year -- most expensive (always winter weekdays)

Each day color has HC and HP pricing:

| Day Color | Heures Creuses (HC)  | Heures Pleines (HP)  |
|-----------|---------------------|---------------------|
| Blue      | ~15.68 cents/kWh    | ~16.50 cents/kWh    |
| White     | ~18.07 cents/kWh    | ~19.89 cents/kWh    |
| Red       | ~15.69 cents/kWh    | ~79.47 cents/kWh    |

Red day HP pricing is extremely high (~80 cents/kWh), creating a strong incentive
to shift load. Red days are always November-March, always weekdays, never during
school holidays.

**Tempo API/Signal**:
- EDF publishes the day color for tomorrow at 5:00 PM
- Available on the EDF Tempo page and via the RTE (Reseau de Transport d'Electricite) API
- RTE Eco2Mix API provides Tempo signals

**RTE API** (France's TSO):
```
GET https://digital.iservices.rte-france.com/open_api/tempo_like_supply_contract/v1/tempo_like_calendars

Headers:
  Authorization: Bearer {ACCESS_TOKEN}

Response includes day-by-day color assignments.
```

RTE API requires OAuth2 client credentials (free registration at
`https://data.rte-france.com/`).

#### Default YAML for WattWise (France)

```yaml
utility: EDF France
region: FR
country: FR
currency: EUR
rate_type: fixed_tou  # HP/HC
# Note: HC hours vary by commune. These are the most common pattern.
rates:
  - name: heures_creuses
    rate_per_kwh: 0.2068
    periods:
      - days: [0,1,2,3,4,5,6]
        ranges: [[22,24],[0,6]]  # 10 PM - 6 AM (most common)
  - name: heures_pleines
    rate_per_kwh: 0.2700
    periods:
      - days: [0,1,2,3,4,5,6]
        ranges: [[6,22]]
# Tempo overlay (opt-in):
tempo:
  enabled: false
  day_colors:
    blue:
      hc_rate: 0.1568
      hp_rate: 0.1650
      days_per_year: 300
    white:
      hc_rate: 0.1807
      hp_rate: 0.1989
      days_per_year: 43
    red:
      hc_rate: 0.1569
      hp_rate: 0.7947
      days_per_year: 22
      season: { start_month: 11, end_month: 3 }
      weekdays_only: true
  signal_api:
    provider: rte_france
    url: "https://digital.iservices.rte-france.com/open_api/tempo_like_supply_contract/v1/tempo_like_calendars"
    auth: oauth2_client_credentials
    publish_time: "17:00"
```

---

### 2.4 Netherlands

The Netherlands has a fully liberalized electricity market with mandatory smart
meter rollout (nearly complete). Dynamic tariffs are widely available.

#### Traditional Rate

Most Dutch households had flat-rate or dual-tariff (dal/normaal) contracts:

| Period    | Hours (typical)      | Rate (approx.)     |
|-----------|---------------------|---------------------|
| Normaal   | 7:00 AM -- 11:00 PM | ~28-35 cents/kWh   |
| Dal (low) | 11:00 PM -- 7:00 AM + weekends | ~24-30 cents/kWh |

#### Dynamic Tariff Providers

Since January 2023, all Dutch energy suppliers must offer a dynamic tariff option
(EU directive transposition). Major providers:

**Tibber** (same API as Germany, NL market):
- Same GraphQL API, returns NL day-ahead prices
- EPEX Spot NL zone

**ANWB Energie / Zonneplan / Frank Energie / EasyEnergy**:
Multiple providers offer hourly spot-price pass-through.

**EasyEnergy API** (public, no auth):
```
GET https://mijn.easyenergy.com/nl/api/tariff/getapxtariffs
  ?startTimestamp=2025-01-15T00:00:00.000Z
  &endTimestamp=2025-01-16T00:00:00.000Z
  &grouping=

Response (JSON array):
[
  {
    "Timestamp": "2025-01-15T00:00:00+01:00",
    "SupplierId": 1,
    "TariffUsage": 0.08234,      // EUR/kWh (excl. VAT and energy tax)
    "TariffReturn": 0.08234
  },
  ...
]
```

No authentication required. Returns 24 hourly APX (now EPEX) spot prices.
Note: does NOT include energy tax (~12.7 cents/kWh) or VAT (21%) or grid fees.

#### Default YAML for WattWise (Netherlands)

```yaml
utility: Netherlands Default
region: NL
country: NL
currency: EUR
rate_type: dual_tariff  # normaal/dal
rates:
  - name: normaal
    rate_per_kwh: 0.32
    periods:
      - days: [0,1,2,3,4]
        ranges: [[7,23]]
  - name: dal
    rate_per_kwh: 0.27
    periods:
      - days: [0,1,2,3,4]
        ranges: [[23,24],[0,7]]
      - days: [5,6]
        ranges: [[0,24]]
dynamic_tariffs:
  easyenergy:
    api_url: "https://mijn.easyenergy.com/nl/api/tariff/getapxtariffs"
    auth_required: false
    format: json_rest
    resolution_minutes: 60
    price_includes: spot_only
    surcharges:
      energy_tax_per_kwh: 0.127
      vat_rate: 0.21
  tibber:
    api_url: "https://api.tibber.com/v1-beta/gql"
    auth_required: true
    format: graphql
    resolution_minutes: 60
    price_includes: all_in
```

---

### 2.5 Nordics (Nord Pool)

The Nordic countries (Norway, Sweden, Denmark, Finland) operate under the Nord Pool
spot market. Electricity pricing is inherently dynamic/hourly, with prices set
day-ahead on the Nord Pool exchange.

#### How It Works

- Nord Pool runs a day-ahead auction every day at ~12:42 CET
- Prices published for the next day (24 hourly prices) by ~12:45 CET
- Prices vary by bidding zone (Norway has 5 zones: NO1-NO5; Sweden has 4: SE1-SE4;
  Denmark has 2: DK1, DK2; Finland has 1: FI)
- Most Nordic consumers are on variable/spot-price contracts by default
- Consumer pays: spot price + grid tariff + taxes + retailer margin

#### Typical Price Patterns

There are no fixed TOU blocks, but consistent daily patterns emerge:
- Low prices: ~1:00 AM -- 6:00 AM (can go negative in high-wind periods)
- Morning peak: ~7:00 AM -- 10:00 AM
- Midday dip: ~11:00 AM -- 3:00 PM (especially in summer with solar)
- Evening peak: ~5:00 PM -- 8:00 PM
- Prices are highly seasonal: winter prices much higher than summer

#### Nord Pool API

**Transparency Platform** (public):
```
GET https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices
  ?date=2025-01-15
  &market=DayAhead
  &deliveryArea=NO1,SE3,DK1,FI
  &currency=EUR

Response includes 24 hourly prices per area.
```

Note: Nord Pool has changed their API structure over time. The current data
portal may require different endpoints.

**ENTSO-E Transparency Platform** (EU-wide, covers Nordics):
```
GET https://web-api.tp.entsoe.eu/api
  ?securityToken={TOKEN}
  &documentType=A44           # day-ahead prices
  &in_Domain=10YNO-1--------2  # Norway NO1 EIC code
  &out_Domain=10YNO-1--------2
  &periodStart=202501150000
  &periodEnd=202501160000

Response: XML with hourly price data.
```

ENTSO-E requires a free API key (registered at `https://transparency.entsoe.eu/`).

**Tibber** operates in all Nordic countries and provides the same GraphQL API.

#### Grid Tariffs (Norway example)

Norwegian grid companies are implementing TOU grid tariffs (separate from energy price):

| Period   | Hours              | Grid rate (approx.)  |
|----------|--------------------|----------------------|
| Day      | 6:00 AM -- 10:00 PM | ~35-55 ore/kWh     |
| Night    | 10:00 PM -- 6:00 AM | ~25-35 ore/kWh     |

Plus a capacity-based component (peak demand charge).

#### Default YAML for WattWise (Nordics)

```yaml
utility: Nordic Spot (Nord Pool)
region: Nordic
country: "NO|SE|DK|FI"  # user selects
currency: EUR  # or local: NOK, SEK, DKK
rate_type: dynamic_spot
spot_source: nord_pool_day_ahead
bidding_zones:
  NO: [NO1, NO2, NO3, NO4, NO5]
  SE: [SE1, SE2, SE3, SE4]
  DK: [DK1, DK2]
  FI: [FI]
dynamic_tariffs:
  nord_pool:
    api_url: "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
    auth_required: false
    format: json_rest
    resolution_minutes: 60
    price_includes: spot_only
    price_unit: eur_per_mwh
  entsoe:
    api_url: "https://web-api.tp.entsoe.eu/api"
    auth_required: true  # free API key
    format: xml
    resolution_minutes: 60
    price_includes: spot_only
  tibber:
    api_url: "https://api.tibber.com/v1-beta/gql"
    auth_required: true
    format: graphql
    resolution_minutes: 60
    price_includes: all_in
# Static fallback: approximate Norwegian TOU grid tariff
static_fallback:
  - name: day
    rate_per_kwh: 0.15  # approximate total cost (spot avg + grid + taxes)
    periods:
      - days: [0,1,2,3,4,5,6]
        ranges: [[6,22]]
  - name: night
    rate_per_kwh: 0.08
    periods:
      - days: [0,1,2,3,4,5,6]
        ranges: [[22,24],[0,6]]
```

---

### 2.6 Spain

Spain has a regulated TOU tariff that applies to most residential consumers.

#### PVPC (Precio Voluntario para el Pequeno Consumidor)

Since June 2021, Spain implemented mandatory TOU periods for all consumers on
the regulated PVPC tariff:

**Three-period structure** (applies to tariff 2.0TD):

| Period | Weekday Hours                              | Rate Behavior     |
|--------|--------------------------------------------|--------------------|
| Punta (Peak)   | 10:00 AM -- 2:00 PM, 6:00 PM -- 10:00 PM | Highest           |
| Llano (Flat)   | 8:00 AM -- 10:00 AM, 2:00 PM -- 6:00 PM, 10:00 PM -- 12:00 AM | Middle |
| Valle (Off-Peak)| 12:00 AM -- 8:00 AM                      | Lowest            |

**Weekend/Holiday**: All hours are "Valle" (off-peak).

**Seasonal note**: The time periods are the same year-round. However, PVPC energy
prices themselves are set hourly based on the wholesale market (OMIE), so the actual
price per kWh varies hour by hour. The period classification (Punta/Llano/Valle)
affects the grid access charges (peajes), not the energy component.

#### PVPC/OMIE API

**REE (Red Electrica de Espana) API** -- provides PVPC prices:
```
GET https://apidatos.ree.es/en/datos/mercados/precios-mercados-tiempo-real
  ?start_date=2025-01-15T00:00
  &end_date=2025-01-15T23:59
  &time_trunc=hour

Response (JSON): hourly PVPC prices in EUR/MWh
```

No authentication required. Data available for current and next day.

**OMIE (Iberian Market Operator)**:
```
GET https://www.omie.es/en/file-access-list
  ?parents%5B0%5D=/&parents%5B1%5D=Day-ahead%20Market&date=2025-01-15

Provides CSV files of day-ahead market results.
```

#### Default YAML for WattWise (Spain)

```yaml
utility: Spain PVPC (2.0TD)
region: ES
country: ES
currency: EUR
rate_type: hybrid_tou_spot  # fixed TOU periods but spot energy pricing
tou_periods:
  - name: punta
    periods:
      - days: [0,1,2,3,4]
        ranges: [[10,14],[18,22]]
  - name: llano
    periods:
      - days: [0,1,2,3,4]
        ranges: [[8,10],[14,18],[22,24]]
  - name: valle
    periods:
      - days: [0,1,2,3,4]
        ranges: [[0,8]]
      - days: [5,6]
        ranges: [[0,24]]
holiday_treatment: valle  # weekends and national holidays are all valle
# Approximate static rates (grid + energy average):
static_rates:
  punta_per_kwh: 0.22
  llano_per_kwh: 0.16
  valle_per_kwh: 0.10
dynamic_tariffs:
  ree:
    api_url: "https://apidatos.ree.es/en/datos/mercados/precios-mercados-tiempo-real"
    auth_required: false
    format: json_rest
    resolution_minutes: 60
    price_unit: eur_per_mwh
```

---

### 2.7 Italy

Italy has a regulated TOU structure managed by ARERA (Autorita di Regolazione
per Energia Reti e Ambiente).

#### Regulated TOU Tariff (Maggior Tutela / Servizio Elettrico Nazionale)

Italian residential consumers on the regulated tariff have three time bands:

| Band | Hours                                     | Rate (approx.)     |
|------|-------------------------------------------|---------------------|
| F1   | Mon-Fri 8:00 AM -- 7:00 PM               | ~27-30 cents/kWh   |
| F2   | Mon-Fri 7:00 AM -- 8:00 AM, 7:00 PM -- 11:00 PM; Sat 7:00 AM -- 11:00 PM | ~25-28 cents/kWh |
| F3   | Mon-Sat 11:00 PM -- 7:00 AM; Sun and holidays all day | ~22-25 cents/kWh |

Note: F1 is the peak weekday band. F2 is the shoulder/transition band. F3 is the
cheapest off-peak band. Some contracts merge F2+F3 into a single "fuori punta" rate.

**No seasonal variation** in the time bands (same year-round).

#### GME/IPEX API

Italy's wholesale market operator (GME) publishes day-ahead prices:
```
GET https://www.mercatoelettrico.org/En/download/DownloadDati.aspx?val=MGP_Prices

CSV download of zonal day-ahead prices (PUN = national average price).
```

No real-time API in the same style as Octopus/Tibber, but data is publicly
available for download.

#### Default YAML for WattWise (Italy)

```yaml
utility: Italy ARERA Regulated
region: IT
country: IT
currency: EUR
rate_type: fixed_tou
rates:
  - name: f1_peak
    rate_per_kwh: 0.285
    periods:
      - days: [0,1,2,3,4]
        ranges: [[8,19]]
  - name: f2_shoulder
    rate_per_kwh: 0.265
    periods:
      - days: [0,1,2,3,4]
        ranges: [[7,8],[19,23]]
      - days: [5]
        ranges: [[7,23]]
  - name: f3_off_peak
    rate_per_kwh: 0.235
    periods:
      - days: [0,1,2,3,4,5]
        ranges: [[23,24],[0,7]]
      - days: [6]
        ranges: [[0,24]]
holiday_treatment: f3_off_peak
```

---

## 3. Key Architectural Questions

### 3.1 Do European TOU rates work fundamentally differently from North American ones?

**Yes, there are three distinct models that WattWise must support:**

| Model | Description | Examples |
|-------|-------------|---------|
| **Fixed-Block TOU** | Pre-defined time blocks with fixed rates. Blocks may change by season. | Ontario, France HP/HC, Italy ARERA, UK Economy 7, Spain (grid charges) |
| **Dynamic Spot Pricing** | Hourly (or half-hourly) prices set day-ahead based on wholesale markets. | Octopus Agile, Tibber, aWATTar, Nord Pool, Spain PVPC (energy component), EasyEnergy |
| **Event-Based Dynamic** | Base rate with occasional high-price critical peak events announced day-ahead. | Quebec Flex D, France EDF Tempo |

Additionally, there are **non-TOU models** that WattWise should support as fallbacks:
- **Flat rate**: Single price per kWh (Alberta RRO, Manitoba)
- **Tiered block**: Price depends on cumulative consumption, not time (BC Hydro, Quebec base, most other Canadian provinces)

**Key differences from North American fixed TOU:**

1. **Granularity**: European dynamic tariffs use 30-minute or 60-minute price slots,
   not multi-hour blocks. The optimizer needs per-hour (or per-half-hour) price inputs,
   not just 3 tiers.

2. **Predictability**: Fixed TOU rates are known months ahead. Dynamic spot prices
   are only known day-ahead (published at ~12:00-5:00 PM for the next day). The
   optimizer must be able to run on day-ahead data and re-optimize each day.

3. **Price volatility**: Spot prices can range from -5 to +80 cents/kWh in a single
   day. Fixed TOU ratios are typically 1.5:1 to 2:1 between peak and off-peak.
   The optimizer should handle negative prices (where running the heater is free/paid).

4. **Weekend/holiday handling**: Some systems (Ontario, Spain, Italy) treat weekends
   as all off-peak. Others (France HP/HC, Nordics) have no weekend distinction.

5. **Seasonal structure**: Ontario swaps which block is peak vs. mid-peak by season.
   France Tempo has a "red day" winter-only penalty. Nordics have much higher winter
   prices but no structural season change.

### 3.2 What schema differences are needed to support both models?

The current WattWise schema (TOURateEntry model) supports fixed-block TOU only:

```python
class TOURateEntry(Base):
    name: str           # peak, mid_peak, off_peak
    start_hour: int     # 0-23
    end_hour: int       # 1-24
    rate_per_kwh: float
    days_of_week: str   # comma-separated 0-6
    holiday_exception: bool
```

**This schema cannot represent:**
- Dynamic hourly/half-hourly prices (no date dimension, no sub-hour resolution)
- Event-based pricing (Tempo day colors, Flex D critical peaks)
- Tiered block rates (volume-based, not time-based)
- Seasonal rate variations within the same tier
- Multiple currencies or regional zones

**Proposed extended schema** -- see Section 4 below.

### 3.3 Which APIs offer real-time or near-real-time rate data?

| API | Auth | Granularity | Latency | Free |
|-----|------|-------------|---------|------|
| **Octopus Energy** (UK) | API key (free) | 30 min | Day-ahead (~4 PM) | Yes |
| **Tibber** (DE, NL, NO, SE) | Personal token | 60 min | Day-ahead (~1 PM) | Yes (with account) |
| **aWATTar** (DE, AT) | None | 60 min | Day-ahead (~1 PM) | Yes |
| **EasyEnergy** (NL) | None | 60 min | Day-ahead | Yes |
| **Nord Pool** (Nordics) | None (data portal) | 60 min | Day-ahead (~12:45 CET) | Yes |
| **ENTSO-E** (EU-wide) | API key (free) | 60 min | Day-ahead | Yes |
| **REE** (Spain) | None | 60 min | Day-ahead | Yes |
| **RTE** (France Tempo) | OAuth2 (free) | Daily color | Day-ahead (~5 PM) | Yes |
| **AESO** (Alberta) | None | 5 min (pool price) | Real-time | Yes |
| **OEB** (Ontario) | None | Static (updated 2x/year) | N/A | Yes (web scrape) |

---

## 4. Proposed Schema Design

To support all three pricing models (fixed TOU, dynamic spot, event-based) alongside
the existing North American fixed-block system, the schema needs to be extended.

### 4.1 Rate Plan Definition

A new `RatePlan` concept wraps the rate configuration:

```python
class RatePlan:
    """Top-level rate configuration for a user's utility."""
    id: int
    name: str                    # e.g., "Ontario TOU", "Octopus Agile"
    utility: str                 # utility name
    country: str                 # ISO 3166-1 alpha-2
    region: str                  # province/state/zone
    currency: str                # ISO 4217 (CAD, EUR, GBP, USD)
    rate_type: str               # fixed_tou | dynamic_spot | event_dynamic |
                                 # flat | tiered_block | hybrid_tou_spot
    timezone: str                # IANA timezone
    is_active: bool
    source_url: str | None       # URL for rate information
    last_verified: date | None   # when rates were last confirmed accurate
```

### 4.2 Fixed TOU Entries (existing, extended)

```python
class TOURateEntry:
    """Fixed time-of-use rate blocks (Ontario, France HP/HC, Italy, UK E7)."""
    id: int
    rate_plan_id: int
    name: str                    # peak, mid_peak, off_peak, heures_creuses, etc.
    rate_per_kwh: float
    start_hour: int              # 0-23
    end_hour: int                # 1-24
    start_minute: int = 0        # for 30-min granularity (UK E7 varies)
    end_minute: int = 0
    days_of_week: str            # comma-separated 0-6
    season: str | None           # winter, summer, or null (year-round)
    holiday_exception: bool = False
    holiday_treatment: str | None  # off_peak, valle, f3, etc.
```

### 4.3 Dynamic Price Cache

```python
class DynamicPriceSlot:
    """Cached hourly/half-hourly prices from dynamic tariff APIs."""
    id: int
    rate_plan_id: int
    timestamp_utc: datetime      # start of the price slot
    duration_minutes: int        # 30 or 60
    price_per_kwh: float         # in local currency, all-in or as specified
    price_includes: str          # spot_only | spot_plus_margin | all_in
    source: str                  # octopus_agile, tibber, awattar, etc.
    fetched_at: datetime         # when we retrieved this price
```

### 4.4 Event-Based Pricing

```python
class PricingEvent:
    """Critical peak / Tempo day color events (Quebec Flex D, France Tempo)."""
    id: int
    rate_plan_id: int
    event_date: date
    event_type: str              # critical_peak, tempo_red, tempo_white, tempo_blue
    rate_per_kwh: float | None   # override rate during event (if applicable)
    start_hour: int | None       # null = all day
    end_hour: int | None
    announced_at: datetime | None
    source: str                  # manual, rte_api, hydroquebec_app
```

### 4.5 Tiered Block Rates

```python
class TieredBlockRate:
    """Volume-based tiered rates (BC Hydro, Quebec base, most Canadian provinces)."""
    id: int
    rate_plan_id: int
    tier_name: str               # step_1, step_2, first_tier, second_tier
    rate_per_kwh: float
    threshold_kwh: float | None  # null = unlimited (top tier)
    threshold_period: str        # daily, monthly, billing_period, annual
```

### 4.6 Dynamic Tariff Configuration

```python
class DynamicTariffConfig:
    """API configuration for fetching dynamic prices."""
    id: int
    rate_plan_id: int
    provider: str                # octopus, tibber, awattar, easyenergy, nord_pool, etc.
    api_url: str
    auth_type: str               # none, api_key, oauth2, bearer_token
    api_key_env_var: str | None  # e.g., "OCTOPUS_API_KEY" (never store key in DB)
    format: str                  # json_rest, graphql, xml, csv
    resolution_minutes: int      # 30 or 60
    price_unit: str              # local_currency_per_kwh, eur_per_mwh, pence_per_kwh
    price_includes: str          # spot_only, all_in
    region_code: str | None      # bidding zone, GSP group, etc.
    fetch_schedule: str          # cron expression or "day_ahead_13:00"
```

---

## 5. API Reference Summary

### Public APIs (No Authentication)

| Provider | Endpoint | Data |
|----------|----------|------|
| aWATTar (DE/AT) | `https://api.awattar.de/v1/marketdata` | Hourly EPEX spot (EUR/MWh) |
| EasyEnergy (NL) | `https://mijn.easyenergy.com/nl/api/tariff/getapxtariffs` | Hourly APX spot (EUR/kWh excl. tax) |
| REE (Spain) | `https://apidatos.ree.es/en/datos/mercados/precios-mercados-tiempo-real` | Hourly PVPC (EUR/MWh) |
| AESO (Alberta) | `http://ets.aeso.ca/ets_web/ip/Market/Reports/SMPriceReportServlet` | 5-min pool price (CAD/MWh) |

### Free Registration Required

| Provider | Endpoint | Auth Type |
|----------|----------|-----------|
| Octopus Energy (UK) | `https://api.octopus.energy/v1/products/` | API key (from account) |
| Tibber (DE/NL/NO/SE) | `https://api.tibber.com/v1-beta/gql` | Bearer token |
| ENTSO-E (EU-wide) | `https://web-api.tp.entsoe.eu/api` | Security token |
| RTE France | `https://digital.iservices.rte-france.com/open_api/` | OAuth2 client credentials |

### Static (No API -- Embedded Defaults)

| Region | Source | Update Frequency |
|--------|--------|-----------------|
| Ontario | OEB website | Twice yearly (May 1, Nov 1) |
| France HP/HC | EDF published rates | ~Annually |
| Italy ARERA | ARERA rate tables | Quarterly |
| UK Economy 7 | Supplier rate cards | ~Annually |
| BC Hydro | BC Hydro website | ~Annually |
| Quebec | Hydro-Quebec website | ~Annually |

---

## Implementation Priority

For v1 of WattWise international support, recommended phased rollout:

### Phase 1: Static Fixed-TOU Defaults
- Ontario (complete, well-structured, large market)
- France HP/HC (simple 2-tier, huge market)
- UK Economy 7 (simple 2-tier, large market)
- Italy ARERA (3-tier, straightforward)
- Spain PVPC periods (3-tier structure for grid charges)

### Phase 2: Dynamic Spot Integration
- Octopus Agile API (UK -- best-documented API)
- aWATTar API (Germany/Austria -- no auth needed, easiest to start)
- Tibber API (covers DE, NL, NO, SE in one integration)

### Phase 3: Event-Based and Advanced
- France Tempo (RTE API integration)
- Quebec Flex D (manual event entry until API available)
- Nord Pool / ENTSO-E (covers all of Europe)

### Phase 4: Canadian Flat/Tiered
- Alberta RRO flat rate
- BC Hydro 2-step
- Quebec base rate
- Other provinces (flat/tiered)

---

## Notes and Caveats

1. **All rates in this document should be verified** against current utility
   publications before shipping as defaults. Electricity rates change regularly.

2. **Tax and surcharges**: European rates often have multiple components (energy,
   grid tariff, taxes, levies) that may or may not be included in the quoted
   price. The schema should track what is included via `price_includes`.

3. **Currency handling**: WattWise currently assumes USD. International support
   requires currency field on rate plans and proper display formatting.

4. **Timezone handling**: All TOU schedules are in local time. The app must
   correctly apply the user's timezone, which may differ from the server timezone.
   The current `default_rates.yaml` does not specify timezone.

5. **Smart meter data**: In Europe, smart meters (Linky in France, SMETS2 in UK)
   often provide consumption data that could enhance optimization. This is a
   future integration opportunity but out of scope for TOU rate defaults.

6. **VAT**: UK domestic electricity has 5% VAT. Most EU countries have reduced
   VAT on electricity (varies 5-21%). Octopus API provides both exc. and inc. VAT.
   Other spot APIs typically provide pre-tax prices.
