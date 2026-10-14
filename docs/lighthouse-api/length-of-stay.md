# Lighthouse length of stay

Captured 2026-10-10 against hotel 202158 (Spider hotel 9203). Implemented as `length-of-stay`.

The page is `https://app.mylighthouse.com/hotel/{hotel_id}/day-by-day/length-of-stay`. It loads the same six `GetLhDayByDayCommon` calls as [strategy](strategy.md). This stream does not request them.

## `GetLhDayByDayLengthOfStays`

Document: [`graphql/GetLhDayByDayLengthOfStays.graphql`](../../packages/tap-lighthouse/tap_lighthouse/graphql/GetLhDayByDayLengthOfStays.graphql)

`POST https://app.mylighthouse.com/apigateway/v1/proxy/spider/graphql`

Variables match [market segments](market-segments.md): hotel id, as-of, pickup-from, stay-date range, currency. There is no length-of-stay or rate-plan argument.

Response: `data.lhDayByDayLengthOfStays`, a list of `{stayDate, aggregates[]}`. Each aggregate is one bucket:

| `lengthOfStay` | Column on the page |
|---|---|
| `los1` | 1 night stay |
| `los2` | 2 night stay |
| `los3to6` | 3–6 night stay |
| `los7to14` | 7–14 night stay |
| `los15to29` | 15–29 night stay |
| `los30plus` | 30+ night stay |

Rooms and revenue are on-the-books, the pickup-from snapshot, and same time last year. `marketSegment` and `ratePlan` were empty. Opening the Rate Plan dropdown sent the same query again.

This hotel returned 204 stay dates from 2026-10-10 through 2027-07-08, with gaps, and 572 bucket rows. A date can omit a bucket. A present bucket can be zero rooms.

## Stream

- Name: `length-of-stay`
- Bronze: `mlt_lighthouse_ota__length_of_stay_hotel_{hotel_id}`
- Primary key: `(as_of_date, stay_date, length_of_stay)`
- Replication key: `as_of_date`
- One GraphQL call per as-of date, after one page load for the session
- Pickup window and as-of cap reuse `strategy_v2_pickup_days` and `strategy_v2_max_as_of_dates`
