# Warehouse table names

Gold names the business area. Silver names the product the rows were loaded from. Property id is a suffix on the physical table, not part of the model name.

Gold models use these names. Silver stays on the product stream name.

## Pattern

```text
silver:  {source}__{stream}_{property_id}
gold:    mlt_mart__{area}__{subject}_{grain}_{property_id}
```

Model file and dbt alias drop `_{property_id}`. A portfolio view drops it too, and unions one row set per property.

`grain` is the row's time bucket: `daily` is one row per stay date, `weekly` one row per week, `monthly` one row per month. Competitor, channel, segment, and index stay columns.

Areas in use:

| Area | What it is |
|---|---|
| `commercial` | This hotel's rooms, rates, parity, rooms budget, and rooms forecast |
| `market` | Comp set and the wider market. Not this hotel's own books |
| `labor` | Hours, productivity, overtime |
| `finance` | P&L, actuals, and the accounting budget |

`labor` already follows this in `aria-labor-transforms` (`mlt_mart__labor__status_weekly`).

## Commercial

Lighthouse feeds these. The product name stays on the silver stream.

| Mart | Grain |
|---|---|
| `mlt_mart__commercial__otb_daily` | Stay date. As-of date is a column |
| `mlt_mart__commercial__rate_shop_daily` | Stay date. Competitor is a column |
| `mlt_mart__commercial__parity_daily` | Stay date. Channel is a column |
| `mlt_mart__commercial__parity_loss_daily` | Stay date. One row per losing channel |
| `mlt_mart__commercial__budget_daily` | Stay date. Segment is a column |
| `mlt_mart__commercial__forecast_daily` | Stay date. Segment is a column |

Silver stays `mlt_lighthouse_ota__{stream}_{property_id}`.

## Market

| Mart | Source | Grain |
|---|---|---|
| `mlt_mart__market__comp_set_daily` | STR | Stay date. Occupancy, ADR, RevPAR, and indexes (MPI, ARI, RGI) are columns. Week and month are summed in the BI tool from supply, demand, and revenue |
| `mlt_mart__market__comp_set_segment_monthly` | STR | Month. Transient, group, and contract are a column |
| `mlt_mart__market__pace_daily` | Demand360 | Stay date. Comp set and market scope are a column |
| `mlt_mart__market__agency_monthly` | Agency360 | Month. Account and channel are columns |

Silver for STR is `mlt_str__{stream}_{property_id}`.

## Adding a mart

1. Pick the area from the table above. Add a row to that table when a new area is real.
2. Name the subject for the thing a person asks for, not the vendor page or file.
3. Put the grain last. Do not encode the rest of the primary key in the table name.
4. Pass `area__subject_grain` to the mart alias macro, which expands to `mlt_mart__{suffix}_{property_id}`.
5. Leave the product name on silver only.
