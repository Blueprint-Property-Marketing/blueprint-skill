# Material information

National Trading Standards' guidance says property listings in England and Wales must include material information,
in three parts:

- **Part A:** council tax band, price, tenure. For leasehold: the lease length, ground rent and service charge.
- **Part B:** property type, rooms and floor area, utilities (electricity, water, sewerage, heating), broadband,
  mobile signal, parking.
- **Part C:** building safety, restrictions and rights (covenants, listed status, conservation area, tree
  preservation orders, rights of way), flood risk, coastal erosion, planning permission and proposals, accessibility,
  and coal mining or other mining.

## What the skill fills in

`python scripts/blueprint.py local "<postcode>" [--page]`, or the `material_information` list from `address`. Each row
has a `status`:

| Status | Meaning |
|---|---|
| `data` | Filled from open data (with the source in the value) |
| `link` | A free official check to do (council tax band, EPC, coastal erosion) |
| `supply` | The seller or agent supplies it (rooms, utilities, parking, lease details, building safety) |
| `n/a` | Not needed (lease details for a freehold) |

## Sources and limits

| Item | Source | Covers | Limit |
|---|---|---|---|
| Flood (rivers and sea) | Environment Agency, postcodes in areas at risk | England | Not surface water, groundwater or reservoirs; Wales via Natural Resources Wales |
| Broadband | Ofcom Connected Nations 2025, per postcode | England and Wales | Availability, not what a line actually gets |
| Mobile | Ofcom, per council area | England and Wales | Not the postcode |
| Planning and heritage | Planning Data platform (councils, Historic England, Natural England) | England | Only what councils have published; check the council's maps |
| Coal mining | Mining Remediation Authority, Development High Risk Areas | England and Wales | The wider coalfield isn't included; a conveyancer's coal search confirms |
| Schools, stations | DfE (England), DfT | Schools England; stations Great Britain | Straight-line distances; no catchments |
| Tenure, type | HM Land Registry, at the last registered sale | England and Wales | Confirm with the title |

## Rules

- Everything is for the postcode's centre point. Say so, and point to the source for anything decisive.
- Don't present a flood or coal fact as a selling point or a scare; state it with its source.
- Never fill a `supply` row yourself. Ask the seller, or leave it marked "to confirm".
- Not legal advice. Agents remain responsible for their listings.
