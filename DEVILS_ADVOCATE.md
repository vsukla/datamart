# Devil's Advocate: Why This Fails

An honest assessment of why this idea is harder than it looks,
why it has been tried before, and the most likely failure modes.

---

## It Has Already Been Tried

This is the most important thing to say first. This idea is not new.
Multiple well-funded teams have built versions of it. The fact that
none of them became the "Stripe of data" is itself evidence.

| Who | What They Built | Founded | Status |
|---|---|---|---|
| **Google Data Commons** | Exact same vision: unified, normalized, queryable public data across Census, WHO, World Bank, Eurostat, CDC, and 250+ more sources. SPARQL + REST API. Free. | 2018 | Active, Google-funded, growing |
| **PolicyMap** | County/tract-level data aggregation for government, nonprofits, healthcare. 50+ sources normalized. | 2008 | ~$10M ARR, niche, not scaled |
| **SimplyAnalytics** | Multi-source county/ZIP demographic and business data for retail/CPG. | 2010 | Modest scale, subscription |
| **ESRI Business Analyst** | Site selection with aggregated federal data. Dominant in market. | ~2000 | Mature, but expensive and heavy |
| **Social Explorer** | Census + ACS normalized and visualized. | 2004 | Academic niche, Columbia Univ. |
| **Opportunity Atlas** | Harvard/Census joint project. County-level mobility data. | 2018 | Free, narrow scope |
| **DataUSA** | Deloitte/MIT Media Lab. Multi-source public data visualization. | 2016 | Free, stalled development |
| **Urban Institute Data Catalog** | Curated normalized public datasets. | Ongoing | Nonprofit, not monetized |
| **ProximityOne** | County/tract data aggregation for research. | 2000s | Tiny, obscure |
| **County Health Rankings** | Robert Wood Johnson Foundation. Health + SDOH by county. | 2010 | Free, narrow domain |

**Google Data Commons alone should give us serious pause.** It is doing exactly
what this strategy document describes — at Google scale, with Google infrastructure,
for free. It already has Census, CDC, World Bank, Eurostat, UN SDGs, and hundreds
more sources normalized to a common entity graph. It has a REST API, a SPARQL
endpoint, and a natural language query interface backed by Gemini.

If Google is giving this away free and still hasn't achieved ubiquity after 7 years,
that tells us something important about the difficulty of the problem — and about
how strong the incumbent pull is for existing workflows.

---

## The Structural Problems

### 1. Public data is not a moat

Every file we download is available to anyone. A competitor —
or a well-funded customer — can download the same Census files,
the same BLS flat files, the same CDC datasets, and build the
same normalized tables. The raw data creates no competitive advantage.

The normalization work is where the value lives. But normalization
is copyable. A team of five data engineers working for six months
can replicate everything we build. There is no patent on a FIPS crosswalk.

The only durable moats in a business like this are:
- **Network effects** — this is NOT a network effects business.
  More users do not make the data more valuable to other users.
- **Switching costs** — real, but only after customers have built
  workflows on top of the API. Takes years to establish.
- **Data exclusivity** — impossible if all sources are public.
- **Brand/trust** — possible but takes a decade to build.

Without a structural moat, pricing power is low and competition
from better-funded players is a permanent existential threat.

### 2. The maintenance burden is catastrophically underestimated

500 datasets × annual updates × schema drift × API changes
× source URL rot × government website redesigns
= a full-time operations team before you've written a single product feature.

Each of the ~10 datasets we've ingested so far has already required
significant one-off engineering (BLS LAUS series ID format bug,
EDFacts range value parsing, EPA county name normalization).
That ratio — 1 dataset = 1 unique problem — does not improve at scale.

It gets worse. Datasets we depend on will:
- Change their download URLs without notice
- Change column names between vintages
- Be deprecated and replaced with incompatible successors
- Have retroactive corrections that invalidate prior ingested data
- Switch from flat file to API (or vice versa)
- Add embargo periods before public release

