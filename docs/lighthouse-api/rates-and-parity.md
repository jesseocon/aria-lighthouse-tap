# Lighthouse rates and parity pages: API catalog and hover equivalence

Status: **draft for review**. Captured 2026-10-09 against hotel 202158 (workshop run `20261009-195741-0437d95f`). No rate refresh or live shop was triggered.

## Summary

- **Rates page** (`/hotel/202158/rates`): one REST call, `GET /apigateway/v1/app/rates/`, returns every hotel's rate per stay date, including everything the hover shows: rate, room name, update time, and sold-out status.
- **Parity list** (`/hotel/202158/parity/list`): one REST call, `GET /apigateway/v1/app/parities/`, returns every channel's rate per stay date. That includes the metasearch sub-channels behind the "loss channels" hover, with their price difference to Brand.com.
- **Rates hovers:** "My OTB", market demand, and events come from three small calls: `revenueinsight/occupancies`, `demand/ari/demands`, and `events/accepted`.
- **Every hover field we scrape today has an API equivalent** (table below). The API is usually richer: exact timestamps instead of "3 hours ago", rate name and code, cancellability, taxes, and the source system.
- **Authentication:** the Lighthouse session cookie only. These are same-origin calls from `app.mylighthouse.com` with no extra headers.

## Hotel ids (shared by all Lighthouse APIs)

| Id | Meaning | Where it appears |
|---|---|---|
| `202158` | Lighthouse **subscription** id; the id in app URLs | `hotel_id` / `subscription_id` query params |
| `28650` | Lighthouse **hotelinfo** id of the subject hotel | Keys in `rates`, `hotelinfo` in parity and occupancy rows, `hotelId` in redirect URLs |
| `263238`, `38486`, `185158`, `57477`, `521053` | hotelinfo ids of the 5 competitors in comp set 1 | Keys in `rates`; also Spider's `vendorId` in [strategy](strategy.md) |
| `28646`, `266864` | Two more competitors on the subscription (`/api/v3/hotels/` lists 7 in total), outside comp set 1 | Names not captured yet |
| `9203` | Spider (strategy) hotel id | Spider GraphQL only |

Spider's `vendorId` is the same id as Lighthouse's hotelinfo id, so rates, parity, and strategy can all join on it.

## Rates: `GET /apigateway/v1/app/rates/`

Example request (Brand.com, Best flex):

```
/apigateway/v1/app/rates/?ota=branddotcom&los=1&mealtype=0&persons=2&roomtype=all&membershiptype=0
  &compset_ids=1&platform=-1&meta=nested&bar=true&flexible=true&rate_type=0
  &from_date_range_start=2026-09-28&from_date_range_end=2026-11-01&hotel_id=202158
```

- One call covers a whole month view. The page requests the full calendar weeks around the month: 35 stay dates, about 200 KB.
- Response: `periods[]`, one per stay date (`from_date`). Each has `rates: {<hotelinfo id>: [rate item]}` for the subject and all comp-set hotels.

### Rate-type parameters

| Stream `rates_rate_types` key | UI `rateParam` | `bar` | `flexible` | `rate_type` |
|---|---|---|---|---|
| `best_flex` (default) | none | `true` | `true` | `0` |
| `lowest_flex` | `flex` | `false` | `true` | `0` |
| `lowest` | `lowest` | `false` | `false` | `0` |
| `third_party` | `thirdparty` | `false` | `false` | `1` |

The channel goes in `ota`: `branddotcom`, `bookingdotcom`, `expedia`, or `priceline`. The current stream uses those four.

### Rate item fields

`value`, `shop_value`, `currency`, `shop_currency`, `message` (`rates.soldout` or empty), `room_name`, `room_type`, `cema_category`, `rate_name`, `rate_code`, `best_flex`, `cancellable`, `cancellation`, `mealtype_included`, `membershiptype`, `max_persons`, `vat`, `vat_incl`, `city_tax`, `city_tax_incl`, `other_taxes`, `other_taxes_incl`, `is_out_of_sync`, `is_wholesale_rate`, `source_id` (`hilton`, `ihg`, …), `extract_datetime`, `hotelinfo`, `ota`, `platform`, `labels`.

