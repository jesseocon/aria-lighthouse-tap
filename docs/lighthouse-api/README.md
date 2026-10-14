# Lighthouse API catalog

These are the internal APIs behind the Lighthouse pages we scrape, captured with the workshop daemon's network recorder (`workshop network …` in `aria-singer-playwright`). They are the basis for the v2 streams, which call these APIs directly instead of reading the rendered DOM. The v1 streams stay in place.

| Doc | Pages | v2 streams |
|---|---|---|
| [strategy.md](strategy.md) | Day-by-day strategy (Spider iframe, GraphQL) | `strategy-snapshot-v2` |
| [market-segments.md](market-segments.md) | Day-by-day market segments (same GraphQL gateway) | `market-segments` |
| [rate-plans.md](rate-plans.md) | Day-by-day rate plans (same GraphQL gateway) | `rate-plans` |
| [length-of-stay.md](length-of-stay.md) | Day-by-day length of stay (same GraphQL gateway) | `length-of-stay` |
| [room-type.md](room-type.md) | Day-by-day room type (same GraphQL gateway) | `room-type` |
| [rates-and-parity.md](rates-and-parity.md) | Rates table, parity list (REST) | `rates-v2`, `parity-list-v2` |
| [tap_lighthouse/graphql/](../../packages/tap-lighthouse/tap_lighthouse/graphql/) | Captured Spider GraphQL documents (used by the tap) | |

Hotel ids differ by system (subscription `202158`, hotelinfo `28650`, Spider `9203`). See [rates-and-parity.md#hotel-ids-shared-by-all-lighthouse-apis](rates-and-parity.md#hotel-ids-shared-by-all-lighthouse-apis).

The v2 streams are implemented in `tap_lighthouse/streams_v2.py` (API client: `api_client.py`; mapping: `spider_api.py`, `lighthouse_api.py`).
