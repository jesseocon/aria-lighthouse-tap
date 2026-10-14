# Lighthouse rate plans

Captured 2026-10-10 against hotel 202158 (Spider hotel 9203). Implemented as `rate-plans`.

The page is `https://app.mylighthouse.com/hotel/{hotel_id}/day-by-day/rate-plans`. It loads the same Spider iframe and the same six `GetLhDayByDayCommon` calls as [strategy](strategy.md). This stream does not request them.

## `GetLhDayByDayRatePlans`

Document: [`graphql/GetLhDayByDayRatePlans.graphql`](../../packages/tap-lighthouse/tap_lighthouse/graphql/GetLhDayByDayRatePlans.graphql)

`POST https://app.mylighthouse.com/apigateway/v1/proxy/spider/graphql`

Variables match [market segments](market-segments.md): hotel id, as-of, pickup-from, stay-date range, currency. There is no rate-plan argument.

Response: `data.lhDayByDayRatePlans`.

- `topRatePlans`: `{marketSegment, ratePlans[]}`, the full column list. This hotel had 184 plans across the nine market segments. Each plan belongs to one segment.
- `aggregates`: one entry per stay date that has activity, and inside it one row per segment and rate plan. Rooms and revenue are on-the-books, the pickup-from snapshot, and same time last year.

Opening the Rate Plan dropdown and leaving it open sent the same query again, with the same 184 plans. The dropdown filters the table on data the page already has.

This hotel returned 204 stay dates from 2026-10-10 through 2027-07-08, with gaps. Company, room type, and reservation id were empty.

## Stream

- Name: `rate-plans`
- Bronze: `mlt_lighthouse_ota__rate_plans_hotel_{hotel_id}`
- Primary key: `(as_of_date, stay_date, market_segment, rate_plan)`
- Replication key: `as_of_date`
- One GraphQL call per as-of date, after one page load for the session
- Pickup window and as-of cap reuse `strategy_v2_pickup_days` and `strategy_v2_max_as_of_dates`