### Hover equivalence (verified for stay date 2026-10-17, Brand.com, Best flex)

| Bronze field (v1) | API source | Example: v1 vs API |
|---|---|---|
| `rate` / `hover_rate` | `value` | `$ 399` vs `399` |
| `hover_room_name` | `room_name` | `1 KING BED W/ACCESSIBLE BATHTUB - HEARING`, identical |
| `hover_updated` | `extract_datetime` | `2 minutes ago` vs `2026-10-09T16:15:40Z` |
| Sold-out cell | `message = "rates.soldout"`, `value = 0` | Crowne Plaza sold out in both |
| `competitor` name | Hotel name by hotelinfo id (from [strategy](strategy.md) `GetDayByDayStrategy` competitors, or the hotels API) | |
| `my_otb`, `my_otb_hover` | `revenueinsight/occupancies` (below) | `81% (146/181), transient 101, groups 45, available 35`; identical numbers |
| `market_demand` | `demand/ari/demands` `value` | `100%` vs `0.99921` |
| `events_hover` | `events/accepted` | `Head of the Charles Regatta, 16/10–18/10` in both |
| `redirect_url` | Built from request params: `/redirect?ota=…&hotelId=<hotelinfo>&direct=false&fromDate=…&los=…&persons=…&city=false&subscription_id=202158&pos=&source=app_rates` | |

All 6 hotels matched exactly on rate, room name, and sold-out status.

### Supporting calls on the rates page

| Endpoint | Params | What it is | Hover it replaces |
|---|---|---|---|
| `GET /apigateway/v1/app/revenueinsight/occupancies/` | `subscription_id`, `from_date_range_start`/`end`, `compare_extract_date` | Per stay date: `rooms_booked`, `rooms_booked_individual` (transient), `rooms_booked_group`, `rooms_out_of_order`, `total_capacity`, plus `occupancy_changes[]` at `compare_extract_date` | `my_otb`, `my_otb_hover` |
| `GET /apigateway/v1/app/demand/ari/demands/` | `subscription_id`, date range, `change_dates[]` | Market demand index (0–1) per stay date, with `demand_changes[]` | `market_demand` |
| `GET /apigateway/v1/app/events/accepted/` | `subscription_id`, `hotel_id`, date range, `change_dates[]` | Events: name, category, dates, visitors, location, lat/lon | `events_hover` |
| `GET /apigateway/v1/app/holidays/` | Same | Holidays per date | |
| `GET /apigateway/v1/app/roomtypes/rates/` | `hotel_id`, `ota`, `data_type=rates` | Room-type mapping per competitor (name, mapped type, average price) | |
| `GET /api/v3/liveupdates/` | `hotel_id` | Live-shop status and shop limits | Refresh-button state |

`my_otb_hover` showed the values at `occupancy_changes[0]` ("Update a day ago": extract 2026-10-08). The top-level row holds the latest extract (2026-10-09). v2 should land both.

## Parity: `GET /apigateway/v1/app/parities/`

Example request:

```
/apigateway/v1/app/parities/?hotel_id=202158&from_date_range_start=2026-10-09&from_date_range_end=2026-10-31
  &mealtype=0&los=1&persons=2&pos=&roomtype=all&membershiptype=0&platform=-1&meta=nested
  &base_membershiptype=0&bar=false&flexible=false&rate_type=0
```

- One call per month view: 23 stay dates (today to month end), about 430 KB.
- Response: `periods[]` per stay date. Each has `parities[]`, about 20 entries: one per OTA **and** per metasearch sub-channel.
- `meta` contains `num_shops_major` and `num_shops_other`.
- Parity items have the same fields as rate items, plus:
  - `channel`: the actual seller, for example `ota=googlehotelfinder, channel=momondo`.
  - `unmapped_channel`.
  - `is_baserate`: true for Brand.com, the reference rate.
  - `difference_with_baserate`: price minus the Brand.com rate.
  - `position_to_baserate`: `-1` cheaper, `0` equal, `1` more expensive.
  - `issue_type`.
  - `pos`: point of sale.
  - `labels`: for example `metasearch_header_deal`.

