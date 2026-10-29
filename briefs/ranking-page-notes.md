# Ranking page: new streams (spec, not built)

Captured 2026-10-29 in workshop run `20261029-220956-9401d156` (hotel 202158, `/hotel/202158/ranking?compsetId=1`).
Two JSON calls; each is a stream. Briefs: `ota-ranking-summary.yaml`, `ota-ranking-daily.yaml`.

| Stream | Kind | Per run | Key |
| --- | --- | --- | --- |
| ota_ranking_summary | upsert | weekly + monthly, 12 periods each, 3 OTAs, subject + compset | hotel, compset, hotelinfo, ota, granularity, period |
| ota_ranking_daily | daily snapshot | bookingdotcom (91 stay dates) + expedia (~16) | hotel, compset, as_of_date, stay_date, ota, hotelinfo |

Decisions (2026-10-29): both streams; weekly and monthly; Expedia included in the daily snapshot; compset "App Primary" (`compset_ids=1`) only.

Build notes:
- `LighthouseApiStream`s, JSON only. Competitor names and the subject hotelinfo come from the hotel context call the tap already makes.
- Keep `available_hotels` beside every rank: Booking.com and Tripadvisor rank within the compset, Expedia within the whole market.
- Review scores: 0-10 for Booking.com and Expedia, 0-5 for Tripadvisor.
- The daily snapshot can't be backfilled; schedule daily.

Resolved 2026-10-29: "App Primary" is compset 1 for both hotels checked (`compsets[].id` = `<hotel>,1`). Still look it up by name in the hotel context and fall back to 1.

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
