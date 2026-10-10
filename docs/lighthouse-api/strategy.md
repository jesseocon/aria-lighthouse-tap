# Lighthouse strategy page: API catalog and `strategy-snapshot-v2` proposal

Status: **draft for review**. Captured 2026-10-09 against hotel 202158 (Hilton Garden Inn Boston-Burlington).

## Summary

- The day-by-day strategy table is rendered from **GraphQL**, served through Lighthouse's own gateway: `POST https://app.mylighthouse.com/apigateway/v1/proxy/spider/graphql`.
- Four operations carry everything the table shows: `GetLhDayByDayCommon` (6 calls per as-of date), `GetDayByDayStrategy`, `GetHotel`, and `GetDataQualityStatus`.
- Responses are raw numbers, not formatted text, covering a full year of stay dates per as-of date.
- Authentication is the Lighthouse session cookie plus two fixed headers. There is no iframe token.
- A replay for a different as-of date (2026-09-20) returned 200 in 1.5–7.5 s per call with no page load. Today's DOM stream takes about 30 s per as-of date.

Implemented as `strategy-snapshot-v2` (`tap_lighthouse/streams_v2.py`), a new stream that calls these operations directly. The existing `strategy-snapshot` stream and every other stream stay as they are.

## How this was captured

The workshop daemon (in `aria-singer-playwright`) now records page API traffic. To reproduce:

```bash
W() { uv run --project ../aria-singer-playwright python -m singer_playwright workshop "$@"; }
export PLAYWRIGHT_BROWSERS_PATH=$HOME/Library/Caches/ms-playwright
W start --storage-state <runner session storage_state.json> --detach
W network mark --label initial-load
W goto --url "https://app.mylighthouse.com/hotel/202158/day-by-day/strategy?startDate=2026-10-09&endDate=2027-10-08"
W act wait_for_frame --url-pattern 'spider\.kriyarevgen\.com/dashboards/day-by-day'
W network mark --label change-asof
W act frame_goto --url-pattern 'spider\.kriyarevgen\.com' --query-params '{"asof":"2026-10-01","pickupFrom":"2026-10-01"}'
W network catalog --host-pattern 'mylighthouse|kriya'
W network show --seq <n>
W network replay --seq <n> --json-patch '{"variables.asofDate":"2026-09-20"}'
W stop
```

- Raw capture: `workshop-runs/20261009-195741-0437d95f/network/`. It is gitignored and local only: `calls.jsonl`, `catalog.json`, and full bodies in `bodies/`.
- The GraphQL query documents are saved verbatim (the tap sends them byte for byte): [`tap_lighthouse/graphql/`](../../packages/tap-lighthouse/tap_lighthouse/graphql/).
- Cookies, Authorization headers, token parameters, and JWTs are masked in everything written to disk.

## Authentication and request conventions

Spider GraphQL requests are sent from the Spider iframe (`https://spider.kriyarevgen.com/dashboards/day-by-day/9203/...`) to the Lighthouse gateway:

| Header | Value | Notes |
|---|---|---|
| `cookie` | Lighthouse session cookie | From `storage_state.json`; the only credential |
| `content-type` | `application/json` | |
| `origin` | `https://spider.kriyarevgen.com` | Set by the browser |
| `referer` | `https://spider.kriyarevgen.com/` | Set by the browser |
| `x-oi-resource-id` | `SP9203` | `SP` + Spider hotel id |
| `x-oi-resource-type` | `subscription` | Fixed |

Body: `{"query": "<document>", "variables": {...}}`. The page does not send `operationName`; the name appears only in the query text.

**Hotel ids.** Spider calls the hotel `9203` (in the iframe URL path and in `GetHotel.id`). Lighthouse uses `202158` for the subscription and `28650` for the hotel itself. Spider's competitor `vendorId` values are Lighthouse hotelinfo ids, so strategy joins to rates and parity on them. See [rates-and-parity.md](rates-and-parity.md#hotel-ids-shared-by-all-lighthouse-apis).

## Endpoint catalog

One page load plus one as-of change produced 50 calls on Lighthouse hosts. Calls marked **Needed** are the ones v2 would make.

### Spider GraphQL (`POST /apigateway/v1/proxy/spider/graphql`)