### `issue_type` (inferred; confirm against a same-day v1 run)

| `issue_type` | `position_to_baserate` | Meaning | v1 `*_parity_status` |
|---|---|---|---|
| `0` | 0 | Base rate (Brand.com) | none |
| `3` | -1 | Channel cheaper than Brand.com (**loss**) | `parity-loss` |
| `4` | 0 | Equal (**meet**) | `parity-meet` |
| `5` | 1 | Channel more expensive (**win**) | `parity-win` |

### Hover equivalence

The latest v1 bronze parity run is from 2026-10-02 and this capture is from 2026-10-09, so values differ. Every field has a source:

| Bronze field (v1) | API source |
|---|---|
| `<channel>` (cell rate) | `value` for the item where `ota = <channel>` and `channel = <channel>` |
| `<channel>_hover_room_name` | `room_name`; matched for Brand.com and Booking.com room names |
| `<channel>_hover_updated`, `lowest_rate_hover_text` ("Updated 13 hours ago") | `extract_datetime` |
| `<channel>_parity_status` | `issue_type` / `position_to_baserate` |
| `lowest_rate` | Minimum `value` across the period's items |
| `loss_channels_on_metasearch` and `_hover_channels` (`[{channel, rate, loss, source}]`) | Items with `position_to_baserate = -1`: `channel`, `value`, `difference_with_baserate`, source from `ota` (`googlehotelfinder` → Google, `tripadvisor` → Tripadvisor, `trivago` → Trivago) |
| `<channel>_redirect_ota`, `_from_date`, `_links` | Built from `ota`, `period`, and request params |

### Supporting calls on the parity page

| Endpoint | What it is |
|---|---|
| `GET /apigateway/v1/app/roomtypes/parity/?ota=allchannels&data_type=parity` | Room-type mapping across channels (21 mapped names) |
| `GET /apigateway/v1/app/usermanagement/otahotelinfos/` | The hotel's listing id on each of 16 OTAs (`their_hotel_id`) |
| `GET /apigateway/v1/app/parityanalytics/subscriptions/{id}/config/` | Parity-analytics LOS and POS settings |

## v2 streams (implemented in `tap_lighthouse/streams_v2.py`)

Same approach as [strategy-snapshot-v2](strategy.md#proposed-strategy-snapshot-v2-stream). Existing `rates` and `parity-list` stay as they are.

### `rates-v2`

- Per run: load the rates page once. It serves as the session check; **do not click refresh unless `rates_refresh` is on**, which stays the same opt-in it is today.
- Then, for each month × channel × rate type, call `rates/` once. The default config (1 month, 4 channels, Best flex) is **4 calls**, against 4 page loads plus hundreds of hovers in v1.
- Once per run: `occupancies`, `demands`, and `events` for the date range (3 calls).
- Record per stay date × channel × rate type × hotel: every rate-item field, plus `competitor_name`, `is_subject`, and the OTB, demand, and events fields joined on stay date.

### `parity-list-v2`

- Per month: one `parities/` call.
- Record per stay date × `ota` × `channel`: every parity-item field. Wide per-channel columns and `lowest_rate` move to dbt.

### Traffic

Both pages send these calls once per page view, and v2 sends the same calls with the same parameters, from the page's own context, paced like the strategy stream. Volumes are tiny. A default rates run (2 months × 4 channels × Best flex) makes 12 calls: 8 `rates/`, plus hotels, occupancies, demands, and events once. A default parity run makes 4: hotels plus 3 months of `parities/`. v1 needs page loads plus one hover per cell.

## Open questions

1. Which comp set has `28646` and `266864`? Is it `compset_ids=2`? One capture would show it.
2. Should `issue_type` be confirmed with a same-day v1 parity run before v2 depends on it?
3. Does `rates/` accept a wider date range than one month per call? It's the same server load either way; matching the page's month window is the safer default.
4. Should "My OTB" land the latest extract, the compare extract, or both? This document proposes both.
