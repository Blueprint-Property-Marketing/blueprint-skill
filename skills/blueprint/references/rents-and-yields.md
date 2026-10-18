# Rents and yields

`python scripts/blueprint.py rents <district> [--page]` gives the ONS Price Index of Private Rents for the council
area: the average monthly rent across all tenancies (new and existing), by bedrooms (1, 2, 3, 4+) and property type,
with the annual change, the region and the country, and gross yields by type against this district's sale prices.

## Rent reviews (Renters' Rights Act)

From 1 May 2026, rent increases for assured periodic tenancies in England use a Section 13 notice, and a tenant can
challenge one at the First-tier Tribunal, which decides the market rent.

- The ONS figures are **market background for the whole council area**: the trend and the average for the size and
  type. Tribunals put more weight on rents for genuinely similar homes nearby, so the landlord or agent should add
  advertised or agreed rents for comparable homes.
- Write the evidence as: the property (type, bedrooms, condition), the council-area averages and their annual change
  (with the month), the comparable rents the user supplies, and the proposed rent.
- **No legal advice.** Point to GOV.UK for the notice, the timings and the tribunal process. Don't tell anyone a
  notice is valid or that they'll win.

## Landlords deciding whether to sell or hold

Facts only, in this order: the price trend for their type (UK HPI, council area), the comparables for their home
(`address`), the council's average rent for the type, the gross yield, and the costs the data can't see (mortgage,
tax, repairs, voids, agent fees, compliance work). The decision is theirs; never recommend selling or holding.

## Lettings market updates

For a letting agent's landlord newsletter or post: the council's average rent and annual change, rent by bedrooms,
the region for comparison, the price trend, and gross yields by type. Name the source and month every time.

## Investors

Gross yield = average rent for the type x 12 / median registered sale price of that type in the district over the
last 12 months. It's indicative: before costs, voids, tax and finance, and the rent is a council-wide average while the
price is the district's. Compare districts with `compare` and `rents` for each.
