"use strict";
(() => {
  // src/core/text.ts
  function normalizeText(value) {
    return value.replace(/\s+/g, " ").trim();
  }

  // src/core/header-text.ts
  function isSpacerElement(element) {
    return element.classList.contains("spacer");
  }
  function isTruncatedHeaderText(text) {
    return /\.\.\.$|…$/u.test(text.trim());
  }
  function cleanHeaderText(element) {
    const clone = element.cloneNode(true);
    clone.querySelectorAll("script, style, form, label, input, select, option").forEach((node) => {
      node.remove();
    });
    const visible = normalizeText(clone.textContent ?? "");
    const title = element.getAttribute("title");
    if (title) {
      const normalizedTitle = normalizeText(title);
      const visibleStem = visible.replace(/\.{3}$|…$/u, "").trim();
      if (isTruncatedHeaderText(visible) || visibleStem.length > 0 && normalizedTitle.length > visible.length && normalizedTitle.toLowerCase().startsWith(visibleStem.toLowerCase())) {
        return normalizedTitle;
      }
    }
    return visible;
  }

  // src/core/detect-table.ts
  function rowLooksLikeHeader(row, headerMarkers) {
    const text = normalizeText(row.textContent ?? "");
    return headerMarkers.some((marker) => text.includes(marker));
  }
  function findCandidateTables(root, preferredSelector) {
    if (preferredSelector) {
      const preferred = root.querySelector(preferredSelector);
      if (preferred) return [preferred];
    }
    const candidates = [];
    for (const table of root.querySelectorAll("table")) {
      candidates.push(table);
    }
    for (const grid of root.querySelectorAll('[role="grid"], [role="table"]')) {
      candidates.push(grid);
    }
    const divTables = root.querySelectorAll(
      '[class*="table"], [class*="grid"], [data-testid*="table"], [data-testid*="grid"]'
    );
    for (const div of divTables) {
      if (div.querySelector('[role="row"], tr, [class*="row"]')) {
        candidates.push(div);
      }
    }
    return candidates;
  }
  function scoreTableCandidate(root, headerMarkers) {
    const text = normalizeText(root.textContent ?? "");
    let score = 0;
    for (const marker of headerMarkers) {
      if (text.includes(marker)) score += 10;
    }
    const rowCount = root.querySelectorAll('[role="row"], tr').length;
    if (rowCount >= 5) score += 5;
    if (rowCount >= 20) score += 5;
    return score;
  }
  function getRows(container) {
    const ariaRows = Array.from(container.querySelectorAll(':scope > [role="row"]'));
    if (ariaRows.length > 0) return ariaRows;
    const theadRows = Array.from(container.querySelectorAll(":scope > thead > tr"));
    if (theadRows.length > 0) return theadRows;
    const tbodyRows = Array.from(container.querySelectorAll(":scope > tbody > tr"));
    if (tbodyRows.length > 0) return tbodyRows;
    const directRows = Array.from(container.querySelectorAll(":scope > tr"));
    if (directRows.length > 0) return directRows;
    return [];
  }
  function findDefaultHeaderRows(root, headerMarkers) {
    const thead = root.querySelector("thead");
    if (thead) {
      const rows = Array.from(thead.querySelectorAll(":scope > tr"));
      if (rows.length >= 2) return rows.slice(0, 3);
      if (rows.length === 1) return rows;
    }
    const explicitHeader = root.querySelector(
      '[role="rowgroup"][aria-label*="header"], [class*="header-row"], [data-testid*="header"]'
    );
    if (explicitHeader) {
      const rows = getRows(explicitHeader);
      if (rows.length > 0) return rows.slice(0, 2);
    }
    const allRows = getRows(root);
    const headerRows = allRows.filter((row) => rowLooksLikeHeader(row, headerMarkers));
    if (headerRows.length >= 1) {
      return headerRows.slice(0, 2);
    }
    return allRows.slice(0, 2);
  }
  function findBodyContainer(root, headerRows) {
    const body = root.querySelector('[role="rowgroup"]:not([aria-label*="header"]), tbody, [class*="body"]');
    if (body) return body;
    const allRows = getRows(root);
    const headerSet = new Set(headerRows);
    const dataRows = allRows.filter((row) => !headerSet.has(row));
    if (dataRows.length > 0 && dataRows[0].parentElement) {
      return dataRows[0].parentElement;
    }
    return root;
  }
  function findScrollContainer(root) {
    let current = root;
    while (current) {
      const style = getComputedStyle(current);
      const overflowY = style.overflowY;
      if ((overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") && current.scrollHeight > current.clientHeight + 4) {
        return current;
      }
      current = current.parentElement;
    }
    return null;
  }
  function detectTable(doc = document, config) {
    const candidates = findCandidateTables(doc, config.preferredSelector);
    if (candidates.length === 0) return null;
    const minScore = config.minScore ?? 20;
    const ranked = candidates.map((candidate) => ({
      candidate,
      score: scoreTableCandidate(candidate, config.headerMarkers)
    })).filter(({ score }) => score >= minScore).sort((a, b) => b.score - a.score);
    if (ranked.length === 0) return null;
    const root = ranked[0].candidate;
    const headerRows = config.findHeaderRows ? config.findHeaderRows(root, config.headerMarkers) : findDefaultHeaderRows(root, config.headerMarkers);
    const bodyContainer = findBodyContainer(root, headerRows);
    const scrollContainer = findScrollContainer(bodyContainer);
    return {
      root,
      headerRows,
      bodyContainer,
      scrollContainer
    };
  }
  function looksLikeDate(value) {
    return /\b\d{1,2}\/\d{1,2}\/\d{2,4}\b/.test(value) || /\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b/i.test(value);
  }
  function looksLikeSummaryRow(firstCellText, row) {
    const normalized = normalizeText(firstCellText);
    if (/^total$/i.test(normalized)) return true;
    const className = row.className?.toString() ?? "";
    if (/summary|total|aggregate|main-foot/i.test(className)) return true;
    if (row.closest("tfoot")) return true;
    const style = row.getAttribute("style") ?? "";
    if (/background/i.test(style) && !looksLikeDate(normalized)) return true;
    return false;
  }

  // src/core/export/to-csv.ts
  function escapeCsvValue(value) {
    if (/[",\n\r]/.test(value)) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  }
  function getExportHeaders(columns) {
    return columns.map((column) => column.label);
  }
  function rowToCsvValues(row, columns) {
    return columns.map((_, index) => row.cells[index]?.raw ?? "");
  }
  function toCsv(columns, rows, options = {}) {
    const dataHeaders = getExportHeaders(columns);
    const provenance = options.provenance ?? { headers: [], values: [] };
    const headers = [...dataHeaders, ...provenance.headers];
    const lines = [headers.map(escapeCsvValue).join(",")];
    for (const row of rows) {
      const values = [...rowToCsvValues(row, columns), ...provenance.values];
      lines.push(values.map(escapeCsvValue).join(","));
    }
    return `${lines.join("\n")}
`;
  }

  // src/core/export/filename.ts
  function slugifyFilenameSegment(text, maxLength = 30) {
    return text.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/['']/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, maxLength);
  }
  function parseDisplayDateToIso(date) {
    if (!date) return void 0;
    const mdy = date.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (mdy) {
      const [, month, day, year] = mdy;
      return `${year}${month.padStart(2, "0")}${day.padStart(2, "0")}`;
    }
    const iso = date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (iso) {
      return `${iso[1]}${iso[2]}${iso[3]}`;
    }
    return void 0;
  }

  // src/core/derive-date-range.ts
  function parseRowDateCell(text) {
    const match = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
    if (!match) return void 0;
    const [, month, day, yearRaw] = match;
    const year = yearRaw.length === 2 ? `20${yearRaw}` : yearRaw;
    return `${month.padStart(2, "0")}/${day.padStart(2, "0")}/${year}`;
  }
  function comparableDisplayDate(date) {
    const iso = parseDisplayDateToIso(date);
    return iso ? Number(iso) : 0;
  }
  function deriveDateRangeFromRows(rows) {
    const dates = [];
    for (const row of rows) {
      if (row.isSummary) continue;
      const firstCell = row.cells[0]?.raw ?? "";
      if (!looksLikeDate(firstCell)) continue;
      const parsed = parseRowDateCell(firstCell);
      if (parsed) dates.push(parsed);
    }
    if (dates.length === 0) return {};
    let start = dates[0];
    let end = dates[0];
    for (const date of dates) {
      if (comparableDisplayDate(date) < comparableDisplayDate(start)) start = date;
      if (comparableDisplayDate(date) > comparableDisplayDate(end)) end = date;
    }
    return { start, end };
  }

  // src/core/column-name.ts
  function slugifyPart(text) {
    return entitySlugFromDisplayLabel(text);
  }
  function entitySlugFromDisplayLabel(text) {
    return text.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  }
  function toBigQueryColumnName(parts) {
    const slug = parts.map(slugifyPart).filter(Boolean).join("_");
    let name = slug || "column";
    if (/^[0-9]/.test(name)) {
      name = `_${name}`;
    }
    return name.slice(0, 300);
  }
  function buildColumnNameFromParts(parts) {
    const cleaned = parts.map((part) => part.trim()).filter(Boolean);
    if (cleaned.length === 0) return "column";
    return toBigQueryColumnName(cleaned);
  }
  function dedupeColumnLabels(columns) {
    const used = /* @__PURE__ */ new Set();
    return columns.map((column, index) => {
      let label = column.label;
      let suffix = 2;
      while (used.has(label)) {
        label = `${column.label}_${suffix}`;
        suffix += 1;
      }
      used.add(label);
      if (label === column.label) return column;
      return {
        ...column,
        id: makeColumnId(label, index),
        label
      };
    });
  }
  function makeColumnId(label, index) {
    const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    return slug || `col-${index}`;
  }
  function provenanceColumnName(key) {
    const snake = key.replace(/([a-z])([A-Z])/g, "$1_$2").replace(/([A-Z])([A-Z][a-z])/g, "$1_$2").toLowerCase();
    return `_${snake}`;
  }

  // src/core/header-grid.ts
  function resolveCleanHeaderText(options = {}) {
    return options.cleanHeaderText ?? cleanHeaderText;
  }
  function isEmptyVarianceLeaf(cell) {
    return !cell.text && cell.element.classList.contains("mw-xs");
  }
  function getHeaderCells(row, options = {}) {
    const readHeaderText = resolveCleanHeaderText(options);
    const cells = Array.from(
      row.querySelectorAll('[role="columnheader"], th, [class*="header-cell"], [class*="col-header"]')
    ).filter((element) => !isSpacerElement(element));
    if (cells.length === 0) {
      const fallback = Array.from(row.children).filter(
        (child) => child.tagName !== "SCRIPT" && !isSpacerElement(child)
      );
      return fallback.map((element) => ({
        element,
        text: readHeaderText(element),
        colSpan: Number(element.getAttribute("colspan") ?? 1),
        rowSpan: Number(element.getAttribute("rowspan") ?? 1)
      }));
    }
    return cells.map((element) => ({
      element,
      text: readHeaderText(element),
      colSpan: Number(element.getAttribute("colspan") ?? 1),
      rowSpan: Number(element.getAttribute("rowspan") ?? 1)
    }));
  }
  function expandHeaderGrid(headerRows, options = {}) {
    const numRows = headerRows.length;
    const grid = [];
    const occupied = Array.from({ length: numRows }, () => []);
    for (let rowIndex = 0; rowIndex < numRows; rowIndex += 1) {
      const cells = getHeaderCells(headerRows[rowIndex], options);
      let col = 0;
      for (const cell of cells) {
        while (occupied[rowIndex][col]) col += 1;
        for (let rowOffset = 0; rowOffset < cell.rowSpan; rowOffset += 1) {
          for (let colOffset = 0; colOffset < cell.colSpan; colOffset += 1) {
            const targetRow = rowIndex + rowOffset;
            const targetCol = col + colOffset;
            if (!grid[targetRow]) grid[targetRow] = [];
            grid[targetRow][targetCol] = cell;
            occupied[targetRow][targetCol] = true;
          }
        }
        col += cell.colSpan;
      }
    }
    const maxCols = Math.max(0, ...grid.map((row) => row?.length ?? 0));
    const leafRowIndex = numRows - 1;
    const columns = [];
    for (let col = 0; col < maxCols; col += 1) {
      const bottomCell = grid[leafRowIndex]?.[col];
      if (!bottomCell) continue;
      const keepEmptyLeaf = options.includeEmptyVarianceLeaves && isEmptyVarianceLeaf(bottomCell) || Boolean(options.includeEmptyParentedLeaves);
      if (!bottomCell.text && !keepEmptyLeaf) {
        continue;
      }
      if (col > 0 && grid[leafRowIndex]?.[col - 1] === bottomCell) continue;
      const parts = [];
      for (let rowIndex = 0; rowIndex < numRows; rowIndex += 1) {
        const cell = grid[rowIndex]?.[col];
        if (!cell?.text) continue;
        if (parts[parts.length - 1] !== cell.text) {
          parts.push(cell.text);
        }
      }
      if (parts.length === 0) continue;
      columns.push({ parts, bottomCell });
    }
    return columns;
  }
  function getSingleRowHeaderLabels(headerRow, options = {}) {
    return getHeaderCells(headerRow, options).flatMap(
      (cell) => Array.from({ length: Math.max(1, cell.colSpan) }, () => cell.text || "column")
    );
  }

  // src/core/flatten-headers.ts
  function pushDefaultColumn(columns, parts) {
    const leaf = parts[parts.length - 1] ?? "column";
    const groups = parts.length > 1 ? parts.slice(0, -1) : [];
    const label = buildColumnNameFromParts(parts);
    columns.push({
      id: makeColumnId(label, columns.length),
      label,
      groups: groups.length > 0 ? groups : void 0,
      group: groups[groups.length - 1],
      leaf
    });
  }
  function applyQualifiers(rawParts, bottomCell, headerRows, qualifiers, docContext, state) {
    let parts = [...rawParts];
    const ctx = {
      headerRows,
      parts,
      bottomCell,
      docContext,
      state
    };
    for (const qualifier of qualifiers) {
      if (qualifier.qualifyParts) {
        parts = qualifier.qualifyParts(parts, { ...ctx, parts });
        ctx.parts = parts;
      }
    }
    for (const qualifier of qualifiers) {
      if (qualifier.expandColumn) {
        const expanded = qualifier.expandColumn({ ...ctx, parts });
        if (expanded) return expanded;
      }
    }
    const columns = [];
    pushDefaultColumn(columns, parts);
    return columns;
  }
  function flattenExpandedColumns(headerRows, expanded, options) {
    const columns = [];
    const docContext = options.context ?? {};
    const state = options.createState?.();
    for (const { parts: rawParts, bottomCell } of expanded) {
      if (options.prepareColumnState && state !== void 0) {
        options.prepareColumnState({ parts: rawParts, state });
      }
      const produced = applyQualifiers(
        rawParts,
        bottomCell,
        headerRows,
        options.variant.qualifiers,
        docContext,
        state
      );
      columns.push(...produced);
    }
    return dedupeColumnLabels(columns);
  }
  function flattenHeaders(headerRows, options) {
    if (headerRows.length === 0) return [];
    if (headerRows.length === 1) {
      const labels = getSingleRowHeaderLabels(headerRows[0], {
        cleanHeaderText: options.cleanHeaderText
      });
      return dedupeColumnLabels(
        labels.map((label, index) => ({
          id: makeColumnId(buildColumnNameFromParts([label]), index),
          label: buildColumnNameFromParts([label]),
          leaf: label
        }))
      );
    }
    return flattenExpandedColumns(
      headerRows,
      expandHeaderGrid(headerRows, {
        includeEmptyVarianceLeaves: options.variant.includeEmptyVarianceLeaves ?? false,
        includeEmptyParentedLeaves: options.variant.includeEmptyParentedLeaves ?? false,
        cleanHeaderText: options.cleanHeaderText
      }),
      options
    );
  }

  // src/core/parse-rows.ts
  function getRowCells(row) {
    const directCells = Array.from(row.children).filter(
      (child) => child.tagName === "TD" || child.tagName === "TH"
    );
    if (directCells.length > 0) return directCells;
    return Array.from(
      row.querySelectorAll(':scope > [role="cell"], :scope > [role="gridcell"], :scope > td')
    );
  }
  function extractGenericCellValue(cell) {
    return normalizeText(cell.textContent ?? "");
  }
  function parseRowCells(cellElements, columns) {
    const cells = [];
    for (let colIndex = 0; colIndex < columns.length; colIndex += 1) {
      const domCell = cellElements[colIndex];
      cells.push({ raw: domCell ? extractGenericCellValue(domCell) : "" });
    }
    return cells;
  }
  function rowKey(firstCell, rowIndex) {
    const text = normalizeText(firstCell.raw);
    if (text) return text;
    return `row-${rowIndex}`;
  }
  function parseRow(row, columns, rowIndex, options) {
    const isFooterRow = row.closest("tfoot") !== null;
    if (isFooterRow && !options.includeSummaryRows) {
      return null;
    }
    const cellElements = getRowCells(row);
    if (cellElements.length === 0) return null;
    const cells = parseRowCells(cellElements, columns);
    const firstCellText = cells[0]?.raw ?? "";
    const isSummary = looksLikeSummaryRow(firstCellText, row);
    if (isSummary && !options.includeSummaryRows) {
      return null;
    }
    if (!looksLikeDate(firstCellText) && !isSummary) {
      return null;
    }
    return {
      key: rowKey(cells[0], rowIndex),
      isSummary,
      cells
    };
  }
  function getDataRows(container, headerRows) {
    const headerSet = new Set(headerRows);
    const tbody = container.querySelector(":scope > tbody") ?? container;
    return Array.from(tbody.querySelectorAll(":scope > tr")).filter((row) => {
      if (headerSet.has(row)) return false;
      return getRowCells(row).length > 0;
    });
  }
  function alignCellsToColumns(cells, columns) {
    if (cells.length === columns.length) return cells;
    if (cells.length < columns.length) {
      return [...cells, ...Array.from({ length: columns.length - cells.length }, () => ({ raw: "" }))];
    }
    return cells.slice(0, columns.length);
  }

  // src/core/scroll-collect.ts
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
  function collectVisibleRows(bodyContainer, headerRows, columns, seen, options, rowParser) {
    const rows = rowParser.getDataRows(bodyContainer, headerRows);
    rows.forEach((row, index) => {
      const parsed = rowParser.parseRow(row, columns, index, options);
      if (!parsed) return;
      if (!seen.has(parsed.key)) {
        seen.set(parsed.key, parsed);
      }
    });
  }
  async function collectAllRows(bodyContainer, headerRows, columns, scrollContainer, options, rowParser = {
    parseRow,
    getDataRows
  }) {
    const seen = /* @__PURE__ */ new Map();
    const shouldScroll = (options.collectAllRows ?? true) && scrollContainer !== null;
    if (!shouldScroll) {
      collectVisibleRows(bodyContainer, headerRows, columns, seen, options, rowParser);
      return Array.from(seen.values());
    }
    const originalScrollTop = scrollContainer.scrollTop;
    let previousSize = -1;
    let stagnantPasses = 0;
    scrollContainer.scrollTop = 0;
    await sleep(50);
    while (stagnantPasses < 2) {
      collectVisibleRows(bodyContainer, headerRows, columns, seen, options, rowParser);
      if (seen.size === previousSize) {
        stagnantPasses += 1;
      } else {
        stagnantPasses = 0;
        previousSize = seen.size;
      }
      const nextTop = Math.min(
        scrollContainer.scrollTop + scrollContainer.clientHeight,
        scrollContainer.scrollHeight
      );
      if (nextTop === scrollContainer.scrollTop) {
        break;
      }
      scrollContainer.scrollTop = nextTop;
      await sleep(50);
    }
    scrollContainer.scrollTop = originalScrollTop;
    return Array.from(seen.values());
  }

  // src/core/pipeline.ts
  async function scrape(profile, doc = document, options = {}) {
    const detected = detectTable(doc, profile.tableDetection);
    if (!detected) {
      throw new Error(profile.messages.tableNotFound);
    }
    const variant = profile.resolveVariant(doc, detected);
    const context = profile.extractContext(doc, { view: profile.viewName, ...options });
    const columns = profile.flattenTableHeaders ? profile.flattenTableHeaders(detected.headerRows, { variant, context }) : flattenHeaders(detected.headerRows, {
      variant,
      context,
      createState: profile.createHeaderState
    });
    if (columns.length === 0) {
      throw new Error("Could not parse table headers.");
    }
    const rowParser = {
      parseRow: profile.parseRow ?? parseRow,
      getDataRows: profile.getDataRows ?? getDataRows
    };
    const rows = await collectAllRows(
      detected.bodyContainer,
      detected.headerRows,
      columns,
      detected.scrollContainer,
      options,
      rowParser
    );
    const alignedRows = rows.map((row) => ({
      ...row,
      cells: alignCellsToColumns(row.cells, columns)
    }));
    if (alignedRows.length === 0) {
      throw new Error("No data rows found in the table.");
    }
    if (!context.dateRangeStart || !context.dateRangeEnd) {
      const derived = deriveDateRangeFromRows(alignedRows);
      if (!context.dateRangeStart && derived.start) {
        context.dateRangeStart = derived.start;
      }
      if (!context.dateRangeEnd && derived.end) {
        context.dateRangeEnd = derived.end;
      }
    }
    const metadata = profile.enrichMetadata ? profile.enrichMetadata(context, columns) : context;
    return {
      columns,
      rows: alignedRows,
      metadata
    };
  }

  // src/adapters/lighthouse/context/view-context.ts
  function cleanDropdownText(text) {
    const normalized = normalizeText(text ?? "");
    return normalized || void 0;
  }
  function readDropdownSelectedValue(dropdown) {
    if (!dropdown) return void 0;
    const selected = dropdown.querySelector("li.selected");
    if (selected) {
      return cleanDropdownText(selected.textContent);
    }
    return void 0;
  }
  function readPickerPanelSelection(container) {
    if (!container) return void 0;
    const selectedRow = Array.from(container.querySelectorAll("div")).find((element) => {
      const className = element.className ?? "";
      return className.includes("edfaff") && element.querySelector(".truncate");
    });
    const label = selectedRow?.querySelector(".truncate[title]") ?? selectedRow?.querySelector(".truncate");
    return cleanDropdownText(label?.getAttribute("title") ?? label?.textContent);
  }
  function readPickerButtonValue(container) {
    const button = container?.querySelector("button.jw-button");
    return cleanDropdownText(button?.textContent);
  }
  function readDatePickerValue(picker) {
    const input = picker.querySelector("input");
    const inputValue = input?.value?.trim() || input?.getAttribute("value")?.trim();
    if (inputValue) return inputValue;
    const start = picker.getAttribute("start")?.trim();
    if (!start) return void 0;
    const [year, month, day] = start.split("-");
    if (!year || !month || !day) return start;
    return `${month}/${day}/${year}`;
  }
  function readTableDateValue(doc, mode) {
    const picker = doc.querySelector(`date-picker[mode="${mode}"]`);
    if (!picker) return void 0;
    return readDatePickerValue(picker);
  }
  function isoAttrToDisplayDate(iso) {
    if (!iso) return void 0;
    const trimmed = iso.trim();
    const isoMatch = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!isoMatch) return trimmed;
    const [, year, month, day] = isoMatch;
    return `${month}/${day}/${year}`;
  }
  function readTableDateRange(doc = document) {
    const picker = doc.querySelector("th.date-col date-picker[start][end]") ?? doc.querySelector(".sub-head date-picker[start][end]") ?? doc.querySelector("date-picker[start][end]:not([mode])");
    if (!picker) return {};
    return {
      start: isoAttrToDisplayDate(picker.getAttribute("start")),
      end: isoAttrToDisplayDate(picker.getAttribute("end"))
    };
  }
  function readUrlDateParam(doc, key) {
    const href = doc.defaultView?.location?.href ?? "";
    const match = href.match(new RegExp(`[?&]${key}=([^&]+)`));
    if (!match?.[1]) return void 0;
    const raw = decodeURIComponent(match[1]);
    const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!isoMatch) return raw;
    const [, year, month, day] = isoMatch;
    return `${month}/${day}/${year}`;
  }
  function readHotelId(doc) {
    const href = doc.defaultView?.location?.href ?? "";
    const match = href.match(/[?&]subscriptionId=(\d+)/);
    return match?.[1];
  }
  function readStlyPickupComparison(root, containerSelector) {
    const container = root.querySelector(containerSelector);
    if (!container) return void 0;
    const labels = Array.from(container.querySelectorAll("form label"));
    for (const label of labels) {
      const input = label.querySelector('input[type="radio"]');
      if (!input?.checked && !input?.hasAttribute("checked")) continue;
      const text = normalizeText(label.textContent ?? "");
      if (/pickup/i.test(text)) return "Pickup From";
      if (/stly/i.test(text)) return "STLY";
    }
    return void 0;
  }
  function readMarketSegmentComparison(root = document) {
    return readStlyPickupComparison(root, "#dbd-mkt-segment");
  }
  function readRatePlanComparison(root = document) {
    return readStlyPickupComparison(root, "#dbd-rp-plan");
  }
  function readLengthOfStayComparison(root = document) {
    return readStlyPickupComparison(root, "#dbd-los-los");
  }
  function readRoomTypeComparison(root = document) {
    return readStlyPickupComparison(root, "#dbd-rt-type");
  }
  function readLastYearStlyType(root = document) {
    const select = root.querySelector("#dbd-ly-stly select");
    return readSelectValue(select);
  }
  function readLastYearForecastType(root = document) {
    const select = root.querySelector("#dbd-ly-forecast select");
    return readSelectValue(select);
  }
  function readGroupRatesForecastType(root = document) {
    if (root.querySelector("#strategy-pricing")) return void 0;
    if (!root.querySelector("#dbd-ge-rates, #dbd-ge-forecast")) return void 0;
    return readSelectValue(root.querySelector("thead tr.sub-head th.mw-l select"));
  }
  function readSelectValue(select) {
    if (!select) return void 0;
    const selected = select.selectedOptions[0]?.textContent?.trim() || select.querySelector("option[selected]")?.textContent?.trim() || select.options[select.selectedIndex]?.textContent?.trim();
    const normalized = normalizeText(selected ?? "");
    return normalized || void 0;
  }
  function readRatePlanSegment(root = document) {
    const select = root.querySelector("#dbd-rp-plan select");
    return readSelectValue(select);
  }
  function extractViewContext(doc = document, options = {}) {
    const dayByDayView = readDropdownSelectedValue(doc.querySelector("#day-by-day-view"));
    const hierarchy = readDropdownSelectedValue(doc.querySelector("#hierarchy-dropdown"));
    const exchangeRatePicker = doc.querySelector("#currency-variant-picker");
    const exchangeRateType = readPickerPanelSelection(exchangeRatePicker) ?? readPickerButtonValue(exchangeRatePicker);
    const currencyPicker = doc.querySelector("#spider-currency-picker");
    const currency = readPickerButtonValue(currencyPicker);
    const asOfDate = readTableDateValue(doc, "as-of") ?? readUrlDateParam(doc, "asof");
    const pickupFromDate = readTableDateValue(doc, "pickup") ?? readUrlDateParam(doc, "pickupFrom");
    const { start: dateRangeStart, end: dateRangeEnd } = readTableDateRange(doc);
    const marketSegmentComparison = readMarketSegmentComparison(doc);
    const ratePlanComparison = readRatePlanComparison(doc);
    const ratePlanSegment = readRatePlanSegment(doc);
    const lengthOfStayComparison = readLengthOfStayComparison(doc);
    const roomTypeComparison = readRoomTypeComparison(doc);
    const lastYearStlyType = readLastYearStlyType(doc);
    const lastYearForecastType = readLastYearForecastType(doc);
    const groupRatesForecastType = readGroupRatesForecastType(doc);
    const propertyName = doc.querySelector('[class*="property"] select option:checked')?.textContent?.trim() || Array.from(doc.querySelectorAll("select option:checked")).map((option) => option.textContent?.trim() ?? "").find((text) => /[A-Z]{3,}/.test(text) && text.includes("-")) || void 0;
    return {
      exportedAt: options.exportedAt,
      asOfDate,
      pickupFromDate,
      dateRangeStart,
      dateRangeEnd,
      marketSegmentComparison,
      ratePlanComparison,
      ratePlanSegment,
      lengthOfStayComparison,
      roomTypeComparison,
      lastYearStlyType,
      lastYearForecastType,
      groupRatesForecastType,
      dayByDayView,
      hierarchy,
      exchangeRateType,
      currency,
      propertyName,
      hotelId: readHotelId(doc),
      view: options.view
    };
  }

  // src/adapters/lighthouse/detect-table.ts
  function normalizeText2(value) {
    return value.replace(/\s+/g, " ").trim();
  }
  function rowLooksLikeHeader2(row, headerMarkers) {
    const text = normalizeText2(row.textContent ?? "");
    return headerMarkers.some((marker) => text.includes(marker));
  }
  function getRows2(container) {
    const ariaRows = Array.from(container.querySelectorAll(':scope > [role="row"]'));
    if (ariaRows.length > 0) return ariaRows;
    const theadRows = Array.from(container.querySelectorAll(":scope > thead > tr"));
    if (theadRows.length > 0) return theadRows;
    const tbodyRows = Array.from(container.querySelectorAll(":scope > tbody > tr"));
    if (tbodyRows.length > 0) return tbodyRows;
    const directRows = Array.from(container.querySelectorAll(":scope > tr"));
    if (directRows.length > 0) return directRows;
    return [];
  }
  function findLighthouseHeaderRows(root, headerMarkers) {
    const thead = root.querySelector("thead");
    if (thead) {
      const rows = Array.from(thead.querySelectorAll(":scope > tr"));
      const structural = [];
      for (const row of rows) {
        const className = row.className?.toString() ?? "";
        if (structural.length > 0 && className.includes("main-head") && !className.includes("sub")) {
          break;
        }
        const isMainHead = className.includes("main-head");
        const isMidHead = className.includes("mid-head");
        const isSub2Head = className.includes("sub2-head");
        const isFirstSubHead = className.includes("sub-head") && !structural.some((existing) => existing.className.includes("sub-head"));
        if (isMainHead || isMidHead || isSub2Head || isFirstSubHead) {
          structural.push(row);
          continue;
        }
        if (structural.length > 0) {
          break;
        }
      }
      if (structural.length >= 2) {
        return structural.slice(0, 3);
      }
    }
    const mainHead = root.querySelector("thead tr.main-head, tr.main-head");
    const subHead = root.querySelector("thead tr.sub-head, tr.sub-head");
    if (mainHead && subHead) {
      return [mainHead, subHead];
    }
    const explicitHeader = root.querySelector(
      '[role="rowgroup"][aria-label*="header"], thead, [class*="header-row"], [data-testid*="header"]'
    );
    if (explicitHeader) {
      const rows = getRows2(explicitHeader);
      if (rows.length > 0) return rows.slice(0, 2);
    }
    const allRows = getRows2(root);
    const headerRows = allRows.filter((row) => rowLooksLikeHeader2(row, headerMarkers));
    if (headerRows.length >= 1) {
      return headerRows.slice(0, 2);
    }
    return allRows.slice(0, 2);
  }

  // src/adapters/lighthouse/pivot-provenance.ts
  var PIVOT_LABEL_PREFIXES = [
    { prefix: "rate_shop_", section: "rate_shop" },
    { prefix: "no_rate_shop_setup_", section: "rate_shop" },
    { prefix: "rate_plan_", section: "rate_plan" },
    { prefix: "market_segment_", section: "market_segment" },
    { prefix: "length_of_stay_", section: "length_of_stay" },
    { prefix: "room_type_", section: "room_type" }
  ];
  function detectPivotSection(column) {
    if ("rateShopPart" in column && column.rateShopPart) return "rate_shop";
    for (const entry of PIVOT_LABEL_PREFIXES) {
      if (column.label.startsWith(entry.prefix)) {
        return entry.section;
      }
    }
    return void 0;
  }
  function parentGroupsForColumn(column, section) {
    const groups = column.groups ?? [];
    if (groups.length === 0) return [];
    switch (section) {
      case "rate_shop":
        return groups.length >= 2 ? groups.slice(0, -1) : groups;
      case "rate_plan":
        return groups.length >= 2 ? groups.slice(0, 2) : groups;
      case "market_segment":
      case "length_of_stay":
      case "room_type":
        return groups.slice(0, 1);
    }
  }
  function commonPrefix(groups) {
    if (groups.length === 0) return [];
    const [first, ...rest] = groups;
    const shared = [];
    for (let index = 0; index < first.length; index += 1) {
      const value = first[index];
      if (rest.every((group) => group[index] === value)) {
        shared.push(value);
        continue;
      }
      break;
    }
    return shared;
  }
  function formatParentGroup(groups) {
    return groups.join(" > ");
  }
  function entityGroupForColumn(column, section) {
    const groups = column.groups ?? [];
    if (groups.length === 0) return void 0;
    switch (section) {
      case "rate_shop":
        return groups.length >= 2 ? groups[groups.length - 1] : void 0;
      case "rate_plan":
        return groups.length >= 3 ? groups[2] : void 0;
      case "market_segment":
      case "length_of_stay":
      case "room_type":
        return groups.length >= 2 ? groups[1] : void 0;
    }
  }
  function buildPivotEntityLabels(columns) {
    const labels = {};
    for (const column of columns) {
      const section = detectPivotSection(column);
      if (!section) continue;
      const entityGroup = entityGroupForColumn(column, section);
      if (!entityGroup) continue;
      const entitySlug = entitySlugFromDisplayLabel(entityGroup);
      if (!entitySlug || labels[entitySlug]) continue;
      labels[entitySlug] = entityGroup.trim();
    }
    return labels;
  }
  function extractStrategyTypeFromParentGroups(groups) {
    for (const group of groups) {
      const open = group.indexOf("(");
      const close = group.lastIndexOf(")");
      if (open === -1 || close <= open) continue;
      const parts = group.slice(open + 1, close).split(",").map((part) => part.trim()).filter(Boolean);
      if (parts.length >= 2) {
        return parts[1];
      }
    }
    return void 0;
  }
  function buildPivotProvenance(columns) {
    const parentGroupsByColumn = columns.map((column) => {
      const section = detectPivotSection(column);
      if (!section) return void 0;
      return parentGroupsForColumn(column, section);
    }).filter((groups) => groups !== void 0 && groups.length > 0);
    if (parentGroupsByColumn.length === 0) {
      return {};
    }
    const sharedParentGroups = commonPrefix(parentGroupsByColumn);
    if (sharedParentGroups.length === 0) {
      return {};
    }
    const strategyType = extractStrategyTypeFromParentGroups(sharedParentGroups);
    const pivotEntityLabels = buildPivotEntityLabels(columns);
    const serializedEntityLabels = Object.keys(pivotEntityLabels).length > 0 ? JSON.stringify(pivotEntityLabels) : void 0;
    return {
      pivotSection: sharedParentGroups[0],
      pivotParentGroup: formatParentGroup(sharedParentGroups),
      pivotParentGroupSlug: toBigQueryColumnName(sharedParentGroups),
      ...strategyType ? { strategyType } : {},
      ...serializedEntityLabels ? { pivotEntityLabels: serializedEntityLabels } : {}
    };
  }

  // src/adapters/lighthouse/enrich-metadata.ts
  function enrichLighthouseMetadata(metadata, columns) {
    return {
      ...metadata,
      ...buildPivotProvenance(columns)
    };
  }

  // src/adapters/lighthouse/dom/header-select.ts
  function getSelectSelectedLabel(select) {
    if (select.selectedOptions.length > 0) {
      return normalizeText(select.selectedOptions[0].textContent ?? "");
    }
    if (select.selectedIndex >= 0 && select.options[select.selectedIndex]) {
      return normalizeText(select.options[select.selectedIndex].textContent ?? "");
    }
    const explicit = select.querySelector("option[selected]");
    if (explicit) {
      return normalizeText(explicit.textContent ?? "");
    }
    const valueMatch = Array.from(select.options).find(
      (option) => option.value === select.value && option.value !== ""
    );
    if (valueMatch) {
      return normalizeText(valueMatch.textContent ?? "");
    }
    return "";
  }
  function getHeaderSuffixWithoutSelect(element) {
    const clone = element.cloneNode(true);
    clone.querySelectorAll(
      "select, date-picker, img, .toggle, .refresh-container > div, [data-selected-label], .select-selected, .select-value, .dropdown-toggle, .current, .custom-select-display"
    ).forEach((node) => {
      node.remove();
    });
    return normalizeText(clone.textContent ?? "");
  }
  function readVisibleSelectMirror(element, select) {
    const selectors = [
      "[data-selected-label]",
      ".select-selected",
      ".select-value",
      ".dropdown-toggle",
      ".current",
      ".custom-select-display"
    ];
    const scopes = [select.parentElement, element].filter((scope) => scope !== null);
    for (const scope of scopes) {
      for (const selector of selectors) {
        const mirror = scope.querySelector(selector);
        if (!mirror || mirror === select || mirror.contains(select)) continue;
        const text = normalizeText(mirror.textContent ?? "");
        if (text && text.length <= 24) return text;
      }
    }
    return "";
  }
  function readDropdownHeaderLabel(element) {
    const select = element.querySelector("select");
    if (!select) return null;
    const selectedLabel = readVisibleSelectMirror(element, select) || getSelectSelectedLabel(select);
    const suffix = getHeaderSuffixWithoutSelect(element);
    const label = normalizeText([selectedLabel, suffix].filter(Boolean).join(" "));
    return label || null;
  }

  // src/adapters/lighthouse/dom/spider-cells.ts
  var DIRECT_CELL_VALUE_SELECTOR = ":scope > .text-value, :scope > span";
  function getDirectCellValues(cell) {
    return Array.from(cell.querySelectorAll(DIRECT_CELL_VALUE_SELECTOR)).map((child) => normalizeText(child.textContent ?? "")).filter(Boolean);
  }
  function cleanLighthouseHeaderText(element) {
    if (element.id === "dbd-mkt-segment") {
      return "Market Segment";
    }
    if (element.id === "dbd-rp-plan") {
      return "Rate Plan";
    }
    if (element.id === "dbd-los-los") {
      return "Length of Stay";
    }
    if (element.id === "dbd-rt-type") {
      return "Room Type";
    }
    if (element.id === "dbd-ly-last-year") {
      return "Last Year & VAR to LY";
    }
    if (element.id === "dbd-ly-stly") {
      const select = element.querySelector("select");
      const selected = select?.selectedOptions[0]?.textContent?.trim() || select?.options[select.selectedIndex]?.textContent?.trim() || "STLY";
      return `STLY & VAR to ${selected}`;
    }
    if (element.id === "dbd-ly-budget") {
      return "Budget & VAR to Budget";
    }
    if (element.id === "dbd-ly-forecast") {
      const select = element.querySelector("select");
      const selected = select?.selectedOptions[0]?.textContent?.trim() || select?.options[select.selectedIndex]?.textContent?.trim() || "BI";
      return `Forecast & VAR to ${selected} Forecast`;
    }
    if (element.id === "dbd-ge-rates") {
      return "Rates";
    }
    if (element.id === "dbd-ge-group") {
      return "Group";
    }
    if (element.id === "dbd-ge-events") {
      return "Events";
    }
    if (element.id === "dbd-ge-forecast") {
      return "Forecast";
    }
    if (element.id === "dbd-str-current") {
      return "Current Year";
    }
    if (element.id === "dbd-str-prior") {
      return "Prior Year";
    }
    if (element.id === "dbd-str-events") {
      return "Events";
    }
    const dropdownLabel = readDropdownHeaderLabel(element);
    if (dropdownLabel) return dropdownLabel;
    const emptyFallback = readEmptyHeaderFallback(element);
    const clone = element.cloneNode(true);
    clone.querySelectorAll(
      "date-picker, img, .toggle, .refresh-container > div, form, label, input, .inline-radio, .filter-value, .date-picker-icon-container"
    ).forEach((node) => {
      node.remove();
    });
    const visible = normalizeText(clone.textContent ?? "");
    const title = element.getAttribute("title");
    if (title) {
      const normalizedTitle = normalizeText(title);
      const visibleStem = visible.replace(/\.{3}$|…$/u, "").trim();
      if (/\.\.\.$|…$/u.test(visible.trim()) || visibleStem.length > 0 && normalizedTitle.length > visible.length && normalizedTitle.toLowerCase().startsWith(visibleStem.toLowerCase())) {
        return normalizedTitle;
      }
    }
    if (visible) return visible;
    if (emptyFallback) return emptyFallback;
    return cleanHeaderText(element);
  }
  function readEmptyHeaderFallback(element) {
    const aria = normalizeText(element.getAttribute("aria-label") ?? "");
    if (aria) return aria;
    for (const image of Array.from(element.querySelectorAll("img"))) {
      const alt = normalizeText(image.getAttribute("alt") ?? "");
      if (alt) return alt;
    }
    return normalizeText(element.getAttribute("title") ?? "");
  }
  function extractCellValue(cell) {
    if (isSpacerElement(cell)) return "";
    const textValue = cell.querySelector(
      ":scope > .data-bar-container .text-value, :scope > .text-value, :scope > span.text-value"
    );
    if (textValue) {
      return normalizeText(textValue.textContent ?? "");
    }
    const dataValue = cell.getAttribute("data-value");
    if (dataValue) {
      return normalizeText(dataValue);
    }
    const clone = cell.cloneNode(true);
    clone.querySelectorAll(
      ".breakdown-container, flexible-tooltip, .event-icons, date-picker, img, input, .breakdown"
    ).forEach((node) => node.remove());
    if (cell.classList.contains("date-col") || cell.classList.contains("common-date-td")) {
      const day = clone.childNodes[0]?.textContent?.trim() ?? "";
      const weekday = clone.querySelector(".black-text-500, .black-text-400")?.textContent?.trim() ?? "";
      return normalizeText([day, weekday].filter(Boolean).join(" "));
    }
    return normalizeText(clone.textContent ?? "");
  }
  function extractRateVariance(cell) {
    const values = getDirectCellValues(cell);
    if (values.length > 0) return values[0];
    return normalizeText(cell.textContent ?? "");
  }
  function isCombinedRateShopCell(cell) {
    return getDirectCellValues(cell).length >= 2;
  }
  function extractCombinedRateShopValues(cell) {
    const tokens = getDirectCellValues(cell);
    const rate = tokens.find((token) => /^\$[\d,]+(?:\.\d+)?$/.test(token)) ?? "";
    const change = tokens.find((token) => /^-?\$?[\d,]+(?:\.\d+)?$/.test(token) && token !== rate) ?? "";
    return { rate, change };
  }

  // src/adapters/lighthouse/types.ts
  function createLighthouseHeaderState() {
    return { metricByGroupKey: /* @__PURE__ */ new Map() };
  }

  // src/adapters/lighthouse/flatten-headers.ts
  function prepareLighthouseColumnState(parts, state, roomTypeBucketCounter) {
    const isRoomType = parts.length >= 3 && /^room type$/i.test(parts[0] ?? "");
    if (isRoomType && /^avail$/i.test(parts[parts.length - 1] ?? "")) {
      const nextCounter = roomTypeBucketCounter + 1;
      state.metricGroupKey = `${parts[0]}|${parts[1]}|${nextCounter}`;
      return nextCounter;
    }
    if (!isRoomType) {
      state.metricGroupKey = void 0;
    }
    return roomTypeBucketCounter;
  }
  function flattenLighthouseHeaders(headerRows, options) {
    let roomTypeBucketCounter = 0;
    return recoverEmptyPricingLeaves(
      flattenHeaders(headerRows, {
        ...options,
        cleanHeaderText: cleanLighthouseHeaderText,
        createState: createLighthouseHeaderState,
        prepareColumnState: ({ parts, state }) => {
          roomTypeBucketCounter = prepareLighthouseColumnState(
            parts,
            state,
            roomTypeBucketCounter
          );
        }
      })
    );
  }
  function recoverEmptyPricingLeaves(columns) {
    const renamed = columns.map((column, index) => {
      const previous = columns[index - 1]?.label;
      const next = columns[index + 1]?.label;
      if (column.label === "pricing_and_forecast" && previous === "pricing_and_forecast_r28_avg" && next === "pricing_and_forecast_optimal_bar") {
        return {
          ...column,
          label: "pricing_and_forecast_hurdle",
          leaf: "Hurdle"
        };
      }
      return column;
    });
    return insertMissingPricingHurdle(renamed);
  }
  function insertMissingPricingHurdle(columns) {
    if (columns.some((column) => column.label === "pricing_and_forecast_hurdle")) {
      return columns;
    }
    const result = [];
    for (let index = 0; index < columns.length; index += 1) {
      const column = columns[index];
      result.push(column);
      const next = columns[index + 1];
      if (column.label === "pricing_and_forecast_r28_avg" && next?.label === "pricing_and_forecast_optimal_bar") {
        result.push({
          id: makeColumnId("pricing_and_forecast_hurdle", result.length),
          label: "pricing_and_forecast_hurdle",
          group: "Pricing and Forecast",
          groups: ["Pricing and Forecast"],
          leaf: "Hurdle"
        });
      }
    }
    return result.length === columns.length ? columns : dedupeColumnLabels(result);
  }

  // src/adapters/lighthouse/export/filename.ts
  function resolveVariantSlug(metadata, variantId) {
    if (metadata.dayByDayView) {
      return slugifyFilenameSegment(metadata.dayByDayView);
    }
    if (variantId) return variantId;
    return "strategy";
  }
  function marketSegmentComparisonSlug(comparison) {
    if (!comparison) return void 0;
    if (/pickup/i.test(comparison)) return "pickup-from";
    if (/stly/i.test(comparison)) return "stly";
    return slugifyFilenameSegment(comparison);
  }
  function comparisonSlugForVariant(variant, metadata) {
    if (variant === "market-segments") {
      return marketSegmentComparisonSlug(metadata.marketSegmentComparison);
    }
    if (variant === "rate-plans") {
      return marketSegmentComparisonSlug(metadata.ratePlanComparison);
    }
    if (variant === "length-of-stay") {
      return marketSegmentComparisonSlug(metadata.lengthOfStayComparison);
    }
    if (variant === "room-type") {
      return marketSegmentComparisonSlug(metadata.roomTypeComparison);
    }
    return void 0;
  }
  function ratePlanSegmentSlug(segment) {
    if (!segment) return void 0;
    return slugifyFilenameSegment(segment);
  }
  function exportDateSlug(exportDate) {
    const iso = exportDate ?? (/* @__PURE__ */ new Date()).toISOString().slice(0, 10);
    return `export-${iso.replace(/-/g, "")}`;
  }
  function dateRangeSlug(start, end) {
    const startIso = parseDisplayDateToIso(start);
    const endIso = parseDisplayDateToIso(end);
    if (!startIso || !endIso) return void 0;
    return `range-${startIso}_${endIso}`;
  }
  function appendVariantSpecificParts(parts, variant, metadata) {
    if (variant === "market-segments" || variant === "rate-plans" || variant === "length-of-stay" || variant === "room-type") {
      const segment = variant === "rate-plans" ? ratePlanSegmentSlug(metadata.ratePlanSegment) : void 0;
      if (segment) parts.push(segment);
      const comparison = comparisonSlugForVariant(variant, metadata);
      if (comparison) parts.push(comparison);
    }
    if (variant === "last-year-and-forecast") {
      const stlyType = ratePlanSegmentSlug(metadata.lastYearStlyType);
      if (stlyType) parts.push(stlyType);
      const forecastType = ratePlanSegmentSlug(metadata.lastYearForecastType);
      if (forecastType) parts.push(forecastType);
    }
    if (variant === "group-and-events") {
      const forecastType = ratePlanSegmentSlug(metadata.groupRatesForecastType);
      if (forecastType) parts.push(forecastType);
    }
  }
  function buildExportBasename(options) {
    const { metadata, profileSlug = "day-by-day", variantId, exportDate } = options;
    const variant = resolveVariantSlug(metadata, variantId);
    const hotelId = metadata.hotelId ?? "property";
    const parts = ["lh", hotelId];
    if (metadata.propertyName) {
      parts.push(slugifyFilenameSegment(metadata.propertyName, 30));
    }
    parts.push(profileSlug, variant);
    if (metadata.hierarchy) {
      parts.push(slugifyFilenameSegment(metadata.hierarchy));
    }
    if (metadata.exchangeRateType) {
      parts.push(slugifyFilenameSegment(metadata.exchangeRateType));
    }
    const range = dateRangeSlug(metadata.dateRangeStart, metadata.dateRangeEnd);
    if (range) parts.push(range);
    const asOfIso = parseDisplayDateToIso(metadata.asOfDate);
    if (asOfIso) parts.push(`asof-${asOfIso}`);
    const pickupIso = parseDisplayDateToIso(metadata.pickupFromDate);
    if (pickupIso) parts.push(`pickup-${pickupIso}`);
    appendVariantSpecificParts(parts, variant, metadata);
    parts.push(exportDateSlug(exportDate));
    return parts.join("_");
  }
  function buildFilename(options) {
    return `${buildExportBasename(options)}.csv`;
  }

  // src/adapters/lighthouse/export/provenance.ts
  var PROVENANCE_FIELDS = [
    { key: "exportedAt" },
    { key: "asOfDate" },
    { key: "pickupFromDate" },
    { key: "dateRangeStart" },
    { key: "dateRangeEnd" },
    { key: "marketSegmentComparison" },
    { key: "ratePlanComparison" },
    { key: "ratePlanSegment" },
    { key: "lengthOfStayComparison" },
    { key: "roomTypeComparison" },
    { key: "lastYearStlyType" },
    { key: "lastYearForecastType" },
    { key: "groupRatesForecastType" },
    { key: "dayByDayView" },
    { key: "hierarchy" },
    { key: "exchangeRateType" },
    { key: "currency" },
    { key: "propertyName" },
    { key: "hotelId" },
    { key: "view" },
    { key: "pivotSection" },
    { key: "pivotParentGroup" },
    { key: "pivotParentGroupSlug" },
    { key: "strategyType" },
    { key: "pivotEntityLabels" }
  ];
  function getProvenanceHeader(key) {
    return provenanceColumnName(key);
  }
  function getProvenanceHeaders() {
    return PROVENANCE_FIELDS.map((field) => getProvenanceHeader(field.key));
  }
  function getProvenanceValues(metadata = {}) {
    return PROVENANCE_FIELDS.map((field) => metadata[field.key] ?? "");
  }
  function serializeLighthouseProvenance(metadata = {}) {
    return {
      headers: getProvenanceHeaders(),
      values: getProvenanceValues(metadata)
    };
  }

  // src/adapters/lighthouse/parse-rows.ts
  function getRateShopPart(column) {
    if ("rateShopPart" in column) {
      return column.rateShopPart;
    }
    return void 0;
  }
  function getRowCells2(row) {
    const directCells = Array.from(row.children).filter(
      (child) => (child.tagName === "TD" || child.tagName === "TH") && !isSpacerElement(child)
    );
    if (directCells.length > 0) return directCells;
    return Array.from(
      row.querySelectorAll(':scope > [role="cell"], :scope > [role="gridcell"], :scope > td')
    ).filter((cell) => !isSpacerElement(cell));
  }
  function parseRowCells2(cellElements, columns, options) {
    const cells = [];
    let domIndex = 0;
    for (let colIndex = 0; colIndex < columns.length; colIndex += 1) {
      const column = columns[colIndex];
      const domCell = cellElements[domIndex];
      if (!domCell) {
        cells.push({ raw: "" });
        continue;
      }
      const rateShopPart = getRateShopPart(column);
      if (rateShopPart === "rate") {
        const changeColumn = columns[colIndex + 1];
        const pairedChange = getRateShopPart(changeColumn) === "change" && changeColumn?.leaf === column.leaf;
        if (pairedChange && (options.splitRateShopValues ?? true) && isCombinedRateShopCell(domCell)) {
          const combined = extractCombinedRateShopValues(domCell);
          cells.push({ raw: combined.rate });
          cells.push({ raw: combined.change });
          colIndex += 1;
          domIndex += 1;
          continue;
        }
        cells.push({ raw: extractCellValue(domCell) });
        domIndex += 1;
        continue;
      }
      if (rateShopPart === "change") {
        cells.push({ raw: extractRateVariance(domCell) });
        domIndex += 1;
        continue;
      }
      cells.push({ raw: extractCellValue(domCell) });
      domIndex += 1;
    }
    return cells;
  }
  function rowKey2(firstCell, rowIndex) {
    const text = normalizeText(firstCell.raw);
    if (text) return text;
    return `row-${rowIndex}`;
  }
  function parseLighthouseRow(row, columns, rowIndex, options) {
    const isFooterRow = row.closest("tfoot") !== null || row.classList.contains("main-foot");
    if (isFooterRow && !options.includeSummaryRows) {
      return null;
    }
    const cellElements = getRowCells2(row);
    if (cellElements.length === 0) return null;
    const cells = parseRowCells2(cellElements, columns, options);
    const firstCellText = cells[0]?.raw ?? "";
    const isSummary = looksLikeSummaryRow(firstCellText, row);
    if (isSummary && !options.includeSummaryRows) {
      return null;
    }
    if (!looksLikeDate(firstCellText) && !isSummary) {
      return null;
    }
    return {
      key: rowKey2(cells[0], rowIndex),
      isSummary,
      cells
    };
  }
  function getLighthouseDataRows(container, headerRows) {
    const headerSet = new Set(headerRows);
    const tbody = container.querySelector(":scope > tbody") ?? container;
    return Array.from(tbody.querySelectorAll(":scope > tr")).filter((row) => {
      if (headerSet.has(row)) return false;
      if (row.closest(".breakdown-container, .breakdown")) return false;
      if (row.classList.contains("main-foot")) return false;
      return getRowCells2(row).length > 0;
    });
  }

  // src/adapters/lighthouse/column-name.ts
  var GROUPED_HIERARCHIES = {
    "market-segment": {
      matches: (parts) => parts.length >= 3 && /market segment/i.test(parts[0] ?? ""),
      groupKey: (parts) => `${parts[0]}|${parts[1]}`
    },
    "rate-plan": {
      matches: (parts) => parts.length >= 3 && /^rate plan$/i.test(parts[0] ?? ""),
      groupKey: (parts) => parts.length >= 4 ? `${parts[0]}|${parts[1]}|${parts[2]}` : `${parts[0]}|${parts[1]}`
    },
    "length-of-stay": {
      matches: (parts) => parts.length >= 3 && /^length of stay$/i.test(parts[0] ?? ""),
      groupKey: (parts) => `${parts[0]}|${parts[1]}`
    },
    "room-type": {
      matches: (parts) => parts.length >= 3 && /^room type$/i.test(parts[0] ?? ""),
      groupKey: (parts, metricGroupKey) => metricGroupKey ?? `${parts[0]}|${parts[1]}`
    }
  };
  function segmentComparisonSuffix(comparison) {
    return comparison === "Pickup From" ? "Pickup_From" : "STLY";
  }
  function isComparisonLeaf(leaf, comparison) {
    if (/^stly$/i.test(leaf)) return true;
    return comparison === "Pickup From" && /^pickup$/i.test(leaf);
  }
  function qualifyGroupedMetricParts(parts, previousMetricInGroup, comparison, matchesHierarchy) {
    const leaf = parts[parts.length - 1]?.trim() ?? "";
    if (matchesHierarchy(parts) && previousMetricInGroup && isComparisonLeaf(leaf, comparison) && !/^stly$/i.test(previousMetricInGroup)) {
      return [
        ...parts.slice(0, -1),
        `${previousMetricInGroup}_${segmentComparisonSuffix(comparison)}`
      ];
    }
    return [...parts];
  }
  function qualifyForKind(kind, parts, previousMetric, comparison = "STLY") {
    const def = GROUPED_HIERARCHIES[kind];
    return qualifyGroupedMetricParts(parts, previousMetric, comparison, def.matches);
  }
  function getGroupKeyForKind(kind, parts, metricGroupKey) {
    const def = GROUPED_HIERARCHIES[kind];
    if (!def.matches(parts)) return void 0;
    return def.groupKey(parts, metricGroupKey);
  }
  function isAmbiguousComparisonLeaf(parts, kind, comparison = "STLY") {
    const def = GROUPED_HIERARCHIES[kind];
    const leaf = parts[parts.length - 1]?.trim() ?? "";
    if (!def.matches(parts)) return false;
    return isComparisonLeaf(leaf, comparison);
  }
  function isBareRatePlanColumn(parts) {
    return parts.length === 3 && /^rate plan$/i.test(parts[0] ?? "");
  }

  // src/adapters/lighthouse/qualifiers/grouped-comparison-qualifier.ts
  function resolveComparison(ctx, comparisonKey, readComparison) {
    const fromContext = ctx.docContext[comparisonKey];
    if (fromContext) return fromContext;
    for (const row of ctx.headerRows) {
      const mode = readComparison(row);
      if (mode) return mode;
    }
    return "STLY";
  }
  function createGroupedComparisonQualifier(config) {
    return {
      id: config.id,
      qualifyParts(parts, ctx) {
        const prepared = config.prepareParts?.(parts, ctx) ?? parts;
        const groupKey = getGroupKeyForKind(
          config.hierarchyKind,
          prepared,
          ctx.state.metricGroupKey
        );
        const comparison = resolveComparison(ctx, config.comparisonKey, config.readComparison);
        const previousMetric = groupKey ? ctx.state.metricByGroupKey.get(groupKey) : void 0;
        const qualified = qualifyForKind(config.hierarchyKind, prepared, previousMetric, comparison);
        if (groupKey && !isAmbiguousComparisonLeaf(prepared, config.hierarchyKind, comparison)) {
          ctx.state.metricByGroupKey.set(groupKey, prepared[prepared.length - 1] ?? "");
        }
        return qualified;
      }
    };
  }

  // src/adapters/lighthouse/qualifiers/grouped-comparison-qualifiers.ts
  function injectRatePlanSegment(parts, ctx) {
    if (!isBareRatePlanColumn(parts)) return parts;
    const segment = ctx.docContext.ratePlanSegment;
    if (!segment) return parts;
    return [parts[0], segment, ...parts.slice(1)];
  }
  var marketSegmentQualifier = createGroupedComparisonQualifier({
    id: "market-segment",
    hierarchyKind: "market-segment",
    comparisonKey: "marketSegmentComparison",
    readComparison: readMarketSegmentComparison
  });
  var ratePlanQualifier = createGroupedComparisonQualifier({
    id: "rate-plan",
    hierarchyKind: "rate-plan",
    comparisonKey: "ratePlanComparison",
    readComparison: readRatePlanComparison,
    prepareParts: injectRatePlanSegment
  });
  var lengthOfStayQualifier = createGroupedComparisonQualifier({
    id: "length-of-stay",
    hierarchyKind: "length-of-stay",
    comparisonKey: "lengthOfStayComparison",
    readComparison: readLengthOfStayComparison
  });
  var roomTypeQualifier = createGroupedComparisonQualifier({
    id: "room-type",
    hierarchyKind: "room-type",
    comparisonKey: "roomTypeComparison",
    readComparison: readRoomTypeComparison
  });

  // src/adapters/lighthouse/profiles/day-by-day/market-segments.ts
  var marketSegmentsVariant = {
    id: "market-segments",
    qualifiers: [marketSegmentQualifier]
  };

  // src/adapters/lighthouse/profiles/day-by-day/rate-plans.ts
  var ratePlansVariant = {
    id: "rate-plans",
    qualifiers: [ratePlanQualifier]
  };

  // src/adapters/lighthouse/profiles/day-by-day/length-of-stay.ts
  var lengthOfStayVariant = {
    id: "length-of-stay",
    qualifiers: [lengthOfStayQualifier]
  };

  // src/adapters/lighthouse/profiles/day-by-day/room-type.ts
  var roomTypeVariant = {
    id: "room-type",
    qualifiers: [roomTypeQualifier]
  };

  // src/adapters/lighthouse/qualifiers/last-year-forecast.ts
  var LAST_YEAR_SECTIONS = [
    /^last year & var to ly$/i,
    /^stly & var to /i,
    /^budget & var to budget$/i,
    /^forecast & var to /i
  ];
  function isLastYearSection(section) {
    return LAST_YEAR_SECTIONS.some((pattern) => pattern.test(section.trim()));
  }
  function varianceLeafForSection(section) {
    if (/^last year & var to ly$/i.test(section)) return "VAR to LY";
    if (/^stly & var to /i.test(section)) return "VAR to STLY";
    if (/^budget & var to budget$/i.test(section)) return "VAR to Budget";
    if (/^forecast & var to /i.test(section)) return "VAR to Forecast";
    return "VAR";
  }
  var lastYearForecastQualifier = {
    id: "last-year-and-forecast",
    qualifyParts(parts, ctx) {
      const section = parts[0]?.trim() ?? "";
      if (!isLastYearSection(section)) return parts;
      if (parts.length === 1) {
        const previousMetric = ctx.state.metricByGroupKey.get(section);
        if (!previousMetric) return parts;
        return [section, previousMetric, varianceLeafForSection(section)];
      }
      const leaf = parts[parts.length - 1]?.trim() ?? "";
      if (leaf && !/^var to /i.test(leaf)) {
        ctx.state.metricByGroupKey.set(section, leaf);
      }
      return parts;
    }
  };

  // src/adapters/lighthouse/profiles/day-by-day/last-year-and-forecast.ts
  var lastYearForecastVariant = {
    id: "last-year-and-forecast",
    qualifiers: [lastYearForecastQualifier],
    includeEmptyVarianceLeaves: true
  };

  // src/adapters/lighthouse/profiles/day-by-day/group-and-events.ts
  var groupAndEventsVariant = {
    id: "group-and-events",
    qualifiers: []
  };

  // src/adapters/lighthouse/profiles/day-by-day/str.ts
  var strVariant = {
    id: "str",
    qualifiers: []
  };

  // src/adapters/lighthouse/qualifiers/rate-shop.ts
  function isRateShopGroup(group) {
    if (!group) return false;
    return /rate shop|rate insight|no rate shop setup/i.test(group);
  }
  function isNotesColumn(text) {
    return /^notes$/i.test(text.trim());
  }
  function isRateShopCompetitorCell(cell, primaryGroup) {
    if (isNotesColumn(cell.text)) return false;
    if (cell.colSpan !== 2) return false;
    return cell.element.classList.contains("self") || cell.element.classList.contains("cell-divider-right") || cell.element.hasAttribute("title") || isRateShopGroup(primaryGroup);
  }
  function isCombinedRateShopCell2(cell, primaryGroup) {
    if (isNotesColumn(cell.text)) return false;
    if (cell.colSpan !== 1) return false;
    return isRateShopGroup(primaryGroup) || /hotel|inn|marriott|hampton|courtyard|hyatt|comp set/i.test(cell.text);
  }
  function pushColumn(columns, parts, extras = {}) {
    const leaf = extras.leaf ?? parts[parts.length - 1] ?? "column";
    const { leaf: _ignoredLeaf, ...restExtras } = extras;
    const groups = parts.length > 1 ? parts.slice(0, -1) : [];
    const label = buildColumnNameFromParts(parts);
    columns.push({
      id: makeColumnId(label, columns.length),
      label,
      groups: groups.length > 0 ? groups : void 0,
      group: groups[groups.length - 1],
      leaf,
      ...restExtras
    });
  }
  var rateShopQualifier = {
    id: "rate-shop",
    expandColumn(ctx) {
      const { parts, bottomCell } = ctx;
      const primaryGroup = parts.length > 1 ? parts[0] : void 0;
      const metric = parts[parts.length - 1] ?? "column";
      if (isRateShopCompetitorCell(bottomCell, primaryGroup) || isCombinedRateShopCell2(bottomCell, primaryGroup)) {
        const columns = [];
        pushColumn(columns, [...parts, "Rate"], { rateShopPart: "rate", leaf: metric });
        pushColumn(columns, [...parts, "Change"], { rateShopPart: "change", leaf: metric });
        return columns;
      }
      return null;
    }
  };

  // src/adapters/lighthouse/profiles/day-by-day/strategy.ts
  var strategyVariant = {
    id: "strategy",
    qualifiers: [rateShopQualifier],
    includeEmptyParentedLeaves: true
  };

  // src/adapters/lighthouse/profiles/day-by-day/resolve-variant.ts
  function resolveDayByDayVariant(doc, detected) {
    const context = extractViewContext(doc);
    if (context.dayByDayView === "Market segments") {
      return marketSegmentsVariant;
    }
    if (context.dayByDayView === "Rate plans") {
      return ratePlansVariant;
    }
    if (context.dayByDayView === "Length of stay") {
      return lengthOfStayVariant;
    }
    if (context.dayByDayView === "Room type") {
      return roomTypeVariant;
    }
    if (context.dayByDayView === "Last year & forecast") {
      return lastYearForecastVariant;
    }
    if (context.dayByDayView === "Group & events") {
      return groupAndEventsVariant;
    }
    if (context.dayByDayView === "STR") {
      return strVariant;
    }
    if (context.dayByDayView === "Strategy") {
      return strategyVariant;
    }
    const pathname = doc.defaultView?.location?.pathname ?? "";
    if (/\/market-segments/i.test(pathname)) {
      return marketSegmentsVariant;
    }
    if (/\/rate-plans/i.test(pathname)) {
      return ratePlansVariant;
    }
    if (/\/length-of-stay/i.test(pathname)) {
      return lengthOfStayVariant;
    }
    if (/\/room-type/i.test(pathname)) {
      return roomTypeVariant;
    }
    if (/\/last-year-and-forecast/i.test(pathname)) {
      return lastYearForecastVariant;
    }
    if (/\/group-and-events/i.test(pathname)) {
      return groupAndEventsVariant;
    }
    if (/\/str(?:\/|$|\?)/i.test(pathname)) {
      return strVariant;
    }
    if (doc.querySelector("#dbd-mkt-segment")) {
      return marketSegmentsVariant;
    }
    if (doc.querySelector("#dbd-rp-plan")) {
      return ratePlansVariant;
    }
    if (doc.querySelector("#dbd-los-los")) {
      return lengthOfStayVariant;
    }
    if (doc.querySelector("#dbd-rt-type")) {
      return roomTypeVariant;
    }
    if (doc.querySelector("#dbd-ly-last-year, #dbd-ly-stly, #dbd-ly-budget, #dbd-ly-forecast")) {
      return lastYearForecastVariant;
    }
    if (doc.querySelector("#dbd-ge-group, #dbd-ge-events, #dbd-ge-rates, #dbd-ge-forecast")) {
      return groupAndEventsVariant;
    }
    if (doc.querySelector("#dbd-str-current, #dbd-str-prior, #dbd-str-events")) {
      return strVariant;
    }
    if (detected.headerRows.length >= 3) {
      const hasMidHead = detected.headerRows.some((row) => row.className.includes("mid-head"));
      if (hasMidHead) {
        return marketSegmentsVariant;
      }
    }
    return strategyVariant;
  }

  // src/adapters/lighthouse/profiles/day-by-day/profile.ts
  var DAY_BY_DAY_MARKERS = [
    "As of Date",
    "On The Books",
    "Revenue",
    "Rate Shop",
    "No Rate Shop Setup",
    "Rate Plan",
    "Length of Stay",
    "Room Type",
    "Forecast",
    "Last Year",
    "VAR to LY",
    "Budget",
    "Group",
    "Events",
    "STR",
    "MPI",
    "ARI",
    "RGI"
  ];
  var dayByDayProfile = {
    id: "day-by-day",
    label: "Day by day",
    viewName: "Day by day",
    filenameSlug: "day-by-day",
    parentPathPattern: /\/day-by-day\//i,
    spiderPathPattern: /\/dashboards\/day-by-day\//i,
    parentContentScriptMatches: ["https://app.mylighthouse.com/hotel/*/day-by-day/*"],
    spiderContentScriptMatches: ["https://spider.kriyarevgen.com/dashboards/day-by-day/*"],
    spiderIframeSrcIncludes: ["spider.kriyarevgen.com", "day-by-day"],
    tableDetection: {
      preferredSelector: "table.analytics.day-by-day",
      headerMarkers: DAY_BY_DAY_MARKERS,
      urlPattern: /\/day-by-day\//i,
      findHeaderRows: findLighthouseHeaderRows
    },
    variants: [
      strategyVariant,
      marketSegmentsVariant,
      ratePlansVariant,
      lengthOfStayVariant,
      roomTypeVariant,
      lastYearForecastVariant,
      groupAndEventsVariant,
      strVariant
    ],
    resolveVariant: resolveDayByDayVariant,
    extractContext: (doc, options = {}) => {
      const context = extractViewContext(doc, options);
      const overrides = options;
      return {
        ...context,
        ...overrides.marketSegmentComparison ? { marketSegmentComparison: overrides.marketSegmentComparison } : {},
        ...overrides.ratePlanComparison ? { ratePlanComparison: overrides.ratePlanComparison } : {},
        ...overrides.lengthOfStayComparison ? { lengthOfStayComparison: overrides.lengthOfStayComparison } : {},
        ...overrides.roomTypeComparison ? { roomTypeComparison: overrides.roomTypeComparison } : {}
      };
    },
    enrichMetadata: enrichLighthouseMetadata,
    createHeaderState: createLighthouseHeaderState,
    flattenTableHeaders: flattenLighthouseHeaders,
    parseRow: parseLighthouseRow,
    getDataRows: getLighthouseDataRows,
    buildExportFilename: ({ metadata, variantId, exportDate }) => buildFilename({
      metadata,
      profileSlug: "day-by-day",
      variantId,
      exportDate
    }),
    serializeProvenance: serializeLighthouseProvenance,
    messages: {
      tableNotFound: "Day by day table not found. Open the Day by day tab and try again.",
      iframeLoading: "Day by day table is still loading. Wait a few seconds and try again."
    }
  };

  // src/adapters/profitsword/flatten-headers.ts
  var METRIC_LEAVES = ["amt", "pct_rev"];
  var PERIOD_COMPARISONS = [
    "actuals",
    "budget",
    "variance",
    "actuals_last_year",
    "variance_last_year"
  ];
  function buildMetricColumns(prefix) {
    const columns = [];
    for (const comparison of PERIOD_COMPARISONS) {
      for (const leaf of METRIC_LEAVES) {
        const parts = [prefix, comparison, leaf];
        const label = buildColumnNameFromParts(parts);
        columns.push({
          id: makeColumnId(label, columns.length),
          label,
          groups: [prefix, comparison],
          group: comparison,
          leaf
        });
      }
    }
    return columns;
  }
  function flattenPlSummaryHeaders() {
    const columns = [
      ...buildMetricColumns("period"),
      {
        id: makeColumnId("line_item", 10),
        label: "line_item",
        leaf: "line_item"
      },
      {
        id: makeColumnId("line_item_level", 11),
        label: "line_item_level",
        leaf: "line_item_level"
      },
      ...buildMetricColumns("ytd")
    ];
    return dedupeColumnLabels(columns);
  }
  var PL_SUMMARY_COLUMN_COUNT = flattenPlSummaryHeaders().length;

  // src/adapters/profitsword/profiles/room-stats/flatten-headers.ts
  var PRIMARY_FORECAST_METRICS = ["rooms", "occ_rooms", "occ_pct", "adr", "revpar", "revenue"];
  var COMPARISON_METRICS = ["occ_rooms", "occ_pct", "adr", "revpar", "revenue"];
  function buildSectionColumns(section, metrics) {
    return metrics.map((metric, index) => {
      const label = buildColumnNameFromParts([section, metric]);
      return {
        id: makeColumnId(label, index),
        label,
        groups: [section],
        group: section,
        leaf: metric
      };
    });
  }
  function flattenRoomStatsHeaders() {
    const columns = [
      {
        id: makeColumnId("date", 0),
        label: "date",
        leaf: "date"
      },
      ...buildSectionColumns("primary_forecast", PRIMARY_FORECAST_METRICS),
      ...buildSectionColumns("budget", COMPARISON_METRICS),
      ...buildSectionColumns("variance", COMPARISON_METRICS)
    ];
    return dedupeColumnLabels(columns);
  }
  var ROOM_STATS_COLUMN_COUNT = flattenRoomStatsHeaders().length;

  // src/browser/export-in-page.ts
  async function exportInPage(options = {}) {
    const exportedAt = (/* @__PURE__ */ new Date()).toISOString();
    const parsed = await scrape(dayByDayProfile, document, {
      splitRateShopValues: options.splitRateShopValues ?? true,
      includeSummaryRows: options.includeSummaryRows ?? false,
      collectAllRows: options.collectAllRows ?? true,
      marketSegmentComparison: options.marketSegmentComparison,
      ratePlanComparison: options.ratePlanComparison,
      lengthOfStayComparison: options.lengthOfStayComparison,
      roomTypeComparison: options.roomTypeComparison
    });
    parsed.metadata.exportedAt = exportedAt;
    parsed.metadata.view = dayByDayProfile.viewName;
    if (options.hotelId) {
      parsed.metadata.hotelId = options.hotelId;
    }
    const detected = detectTable(document, dayByDayProfile.tableDetection);
    const variant = detected ? dayByDayProfile.resolveVariant(document, detected) : void 0;
    const provenance = dayByDayProfile.serializeProvenance(parsed.metadata);
    const csv = toCsv(parsed.columns, parsed.rows, { provenance });
    const filename = dayByDayProfile.buildExportFilename({
      metadata: parsed.metadata,
      variantId: variant?.id
    });
    return {
      csv,
      filename,
      rowCount: parsed.rows.length,
      columnCount: parsed.columns.length,
      columnLabels: parsed.columns.map((column) => column.label)
    };
  }
  if (typeof globalThis !== "undefined") {
    globalThis.__ariaLighthouseExport = exportInPage;
  }
})();