| Operation | Needed | Calls per as-of | Size | What it is |
|---|---|---|---|---|
| `GetLhDayByDayCommon` | **Yes** | 6 (one per `queryKey`) | ~560–580 KB each | Per-stay-date summaries: rooms and revenue on the books, same time last year (STLY), forecasts, budget, groups, system rate. The body of the table. |
| `GetDayByDayStrategy` | **Yes** | 1 | ~170 KB | Rate shop: the subject hotel's rate and variance, each competitor's rate and variance, comp-set average, competitor names, and user notes per date |
| `GetHotel` | **Yes**, once per run | 1 per page load | 1.5 KB | Hotel context: Spider id, name, code, time zone, room count, rate-shop settings, earliest available as-of dates |
| `GetDataQualityStatus` | Optional, once per run | 1 per page load | 342 B | Whether today's reservation and summary loads are `good`. Useful as a freshness gate. |
| `GetHotelFeatures` | No | 1 per page load | 45 B | Feature flags for the hotel |
| `GetMe` | No | 1 per page load | 128 B | The logged-in user (`externalMe`). Contains personal data, so we don't use it. |

### Lighthouse REST (loaded by the page shell; not needed for strategy data)

| Endpoint | What it is |
|---|---|
| `GET /api/v3/users/?only_self=true` | Logged-in user profile |
| `GET /api/v3/otas/` | List of 51 OTAs and their capabilities |
| `GET /api/v3/hotels/?id=202158` | Lighthouse hotel settings, competitor ids, OTA lists |
| `GET /apigateway/v1/app/hotelinfos/{id}/featurescontexts/` | Enabled product features |
| `GET /apigateway/v1/app/hotelinfos/{id}/subscriptions/` | Subscription name and type |
| `GET /apigateway/v1/app/smartinsights/insights/` | Smart Insights per stay date (`extract_date`, `ota`, `rate_type`) |
| `GET /apigateway/v1/app/demand/ari/demands` | Market demand index per stay date (365 values) |
| `GET /apigateway/v1/app/events/accepted` | Local events accepted for the hotel |
| `GET /apigateway/v1/app/holidays` | Holidays per date |
| `GET /apigateway/v1/app/users/{id}/currencies` | Exchange rates |
| `GET /apigateway/v1/app/finance/exchange-rate-profiles` | Exchange-rate profiles (empty here) |
| `GET /apigateway/v1/app/payment/info`, `/api/v3/smartinsights/upsell/`, `/api/v3/user_engagements_elements/` | Billing and UI state |
| `route-manifest.json` | Front-end routing |

Demand, events, holidays, and Smart Insights are candidates for future streams. They aren't part of this proposal.

Third-party calls (not needed): LaunchDarkly feature flags and events, Segment, Sentry, Google Maps, SatisMeter, `pbrf.mylighthouse.com`.

## `GetLhDayByDayCommon`

Document: [`graphql/GetLhDayByDayCommon.graphql`](../../packages/tap-lighthouse/tap_lighthouse/graphql/GetLhDayByDayCommon.graphql)

Variables:

```json
{
  "hotelId": "9203",
  "filters": {
    "dateRange": {"start": "2026-10-09", "end": "2027-10-08"},
    "pickupFrom": "2026-10-02",
    "asof": "2026-10-09"
  },
  "dateRange": {"start": "2026-10-09", "end": "2027-10-08"},
  "currency": "USD",
  "currencyVariant": "today",
  "queryKey": "main"
}
```

- `filters.asof` is the as-of (snapshot) date.
- `filters.pickupFrom` is the comparison date for pickup. The page defaults it to as-of minus 7 days, or sets it equal to the as-of date when the `pickupFrom` URL parameter is passed.
- The response is `data.lhDayByDaySummaries`: one row per stay date (365 rows). `hotelId` in each row is always `"0"`.

### Variants (`queryKey`)

The page sends the same query 6 times with a different `queryKey`. Each variant fills only its own fields and returns 0 for the rest. Across all 365 stay dates, no field was non-zero in more than one variant, so merging the variants per stay date is unambiguous.

| `queryKey` | Fields it fills |
|---|---|
| `main` | `inventory`, `totalRooms`, `totalRevenue`, `transientRooms`, `transientRevenue`, `groupOtbRooms`, `groupOtbRevenue`, `groupBlockRooms` |
| `asof` | `asof.totalRooms`, `asof.totalRevenue`, `asof.groupBlockRooms`, `asof.groupOtbRooms` (the comparison snapshot at `pickupFrom`) |
| `stly` | `stlyDow*`, `netStlyDow*` (with and without group), `lastYearDow.totalRooms`, `lastYearDow.totalRevenue`, `lastYearDow.groupBlockRevenue` |
| `main_kriya` | `spiderForecastRooms`, `spiderForecastRevenue`, `spiderForecastUnconstrainedRooms`, `rmsForecastRooms`, `rmsForecastRevenue`, `optimalBar`, `systemRate`, `barBasedPace`, `r28RoomsAverage`, `hurdle` |
| `budget_forecast` | `budgetRooms`, `budgetRevenue` |
| `group_bar` | `barBasedRooms`, `groups` (list of `{name, rooms, revenue}`) |

