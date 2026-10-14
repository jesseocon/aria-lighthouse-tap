# Lighthouse market segments

Captured 2026-10-09 against hotel 202158 (Spider hotel 9203). Implemented as `market-segments`.

The page is `https://app.mylighthouse.com/hotel/{hotel_id}/day-by-day/market-segments`. It loads the same Spider iframe and the same six `GetLhDayByDayCommon` calls as [strategy](strategy.md). Those calls are the shared hotel-day shell. This stream does not request them.

## `GetLhDayByDayMarketSegments`

Document: [`graphql/GetLhDayByDayMarketSegments.graphql`](../../packages/tap-lighthouse/tap_lighthouse/graphql/GetLhDayByDayMarketSegments.graphql)

`POST https://app.mylighthouse.com/apigateway/v1/proxy/spider/graphql`

```json
{
  "hotelId": "9203",
  "filters": {
    "dateRange": {"start": "2026-10-09", "end": "2027-10-08"},
    "pickupFrom": "2026-10-02",
    "asof": "2026-10-09"
  },
  "currency": "USD",
  "currencyVariant": "today"
}
```

Response: `data.lhDayByDayMarketSegments`. `aggregates` is one entry per stay date that has segment activity. Each entry's `aggregates` is one row per market segment. `topMarketSegments` is the column list for the page (Retail, OTA Discount, Group, Corp Negotiated, Brand Discount, Government, Local Negotiated, Complimentary, Qualified Discount on this hotel).

Each segment row has rooms and revenue for on-the-books, the pickup-from snapshot (`asof*`), and same time last year (`stly*`), plus variance. `ratePlan`, `roomType`, `company`, `groupName`, and `reservationId` are on the type and were empty here. Stay date comes from the parent entry; the segment's own `stayDate` was null.

This hotel returned 205 stay dates from 2026-10-09 through 2027-07-08, with gaps. The strategy summary for the same window returned 365 dates. Missing segment dates are dates with no rows, not a second page.

## Stream

- Name: `market-segments`
- Bronze: `mlt_lighthouse_ota__market_segments_hotel_{hotel_id}`
- Primary key: `(as_of_date, stay_date, market_segment)`
- Replication key: `as_of_date`
- One GraphQL call per as-of date, after one page load for the session
- Pickup window and as-of cap reuse `strategy_v2_pickup_days` and `strategy_v2_max_as_of_dates`

Hotel totals, inventory, transient versus group, named groups, forecast, budget, and system rate stay on `strategy-snapshot-v2`. The `GROUP` market segment is one code in this list, not those group fields.