The Census Bureau alone has dozens of these events per year.
The ongoing maintenance cost of 500 datasets is 10–20x the
one-time ingestion cost. This is an operations company, not
a software company. Operations companies have fundamentally
different unit economics.

### 3. The schema normalization problem is not solved

We are betting that LLM-assisted column mapping will work at scale.
The evidence for this is thin. Consider what column mapping actually requires:

- `PCT_POVERTY` in the Census 2019 ACS uses a **different methodology**
  than `PCT_POVERTY` in the Census 2020 ACS (COVID disruption changed
  collection methods). Naively joining them gives wrong answers.
- `UNEMPLOYMENT_RATE` from BLS LAUS and `unemployment_rate` from
  Census ACS measure different things (BLS = administrative records,
  ACS = survey-based). Joining them as the "same" metric misleads users.
- `MEDIAN_INCOME` in dollar terms is not comparable across years
  without inflation adjustment — but which deflator? CPI? PCE? PCEPI?

An LLM can match column names. It cannot understand methodological
differences across datasets without domain expertise encoded somewhere.
When we normalize 500 datasets and a hospital system makes a policy
decision based on a metric that was silently mis-mapped, the liability
is ours.

The incumbent players (PolicyMap, ESRI, Social Explorer) have
**teams of domain experts** who manually validate every dataset,
write documentation about methodological differences, and flag
comparability issues. We plan to automate that with an LLM.
This has not been demonstrated to work.

### 4. The "last mile" problem destroys unit economics

Data infrastructure is worth very little on its own.
The value is in the analysis that runs on top of it.

Consider who actually buys data products:
- A hospital system doesn't want county obesity rates — they want
  a CHNA report with specific conclusions and recommendations.
- A retailer doesn't want county income data — they want a ranked
  list of the top 50 expansion markets with a scoring rationale.
- A policy researcher doesn't want a normalized API — they want
  a Stata/R dataset they can run regressions on.

The "raw data infrastructure" framing keeps us out of the value layer.
But building the value layer (analysis, reports, scoring, conclusions)
requires domain expertise in every vertical we sell to — healthcare,
real estate, insurance, agriculture, civic. That's not one company.
That's ten companies.

Everyone who has tried to be a pure data infrastructure play
has eventually either added the analysis layer (massive investment,
new skillset, different business) or stayed small in a niche
where they have deep domain expertise (County Health Rankings = health only,
PolicyMap = community development only).

### 5. The target customers don't have budget

The customers most excited about this product are:
- Academic researchers (zero budget, expect everything free)
- Journalists (tiny budget, expect steep discounts)
- Government agencies (12-18 month procurement cycles, then budget freezes)
- Nonprofits (grant-funded, unpredictable spend)