Always 0 or null for this hotel: `financeForecast*`, `userForecast*`, `barBasedRevenue`, `groupBlockRevenue`, `outOfOrder`, most `lastYearDow.*` detail fields, and the remaining `asof.*` fields. These will still be landed, since other hotels may populate them.

Response times observed: 0.7–7.5 s per call. The page sends all 6 at once.

## `GetDayByDayStrategy`

Document: [`graphql/GetDayByDayStrategy.graphql`](../../packages/tap-lighthouse/tap_lighthouse/graphql/GetDayByDayStrategy.graphql)

Variables:

```json
{
  "hotelId": "9203",
  "asofDate": "2026-10-09",
  "varianceAsofDate": "2026-10-02",
  "dateRange": {"start": "2026-10-09", "end": "2027-10-08"},
  "timeZone": "America/New_York",
  "currency": "USD"
}
```

The response has four parts:

- `rates.metadata[0]`: rate-shop settings (`bar`, `channel`, `guests`, `los`) and `competitors: [{vendorId, name}]`.
- `rates.periods[]`: one entry per stay date. Each entry contains `rates[0]` with these fields:
  - `rate` and `rateVariance`: the **subject hotel**'s own rate, with `hotelId` = 9203.
  - `competitorRates: [{vendorId, rate, rateVariance}]`
  - `competitorRateAverage` and `competitorRateAverageVariance`
- `userSummaries[]`: `{date, notes}`, the user-entered notes per date.
- `rateRequests[]` and `roomIncrements[]`: empty for this hotel.

**Subject hotel.** The subject's rate is the top-level `rate`, not an entry in `competitorRates`, so there's no need to guess it from styling. This fixes the cause of null `_subject_entity_key` values in v1. The subject's name comes from `GetHotel.name` ("Hilton Garden Inn Boston-Burlington"). Competitor names come from `metadata.competitors`, joined on `vendorId`.

## `GetHotel`

Document: [`graphql/GetHotel.graphql`](../../packages/tap-lighthouse/tap_lighthouse/graphql/GetHotel.graphql). Variables: `{"hotelId": "9203", "currency": null, "dataReplatforming": null}`.

Fields used:

- `id` (9203), `name`, `code` (`GIBOSBU`), `timeZone` (needed by `GetDayByDayStrategy`), `rooms` (180).
- `firstMaterializedAsofDate` (2024-01-02) and `minSummaryAsofDate` (2024-12-02): the earliest as-of dates the API can serve. These bound backfills.
- `rateShopContext` (`channel`, `los`, `type`).

## Proposed `strategy-snapshot-v2` stream

### Scope

- A new stream, `strategy-snapshot-v2`, writing to its own bronze table. `strategy-snapshot` (DOM) is untouched and stays selectable.
- The same incremental rules as v1:
  - The replication key is `as_of_date`.
  - The first sync starts at `start_date`.
  - Every later sync starts at the bookmark minus `lookback_days`.
  - An explicit `start_date` plus `end_date` acts as a backfill.
- Primary key: `(as_of_date, stay_date)`.

### Run flow

1. Launch Chromium with `storage_state.json`, open the strategy page once, and wait for the Spider iframe. This is a normal page view, and it also serves as the session check: if the page bounces to login, stop with "re-auth needed".
2. Read the Spider hotel id from the iframe URL. Call `GetHotel` once for the time zone, name, and earliest as-of dates.
3. For each as-of date, send the 7 GraphQL requests (6 `GetLhDayByDayCommon` variants and 1 `GetDayByDayStrategy`) with `fetch()` **from inside the Spider iframe**, then merge them into one record per stay date.
4. Pause between as-of dates (see below).

### Record shape (one per as-of date and stay date)

