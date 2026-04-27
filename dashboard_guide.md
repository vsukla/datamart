# Dashboard User Guide

**URL:** `http://localhost:8001/dashboard/`

The dashboard lets you explore U.S. county-level data across four federal sources — Census ACS5, CDC PLACES, BLS LAUS, and USDA Food Environment Atlas — without writing any queries. You can compare states, drill into counties, and view cross-source correlations in charts and a sortable table.

---

## Controls

Four controls sit at the top of every page.

| Control | What it does |
|---|---|
| **Metric** | Selects what you're analyzing. Three grouped sections: Census (income, education, housing, poverty, unemployment), Health (obesity, diabetes, smoking, hypertension, depression, physical activity, mental health), and Food (food access, grocery density, fast food, SNAP, farmers markets). |
| **Year** | Vintage year for Census and health data (2018–2022). |
| **Drill into State** | Select a state to switch from state-level to county-level view. Select "— All States —" to return to the national view. |
| **Health metric / Food metric** | Appear only in county mode. Change what the Health Outcomes and Food Environment panels are ranking. |

---

## All-States Mode

When no state is selected you see three charts comparing all 50 states.

### National Trend
A line chart showing how the selected Census metric has moved nationally from 2018 to 2022. A pill in the top-right shows the total change since 2018. Only available for Census metrics — selecting a health or food metric hides this chart.

### State Ranking
A horizontal bar chart ranking all 50 states by the selected metric for the chosen year. Top 5 are blue, bottom 5 are red. Works for all three metric groups:
- **Census metric** — uses pre-computed state averages from the Census batch job.
- **Health metric** — uses county-level CDC PLACES data averaged to state level.
- **Food metric** — uses county-level USDA data averaged to state level.

### Year-over-Year Movers
Shows the 5 states that improved the most and the 5 that declined the most between the selected year and the prior year. Only available for Census metrics (health and food data are single-vintage snapshots with no year-over-year comparison).

---

## County Mode

Select a state from the **Drill into State** dropdown. All county data loads in parallel; subsequent metric changes are instant from cache.

### County Ranking
Same bar chart as state ranking, now showing all counties in the selected state. Color logic is the same (blue = top 5, red = bottom 5).
- For **Census metrics**: ranks from the aggregates API.
- For **Health or Food metrics**: ranks directly from the county profile data.

### Year-over-Year Movers
Top 5 and bottom 5 counties by Census metric change. Hidden for health and food metrics.

### Health Outcomes (CDC PLACES)
Ranks counties by the measure selected in the **Health metric** dropdown: Obesity, Diabetes, Smoking, Hypertension, Depression, Physical Inactivity, or Poor Mental Health. Uses data for the selected year. Top 5 highest-rate counties shown in pink, bottom 5 in green.

### Food Environment (USDA Atlas)
Ranks counties by the measure selected in the **Food metric** dropdown: Low Food Access %, Grocery Stores per 1,000, Full-Service Restaurants per 1,000, SNAP Participation %, or Farmers Markets count. Top 5 highest shown in green, bottom 5 in amber.

### Cross-Source Scatter
Plots each county as a dot — any metric on the X axis, any metric on the Y axis, from any source. Use the two dropdowns in the card header to pick axes.

**Default:** Poverty Rate vs. Obesity % — shows the classic poverty–health correlation at county level.

Useful combinations to try:
- Poverty % (X) vs. SNAP Participation % (Y) — food assistance uptake tracks poverty
- Median Income (X) vs. Low Food Access % (Y) — food deserts and income
- Obesity % (X) vs. Diabetes % (Y) — co-morbidity clustering
- Education % (X) vs. Poor Mental Health % (Y) — education and mental health

Counties with missing or invalid data for either axis are excluded from the plot. Hover a dot to see the county name and both values.

### County Data Table
A full cross-source table with one row per county. Columns:

| Column | Source |
|---|---|
| County | — |
| Population | Census |
| Median Income | Census |
| Poverty % | Census |
| Bachelors % | Census |
| Obesity % | CDC PLACES |
| Diabetes % | CDC PLACES |
| Depression % | CDC PLACES |
| Low Food Access % | USDA |
| SNAP % | USDA |
| Grocery /1k | USDA |

**Click any column header to sort.** Click again to reverse the sort direction. Headers are color-coded: blue for Census, pink for Health, green for Food. Scroll horizontally if needed.

---

## Navbar Links

The source labels in the top navbar are clickable links to the live API:

- **Census ACS5** → `/api/estimates/` — raw county estimates with geo metadata
- **CDC PLACES** → `/api/health/` — county health outcomes
- **BLS LAUS** → `/api/labor/` — county unemployment and labor force
- **USDA Food Env** → `/api/food/` — county food environment metrics

Each opens a paginated JSON response. Add `?state_fips=06` or `?fips=06001` to filter.

---

## Tips

- **Switch metrics without reloading** — after the first state selection all data is cached. Changing any metric or dropdown is instant.
- **Scatter defaults change automatically** — when you select a health metric as the main metric, the county ranking chart updates accordingly; the scatter chart axes are independent and stay where you set them.
- **Table + scatter use the same data** — both are powered by `/api/profile/`, which joins all four sources at the most recent year available for each.
- **Missing data shows as N/A** — not every county has data for every source. CDC PLACES covers ~2,900 counties; USDA covers ~3,100; BLS is being loaded incrementally.
