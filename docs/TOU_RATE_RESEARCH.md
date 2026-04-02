# Time-of-Use (TOU) Electricity Rate Research

Comprehensive research report for building a server-side TOU rate database
covering the USA, Canada, and Europe.

**Date:** 2026-04-01
**Purpose:** Drive the architecture of the WattWise rate service, allowing users
to select default TOU schedules by utility/zone/city instead of manual entry.

---

## Table of Contents

1. [APIs That Provide TOU Rate Data](#1-apis-that-provide-tou-rate-data)
2. [Public Data Sources and Downloadable Datasets](#2-public-data-sources-and-downloadable-datasets)
3. [Source Comparison Matrix](#3-source-comparison-matrix)
4. [Proposed Supabase Table Schema](#4-proposed-supabase-table-schema)
5. [Top 20 US Utilities and Their TOU Rate Structures](#5-top-20-us-utilities-and-their-tou-rate-structures)
6. [Implementation Recommendations](#6-implementation-recommendations)

---

## 1. APIs That Provide TOU Rate Data

### 1.1 OpenEI Utility Rate Database (URDB) -- PRIMARY SOURCE

- **URL:** `https://api.openei.org/utility_rates`
- **Documentation:** https://openei.org/services/doc/rest/util_rates
- **Data format:** JSON (primary), XML (alternate)
- **Coverage:** ~50,000+ rate schedules from ~3,700+ US utilities. Covers all 50
  states, DC, and US territories.
- **Auth:** Free API key required (register at https://openei.org/services/)
- **Rate limits:** 1,000 requests/hour (free tier)
- **TOU time blocks:** Yes -- includes `energyratestructure` with period
  definitions mapping to hours of the day via `energyweekdayschedule` and
  `energyweekendschedule` (24x12 matrices: 24 hours x 12 months).
- **Seasonal variations:** Yes -- the 24x12 schedule matrix explicitly encodes
  month-by-month variation.
- **Day-of-week:** Yes -- separate weekday and weekend schedules.
- **Update frequency:** Community-maintained with DOE oversight; rates are
  updated as utilities file new tariffs. Typically within weeks of PUC approval.
- **License:** Public domain (US Government work), CC-BY for community
  contributions.
- **Key endpoints:**
  - `GET /utility_rates?version=8&format=json&api_key=KEY&getpage=GUID` --
    full rate detail by GUID
  - `GET /utility_rates?version=8&format=json&api_key=KEY&eia=NNNN` --
    rates by EIA utility ID
  - `GET /utility_rates?version=8&format=json&api_key=KEY&sector=Residential&is_default=true` --
    default residential rates
- **Data structure highlights:**
  ```
  energyratestructure: [[{rate: 0.08, unit: "kWh"}], [{rate: 0.15}], ...]
  energyweekdayschedule: [[0,0,0,...,1,1,2,2,1,1,...,0,0], ...]  // 12 months x 24 hours
  energyweekendschedule: [[0,0,0,...,0,0,0,0,0,0,...,0,0], ...]
  ```
  Each integer in the schedule matrices is an index into `energyratestructure`.
- **Notes:** This is the gold standard for US rates. The NREL System Advisor
  Model (SAM) and many commercial tools use URDB as their backend. The data
  model is complex but comprehensive.

### 1.2 EIA (Energy Information Administration)

- **URL:** `https://api.eia.gov/v2/electricity/`
- **Documentation:** https://www.eia.gov/opendata/documentation.php
- **Data format:** JSON
- **Coverage:** All US utilities, but focuses on average rates rather than TOU
  schedules.
- **Auth:** Free API key required (register at https://www.eia.gov/opendata/register.php)
- **Rate limits:** 100 requests/hour
- **TOU time blocks:** NO -- EIA reports average residential/commercial/industrial
  rates per utility per state. Does not break down into peak/off-peak periods.
- **Seasonal variations:** Provides monthly average rates.
- **Update frequency:** Monthly (Form EIA-861 annually; Form EIA-826 monthly).
- **License:** Public domain (US Government).
- **Key endpoints:**
  - `GET /v2/electricity/retail-sales/data/?api_key=KEY&frequency=monthly&data[]=price` --
    average retail price by state/sector
  - `GET /v2/electricity/state-electricity-profiles/` -- state-level profiles
- **Value for this project:** Useful as a validation/fallback source for
  average rates, and for mapping utility IDs. Not suitable as a primary TOU
  source because it lacks time-block granularity.

### 1.3 Genability / Arcadia (Commercial)

- **URL:** https://arcadia.com/platform (formerly Genability Signal API)
- **Data format:** JSON REST API
- **Coverage:** ~3,000+ US and Canadian utilities, 14,000+ rate plans.
- **Auth:** Commercial API key; paid subscription required.
- **Rate limits:** Varies by plan.
- **TOU time blocks:** Yes -- full TOU support with calculated cost per interval.
  Their "Signal" API can calculate the exact cost of electricity at any hour for
  any location.
- **Seasonal variations:** Yes.
- **Update frequency:** Professionally maintained; rates typically updated within
  days of PUC approval.
- **License:** Commercial. Contact for pricing.
- **Key features:**
  - Address-based utility lookup (given a street address, returns the utility
    and applicable rate).
  - Rate calculation engine -- input usage profile, get cost.
  - Covers some Canadian utilities.
- **Notes:** Best-in-class for accuracy and coverage, but the cost may be
  prohibitive for a free/open-source project. Worth considering as a premium
  data source or for validation. Arcadia acquired Genability in 2021.

### 1.4 WattTime API

- **URL:** https://www.watttime.org/api-documentation/
- **Data format:** JSON
- **Coverage:** US grid regions (not utility-specific).
- **Auth:** Free tier available; registration required.
- **TOU time blocks:** No -- provides grid marginal emissions data, not rate
  data. However, the grid region mapping is useful.
- **Notes:** Not directly applicable for TOU rates, but useful for future
  carbon-aware scheduling features.

### 1.5 Octopus Energy API (UK/Europe)

- **URL:** `https://api.octopus.energy/`
- **Documentation:** https://developer.octopus.energy/docs/api/
- **Data format:** JSON REST
- **Coverage:** UK (Octopus Energy customers). Octopus also operates in Germany,
  Spain, Italy, France, and Japan, but API coverage varies.
- **Auth:** API key provided to Octopus customers (account-specific).
- **Rate limits:** Reasonable for personal use.
- **TOU time blocks:** Yes -- their "Agile" tariff provides half-hourly pricing.
  "Go" tariff has classic TOU (cheap overnight period). "Flux" has
  import/export TOU bands.
- **Seasonal variations:** Agile pricing varies by season naturally (market
  rates). Fixed tariffs have quarterly updates.
- **Update frequency:** Agile: every 30 minutes. Fixed: quarterly.
- **License:** Terms of service; for customer use.
- **Key endpoints:**
  - `GET /v1/products/` -- list all available tariff products
  - `GET /v1/products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates/`
    -- unit rates with time-of-day
  - `GET /v1/products/{product_code}/electricity-tariffs/{tariff_code}/standing-charges/`
- **Notes:** Octopus is the most developer-friendly European energy API. Their
  Agile tariff data is public (no auth needed for product listing). They are
  the best starting point for UK/EU TOU data.

### 1.6 Tibber API (Nordics/Europe)

- **URL:** https://developer.tibber.com/
- **Data format:** GraphQL
- **Coverage:** Norway, Sweden, Germany, Netherlands.
- **Auth:** OAuth2 / personal access token (customer only).
- **TOU time blocks:** Yes -- provides hourly spot pricing (Nord Pool).
- **Seasonal variations:** Market-driven variation.
- **Update frequency:** Hourly (day-ahead spot prices).
- **License:** Customer API; must be a Tibber subscriber.
- **Notes:** Excellent for Nordic countries. Spot pricing rather than
  traditional TOU tiers, but can be binned into peak/off-peak.

### 1.7 ENTSO-E Transparency Platform (Pan-European)

- **URL:** https://transparency.entsoe.eu/
- **API:** `https://web-api.tp.entsoe.eu/api`
- **Documentation:** https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html
- **Data format:** XML (primary)
- **Coverage:** All EU/EEA countries (37 countries, 42 TSOs).
- **Auth:** Free registration required for API token.
- **Rate limits:** 400 requests/minute.
- **TOU time blocks:** Provides wholesale day-ahead and intraday market prices
  (hourly resolution). Does not provide retail tariff structures directly.
- **Seasonal variations:** Market-driven.
- **Update frequency:** Day-ahead prices published daily at ~13:00 CET.
- **License:** CC-BY-4.0 for most datasets.
- **Key data types:**
  - A44: Day-ahead prices (hourly)
  - A62: Intraday prices
- **Notes:** Wholesale prices, not retail TOU tariffs. However, many European
  dynamic tariffs (like Tibber, Octopus Agile) are derived from these wholesale
  prices with a fixed markup. This is the most comprehensive pan-European
  price source.

### 1.8 Ontario Energy Board (OEB) -- Canada

- **URL:** https://www.oeb.ca/consumer-information-and-protection/electricity-rates
- **Data format:** Published on web pages and PDF rate orders. No formal API.
- **Coverage:** Ontario, Canada (all Ontario utilities regulated by OEB).
- **TOU time blocks:** Yes -- Ontario has province-wide TOU rates set by the
  OEB. Three tiers: Off-Peak, Mid-Peak, On-Peak.
- **Seasonal variations:** Yes -- summer (May 1 - Oct 31) and winter
  (Nov 1 - Apr 30) have different peak/mid-peak schedules. Off-peak hours are
  the same year-round.
- **Update frequency:** Rates adjusted May 1 and November 1 each year.
- **License:** Public government data.
- **Current Ontario TOU rates (as of Nov 1, 2025):**
  - Off-Peak: $0.076/kWh (weekdays 7pm-7am, all day weekends/holidays)
  - Mid-Peak: $0.122/kWh (weekdays vary by season)
  - On-Peak: $0.158/kWh (weekdays vary by season)
  - Summer: On-Peak 11am-5pm, Mid-Peak 7am-11am & 5pm-7pm
  - Winter: On-Peak 7am-11am & 5pm-7pm, Mid-Peak 11am-5pm
- **Notes:** Ontario is the simplest Canadian province for TOU because the OEB
  sets a uniform TOU schedule province-wide. This can be hardcoded/seeded
  with biannual updates.

### 1.9 BC Hydro -- Canada

- **URL:** https://www.bchydro.com/accounts-billing/rates-energy-use/electricity-rates.html
- **Data format:** Web pages, PDF rate schedules.
- **Coverage:** British Columbia (BC Hydro service area, ~95% of BC).
- **TOU time blocks:** BC Hydro does NOT currently use TOU pricing for
  residential customers. They use a two-tier conservation rate:
  - Step 1: ~$0.0996/kWh (first 1,350 kWh per 2-month billing period)
  - Step 2: ~$0.1496/kWh (above threshold)
- **Notes:** Not TOU-based, but worth including as a flat/tiered rate option.
  BC Hydro has piloted TOU but has not rolled it out province-wide.

### 1.10 Hydro-Quebec -- Canada

- **URL:** https://www.hydroquebec.com/residential/customer-space/rates/
- **Data format:** Web pages.
- **Coverage:** Quebec (virtually all residential customers).
- **TOU time blocks:** Hydro-Quebec introduced an optional "Flex D" dynamic
  pricing tariff (winter peak events) in 2019. The standard residential rate
  (Rate D) is flat-rate/tiered, not TOU.
  - Rate D: ~$0.0740/kWh (first 40 kWh/day), ~$0.1143/kWh above.
  - Flex D: Base rate with winter peak event surcharges.
- **Notes:** Quebec's rates are among the lowest in North America. True TOU is
  limited to the Flex D pilot.

---

## 2. Public Data Sources and Downloadable Datasets

### 2.1 OpenEI URDB Bulk Download

- **URL:** https://openei.org/doe-opendata/dataset/utility-rate-database
- **Format:** JSON (bulk download of entire database)
- **Size:** ~500 MB uncompressed
- **Coverage:** Same as OpenEI API (~50,000 rate schedules)
- **Update frequency:** Periodic bulk exports
- **License:** Public domain / CC-BY
- **Notes:** Best option for seeding the initial database. Download once, parse
  into Supabase, then use the API for incremental updates.

### 2.2 EIA Form 861 -- Utility Service Territories

- **URL:** https://www.eia.gov/electricity/data/eia861/
- **Format:** CSV / Excel
- **Coverage:** All US utilities -- includes utility names, EIA IDs, service
  territory details, number of customers, revenue, and ZIP code mappings.
- **Key file:** `Sales_Ult_Cust_{year}.xlsx` and `Service_Territory_{year}.xlsx`
- **Update frequency:** Annual
- **License:** Public domain
- **Notes:** Essential for the ZIP-to-utility lookup. The service territory file
  maps ZIP codes to utility IDs, which can then be joined with OpenEI URDB data.

### 2.3 EIA Form 861 -- ZIP Code to Utility Mapping

- **URL:** https://www.eia.gov/electricity/data/eia861/zip_code.php
- **Format:** Excel
- **Coverage:** Maps US ZIP codes to their serving utilities (investor-owned,
  municipal, co-op).
- **Notes:** A single ZIP code can be served by multiple utilities. The dataset
  includes the utility ID, utility name, state, and service type (bundled,
  delivery, energy).

### 2.4 NREL Utility Rate Database (mirrors OpenEI)

- **URL:** https://data.nrel.gov/
- **Format:** JSON
- **Notes:** NREL hosts a mirror of the OpenEI URDB. Same data, alternate
  access point.

### 2.5 State Public Utility Commission (PUC) Filings

Major states with active TOU programs:

| State | PUC | TOU Status |
|-------|-----|------------|
| California | CPUC (cpuc.ca.gov) | Mandatory residential TOU since 2020 for PG&E, SCE, SDG&E |
| New York | NYPSC (dps.ny.gov) | ConEd voluntary TOU; mandatory for EV owners |
| Texas | PUCT (puc.texas.gov) | Deregulated; REPs offer TOU plans |
| Massachusetts | DPU (mass.gov/dpu) | National Grid, Eversource offer TOU pilots |
| Arizona | ACC (azcc.gov) | APS, SRP have extensive TOU programs |
| Illinois | ICC (icc.illinois.gov) | ComEd offers hourly pricing and TOU |
| Connecticut | PURA (ct.gov/pura) | Eversource TOU pilots |
| Maryland | PSC (psc.state.md.us) | BGE offers TOU |
| Michigan | MPSC (michigan.gov/mpsc) | DTE, Consumers Energy TOU programs |
| Hawaii | PUC (puc.hawaii.gov) | HECO TOU programs |

- **Format:** Varies -- PDF tariff filings, web pages, sometimes CSV/Excel
  attachments.
- **Notes:** PUC data is the authoritative source but is difficult to parse
  programmatically. OpenEI URDB often lags PUC filings by weeks to months.

### 2.6 European Regulatory Authorities

| Country | Authority | TOU Status |
|---------|-----------|------------|
| UK | Ofgem | Dynamic/TOU tariffs via Energy Price Cap framework |
| Germany | BNetzA | Spot-linked tariffs growing (Tibber, Octopus) |
| France | CRE | EDF Tempo/Heures Creuses (traditional TOU) |
| Spain | CNMC | Mandatory TOU since June 2021 (3 periods: Punta/Llano/Valle) |
| Italy | ARERA | Mandatory multi-hourly pricing (F1/F2/F3 bands) |
| Netherlands | ACM | Spot-linked dynamic tariffs common |
| Norway | NVE | Nord Pool spot pricing via retailers |
| Sweden | Ei | Nord Pool spot pricing via retailers |

### 2.7 France -- EDF Tempo / Heures Creuses

- **URL:** https://www.edf.fr/en/edf-group (rate pages in French)
- **Coverage:** France (EDF serves ~70% of French consumers)
- **TOU structure:**
  - **Heures Creuses / Heures Pleines** (Off-Peak / Peak): 8 off-peak hours
    per day (typically 10pm-6am or split schedule set by local distributor).
  - **Tempo**: 3 colors per day (Blue/White/Red) x 2 periods (HP/HC) = 6 rates.
    22 Red days, 43 White days, 300 Blue days per year.
- **Notes:** Heures Creuses is the most common French TOU. The off-peak
  window varies by commune (set by Enedis, the distribution network operator).

### 2.8 Spain -- PVPC Regulated Tariff

- **URL:** https://www.esios.ree.es/en (Red Electrica data portal)
- **API:** `https://api.esios.ree.es/`
- **Format:** JSON
- **Auth:** Personal token (free registration)
- **Coverage:** Spain
- **TOU structure:** Since June 2021, regulated PVPC tariff has 3 periods:
  - Valle (Off-Peak): Midnight-8am, weekends/holidays
  - Llano (Mid-Peak): 8am-10am, 2pm-6pm, 10pm-midnight (weekdays)
  - Punta (Peak): 10am-2pm, 6pm-10pm (weekdays)
- **Notes:** REE publishes hourly PVPC prices. Good API with historical data.

### 2.9 Italy -- ARERA Multi-Hourly Bands

- **Coverage:** Italy
- **TOU structure:**
  - F1 (Peak): Mon-Fri 8am-7pm (excluding holidays)
  - F2 (Mid-Peak): Mon-Fri 7am-8am, 7pm-11pm; Saturday 7am-11pm
  - F3 (Off-Peak): Mon-Sat 11pm-7am; all day Sunday and holidays
- **Notes:** ARERA publishes quarterly rate updates. Rates are available on
  arera.it but not via API.

---

## 3. Source Comparison Matrix

| Source | Coverage | TOU Detail | API | Free | Format | Update Freq | Best For |
|--------|----------|------------|-----|------|--------|-------------|----------|
| **OpenEI URDB** | US (50k+ schedules) | Full (hours, seasons, tiers) | Yes | Yes (key) | JSON | Community-maintained | Primary US source |
| **EIA** | US (all utilities) | Avg rates only | Yes | Yes (key) | JSON | Monthly | Utility metadata, avg rates |
| **EIA 861 ZIP** | US ZIP codes | N/A (mapping) | No (download) | Yes | CSV/XLS | Annual | ZIP-to-utility lookup |
| **Genability/Arcadia** | US + some CA | Full TOU + calc | Yes | No (paid) | JSON | Days after filing | Premium accuracy |
| **Octopus Energy** | UK (+ 5 EU countries) | Half-hourly (Agile) | Yes | Partial | JSON | 30min (Agile) | UK TOU data |
| **ENTSO-E** | EU (37 countries) | Wholesale hourly | Yes | Yes (token) | XML | Daily | EU wholesale prices |
| **Tibber** | NO, SE, DE, NL | Hourly spot | Yes (GQL) | Subscribers | GraphQL | Hourly | Nordic spot prices |
| **OEB** | Ontario, CA | Full TOU | No (web) | Yes | HTML/PDF | Biannual | Ontario TOU |
| **REE/ESIOS** | Spain | Hourly PVPC | Yes | Yes (token) | JSON | Hourly | Spain regulated tariff |
| **EDF** | France | HC/HP, Tempo | No (web) | Yes | HTML/PDF | Annual | France TOU |
| **ARERA** | Italy | F1/F2/F3 bands | No (web) | Yes | HTML/PDF | Quarterly | Italy TOU |

---

## 4. Proposed Supabase Table Schema

The schema below is designed for Supabase (PostgreSQL) and handles the full
complexity of TOU rates across multiple countries, utilities, rate plans,
time blocks, seasons, day-of-week variations, and historical versioning.

### 4.1 Entity Relationship Diagram (Text)

```
countries
  |
  +-- regions (states/provinces)
  |     |
  |     +-- utilities
  |           |
  |           +-- rate_plans
  |                 |
  |                 +-- rate_plan_versions  (effective date ranges)
  |                       |
  |                       +-- rate_seasons  (summer/winter/etc.)
  |                       |     |
  |                       |     +-- rate_time_blocks  (peak/mid/off per season)
  |                       |           |
  |                       |           +-- rate_day_schedules  (which days)
  |                       |
  |                       +-- rate_holidays  (holiday exceptions)
  |
  +-- zip_utility_map  (ZIP/postal code -> utility lookup)
```

### 4.2 SQL Definitions

```sql
-- ============================================================
-- COUNTRIES
-- ============================================================
CREATE TABLE tou_countries (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    code        VARCHAR(3) NOT NULL UNIQUE,          -- ISO 3166-1 alpha-2/3 (US, CA, GB, FR, etc.)
    name        TEXT NOT NULL,                        -- "United States", "Canada", etc.
    currency    VARCHAR(3) NOT NULL DEFAULT 'USD',   -- ISO 4217
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Seed: US, CA, GB, FR, DE, ES, IT, NL, NO, SE, ...


-- ============================================================
-- REGIONS (states, provinces, territories)
-- ============================================================
CREATE TABLE tou_regions (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    country_id  UUID NOT NULL REFERENCES tou_countries(id),
    code        VARCHAR(10) NOT NULL,                -- "CA", "ON", "ENG", etc.
    name        TEXT NOT NULL,                        -- "California", "Ontario", etc.
    timezone    TEXT NOT NULL DEFAULT 'America/New_York', -- IANA timezone
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(country_id, code)
);


-- ============================================================
-- UTILITIES
-- ============================================================
CREATE TABLE tou_utilities (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    region_id       UUID NOT NULL REFERENCES tou_regions(id),
    name            TEXT NOT NULL,                    -- "Pacific Gas & Electric"
    short_name      VARCHAR(32),                      -- "PG&E"
    eia_id          VARCHAR(16),                      -- EIA utility ID (US only)
    openei_id       VARCHAR(64),                      -- OpenEI utility label
    website         TEXT,
    customer_count  INTEGER,                          -- approximate residential customers
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_utilities_region ON tou_utilities(region_id);
CREATE INDEX idx_utilities_eia ON tou_utilities(eia_id) WHERE eia_id IS NOT NULL;


-- ============================================================
-- RATE PLANS
-- ============================================================
CREATE TABLE tou_rate_plans (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    utility_id      UUID NOT NULL REFERENCES tou_utilities(id),
    name            TEXT NOT NULL,                    -- "E-TOU-C", "TOU-D-4-9PM", etc.
    description     TEXT,
    sector          VARCHAR(16) DEFAULT 'residential', -- residential, commercial, industrial
    is_default      BOOLEAN DEFAULT false,           -- default plan for new residential customers
    is_tou          BOOLEAN DEFAULT true,            -- true = TOU, false = flat/tiered
    openei_guid     VARCHAR(64),                      -- OpenEI rate GUID for cross-reference
    source_url      TEXT,                             -- link to official tariff document
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_rate_plans_utility ON tou_rate_plans(utility_id);
CREATE INDEX idx_rate_plans_openei ON tou_rate_plans(openei_guid) WHERE openei_guid IS NOT NULL;


-- ============================================================
-- RATE PLAN VERSIONS (effective date ranges -- rates change over time)
-- ============================================================
CREATE TABLE tou_rate_plan_versions (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    rate_plan_id    UUID NOT NULL REFERENCES tou_rate_plans(id) ON DELETE CASCADE,
    effective_from  DATE NOT NULL,                    -- when this version takes effect
    effective_to    DATE,                             -- NULL = currently active
    approved_by     TEXT,                             -- "CPUC Decision 22-05-012"
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(rate_plan_id, effective_from)
);

CREATE INDEX idx_rpv_plan ON tou_rate_plan_versions(rate_plan_id);
CREATE INDEX idx_rpv_active ON tou_rate_plan_versions(effective_to)
    WHERE effective_to IS NULL;


-- ============================================================
-- RATE SEASONS (summer/winter/spring/fall or single "all-year")
-- ============================================================
CREATE TABLE tou_rate_seasons (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    version_id      UUID NOT NULL REFERENCES tou_rate_plan_versions(id) ON DELETE CASCADE,
    name            VARCHAR(32) NOT NULL,             -- "summer", "winter", "all_year"
    month_start     SMALLINT NOT NULL CHECK (month_start BETWEEN 1 AND 12),
    month_end       SMALLINT NOT NULL CHECK (month_end BETWEEN 1 AND 12),
    -- month_start=6, month_end=9 means June through September
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_seasons_version ON tou_rate_seasons(version_id);


-- ============================================================
-- RATE TIME BLOCKS (the actual rate tiers within a season)
-- ============================================================
CREATE TABLE tou_rate_time_blocks (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    season_id       UUID NOT NULL REFERENCES tou_rate_seasons(id) ON DELETE CASCADE,
    tier_name       VARCHAR(32) NOT NULL,             -- "peak", "mid_peak", "off_peak", "super_off_peak"
    rate_per_kwh    NUMERIC(10, 6) NOT NULL,          -- e.g., 0.158700
    start_hour      SMALLINT NOT NULL CHECK (start_hour BETWEEN 0 AND 23),
    end_hour        SMALLINT NOT NULL CHECK (end_hour BETWEEN 1 AND 24),
    -- start_hour=16, end_hour=21 means 4:00 PM to 9:00 PM
    -- Supports sub-hourly with separate start_minute/end_minute if needed later
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_blocks_season ON tou_rate_time_blocks(season_id);


-- ============================================================
-- RATE DAY SCHEDULES (which days of week a time block applies to)
-- ============================================================
CREATE TABLE tou_rate_day_schedules (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    time_block_id   UUID NOT NULL REFERENCES tou_rate_time_blocks(id) ON DELETE CASCADE,
    day_of_week     SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    -- 0=Monday, 1=Tuesday, ..., 6=Sunday (ISO 8601)
    UNIQUE(time_block_id, day_of_week)
);

CREATE INDEX idx_day_sched_block ON tou_rate_day_schedules(time_block_id);


-- ============================================================
-- RATE HOLIDAYS (holiday exceptions -- holidays typically use off-peak schedule)
-- ============================================================
CREATE TABLE tou_rate_holidays (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    version_id      UUID NOT NULL REFERENCES tou_rate_plan_versions(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,                     -- "New Year's Day", "Christmas", etc.
    month           SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    day             SMALLINT CHECK (day BETWEEN 1 AND 31),
    -- day NULL = floating holiday (needs rule like "3rd Monday of January")
    float_rule      TEXT,                              -- "3rd_monday", "last_monday", etc.
    schedule_as     VARCHAR(16) DEFAULT 'off_peak',   -- treat this day as off_peak/weekend
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_holidays_version ON tou_rate_holidays(version_id);


-- ============================================================
-- ZIP / POSTAL CODE TO UTILITY MAPPING
-- ============================================================
CREATE TABLE tou_zip_utility_map (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    country_id      UUID NOT NULL REFERENCES tou_countries(id),
    postal_code     VARCHAR(16) NOT NULL,             -- "94105", "M5V 2T6", "SW1A 1AA"
    utility_id      UUID NOT NULL REFERENCES tou_utilities(id),
    is_primary      BOOLEAN DEFAULT true,             -- primary utility for this ZIP
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(postal_code, utility_id)
);

CREATE INDEX idx_zip_postal ON tou_zip_utility_map(postal_code);
CREATE INDEX idx_zip_country ON tou_zip_utility_map(country_id);


-- ============================================================
-- USER RATE SELECTIONS (links a WattWise user to a chosen rate plan)
-- ============================================================
CREATE TABLE tou_user_rate_selections (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         UUID NOT NULL,                    -- references auth.users
    rate_plan_id    UUID NOT NULL REFERENCES tou_rate_plans(id),
    version_id      UUID REFERENCES tou_rate_plan_versions(id), -- NULL = use latest active
    custom_override BOOLEAN DEFAULT false,            -- true if user modified rates
    selected_at     TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id)  -- one active selection per user
);

CREATE INDEX idx_user_rate_user ON tou_user_rate_selections(user_id);


-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
-- Reference tables (countries, regions, utilities, rate_plans, versions,
-- seasons, blocks, day_schedules, holidays, zip_map) should be readable
-- by all authenticated users but writable only by service_role.

ALTER TABLE tou_countries ENABLE ROW LEVEL SECURITY;
ALTER TABLE tou_regions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tou_utilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE tou_rate_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE tou_rate_plan_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tou_rate_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE tou_rate_time_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE tou_rate_day_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE tou_rate_holidays ENABLE ROW LEVEL SECURITY;
ALTER TABLE tou_zip_utility_map ENABLE ROW LEVEL SECURITY;
ALTER TABLE tou_user_rate_selections ENABLE ROW LEVEL SECURITY;

-- Read access for all authenticated users on reference tables
CREATE POLICY "read_tou_reference" ON tou_countries FOR SELECT
    TO authenticated USING (true);
CREATE POLICY "read_tou_reference" ON tou_regions FOR SELECT
    TO authenticated USING (true);
CREATE POLICY "read_tou_reference" ON tou_utilities FOR SELECT
    TO authenticated USING (true);
CREATE POLICY "read_tou_reference" ON tou_rate_plans FOR SELECT
    TO authenticated USING (true);
CREATE POLICY "read_tou_reference" ON tou_rate_plan_versions FOR SELECT
    TO authenticated USING (true);
CREATE POLICY "read_tou_reference" ON tou_rate_seasons FOR SELECT
    TO authenticated USING (true);
CREATE POLICY "read_tou_reference" ON tou_rate_time_blocks FOR SELECT
    TO authenticated USING (true);
CREATE POLICY "read_tou_reference" ON tou_rate_day_schedules FOR SELECT
    TO authenticated USING (true);
CREATE POLICY "read_tou_reference" ON tou_rate_holidays FOR SELECT
    TO authenticated USING (true);
CREATE POLICY "read_tou_reference" ON tou_zip_utility_map FOR SELECT
    TO authenticated USING (true);

-- User rate selection: users can only read/write their own row
CREATE POLICY "user_own_rate_selection" ON tou_user_rate_selections
    FOR ALL TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
```

### 4.3 Key Query: Get Current Rate for a User at a Given Hour

```sql
-- Given: user_id, target_date, target_hour, target_dow (0-6)
WITH user_plan AS (
    SELECT
        urs.rate_plan_id,
        COALESCE(urs.version_id, (
            SELECT id FROM tou_rate_plan_versions
            WHERE rate_plan_id = urs.rate_plan_id
              AND effective_from <= CURRENT_DATE
              AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
            ORDER BY effective_from DESC LIMIT 1
        )) AS version_id
    FROM tou_user_rate_selections urs
    WHERE urs.user_id = :user_id
),
active_season AS (
    SELECT s.id AS season_id
    FROM tou_rate_seasons s
    JOIN user_plan up ON s.version_id = up.version_id
    WHERE (
        -- Handle wrap-around seasons (e.g., Nov-Apr: month_start=11, month_end=4)
        CASE WHEN s.month_start <= s.month_end
             THEN EXTRACT(MONTH FROM :target_date) BETWEEN s.month_start AND s.month_end
             ELSE EXTRACT(MONTH FROM :target_date) >= s.month_start
                  OR EXTRACT(MONTH FROM :target_date) <= s.month_end
        END
    )
    LIMIT 1
)
SELECT
    tb.tier_name,
    tb.rate_per_kwh,
    tb.start_hour,
    tb.end_hour
FROM tou_rate_time_blocks tb
JOIN active_season a ON tb.season_id = a.season_id
JOIN tou_rate_day_schedules ds ON ds.time_block_id = tb.id
WHERE ds.day_of_week = :target_dow
  AND :target_hour >= tb.start_hour
  AND :target_hour < tb.end_hour;
```

### 4.4 Schema Design Rationale

1. **Versioning via `rate_plan_versions`**: Rates change regularly (PUC
   decisions, annual adjustments). Storing versions with effective date ranges
   means we keep historical data for accurate cost calculations on past usage,
   and can pre-load upcoming rates before they take effect.

2. **Seasons as a separate table**: Most TOU plans have summer/winter
   distinctions. Some have 4 seasons. Some are year-round. The season table
   handles all cases by storing month ranges.

3. **Day schedules as a join table**: Rather than comma-separated day strings
   (as in the current `TOURateEntry` model), a proper join table allows
   clean queries and indexing.

4. **Holiday exceptions**: Holidays typically revert to off-peak/weekend
   scheduling. The `float_rule` field handles US floating holidays (MLK Day,
   Thanksgiving, etc.) that do not fall on fixed dates.

5. **ZIP-to-utility mapping**: Multiple utilities can serve one ZIP code
   (e.g., investor-owned for delivery + municipal for generation in
   deregulated states). The `is_primary` flag handles this.

6. **Separate from user-specific overrides**: The `tou_user_rate_selections`
   table links users to a plan. The `custom_override` flag indicates if the
   user has manually tweaked rates, in which case the local `tou_rate_entries`
   table (existing SQLite model) takes precedence.

---

## 5. Top 20 US Utilities and Their TOU Rate Structures

Ranked by approximate residential customer count. TOU details reflect
currently published rate schedules as of early 2026.

### 1. Pacific Gas & Electric (PG&E) -- California
- **Customers:** ~5.5 million residential
- **EIA ID:** 14328
- **Default TOU plan:** E-TOU-C
- **Peak:** 4:00 PM - 9:00 PM (all days)
- **Off-Peak:** All other hours
- **Summer (Jun-Sep):** Peak ~$0.49/kWh, Off-Peak ~$0.38/kWh
- **Winter (Oct-May):** Peak ~$0.38/kWh, Off-Peak ~$0.36/kWh
- **Notes:** California mandated default TOU enrollment for residential since 2020.
  E-TOU-D available for those with EVs or storage (peak 5-8 PM).

### 2. Southern California Edison (SCE) -- California
- **Customers:** ~5.1 million residential
- **EIA ID:** 17609
- **Default TOU plan:** TOU-D-4-9PM
- **Peak:** 4:00 PM - 9:00 PM (all days)
- **Off-Peak:** All other hours
- **Super Off-Peak (winter only):** 8:00 AM - 4:00 PM
- **Summer (Jun-Sep):** Peak ~$0.52/kWh, Off-Peak ~$0.35/kWh
- **Winter (Oct-May):** Peak ~$0.45/kWh, Off-Peak ~$0.34/kWh, Super Off ~$0.28/kWh

### 3. Florida Power & Light (FPL) -- Florida
- **Customers:** ~5.0 million residential
- **EIA ID:** 6455
- **TOU available:** Optional TOU plan, not default
- **Peak:** Weekdays 12:00 PM - 9:00 PM (April-October)
- **Off-Peak:** All other hours
- **Notes:** Most FPL customers are on flat rate. TOU adoption is low.

### 4. Consumers Energy -- Michigan
- **Customers:** ~1.8 million residential
- **EIA ID:** 4254
- **TOU plan:** Rate D1.2 (optional TOU)
- **Peak:** Weekdays 2:00 PM - 7:00 PM (summer), 6:00 AM - 9:00 AM (winter)
- **Off-Peak:** All other hours
- **Summer peak:** ~$0.22/kWh, Off-Peak ~$0.09/kWh

### 5. Commonwealth Edison (ComEd) -- Illinois
- **Customers:** ~4.0 million residential
- **EIA ID:** 4110
- **Plan:** Hourly pricing (default) via RRTP program; no traditional TOU blocks
- **Notes:** ComEd offers real-time hourly pricing. Prices vary every hour
  based on PJM wholesale market. Average ~$0.09-0.12/kWh. For TOU modeling,
  can use statistical peak/off-peak averages from historical data.

### 6. Duke Energy Carolinas -- NC/SC
- **Customers:** ~2.7 million residential
- **EIA ID:** 5416
- **TOU plan:** SC-TOU (optional)
- **Peak:** Weekdays 6:00 AM - 1:00 PM, 4:00 PM - 9:00 PM (summer);
  6:00 AM - 1:00 PM (winter)
- **Off-Peak:** All other hours

### 7. Georgia Power -- Georgia
- **Customers:** ~2.7 million residential
- **EIA ID:** 7140
- **TOU plans:** Nights & Weekends, Smart Usage
- **Peak:** Weekdays 2:00 PM - 7:00 PM (summer)
- **Off-Peak:** 11:00 PM - 7:00 AM (super off-peak)
- **Notes:** Georgia Power has several TOU options. "Nights & Weekends"
  is the most popular with ~$0.01/kWh off-peak and ~$0.20/kWh peak.

### 8. DTE Energy -- Michigan
- **Customers:** ~2.3 million residential
- **EIA ID:** 5109
- **TOU plan:** D1.1 Time-of-Use
- **Peak:** Weekdays 3:00 PM - 7:00 PM (summer); 3:00 PM - 7:00 PM (winter)
- **Off-Peak:** 11:00 PM - 7:00 AM
- **Mid-Peak:** All other hours

### 9. San Diego Gas & Electric (SDG&E) -- California
- **Customers:** ~1.5 million residential
- **EIA ID:** 16609
- **Default TOU plan:** TOU-DR1
- **Peak:** 4:00 PM - 9:00 PM
- **Off-Peak:** 12:00 AM - 6:00 AM
- **Super Off-Peak:** 6:00 AM - 4:00 PM, 9:00 PM - 12:00 AM
- **Notes:** SDG&E has among the highest electricity rates in the US.
  Summer peak can exceed $0.60/kWh.

### 10. Dominion Energy Virginia
- **Customers:** ~2.7 million residential
- **EIA ID:** 5635
- **TOU plan:** Schedule 1G (optional)
- **Peak:** Weekdays 1:00 PM - 7:00 PM (summer); 5:00 AM - 9:00 AM (winter)
- **Off-Peak:** All other hours

### 11. Arizona Public Service (APS) -- Arizona
- **Customers:** ~1.3 million residential
- **EIA ID:** 803
- **TOU plans:** Saver Choice, Saver Choice Plus, Saver Choice Max
- **Peak:** 4:00 PM - 7:00 PM (weekdays)
- **Off-Peak:** 10:00 PM - 5:00 AM
- **Super Peak (summer):** 4:00 PM - 7:00 PM, Jun-Aug
- **Notes:** APS has mandatory TOU for new customers. Summer on-peak
  rates range from $0.14-0.24/kWh depending on plan.

### 12. Salt River Project (SRP) -- Arizona
- **Customers:** ~1.1 million residential
- **EIA ID:** 16572
- **TOU plan:** E-26 TOU
- **Peak:** Weekdays 2:00 PM - 8:00 PM (summer); 5:00 AM - 9:00 AM,
  5:00 PM - 9:00 PM (winter)
- **Off-Peak:** All other hours

### 13. Xcel Energy (PSCO) -- Colorado/Minnesota
- **Customers:** ~3.7 million residential (across states)
- **EIA ID:** 15466
- **TOU plan:** Optional TOU-A
- **Peak:** Weekdays 1:00 PM - 7:00 PM (summer); 6:00 PM - 10:00 PM (winter)
- **Off-Peak:** All other hours

### 14. Eversource Energy -- CT/MA/NH
- **Customers:** ~3.7 million residential (across states)
- **EIA ID:** 14725 (CT), 13434 (MA)
- **TOU plan:** TOU pilots in Massachusetts
- **Notes:** Eversource has limited TOU availability. Most customers are on
  flat rate with generation supply charges.

### 15. National Grid -- MA/NY/RI
- **Customers:** ~3.5 million residential
- **EIA ID:** 13511 (NY), 14154 (MA)
- **TOU plan:** SC-1 TOU (New York)
- **Peak:** Weekdays 8:00 AM - 12:00 AM (on-peak); 12:00 AM - 8:00 AM (off-peak)
- **Notes:** National Grid TOU is optional in most territories.

### 16. PPL Electric Utilities -- Pennsylvania
- **Customers:** ~1.4 million residential
- **EIA ID:** 14715
- **TOU plan:** TOU-A (optional)
- **Peak:** Weekdays 7:00 AM - 12:00 PM, 1:00 PM - 6:00 PM
- **Off-Peak:** All other hours

### 17. Entergy (multiple operating companies) -- LA/TX/MS/AR
- **Customers:** ~3.0 million residential (combined)
- **EIA ID:** Various
- **TOU plans:** Limited TOU availability; most customers on flat rates
- **Notes:** Entergy operates in states with limited TOU adoption.

### 18. PSEG -- New Jersey
- **Customers:** ~2.3 million residential
- **EIA ID:** 15477
- **TOU plan:** RLTOU (optional)
- **Peak:** Weekdays 8:00 AM - 8:00 PM (summer); 8:00 AM - 8:00 PM (winter)
- **Off-Peak:** All other hours
- **Notes:** PSEG is implementing AMI smart meters; TOU availability expanding.

### 19. Ameren -- Illinois/Missouri
- **Customers:** ~2.4 million residential
- **EIA ID:** 910 (IL), 911 (MO)
- **TOU plan:** Real-Time Pricing (Illinois); optional TOU (Missouri)
- **Notes:** Ameren Illinois offers Power Smart Pricing (hourly). Missouri
  has limited TOU.

### 20. Hawaiian Electric (HECO) -- Hawaii
- **Customers:** ~0.5 million residential
- **EIA ID:** 7426
- **TOU plan:** TOU-RI (mandatory for new PV customers)
- **Peak:** Weekdays 5:00 PM - 10:00 PM
- **Mid-Peak:** Weekdays 9:00 AM - 5:00 PM
- **Off-Peak:** 10:00 PM - 9:00 AM, all day weekends
- **Notes:** Hawaii has the highest electricity rates in the US (~$0.35-0.45/kWh).
  Strong TOU incentives for solar/battery owners.

---

## 6. Implementation Recommendations

### 6.1 Data Ingestion Strategy

**Phase 1 -- MVP (Week 1-2):**
1. Seed the Supabase tables with the 20 utilities listed above using manually
   curated data (confirmed from utility websites).
2. Add Ontario (OEB) and BC Hydro for Canadian coverage.
3. Add the 3 California IOUs (PG&E, SCE, SDG&E) with full seasonal detail
   first, as they have the most complex and well-documented TOU structures.
4. Build a simple "select your utility" dropdown in the WattWise settings page.

**Phase 2 -- OpenEI Integration (Week 3-4):**
1. Register for an OpenEI API key.
2. Build a backend ingestion script that:
   - Fetches all residential TOU rates from OpenEI URDB.
   - Parses the `energyratestructure`, `energyweekdayschedule`, and
     `energyweekendschedule` matrices into the normalized schema above.
   - Upserts into Supabase.
3. Import the EIA 861 ZIP-to-utility mapping into `tou_zip_utility_map`.
4. Run nightly or weekly incremental sync via a cron job or Supabase Edge
   Function.

**Phase 3 -- European Coverage (Week 5-6):**
1. Add Octopus Energy UK tariffs (Go, Agile, Flux, Cosy) as static seeds.
2. Add Spain PVPC structure (3-period, standardized nationwide).
3. Add France EDF Heures Creuses and Italy ARERA F1/F2/F3 as static seeds.
4. For dynamic pricing (Agile, Tibber, ENTSO-E), consider a separate
   `dynamic_rate_feeds` table that stores hourly prices fetched daily, rather
   than trying to fit market prices into the TOU block structure.

**Phase 4 -- Automated Updates (Week 7+):**
1. Build an OpenEI URDB change detection pipeline (compare last-modified
   dates or re-fetch recently updated rates).
2. Add admin tooling to review and approve rate changes before they go live.
3. Consider adding Arcadia/Genability as a premium validation source.

### 6.2 User Experience Flow

```
User enters ZIP/postal code
        |
        v
Backend looks up tou_zip_utility_map
        |
        v
Returns matching utilities (may be >1)
        |
        v
User selects their utility
        |
        v
Backend returns available rate plans for that utility
        |
        v
User selects their plan (default pre-selected)
        |
        v
Rates auto-populate in the TOU heatmap
        |
        v
User can optionally override specific rates
```

### 6.3 Integration with Existing WattWise Architecture

The current `TOURateEntry` model in `models.py` should be preserved as the
"effective" rate table -- the rates actually used for cost calculation. The
integration approach:

1. When a user selects a rate plan from the Supabase TOU database, the backend
   copies the relevant time blocks into the local `tou_rate_entries` SQLite
   table (existing model).
2. The optimizer and energy cost calculator continue to read from the local
   table -- no changes needed to existing calculation logic.
3. The Supabase TOU tables serve as the reference database; the local SQLite
   table is the working copy.
4. If the user customizes rates, set `custom_override = true` in
   `tou_user_rate_selections` to prevent auto-updates from overwriting
   their changes.

### 6.4 API Endpoints to Add

```
GET  /api/tou/lookup?postal_code=94105
     -> Returns utilities serving that ZIP

GET  /api/tou/utilities/{utility_id}/plans
     -> Returns available rate plans

GET  /api/tou/plans/{plan_id}/rates
     -> Returns full rate structure (seasons, blocks, days)

POST /api/tou/select
     body: { plan_id: "..." }
     -> Selects plan and copies rates to local tou_rate_entries

GET  /api/tou/plans/{plan_id}/preview
     -> Returns a 7x24 heatmap-ready structure for UI rendering
```

### 6.5 Cost Estimates

| Resource | Cost | Notes |
|----------|------|-------|
| OpenEI API | Free | 1,000 req/hour; API key required |
| EIA API | Free | 100 req/hour; API key required |
| Supabase storage | ~$0/month | Rate data is small (~10-50 MB) |
| Supabase Edge Functions | ~$0/month | Ingestion scripts; within free tier |
| Arcadia/Genability | $500-5,000/mo | Only if premium accuracy needed |

### 6.6 Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenEI data stale for some utilities | Rates may be months outdated | Cross-reference with utility websites; allow user override |
| OpenEI rate structure is complex to parse | Engineering time for ingestion | Start with the 20 largest utilities manually; automate later |
| Multiple utilities per ZIP code | User confusion | Show all options with customer count ranking |
| Rate changes mid-billing-cycle | Incorrect cost calculations | Version-based effective dates handle this cleanly |
| European TOU is fragmented | Incomplete coverage | Start with UK/Spain/France/Italy; expand based on user demand |
| Hourly/dynamic pricing does not fit TOU blocks | Schema mismatch | Separate `dynamic_rate_feeds` table for market-linked tariffs |

### 6.7 OpenEI URDB Parsing Reference

The OpenEI rate structure is the most complex part of the ingestion. Here is
how the key fields map to the proposed schema:

```
OpenEI Field                        -> Supabase Table
-----------                            --------------
utility                             -> tou_utilities.name
label (GUID)                        -> tou_rate_plans.openei_guid
name                                -> tou_rate_plans.name
sector                              -> tou_rate_plans.sector
is_default                          -> tou_rate_plans.is_default
startdate / enddate                 -> tou_rate_plan_versions.effective_from/to
energyratestructure[period][tier]    -> tou_rate_time_blocks.rate_per_kwh
energyweekdayschedule[month][hour]  -> tou_rate_seasons + tou_rate_time_blocks + tou_rate_day_schedules (Mon-Fri)
energyweekendschedule[month][hour]  -> tou_rate_seasons + tou_rate_time_blocks + tou_rate_day_schedules (Sat-Sun)
```

The `energyweekdayschedule` is a 12x24 matrix where `[m][h]` gives the period
index for month `m`, hour `h` on weekdays. To convert this:

1. Group consecutive months with identical 24-hour profiles into seasons.
2. For each season, identify unique period indices and their hour ranges.
3. Map each period index to its rate from `energyratestructure`.
4. Create `tou_rate_time_blocks` with appropriate `start_hour`/`end_hour`.
5. Create `tou_rate_day_schedules` entries (0-4 for weekdays from weekday
   schedule, 5-6 for weekends from weekend schedule).

---

## Appendix A: Ontario TOU Rate Reference (Easy to Hardcode)

Ontario is the simplest TOU structure to implement because it is uniform
province-wide.

**Effective November 1, 2025:**

| Period | Summer (May-Oct) Weekdays | Winter (Nov-Apr) Weekdays | Rate ($/kWh CAD) |
|--------|---------------------------|---------------------------|------------------|
| Off-Peak | 7pm - 7am | 7pm - 7am | $0.076 |
| Mid-Peak | 7am - 11am, 5pm - 7pm | 11am - 5pm | $0.122 |
| On-Peak | 11am - 5pm | 7am - 11am, 5pm - 7pm | $0.158 |
| Weekends/Holidays | All day | All day | $0.076 (off-peak) |

Ontario statutory holidays for TOU: New Year's, Family Day (3rd Mon Feb),
Good Friday, Victoria Day (Mon before May 25), Canada Day (Jul 1), Civic
Holiday (1st Mon Aug), Labour Day (1st Mon Sep), Thanksgiving (2nd Mon Oct),
Christmas (Dec 25), Boxing Day (Dec 26).


## Appendix B: California TOU Quick Reference

California's 3 IOUs all use a similar 4-9 PM peak window:

| Utility | Plan | Peak Hours | Summer Peak | Summer Off-Peak | Winter Peak | Winter Off-Peak |
|---------|------|------------|-------------|-----------------|-------------|-----------------|
| PG&E | E-TOU-C | 4-9 PM daily | ~$0.49 | ~$0.38 | ~$0.38 | ~$0.36 |
| SCE | TOU-D-4-9 | 4-9 PM daily | ~$0.52 | ~$0.35 | ~$0.45 | ~$0.34 |
| SDG&E | TOU-DR1 | 4-9 PM daily | ~$0.62 | ~$0.37 | ~$0.45 | ~$0.36 |

*Note: California rates are among the most complex in the US due to baseline
allowances, climate zone adjustments, and CARE/FERA discounts. The rates above
are simplified averages for the default tier.*


## Appendix C: European TOU Quick Reference

| Country | Structure | Peak Hours (Weekdays) | Peak Rate | Off-Peak Rate | Notes |
|---------|-----------|----------------------|-----------|---------------|-------|
| Spain | 3-period | Punta: 10am-2pm, 6pm-10pm | ~EUR 0.18 | ~EUR 0.08 | PVPC regulated |
| Italy | 3-band | F1: 8am-7pm | ~EUR 0.22 | ~EUR 0.19 | F3 cheapest |
| France | 2-period | HP: varies by commune (typ. 6am-10pm) | ~EUR 0.27 | ~EUR 0.20 | HC/HP |
| UK | Dynamic | Varies by tariff | ~GBP 0.35 | ~GBP 0.10 | Octopus Go: 12:30-4:30am cheap |

---

*End of research report. This document should be reviewed and updated as
data sources are validated and rates are confirmed against official tariff
filings.*
