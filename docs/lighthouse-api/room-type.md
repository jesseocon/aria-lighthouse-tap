# Lighthouse room type

Captured 2026-10-10 against hotel 202158 (Spider hotel 9203). Implemented as `room-type`.

The page is `https://app.mylighthouse.com/hotel/{hotel_id}/day-by-day/room-type`. It loads the same six `GetLhDayByDayCommon` calls as [strategy](strategy.md). This stream does not request them.

## `GetLhDayByDayRoomTypes`

Document: [`graphql/GetLhDayByDayRoomTypes.graphql`](../../packages/tap-lighthouse/tap_lighthouse/graphql/GetLhDayByDayRoomTypes.graphql)

`POST https://app.mylighthouse.com/apigateway/v1/proxy/spider/graphql`

Variables match [market segments](market-segments.md): hotel id, as-of, pickup-from, stay-date range, currency. There is no room-type argument. The Rate Plan dropdown on the other day-by-day pages refetched the same query, so this stream does not drive it.

Response: `data.lhDayByDayRoomTypes` with `aggregates` (stay dates), `mappings` (empty for this hotel), and `topCategories` (the room-type codes used as columns). Each aggregate row is one room type. `marketSegment`, `ratePlan`, `company`, and `groupName` were empty. Stay date is on the parent object.

This hotel returned 11 room types (`Q2`, `K1`, `K1RZ`, `K1RRQ`, `K1RZQ`, `K1RZC`, `Q2RRV`, `K1RZD`, `K1DRV`, `K1RRV`, `K1RRC1`), 204 stay dates from 2026-10-10 through 2027-07-08, and 747 rows. A date can omit a room type. No date repeated a room type.

## Stream

- Name: `room-type`
- Bronze: `mlt_lighthouse_ota__room_type_hotel_{hotel_id}`
- Primary key: `(as_of_date, stay_date, room_type)`
- Replication key: `as_of_date`
- One GraphQL call per as-of date, after one page load for the session
- Pickup window and as-of cap reuse `strategy_v2_pickup_days` and `strategy_v2_max_as_of_dates`

## Pages that reuse the strategy snapshot

`last-year-and-forecast` and `group-and-events` do not have their own GraphQL operation. Reloading each page sent the same six `GetLhDayByDayCommon` query keys already stored by `strategy-snapshot-v2` (`main`, `group_bar`, `stly`, `asof`, `budget_forecast`, `main_kriya`). Group and events also sent `GetDayByDayStrategy`, which that stream already stores. Named groups are the `groups` array. Last year, STLY, budget, and forecast are the matching fields on the same row. Holidays, events, and demand are shell REST calls shared by every day-by-day page.
