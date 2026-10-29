# Events page: new streams (spec, not built)

Captured 2026-10-29 in workshop run `20261029-220956-9401d156` (hotel 202158, `/hotel/202158/events?month=2026-10`).
The page loads four JSON calls; each is a new stream. Briefs: `events.yaml`, `holidays.yaml`, `demand.yaml`, `smart-insights.yaml`.

| Stream | Kind | Window per run | Key |
| --- | --- | --- | --- |
| events | upsert | 12 months back, 12 ahead | hotel_id, event_id |
| holidays | upsert | 12 months back, 12 ahead | hotel_id, holiday_id |
| demand | daily snapshot | today .. +90 days (values only through ~+60) | hotel_id, as_of_date, stay_date |
| smart_insights | daily snapshot | 91 stay dates from today | hotel_id, as_of_date, stay_date |

Build notes:
- All four are `LighthouseApiStream`s: JSON fetched from the authenticated page, no DOM scraping.
- Bronze per hotel, matching the existing streams' naming.
- demand and smart_insights only exist as of the capture day. Schedule daily; a missed day can't be backfilled.

Open questions before building:
1. ~~Where `subscription_id` comes from~~ Resolved 2026-10-29: it equals `hotel_id` for both hotels checked (202158, 361466); `hotelinfos/{id}/subscriptions/` confirms it.
2. smart_insights: capture only `rate_type=lowest`, `ota=bookingdotcom` (page default), or several? Verify occupancy fields don't change with `ota`.
3. events: is the 30 km `max_distance` a per-hotel setting we should record?

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
