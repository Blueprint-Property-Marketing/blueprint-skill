# Valuation evidence and price conversations

For estate agents preparing a market appraisal, talking a vendor through price, or writing a price-reduction or
relaunch recommendation. Also for buyers and sellers checking a price.

## What the address check gives you

`python scripts/blueprint.py address "<number or name, street, postcode>" [--asking N] [--page]`

| Field | Use it for | How to say it |
|---|---|---|
| `history` | What the home has sold for | "Registered sales of this home: £X in March 2016 (the latest of two sales from 1995 to 2020)…" |
| `property.on_index_today` | Where that price would be if it had moved with the market | "On today's index, £X: the March 2016 price moved with the UK House Price Index for semi-detached homes in Trafford to July 2026. It's not a valuation." |
| `comparables` | What similar homes nearby actually sold for | "11 semi-detached sales in postcode sector M33 3 from Sep 2024 to Aug 2026; median on today's index £398,000; middle half £372,000 to £421,000." |
| `asking_check` | Where an asking price sits | "£425,000 is above 8 of those 11 sales on today's index, and 6.8% above their median." |
| `rents` | A landlord vendor's alternative | "The ONS average rent for a semi in Trafford was £1,521 a month in August 2026." |

## The conversation, in order

1. **The home's own history first**, then today's index figure, with the "not a valuation" line.
2. **Then the comparables:** how many, where, over what period, and the middle half. Name streets (not numbers) when
   the vendor will keep the document.
3. **Then the asking price's position**, factually: "above all 11", "in the upper quarter", "in the middle".
4. **Then what the data can't see:** size, condition, garden, parking, layout, extensions. That's the agent's
   judgement and the reason the figure isn't a valuation.
5. **Then the recommendation**, which is the agent's, not the data's.

## Rules

- Never call a price overpriced, underpriced or "worth" anything. Give positions and let the agent advise.
- Never present the index figure alone; always alongside the comparables.
- Medians only with their sample sizes; under five sales, list them instead.
- If the home extended or changed type since its last sale, say the index figure can't account for it.
- Comparables come from the same property type. Bedrooms aren't in Land Registry data; say so if they ask.
- A vendor's own home's history can go in a document for that vendor. Other homes appear by street, not number, in
  anything that leaves the agent's office.

## Writing for a vendor

- **Market appraisal follow-up:** the home's history, the index figure, the comparables (streets only), the agent's
  recommended price and why. One page. A subject line like "Your home: the evidence behind our price".
- **Price-reduction conversation:** what's happened since launch (in the agent's words; viewings and feedback aren't in
  the data), where the price sits now, the comparables, the recommendation. No blame, no pressure lines.
- **Relaunch plan:** pair the price position with `references/listing-check.md` (photos, order, floorplan, material
  information, description).
- Always end with the data credit line.
