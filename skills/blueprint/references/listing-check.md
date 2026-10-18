# Listing check: "why isn't it selling?"

When a seller or agent asks why a home isn't selling, or wants a listing reviewed before launch or relaunch.

## Get the listing

The skill can't open Rightmove, Zoopla or OnTheMarket pages. Ask for:

- screenshots of the listing (photos in their order, the key features, the description, the floorplan), or the
  listing text pasted in;
- the asking price, how long it's been on, price changes, number of viewings and any feedback.

Then run `address "<address, postcode>" --asking <price>` (or with `--type` if the home isn't found) for the price
position, comparables and material information.

## What to check, in order

These are what buyers point to most when they explain why they scrolled past.

1. **Price against the evidence.** The `asking_check` position among comparables on today's index, and whether the
   price has been cut in small steps (buyers see every reduction).
2. **The first photo.** It should show the front of the home, in daylight, straight on. A back garden, a kitchen
   detail or an aerial first reads as "something to hide".
3. **Photo order and count.** Front, main living space, kitchen, bedrooms, bathroom, garden, parking. No near-
   duplicates, no utility cupboards, no clutter, nothing that reads as a different property.
4. **Light and staging.** Lights on, curtains open, beds made, surfaces clear, cars off the drive. Real photos only:
   no AI-altered rooms, skies swapped beyond the norm, or virtual furniture that wouldn't fit.
5. **Bedroom claims against the floorplan.** A box room or a downstairs snug sold as a bedroom loses trust. Market it
   as what a buyer will use it for.
6. **The floorplan.** Present, with dimensions, split over floors, readable on a phone.
7. **Material information.** Tenure, and for leasehold the lease length, ground rent and service charge, plus council
   tax band, broadband and parking. Missing service charges and ground rents make buyers assume the worst. Use
   `local` or the `material_information` list.
8. **The description.** Facts a buyer can use (size, aspect, garden direction, parking, schools nearby as distances,
   stations) over adjectives. Cut "nestled", "boasts", "stunning", "luxury", "deceptively spacious", "must be viewed".
   Key features as short facts.
9. **"Offers over".** Shows up in fewer searches than its real price band and can put buyers off when the home has
   been on for weeks.
10. **Timing and freshness.** A long-listed home carries "what's wrong with it?" A relaunch with new photos, a new
    price and full material information can reset that, with the agent's advice.

## How to report it

- Lead with the two or three changes most likely to matter, then the rest as a short list.
- Be direct and kind. The seller loves the home; the listing is what's being judged.
- Price position comes from the data; everything else is your review of what they showed you. Say which is which.
- Never invent viewing numbers, feedback or market claims.