The customers with real budget are:
- Insurance carriers (already have Verisk and ISO relationships, switching cost is enormous)
- Large retailers (already have ESRI relationships, IT won't approve a new vendor without 6 months of security review)
- Hedge funds (will use the data, then build their own pipeline in-house the moment it matters)

The middle market — companies that need this and will pay for it
and don't already have an incumbent solution — is smaller than it looks.

### 6. Government competition is an existential risk

The government is the source of the data and increasingly wants to
be the distributor too. Existing investments:

- **data.gov** itself is a government project doing exactly catalog + discovery
- **data.census.gov** replaced American FactFinder and keeps improving
- **Census Bureau API** is free, already normalized for Census data
- **FRED** (Federal Reserve) is free, excellent for economic time series
- **CDC WONDER** is free for health data
- **GeoFRED** is a free geographic visualization of FRED data
- **opportunity.census.gov** is a free mobility data platform

Congress regularly funds new data infrastructure initiatives.
ARPA-H is funding health data infrastructure. NSF funds data commons.
NIH funds biomedical data platforms. Any of these could pivot to
encompass exactly what we're building — and give it away free.

The moment a federal agency builds and opens a multi-source normalized
geographic API, our paid product argument collapses.

### 7. The entity alignment problem compounds globally

At US county level (3,231 counties, stable FIPS system, federal data standardization),
entity alignment is manageable but still hard (15% of datasets don't have clean FIPS).

Globally:
- Administrative boundaries change constantly (South Sudan secession 2011,
  Kosovo independence, Brexit affecting UK/EU classifications)
- No universal identifier system — ISO 3166 (country) doesn't extend to subnational
- EU NUTS boundaries are revised every ~5 years
- India has 739 districts, some with disputed boundaries
- Brazilian municipality mergers and splits happen every census cycle
- China's administrative geography is politically sensitive and unreliable from Western sources

A global entity graph that stays accurate is a decade-long infrastructure project,
not a 10-month product build. The World Bank's Open Data team has been working
on this problem for 30 years and still has significant gaps.

### 8. The data quality death spiral

Here is how data quality failures compound:

1. We ingest 500 datasets at varying quality levels
2. A customer uses our API to make a decision (grant allocation, store opening, insurance pricing)
3. The decision is wrong because dataset #347 had a methodology change in 2021 that we didn't track
4. The customer loses money or makes a bad policy decision
5. They blame us (rightly or wrongly) and churn
6. The story spreads: "Datamart data isn't trustworthy"
7. Trust, once lost in a data product, is nearly impossible to recover

Data products live and die on trust. One high-profile data quality
failure — a hospital that made a bad capacity decision, a retailer
that entered a market based on wrong demographics — can permanently
damage the brand.

The more datasets we add, the more attack surface for quality failures.
The relationship between dataset count and quality assurance cost is not linear.

### 9. The business is really an operations company

If we're honest about what this business does at scale:

- 40% of time: monitoring source datasets for updates, format changes, URL rot
- 30% of time: fixing ingestion pipelines that broke due to upstream changes
- 20% of time: responding to customer questions about data quality and methodology
- 10% of time: building new product features

This is fundamentally an operations company with a thin technology layer on top.
Operations companies have:
- Low gross margins (people-intensive)
- Difficulty scaling without proportional headcount
- High operational risk (one data incident = customer losses)
- Limited investor appeal (not software-like unit economics)

The SaaS multiple (10–15x ARR) only applies if the business is
truly software-driven. If it requires significant human oversight
of data quality, the multiple is closer to 3–5x — the valuation
of an information services company, not a software company.

---

## The Most Likely Failure Modes

### Failure Mode 1: Data quality incident destroys trust
**Probability: High.** With 500+ datasets, a significant quality failure
is nearly certain within 2 years. The question is whether it's recoverable.
**What it looks like:** A customer makes a wrong decision, traces it to
our data, and posts publicly.

### Failure Mode 2: Google Data Commons wins by being free
**Probability: Medium-High.** If Google decides to aggressively develop
Data Commons with Gemini integration and enterprise support, the "why pay?"
question becomes very hard to answer.
**What it looks like:** Customers evaluate both, choose free, tell others.

### Failure Mode 3: Stuck in the "research tool" trap
**Probability: High.** The easiest customers to acquire are academics and
journalists. They use a lot, pay little, and don't lead to commercial expansion.
We optimize for them, build features they need, raise our profile among
people who can't pay, and never crack the commercial market.
**What it looks like:** 500 users, $50k ARR, "great product" reviews, no path to scale.

### Failure Mode 4: Maintenance overwhelms product development
**Probability: High.** At ~100 datasets, the ratio of maintenance to new
development inverts. We spend all our time keeping existing datasets working
and never have bandwidth to build the query layer, the vertical tools, or
the global expansion that would differentiate us.
**What it looks like:** Dataset count stalls at 80–100. Product feels unfinished.
Customers ask for features that never ship.

### Failure Mode 5: The sales cycle kills us
**Probability: Medium.** Hospital systems, insurers, and government agencies
have 12–18 month sales cycles. We land a promising pilot in month 6, chase
the contract for 12 months, close it in month 18, and deliver in month 24 —
if we're still alive.
**What it looks like:** Strong pipeline, no closed revenue, runway exhausted.

### Failure Mode 6: A vertical competitor out-executes us in our best market
**Probability: Medium.** A company that does ONLY health equity data, or ONLY
retail site selection, but does it brilliantly with deep domain expertise,
will beat a generalist data platform in that vertical every time.
A single-vertical competitor can spend 100% of their product effort on
one customer type's specific needs. We're spreading across ten verticals.
**What it looks like:** We lose health to a CHNA-specific tool, lose real estate
to a site selection specialist, lose finance to a Bloomberg terminal extension.
Each niche goes to someone deeper, and we have no niche.

### Failure Mode 7: The governance architecture creates more liability than protection
**Probability: Low-Medium.** The governance system we designed is good.
But the more formal our compliance posture, the more a plaintiff's lawyer
can point to our own documented standards when we fail to meet them.
A company that promises "every row is traceable to its source and license verified"
and then fails to catch a CC-BY-NC dataset in a paid response has created
its own liability through its governance documentation.
**What it looks like:** A lawsuit citing our own GOVERNANCE_ARCHITECTURE.md
as the standard we failed to meet.

---

## What Would Make This Time Different

These are the genuine reasons it might work now despite all of the above:

**LLMs change the schema normalization economics.** The prior attempts at this
were limited by how expensive it was to normalize schemas manually. LLMs make
the first 70% of schema classification nearly free. This is a genuine structural change.

**The governance layer is a new differentiator.** Post-GDPR, post-AI Act,
the compliance burden on data buyers has increased dramatically. A platform
that ships with governance baked in — license tracking, attribution, audit logs,
suppression rules — is genuinely differentiated from a raw data dump. No incumbent
was built with this in mind. This is new.

**The global entity alignment gap is real and growing.** No one has done
global subnational entity alignment at scale. The World Bank is country-level.
Eurostat is EU-only. Nobody joins US county data to EU NUTS data to Indian
district data in a consistent API. That gap is exploitable.

**The AI-native interface hasn't been built yet.** "Show me counties where
median income is rising but health outcomes are declining" should be a
natural language query, not a developer API call. The tools to build this
(Claude, GPT-4, Gemini) exist now and didn't in 2015 when PolicyMap launched.
A conversational interface to public data is a new product category.

**The entry cost is low enough to find out.** Unlike prior attempts that
required large teams and long runways, we can build a compelling MVP for
tens of thousands of dollars and validate the market before betting heavily on it.
The risk of trying is low. The risk of over-investing before validating is high.

---

## The Honest Summary

The idea is not wrong. The market gap is real. The technology timing is better
than it has ever been. But:

- The business will be harder and more expensive to operate than it looks
- The moat is weaker than it feels
- Google is already doing this for free
- The most accessible customers can't pay
- The paying customers have long sales cycles and incumbent relationships
- Data quality failure is a "when", not an "if", at scale

The right response is not to abandon it. It is to:

1. **Validate the paying customer before building the platform.**
   Find one commercial customer who will pay real money for county-level
   data today, with what we have. If we can't find that customer, the rest
   of the strategy is premature.

2. **Pick one vertical and go deep before going broad.**
   A health equity tool that hospital systems love is worth more than
   a general platform that everyone thinks is "interesting."

3. **Design for the Google Data Commons world.**
   If the free version of this exists, we need to be better — in quality,
   in governance, in domain expertise, in customer support — not just cheaper.

4. **Set a clear maintenance budget before adding datasets.**
   Every dataset we add is a long-term maintenance commitment.
   Be ruthless about the cost before making the commitment.

5. **Treat data quality as the product, not a feature.**
   The companies that have survived in this space (PolicyMap, County Health Rankings)
   have done so by being deeply trusted in a narrow domain. Trust is the product.
   Data breadth is secondary.
