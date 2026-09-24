#!/usr/bin/env python3
"""Deep hover probe for parity price cells and shield icons."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/singer-playwright"))

from singer_playwright.browser import BrowserConfig, BrowserRuntime

URL = "https://app.mylighthouse.com/hotel/202158/parity/list?los=1&maxPersons=2&month=2026-09"

CELL_STRUCTURE_JS = """
() => {
  const normalize = (v) => (v ?? "").replace(/\\s+/g, " ").trim();
  const row = document.querySelector('tbody tr:nth-child(2)');  // Thu 17/09 with prices
  if (!row) return { error: 'no row' };

  return Array.from(row.querySelectorAll('td')).map((td, i) => ({
    index: i,
    text: normalize(td.textContent).slice(0, 100),
    html: td.innerHTML.slice(0, 800),
    attrs: Array.from(td.attributes).map((a) => ({ name: a.name, value: a.value.slice(0, 200) })),
    children: Array.from(td.querySelectorAll('*')).slice(0, 20).map((el) => ({
      tag: el.tagName,
      className: (el.className || '').slice(0, 100),
      role: el.getAttribute('role'),
      title: el.getAttribute('title'),
      'aria-label': el.getAttribute('aria-label'),
      text: normalize(el.textContent).slice(0, 60),
    })),
  }));
}
"""


def main() -> None:
    runtime = BrowserRuntime(
        BrowserConfig(storage_state_path="storage_state.json", headless=True),
    )
    runtime.start()
    try:
        page = runtime.page
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_selector(".prism-table table tbody tr", timeout=60_000)
        page.wait_for_timeout(2000)

        structure = page.evaluate(CELL_STRUCTURE_JS)
        print("=== ROW CELL STRUCTURE (Thu 17/09) ===")
        print(json.dumps(structure, indent=2))

        # Hover shield icons specifically
        shields = page.locator("tbody tr td svg, tbody tr td [class*='shield'], tbody tr td [class*='icon']").all()
        print(f"\n=== Found {len(shields)} icon elements ===")

        hover_results = []
        # Try hovering each td in row 2 (index 1)
        row = page.locator("tbody tr").nth(1)
        tds = row.locator("td").all()
        for i, td in enumerate(tds[:6]):
            entry = {"cell_index": i, "tooltips": []}
            try:
                # Clear any existing tooltips
                page.mouse.move(0, 0)
                page.wait_for_timeout(300)
                td.hover()
                page.wait_for_timeout(800)
                tips = page.locator('[role="tooltip"]:visible, .tippy-box:visible, [class*="popover"]:visible')
                for j in range(tips.count()):
                    text = tips.nth(j).inner_text(timeout=500)
                    if text and text not in ("Member rate", "Any room", "Lowest", "Desktop"):
                        entry["tooltips"].append(text[:500])
            except Exception as exc:  # noqa: BLE001
                entry["error"] = str(exc)
            hover_results.append(entry)

        print("\n=== PER-CELL HOVER ===")
        print(json.dumps(hover_results, indent=2))

        # Check for title/aria on links
        link_meta = page.evaluate("""
        () => Array.from(document.querySelectorAll('tbody tr td a[href*="redirect"]')).slice(3, 8).map(a => ({
          text: a.textContent.trim(),
          title: a.title,
          ariaLabel: a.getAttribute('aria-label'),
          dataset: {...a.dataset},
          parentTitle: a.parentElement?.getAttribute('title'),
          siblingText: a.nextElementSibling?.textContent?.trim(),
        }))
        """)
        print("\n=== LINK METADATA ===")
        print(json.dumps(link_meta, indent=2))

        out = Path("workshop-runs/parity-hover-probe.json")
        out.write_text(json.dumps({"structure": structure, "hovers": hover_results, "links": link_meta}, indent=2), encoding="utf-8")
        print(f"\nWrote {out}")
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
