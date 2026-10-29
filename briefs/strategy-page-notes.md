# Strategy page: rate strategy streams (spec, not built)

Captured 2026-10-29 in workshop run `20261029-220956-9401d156` (hotel 202158, `/hotel/202158/strategy`).
One JSON call, `GET /apigateway/v1/app/ratestrategy/`, split into four streams. Brief: `rate-strategy.yaml`.

| Stream | Source array | Rows per weekly snapshot |
| --- | --- | --- |
| rate_strategy_base_rates | rsbaserates | 60-72 |
| rate_strategy_discounts | rsstrategies | 120 |
| rate_strategy_patterns | rspatterns | 130-139 |
| rate_strategy_cancellation | rscancellationpolicies | 12 |

Decisions (2026-10-29): four streams; backfill 52 weeks on the first run, then weekly; compset "App Primary" (`compset_ids=1`) only.

Build notes:
- Shared key: hotel, compset, snapshot_week (a Monday), hotelinfo. Type and subtype labels are joined in from the same response.
- History is available through `weeks[]` back to -52, so a missed week can be recovered within a year (unlike the demand, smart insights and ranking snapshots).
- Not used by the tap today (no `ratestrategy` reference in `packages/`).

## Lower-tier account check (2026-10-29)

Logged in with a lower-tier Lighthouse account (hotel 361466, Ambros Daytona, 9 App Primary competitors) and replayed every spec'd endpoint with its ids. All return 200 with data:

| Endpoint | Result for 361466 |
| --- | --- |
| events | 48 events (12 months back, 12 ahead) |
| holidays | 47 holidays |
| demand | values for 61 of 91 days |
| smart insights | 91 stay dates; PMS fields (occupancy, room nights, ADR) all null, rate and demand fields filled |
| ranking summary weekly / monthly | 360 rows each, 10 hotels, 3 OTAs |
| ranking daily, Booking.com | 91 dates, 910 cells |
| ranking daily, Expedia | 16 dates, 160 cells (new message: `ranking.soldout`) |
| rate strategy, `weeks[]=-52` | current + 2025-10-27 snapshots, 200 strategies each |

Notes for the build:
- `subscription_id` = `hotel_id`, and App Primary = compset 1, for both hotels.
- Competitor count varies by hotel (5 vs 9): never assume a fixed number.
- Smart insights' PMS fields are optional: hotels without a PMS connection return them as null.
