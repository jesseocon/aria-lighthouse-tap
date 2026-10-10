# Jev morning desk — sample

Hilton Garden Inn Boston-Burlington, as-of **2026-10-09**, from `hospitalityops-dev.bronze_1782243883257222643.mlt_lighthouse_ota__snapshot_daily_v2_hotel_202158`.

The packet numbers are from that snapshot. The probabilities are a sample of the Jev response shape, not a live model call. Parity is left out because this table does not have it.

Jev scores each stay date. The Cursor agent writes a sentence only when the score is clear. Dates that split, or whose shop cannot be trusted, stay on the page as unresolved or drop off it.

## What gets sent

One call per stay date. State is the SQL packet. Questions are fixed.

```json
{
  "model": "jev-latest",
  "state": {
    "property": "Hilton Garden Inn Boston-Burlington",
    "as_of_date": "2026-10-09",
    "stay_date": "2026-10-17",
    "lead_time_days": 8,
    "inventory": 181,
    "otb_rooms": 147,
    "adr": 245.03,
    "stly_rooms": 108,
    "ly_final_rooms": 177,
    "pickup_rooms_7d": 16,
    "forecast_rooms": 181,
    "budget_rooms": 160.2,
    "hurdle": 302.65,
    "optimal_bar": 360.88,
    "subject_rate": 399,
    "subject_rate_change_7d": 70,
    "comp_avg_rate": 369,
    "gap_to_comp_avg": 30,
    "comps": [
      {"name": "Hampton Inn Boston Bedford Burlington", "rate": 344, "change_7d": 30},
      {"name": "Courtyard by Marriott Boston Billerica Bedford", "rate": 349},
      {"name": "Hyatt House Boston/Burlington", "rate": 359, "change_7d": 20},
      {"name": "Boston Marriott Burlington", "rate": 424, "change_7d": 55},
      {"name": "Crowne Plaza Boston - Woburn by IHG", "rate": null}
    ],
    "groups": [
      {"name": "Lion Travel Service", "rooms": 20},
      {"name": "Green Lake Crew", "rooms": 13}
    ],
    "notes": ""
  },
  "questions": {
    "situation": {
      "type": "choice",
      "instructions": "What is the commercial situation on this stay date?",
      "criteria": {
        "hold": "Pace and price are inside a band a revenue manager would leave alone this morning.",
        "raise": "On the books is ahead of the same lead time last year, and the rate is still at or under the hurdle or optimal BAR with rooms left.",
        "ease": "On the books is behind the same lead time last year, and the rate is still above the optimal BAR with rooms left.",
        "held_by_note": "The note marks this date as a group hold, citywide, or do-not-touch.",
        "do_not_touch_untrusted": "The shop is missing, sold out, or not comparable, so the rate should not be moved off this packet."
      }
    },
    "materiality": {
      "type": "score",
      "instructions": "How soon does someone need to look at this date?",
      "criteria": [
        "Ignore through the week",
        "Mention in the revenue meeting",
        "Act this morning",
        "Act before the next shop"
      ]
    },
    "note_blocks_action": {
      "type": "noul",
      "instructions": "Does the note forbid a rate change? A note that only restates the current rate does not."
    },
    "shop_is_comparable": {
      "type": "noul",
      "instructions": "Are enough competitor rates present, and not sold out, to judge the gap?"
    }
  }
}
```

## What Jev returns

Saturday 2026-10-17. On the books is 147 versus 108 at the same lead time last year. The rate is $399, up $70, against a $369 comp average and a $361 optimal BAR. Crowne Plaza has no rate.

```json
{
  "answers": {
    "situation": {
      "type": "choice",
      "choice": "hold",
      "confidence": 0.81,
      "probabilities": {
        "hold": 0.86,
        "raise": 0.09,
        "ease": 0.03,
        "held_by_note": 0.01,
        "do_not_touch_untrusted": 0.01
      }
    },
    "materiality": {
      "type": "score",
      "score": 1.15,
      "confidence": 0.74,
      "probabilities": {"0": 0.04, "1": 0.78, "2": 0.17, "3": 0.01}
    },
    "note_blocks_action": {"type": "noul", "noul": 0.03},
    "shop_is_comparable": {"type": "noul", "noul": 0.77}
  }
}
```

Code lets this through: winning probability 0.86, confidence 0.81, shop usable. Materiality says mention, not act. The agent gets this one date and may only cite the packet.

Monday 2026-10-19 is the split. On the books is 118 versus 58 last year at this lead time, and pickup is +53 rooms. The published comp average is $401.50 because the Marriott is $609. Hampton is $289. Our rate is $299 and did not move.

```json
{
  "situation": {
    "choice": "raise",
    "confidence": 0.22,
    "probabilities": {
      "hold": 0.41,
      "raise": 0.48,
      "ease": 0.06,
      "held_by_note": 0.01,
      "do_not_touch_untrusted": 0.04
    }
  },
  "materiality": {"score": 2.4, "confidence": 0.55},
  "shop_is_comparable": {"noul": 0.61}
}
```

Confidence is under 0.7, so the agent never runs. The date still shows, marked unresolved.

## What the revenue manager sees

**Hilton Garden Inn Boston-Burlington — morning of 2026-10-09**

### Look at

| Stay date | Situation | Why it surfaced |
|---|---|---|
| Sat 10/17 | Hold, 0.86 | 147 on the books vs 108 last year at this lead time. Rate $399, up $70, vs $369 comp average and $361 optimal BAR. |
| Mon 10/19 | Unresolved | 118 vs 58 last year, pickup +53. Comp average $401 is the Marriott at $609; Hampton is $289 and we are $299. Raise and hold are 0.48 and 0.41. |

### Left off the page

| Stay date | What the gates did |
|---|---|
| Sat 10/10 | 181 of 181 sold. Subject rate and comp average are null. `do_not_touch_untrusted`. |
| Mon 10/12 | 56 on the books vs 104 last year, rate already down $80 to $219. Ease and hold split. No card. |
| Tue 10/27 | Note is `229`, the same as the rate. `note_blocks_action` 0.06, so the note does not hold the date. Already cut $103. Not material enough to surface. |

The agent line for 10/17, after the grounding check:

> Leave Saturday 10/17. On the books is 147 rooms against 108 at the same lead time last year, and the rate is $399 versus a $369 comp average and a $361 optimal BAR, after a $70 increase.

A draft that said "cut $40, we are above a $359 comp set" fails the second Jev call: the $359 figure is not in the packet, and `ease` does not match `hold`. That card is dropped.
