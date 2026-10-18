# Developers, land and investment

## The commands

| Need | Command |
|---|---|
| Compare candidate areas | `compare <district> <district> [<district>]` |
| New-build schemes, new build against established | `stats <district>` → `new_builds` |
| One scheme's sales | `query <district> --street "<street>" --new` |
| Unit mix and depth by type | `stats <district>` → `last_12_months.by_type`, `price_bands` |
| Brownfield register sites | `sites <district>` |
| Constraints at a site postcode | `local "<postcode>"` |
| Rents for build-to-rent or yields | `rents <district>` |
| Long-run prices by type | the dashboard's "Houses and flats" chart (UK HPI by type since 2016) |

## A site or area summary (board or land committee)

One page, in this order:

1. **The ask:** the site or areas and the decision.
2. **The market:** registered sales and medians by type for 12 months (with counts), the council's UK HPI trend by
   type, price bands.
3. **New build:** schemes nearby (street, sector, sales, period, medians where five or more), and new build against
   established medians side by side, never as a premium.
4. **Rents:** the council's average rents by bedrooms and type, and gross yields (for BTR or PRS cases).
5. **The site:** constraints at the postcode's centre (conservation area, green belt, listed buildings nearby, flood,
   coal), brownfield register entries nearby, and what needs a full search.
6. **Sources and dates.**

## Rules

- Medians with counts; no premiums; no forecasts; no absorption rates (the data doesn't show time on market).
- A brownfield register entry isn't planning permission unless its status says so.
- Floor areas come from EPCs where a district has them: the address check then gives floor area and £ per square
  metre for the home and its comparables. Elsewhere, no £ per square metre.
- Scheme names aren't in Land Registry data; refer to schemes by street and postcode sector.