| Group | Fields |
|---|---|
| Keys | `as_of_date`, `stay_date`, `hotel_id` (202158), `spider_hotel_id` (9203), `pickup_from`, `currency` |
| Summary | Every scalar from `GetLhDayByDayCommon`, snake_cased (`total_rooms`, `total_revenue`, `spider_forecast_rooms`, `stly_dow_rooms`, `budget_revenue`, `system_rate`, …) |
| Nested summary | `asof_*` and `last_year_dow_*`, flattened. `groups` as an array of `{name, rooms, revenue}`. |
| Rate shop | `subject_name`, `subject_rate`, `subject_rate_variance`, `comp_set_rate_average`, `comp_set_rate_average_variance`, `competitor_rates` (array of `{vendor_id, name, rate, rate_variance}`) |
| Other | `notes`, `_source_variants` (the queryKeys merged) |

The schema is fixed and explicit. Unlike v1, its columns don't depend on which table columns render. Fields that are derived in the UI (occupancy, ADR, RevPAR, pickup deltas) are **not** landed; dbt computes them from rooms, revenue, and inventory.

### Validation before switching anything downstream

- Run v2 for a few as-of dates that v1 already holds in bronze.
- Compare field by field: rooms, revenue, forecasts, STLY, and rates. v1 has formatted text; v2 has raw numbers.
- Document any column that v1 shows but v2 cannot reproduce.

## Traffic and detection

Goal: **look like a person using the page, and send less traffic than the current stream.**

### What the page already sends per as-of date

When a user changes the as-of date, the page reloads the Spider iframe and sends **17 API calls**:

- 7 GraphQL data calls
- `GetHotel`, `GetHotelFeatures`, `GetMe`, and `GetDataQualityStatus`
- Events, holidays, demand, and currencies
- LaunchDarkly

It also reloads the iframe's scripts and styles. The v1 stream does exactly this for every as-of date.

### What v2 sends per as-of date

**7 GraphQL calls**: the same data calls the page makes, with the same document, variables, headers, origin, and cookies. Because they are sent with `fetch()` from inside the Spider iframe, each request matches the browser's own request byte for byte: same `origin`, `referer`, `sec-fetch-*` headers, user agent, and cookie. Sending from a separate HTTP client would differ in exactly the headers a gateway checks first.

### Pacing defaults (configurable)

| Setting | Default | Why |
|---|---|---|
| Requests in flight | The 6 summary variants together, then the strategy call | Matches what the page itself does |
| Pause between as-of dates | Random 4–9 s | Roughly the pace of a person clicking through dates; never back-to-back |
| As-of dates per run | Unlimited for daily syncs; `max_as_of_dates_per_run` cap for backfills (suggested: 60) | Spreads large backfills over several runs and days |
| Retries | Up to 2, with exponential backoff (30 s, then 120 s) on 429 and 5xx | Never hammer a failing server |
| Stop conditions | 401 or 403, a redirect to login, GraphQL `errors`, missing expected fields, or 3 failed as-of dates in a row | Stop with a clear error; never keep retrying |

### Expected volume

- **Daily sync** (7-day lookback, so 8 as-of dates): about 56 GraphQL calls over about 2 minutes. v1 sends about 136 calls plus page assets over 4–5 minutes.
- **Full-year backfill** (365 as-of dates): about 2,555 calls. At about 15 s per as-of date, that's roughly 1.5 hours if run in one go; with a cap of 60 dates per run, it spreads over about 6 runs.

### Existing detection signal to fix (affects v1 too)

The headless browser announces itself. Every request carries `sec-ch-ua: "HeadlessChrome"` and a `HeadlessChrome/153` user agent. That is a stronger tell than anything about request patterns. Proposed fix in `singer-playwright`'s `BrowserConfig`:

- Launch with Chromium's new headless mode (`channel="chromium"`), which reports as regular Chrome.
- Or set a normal Chrome user agent and client-hint headers.
- Use a stable viewport and the America/New_York locale and time zone, so the fingerprint doesn't vary between runs.

## Risks and open questions

1. **Unversioned internal API.** Lighthouse can change these queries without notice. v2 should fail loudly on GraphQL `errors` or missing fields, and the captured documents should be re-checked with the workshop when that happens.
2. **Historical depth.** `minSummaryAsofDate` is 2024-12-02. Earlier as-of dates may return empty or partial data; this needs one replay to confirm.
3. **`pickupFrom` default.** The page uses as-of minus 7 days. Should v2 use the same, or make it configurable?
4. **`dateRange` per as-of.** Should the stay-date window start at the as-of date and run 365 days (as v1 does), or be fixed?
5. **Bronze table name and dbt.** v2 needs its own bronze table and new staging models. Should the existing marts read from v1, v2, or a union during the transition?
6. **Headless fingerprint fix.** Should it ship before v2, since it benefits all streams?
