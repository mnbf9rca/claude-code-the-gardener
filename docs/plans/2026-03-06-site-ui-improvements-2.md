# Site UI Improvements — Round 2

**Date:** 2026-03-06
**Branch:** feat/site-ui-improvements
**Status:** Approved for implementation

## Items

### (c) Bug: drag-to-filter not updating date inputs

`onZoomComplete` is one level too deep. In `chartjs-plugin-zoom@2`, callbacks live at
`plugins.zoom` level, not inside `plugins.zoom.zoom`.

**Fix:** Restructure `DRAG_OPTS` → `ZOOM_PLUGIN_OPTS` so the callback is at the correct level.

---

### (d) Conversation — newest message first

Reverse the sort and date-group order in `conversation.astro`.

**Fix:** Change sort comparator to `b.timestamp.localeCompare(a.timestamp)`; reverse `byDate` array.

---

### (a) Day page — light band overlay on moisture chart

Add a custom inline Chart.js plugin to the moisture chart in `day/[date].astro`.

**Rendering (afterDraw hook):**
- Draw a 6px background strip at `chartArea.top` in dark amber `rgba(240,163,44,0.12)` spanning full chart width.
- For each `turn_on` light event, draw an amber fill `rgba(240,163,44,0.7)` from its timestamp pixel to the corresponding `turn_off` pixel. If no matching off event is found, extend to `chartArea.right`.
- Timestamps converted to x-pixels via `chart.scales.x.getPixelForValue(ts)`.

The existing text list of events is retained below.

---

### (b) Stats page — light band on moisture chart + standalone light chart

Two additions to `stats.astro`:

**1. Band on moisture chart** (same visual language as day page):
- At daily resolution, iterate `filtered` dates. For each date with `dailyData[d]?.light?.minutes_on > 0`, draw an amber cell across that category slot's pixel range.
- Each slot width: `(chartArea.right - chartArea.left) / filtered.length` pixels.

**2. New "LIGHT (MIN/DAY)" chart section:**
- Same layout, sizing, and styling as the cost and moisture chart sections.
- Bar chart (amber palette), same category labels from `allCostDates`, same date filter.
- Data: `dailyData[d]?.light?.minutes_on ?? 0` per day.
- Y-axis label: "minutes".
- Placed between moisture chart and tool table.

---

### (e) Tool use — full table + doughnut pie chart

**Table:**
- Remove `.slice(0, 20)` cap — show all tools.

**Doughnut chart (side-by-side layout):**
- CSS grid: chart column ~220px, table column fills remaining space.
- Build slices by descending call count. Add slices until either 20 slices reached or cumulative share exceeds 80%. Remainder → single "Other" slice in muted colour `rgba(74,62,40,0.8)`.
- Chart.js `doughnut` type, cutout `55%`. Centre label: total call count.
- Colour palette: cycling through amber tones for named slices.
- Chart rebuilt by `buildToolTable` on every `update()` call.

---

## Files Changed

| File | Changes |
|------|---------|
| `site/src/pages/stats.astro` | Fix drag bug, add light band+chart, expand tool table, add doughnut |
| `site/src/pages/day/[date].astro` | Add light band plugin to moisture chart |
| `site/src/pages/conversation.astro` | Reverse sort order |

## Success Criteria

- [ ] Dragging on either chart updates the date filter inputs and all three sections react
- [ ] Day page moisture chart has amber light band visible for days with light events
- [ ] Stats page moisture chart has amber light-per-day band
- [ ] Stats page has a "LIGHT (MIN/DAY)" chart section between moisture and tool table
- [ ] Tool table shows all 38 tools
- [ ] Doughnut chart appears next to tool table with correct "Other" grouping
- [ ] Conversation shows most-recent messages first
- [ ] Zero JS console errors
- [ ] Build passes
