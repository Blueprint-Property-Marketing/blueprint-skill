# Blueprint for Claude

**Your area's property market, in Claude.** A free Claude skill from
[Blueprint Property Marketing](https://blueprintpropertymarketing.com) for estate agents, developers, land and
investment teams, and anyone who markets property in England and Wales.

Give it any address or postcode in England and Wales and it opens a dashboard of that area beside the chat: price trends, sales by
month and property type, new-build schemes, a postcode map, the busiest streets, and every sale since
2021 to search.
Give it your website or your logo and the dashboard carries your logo and colours. It is built from
HM Land Registry data and the UK House Price Index. No API keys, no spreadsheets, nothing to set up
beyond the upload.

![The Blueprint area dashboard for Sale, M33](docs/example-dashboard.png)

## What it does.

- **Area dashboard.** The average price and yearly change for your local authority, against your
  region and England; registered sales by month; prices by property type; price bands; a postcode
  map; the busiest streets.
- **Every sale.** Search any street, postcode or house number since 2021, and filter by type, price
  and new builds. Click a street or a postcode on the map to see its sales. Useful before a valuation
  or a site appraisal.
- **New builds.** Every scheme in the area with units sold, selling period, home types and median
  price, and new-build sales set beside established homes of the same type in the same postcode
  sectors and months. Leasehold shares by property type.
- **Side by side.** Compare two or three areas: prices, sales, medians type by type, price bands and
  the busiest streets. Useful for agents with more than one branch and developers weighing up sites.
- **Any question the data can answer.** "Every semi on this street since 2021 and what each sold for
  before." "Which postcodes in M33 have the most detached sales?" Claude works it out from the sales
  data and says how.
- **In your branding.** Share your website and it uses your logo and brand colour. If Claude can't
  reach your site, attach your logo and it takes the colours from that.
- **Questions in plain English.** "What sold on Brooklands Road since January?" "How do semis in M33
  compare with Trafford?"

More tools for property marketers are on the way.

## Install it.

About two minutes, on Claude's Free, Pro, Max and Team plans.

1. Download **`blueprint.zip`** from the [latest release](https://github.com/Blueprint-Property-Marketing/blueprint-skill/releases/latest).
   Leave it zipped.
2. In Claude, open **Settings → Capabilities** and check **Code execution and file creation** is on.
3. Open **Customize → Skills**, click **+**, choose **Create skill → Upload a skill**, and pick
   `blueprint.zip`. Make sure the toggle next to Blueprint is on.
4. Start a new chat and type: **"Blueprint: my area dashboard for M33, our site is yourcompany.co.uk"**
   (your own postcode district and website).

On Enterprise plans, an admin may need to allow network access to package managers first. If Claude
says it can't download the data, use the area file below instead.

Using Claude Code? Copy `skills/blueprint` into `~/.claude/skills/blueprint`.

## Where it works.

Any address, postcode or place in England and Wales: all 2,288 postcode districts with registered sales,
4,608,851 sales since January 2021. Data is refreshed each month; your installed skill picks up the new
figures automatically.

**If Claude can't download the data:** from the
[latest release](https://github.com/Blueprint-Property-Marketing/blueprint-skill/releases/latest), download the
file for the letters at the start of your postcode (`blueprint-areas-M.zip` for M33, `blueprint-areas-SK.zip` for
SK7), attach it to your chat, and ask Claude to use it.

## The data.

- **HM Land Registry Price Paid Data.** Every standard residential sale in England and Wales registered since
  January 2021 (to 2026-08).
  Sales are registered weeks to months after completion, so the latest months are always incomplete;
  the dashboard marks them as still registering.
- **UK House Price Index.** Published for the local authority, about two months behind. Every price
  trend comes from the index, because medians move with the mix of homes sold.
- **Postcode locations** for the map, and each area's region, from the ONS Postcode Directory.

Contains HM Land Registry data © Crown copyright and database right 2026. This data is licensed under
the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
Postcode locations contain OS data © Crown copyright and database right 2026, and Royal Mail data
© Royal Mail copyright and database right 2026. Source: Office for National Statistics, OGL v3.0.

Price Paid Data contains address data processed against Ordnance Survey's AddressBase Premium product,
which incorporates Royal Mail's PAF database. Royal Mail and Ordnance Survey permit use of this address
data for personal and/or non-commercial use, and to display for the purpose of providing residential
property price information services. For any other use, contact Royal Mail
(address.management@royalmail.com).

The dashboard is not a valuation, and Blueprint Property Marketing is not affiliated with HM Land
Registry. Check figures before you rely on them.

## Privacy.

The skill runs inside your own Claude account. Blueprint Property Marketing can't see your chats,
your files or what you ask.

- **What it downloads.** Area data and its display text (such as the panel at the foot of the
  dashboard) from this public repository on GitHub, and only the areas you ask for. GitHub handles
  that download under its own privacy terms; the request comes from wherever Claude runs the skill.
- **What it sends to Blueprint.** Nothing. There are no accounts, no tracking, no analytics and no
  cookies, and nothing is sent back to us.
- **The dashboard.** One file, created in your chat, with everything it needs inside it. It makes no
  network requests when you open it.
- **Your website and logo.** If you give your website, the skill reads its public homepage,
  stylesheets and logo to take your name, logo and brand colours. If you attach a logo, it reads
  that file. Either way they are used only in your dashboards, in that chat, and aren't stored
  anywhere else.
- **Links to us.** Links to Blueprint Property Marketing's website are tagged so we can see that a
  visit came from the skill, never who you are. Email links open with a subject line saying they
  came from the skill. Anything you send us, or do on our website, is covered by our usual privacy
  policy.
- **Your chats.** What you type and attach in Claude is covered by Anthropic's terms and your
  Claude settings, not by us.
- **The sales data.** HM Land Registry publishes the address and price of every sale as public
  record. The skill holds no names and shows addresses only as price information.

Privacy questions: sam@blueprintpropertymarketing.com

## Who made it.

Blueprint Property Marketing designs brochures, ads, websites and campaigns for estate agents,
developers and investors. [blueprintpropertymarketing.com](https://blueprintpropertymarketing.com)

## Licence.

**Free to use, not to copy.** You can install the skill and use it, and everything it produces, for
your own work and your business, at no cost. You can't copy, republish, sell, rebrand or build on it,
or remove the Blueprint name and credits, without our written permission. The full terms are in
`LICENSE`.

The area data stays under the Open Government Licence v3.0, with the address-data condition above.
The Manrope font is under the SIL Open Font License 1.1 (`skills/blueprint/assets/OFL-Manrope.txt`).
The Blueprint name and logo are trade marks of Blueprint Property Marketing.

Permission requests: sam@blueprintpropertymarketing.com
