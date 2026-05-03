# Datamart: Strategic Assessment & Recommendation

**Prepared for:** vsukla
**Date:** May 2026
**Question on the table:** Hobby project, side business, or full startup?
**Bottom-line recommendation up front:** Pursue this as a **hobby-with-intent** for 6–9 months, structured as a public, opinionated, vertical-narrow tool — *not* as a generalist data infrastructure platform. Convert to a side business only if a specific paying customer surfaces. Do not quit the day job for this.

---

## 1. What you actually have

After reading all six docs end-to-end, here is the honest portrait of what's on the page:

The product strategy and PRD describe a **multi-source, entity-aligned, API-first public data platform** that starts at US county FIPS, expands to schools/hospitals/ZIPs, then to global subnational entities (NUTS, districts, municipalities). The DATA_GOV_STRATEGY doc lays out a credible path to ingest 100–300 high-value federal datasets in 6–10 months for under $3,500 in cloud and LLM cost, leaning on Claude/LLMs for schema classification and column mapping. The two governance docs — and this is the part that genuinely impressed me — design a system where license tracking, attribution, schema-drift detection, and audit trails are enforced *structurally in the schema and middleware*, not just in policy PDFs. The Devil's Advocate doc is the most candid self-assessment I've seen in a strategy package: it names Google Data Commons explicitly, walks through nine structural problems, and lists seven failure modes with probabilities.

The work is **substantively further along than most "I have an idea" repos**: 3,283 geo entities loaded, five federal sources ingested (Census ACS5, CDC PLACES, BLS LAUS, USDA Food Environment, plus partials), aggregates pre-computed, a working dashboard, an API surface, and a county profile view. This isn't a deck — this is a system.

What you are *missing*, and what almost every doc dances around: **a paying customer or a specific, bounded user story that someone is hurting for badly enough to switch from their current workflow.** The PRODUCT_STRATEGY lists ten verticals, each with a plausible $5–10M ARR thesis, but no validation. Devil's Advocate calls this out as Failure Mode 3 ("Stuck in the research tool trap") and recommends item #1: "Validate the paying customer before building the platform." That recommendation is correct and is the single most important sentence in the entire repo.

---

## 2. The competitive picture has shifted under your feet — and you need to see it clearly

Your Devil's Advocate doc identified Google Data Commons as the single biggest threat. That assessment was right when written, but the situation has actually gotten *worse* in the months since, in ways the doc didn't foresee:

**Google Data Commons now ships an MCP server, hosted on Google Cloud, free.** [Google announced this in two stages](https://developers.googleblog.com/announcing-the-data-commons-gemini-cli-extension/): a Data Commons MCP server in September 2025, then a [hosted MCP service on Google Cloud Platform in February 2026](https://developers.googleblog.com/access-public-data-insights-faster-data-commons-mcp-is-now-hosted-on-google-cloud/) so users no longer manage their own infrastructure. The pitch — "billions of data points from sources like the United Nations, the World Bank, and government agencies into a single knowledge graph" with natural-language querying via Gemini — is precisely the AI-native interface your strategy doc labeled as a new opportunity. That window is now closing in real time.

**Federal agencies are publishing their own MCP servers.** As of early 2026, [the US Census Bureau, the Government Publishing Office, CMS, and Treasury have either shipped or are deploying MCP servers](https://fedscoop.com/federal-goverment-mcp-improve-ai-access-public-data/) that connect LLMs directly to their data. A US Digital Corps pilot showed accuracy on USASpending and CDC PLACES queries went from near-0% to 95% with MCP. There is an open-source `us-data-mcp` family covering Census, BLS, EPA AQS, FDA, SEC EDGAR. Anyone can wire these into Claude Desktop today, for free, in fifteen minutes.

**The MCP ecosystem is already enormous.** [The public MCP server registry grew from ~1,200 servers in Q1 2025 to over 9,400 by April 2026](https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol), with 78% of enterprise AI teams reporting at least one MCP-backed agent in production. Time-to-integrate dropped from 18 hours to ~4 hours. The "developer-friendly API for public data" framing — which was your Phase 1 product — is now table stakes for any data source that wants to be used by an LLM agent.

**The closest commercial analog is small.** [PolicyMap, after 17 years and ~$5M raised, sits at roughly $3.8M annual revenue with 33 employees](https://growjo.com/company/PolicyMap). That is the realistic ceiling for "well-executed multi-source community data product without a deep vertical." It is a perfectly fine business; it is not a venture outcome.

**The deep-pocketed incumbents are doubling down on proprietary moats, not public data.** [LexisNexis Risk Solutions launched Location Intelligence for Commercial in June 2025](https://www.prnewswire.com/news-releases/lexisnexis-risk-solutions-launches-location-intelligence-a-first-of-its-kind-underwriting-solution-for-us-commercial-property-risk-assessment-302485445.html), explicitly built around their *proprietary* C.L.U.E. claims database, aerial imagery, and weather forensics — not around public data. Verisk is doing the same. The signal here is important: when a $2.4B revenue incumbent like LexisNexis wants to win in geographic risk, they buy or build proprietary inputs *because public data is no longer differentiating*. That is exactly the moat problem your Devil's Advocate doc flagged.

**A genuinely interesting wildcard: federal data infrastructure is being actively destabilized.** Approximately [9% of the federal civilian workforce was eliminated by March 2026](https://en.wikipedia.org/wiki/2025_United_States_federal_mass_layoffs), with statistical and data offices specifically affected (the Commerce Department's data office was reportedly threatened with layoffs in 2025). [GAO documented 134,000 separations in H1 2025 alone with another 144,000 in deferred resignations](https://www.gao.gov/products/gao-26-108719). The downstream effect on data publication cadence, quality, and continuity is uncertain but real — release schedules have already slipped at multiple agencies. This creates an unusual opening for *preserving and curating* public data, especially with a journalistic or civic-archive framing. It also creates real risk if you bet on automated ingestion from sources whose reliability is degrading.

The synthesis: the original "developer-friendly API for public data" thesis is being commoditized by the federal government itself and Google, simultaneously, in 2026. The "AI-native query interface" angle is being closed by Gemini + Data Commons and by every MCP-aware client. The "global entity alignment" angle is still genuinely open, but it is a multi-year infrastructure problem, not a consumer wedge. The vertical-domain angle (insurance underwriting, healthcare CHNAs, ESG scoring) remains the single most valuable area, but it requires deep vertical expertise that a horizontal data platform cannot easily develop.

---

## 3. Honest evaluation of the three options you proposed

### Option (i): Pure hobby project to learn LLM/AI capabilities

This is the **safest and probably highest expected-value use of your time**, but it requires reframing what "the project" is. The current docs describe the project as building a multi-source data platform; the *learning* is the data engineering, the LLM-assisted schema work, and the governance architecture. All of that learning compounds regardless of whether anyone ever pays you for it.

What you'd actually be learning, day to day: hands-on with LLM-assisted schema inference and column mapping (a genuinely cutting-edge skill), MCP server design and deployment (the dominant integration protocol of 2026), agentic data pipelines with self-healing on schema drift, governance-as-code patterns (license enforcement, attribution injection, audit trails — these are exactly the patterns enterprises will need for AI-grounded data, and very few people have built them), and structured-output prompt engineering at scale.

The reputational payoff if you do this well is non-trivial. A *public* GitHub repo with 100+ federal datasets, a working MCP server, a governance layer that's actually enforced in code, and a written playbook explaining the design choices is the kind of artifact that has serious career signaling value for a senior software executive. You become the person who actually *built* the thing other executives only talk about. That's worth a lot, both internally at your current employer and externally if you ever decide to move.

The risk in this framing is small but real: hobby projects have a way of consuming weekends without producing the artifacts that *create* the reputation. The discipline you need is to ship publicly — blog posts, demos, conference talks — even if the code is incomplete.

**Verdict: Strong fit. This is the option I'd push you toward.**

### Option (ii): Monetizable side business

The honest case here is weaker than the docs imply. The strategy doc projects $10k MRR by Month 10–12, $100k MRR by Year 2. Those numbers assume you can find 10–20 paying Pro subscribers in the first year. That is plausible only if (a) you've validated specific customers in advance, (b) you're willing to do enterprise sales — which is a 12–18 month cycle for the categories with budget, exactly as Devil's Advocate Failure Mode 5 warns — and (c) you accept that the people who use the product most heavily (academics, journalists, nonprofits) will pay the least.

The vertical-narrow version is more credible than the horizontal platform. If you picked one vertical — say, **CHNA reports for hospital systems**, which is a CMS-mandated artifact that hospitals must produce every three years and that costs $25–75k from consultants — and you built a tool that generates a defensible CHNA from public data with a hospital review layer on top, you might find 5–15 hospital systems willing to pay $5–15k/year in Year 1. That's a $50–200k ARR side business. It's real money. It's also a *very* different product from what's described in the strategy doc.

The unfortunate truth that the docs don't quite confront: the verticals where buyers actually have budget (insurance, hedge funds, large retailers, federal agencies) all have either incumbent vendor relationships, proprietary data requirements that public data alone can't satisfy, or 12–18 month sales cycles. The verticals where you can sell quickly (academics, small nonprofits, journalists) don't have budget. This is not solvable by being smarter; it's a structural feature of the market PolicyMap discovered the hard way over 17 years.

If you go this route, the right move is not to pick from the strategy doc's list of ten verticals. The right move is to make 30 cold calls to people in *one* vertical and find the specific repeated pain that public data plus an opinionated tool would relieve. Then build that. Resist the urge to build the platform first.

**Verdict: Possible, but only after a customer-discovery sprint that has not yet happened. Defer this until the hobby phase has surfaced a real use case.**

### Option (iii): Go all-in as a startup

I would advise against this, and I want to be specific about why because the strategy doc is well-argued and it deserves a serious counter.

**The market timing is wrong, not right.** The strategy doc argues that LLMs and the post-GDPR governance burden make this the moment. That was a defensible thesis in 2023. In 2026, the same forces that make the technology cheap also make the *problem* cheap to solve for everyone else: Google ships it for free, the federal government ships it for free, and every developer with Claude Desktop and a $20/month subscription gets 80% of the way there in an afternoon. The technology that enables you also enables everyone else. The window for a generalist platform play has narrowed considerably since the doc was written.

**Public data is not a moat, and the strategy doc admits it.** Devil's Advocate Section 1 ("Public data is not a moat") is correct, and the proposed durable moats (network effects, switching costs, brand) require either an unusual go-to-market motion or a decade. Venture capital does not fund a decade of moat-building on a thin technology layer.

**The unit economics of an operations-heavy data business are not VC-shaped.** Devil's Advocate Section 9 nails this: 70%+ of your time at scale is monitoring sources, fixing pipelines, responding to data-quality questions. SaaS multiples assume software-like leverage. Information-services multiples are 3–5x revenue. PolicyMap is the proof point. If the realistic outcome is a $5–20M ARR information services business at a 3–5x multiple, the right structure is a bootstrapped or modestly-funded LLC, not a VC-backed startup.

**The opportunity cost is enormous and asymmetric.** You are a senior software executive. Your current compensation, network, and decision-rights are extraordinarily expensive to give up for a project where the *base rate of success* (defined as $5M+ ARR) for similar generalist data platforms over the last 15 years is, charitably, 1 in 50. The asymmetry runs the wrong way: leaving costs you a known, large amount; the upside is a low-probability ceiling that is itself capped by the structural moat problem.

**The downside scenario is not "I lose money" — it's "I spend 18–36 months and emerge with no business and a stale executive resume."** Senior software exec is not a role you can easily walk back into after a two-year gap with a failed startup, especially in a 2026–2028 hiring market that may be soft.

**Verdict: Don't do this. Even the strategy doc's most optimistic case doesn't justify it relative to what you're giving up.**

The narrow exception: if during the hobby phase a *specific* enterprise customer offers to pre-pay for a substantial six- or seven-figure deployment, that changes the math. That is the trigger that should move you from hobby to side-business to potentially full-time, in that order, not skipping steps.

---

## 4. The opportunity cost frame you actually proposed

You framed it cleanly: "Develop as a side hobby to develop skills and reputation while employed, then do something more serious if I am forced or decide to work on my own."

This is the correct frame, and I want to make it sharper:

**The hobby phase is not a holding pattern; it is a real-options strategy.** Each month you spend on this, while keeping your day job, you are buying three things at relatively low cost: cutting-edge skills in LLM-assisted data engineering, a public artifact that increases your option value in the executive job market, and progressive customer discovery that may or may not surface a real business. You are buying optionality. You should optimize the hobby phase to maximize the value of those options.

**That optimization implies specific design choices** that differ from what the strategy doc recommends:

1. **Build narrow and ship publicly.** A working CHNA generator, or a working county risk fingerprint tool, or a working "civic data preservation archive" — pick one. Your Phase 3.5 County Statistical Profile concept is a strong candidate; it's the one screen in the entire PRD that does something the existing free tools don't quite do well.

2. **Make the GitHub repo the resume.** Write the README and the design docs as if they were a tech talk. The governance architecture doc is genuinely good; turn it into a blog post and a conference submission. The data.gov scale-up plan is a great case study in LLM-assisted data engineering; turn it into a public benchmark.

3. **Build an MCP server, not just a REST API.** This is where the world is going. A `datamart-mcp` server that exposes your normalized county profile as a set of MCP tools is exactly the kind of artifact that demonstrates 2026-relevant skills. Be aware that this also makes you a complement to, rather than a competitor of, the federal MCP servers and Google Data Commons — which is the *correct* strategic posture for a project of this size.

4. **Set a budget ceiling and a kill date.** Six to nine months, a few thousand dollars in cloud and LLM spend, and a defined decision point. At month nine: do you have either (a) a paying customer, (b) a clear vertical wedge with three identified prospects, or (c) a public artifact that meaningfully increased your professional optionality? If yes to any one, continue. If no to all three, declare victory on the learning, archive the repo, and move on without sunk-cost guilt.

5. **Treat the strategy and PRD docs themselves as reputation-builders.** They are unusually well-written for a personal project. Publish them. The Devil's Advocate doc in particular — the willingness to write down "here is why this fails" with brutal honesty — is itself a differentiated artifact that will get attention from the kinds of people you want attention from.

---

## 5. Specific narrowings that would change the verdict

If, during the hobby phase, you find yourself drawn to one of these narrowings, the analysis tilts substantially more positive:

**Narrowing A: Civic data preservation in a destabilizing federal environment.** Given the [active disruption of federal statistical agencies](https://www.cbpp.org/research/federal-budget/administrations-radical-personnel-cuts-bypassed-congress-and-lacked) and the documented data-publication slowdowns, a *trustworthy archive* of historical federal datasets — versioned, hashed, attribution-tracked, with the provenance architecture you've already designed — has unusual journalistic, academic, and civic value. This is closer to a 501(c)(3) play than a startup, but it is a legitimate, high-impact use of the work you've already done. Foundations (Knight, MacArthur, RWJF, Sloan) actively fund this kind of infrastructure.

**Narrowing B: Healthcare equity / CHNA tooling.** Hospital systems must produce CHNAs every three years; the data is exactly what you've ingested; the buyer has budget; the regulatory requirement is durable. The vertical is narrow enough that domain expertise is acquirable in 12–18 months. This is the single most defensible commercial wedge in the strategy doc, in my read.

**Narrowing C: Insurance-vertical risk data with a governance differentiator.** Your governance architecture (license-tracked, attribution-injected, audit-logged, schema-drift-detected) is genuinely better than what most data brokers offer. As regulators get more aggressive on AI-driven underwriting (NYC LL144, Colorado SB21-169, the EU AI Act), insurers will need data sources that come with provenance baked in. This is the Verisk/LexisNexis category and it has real budget, but it has 12–18 month sales cycles and requires sales motion that does not feel like a hobby.

**Narrowing D: A structured-output evaluation harness for LLM-on-public-data.** Less a product, more a benchmark. "Here is a public dataset of 100 federal datasets and 500 natural-language queries; here is how Gemini, Claude, GPT, and Grok each perform with and without MCP grounding." This is the kind of artifact that gets cited and shared and creates inbound interest. Low effort relative to the platform play; high reputational ROI.

**Narrowing E: Global subnational entity alignment as open infrastructure.** Devil's Advocate calls this out as the one genuinely open problem ("No one has done global subnational entity alignment at scale"). If you maintained the canonical crosswalks (FIPS ↔ NUTS ↔ districts ↔ municipalities) as a public good — versioned, governed, openly licensed — you become the person every analyst working across countries depends on. This is *Wikipedia for entity codes*. Not a business, but extraordinary career capital.

---

## 6. What I'd specifically do, week by week, for the next 90 days

Concrete because abstract advice is too easy to nod at and ignore.

**Weeks 1–2:** Ship the data.gov catalog scrape (Phase A in DATA_GOV_STRATEGY) and publish the scoring function and top-200 list as a blog post. This is two weekends of work and it produces a citable artifact that no one else has.

**Weeks 3–4:** Build a `datamart-mcp` server exposing the county profile as MCP tools. Submit it to the public MCP registry. Write a comparison post: "What can Claude Desktop answer about a US county with vs without datamart-mcp?" This will attract attention from the MCP community, which is the right audience for the kind of executive reputation-building you're after.

**Weeks 5–8:** Pick one of the five narrowings above and build a thin, opinionated UI on top of the API. My recommendation if pressed: Narrowing A or B. A is mission-aligned and could lead to grant funding; B is the most defensible commercial wedge.

**Weeks 9–12:** Customer-discovery sprint. Cold-email 30 people in your chosen narrowing's customer base. Goal: not sales, but validation. Five 30-minute conversations. If three of them describe the same specific pain you can solve with what you've built, you have a side business. If they don't, you have learning, which was the point.

At the end of 90 days you have: a public artifact that demonstrates 2026-relevant skill (MCP, LLM data engineering, governance-as-code), a customer-discovery dataset that tells you whether there's a real wedge, and a decision point about whether to keep going. None of this requires leaving your day job, raising money, or making the kind of bet the strategy doc implicitly asks you to make.

---

## 7. The single recommendation, restated

**Pursue this as a hobby with an explicit reputation-and-options thesis. Build narrow, ship publicly, and convert to a side business only if a specific paying customer surfaces during customer discovery. Do not quit your day job for this idea, period. Re-evaluate at month 9.**

The strategy doc is well-argued, the technical work is real, the governance architecture is genuinely differentiated, and the Devil's Advocate analysis is honest. All of that is true. And it is also true that the market timing for the platform play has worsened rather than improved since the docs were written, that the closest commercial analog ceilings out at ~$4M revenue, and that the opportunity cost of a senior executive role is large enough that the math doesn't work without a much sharper customer thesis than the docs currently contain.

The good news: nothing about this recommendation requires throwing away the work. The work compounds. It buys you optionality, skills, and reputation at a low marginal cost while you remain employed. If the world reveals a sharper opportunity in 6–12 months — a hospital system that wants to pre-pay, a foundation that wants to fund the civic archive, an insurer that wants to license the governance layer — you'll be perfectly positioned to take it. If it doesn't, you'll have built a remarkable public artifact and learned a set of skills that almost no one else at your level has.

That is, on net, an excellent place to land regardless of what the next 12 months reveal.

---

## Appendix: Sources consulted beyond the six docs

- Google Data Commons Gemini CLI extension launch ([Google Developers Blog, Dec 2025](https://developers.googleblog.com/announcing-the-data-commons-gemini-cli-extension/))
- Data Commons hosted MCP service on GCP ([Google Developers Blog, Feb 2026](https://developers.googleblog.com/access-public-data-insights-faster-data-commons-mcp-is-now-hosted-on-google-cloud/))
- Census Bureau MCP server ([uscensusbureau/us-census-bureau-data-api-mcp on GitHub](https://github.com/uscensusbureau/us-census-bureau-data-api-mcp))
- Federal MCP adoption coverage ([FedScoop, Feb 2026](https://fedscoop.com/federal-goverment-mcp-improve-ai-access-public-data/); [Paubox summary, Feb 2026](https://www.paubox.com/blog/feds-adopt-open-source-protocol-to-connect-ai-chatbots-with-public-data))
- MCP ecosystem statistics ([Digital Applied, April 2026](https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol))
- PolicyMap revenue and headcount ([Growjo company profile](https://growjo.com/company/PolicyMap); [PitchBook profile](https://pitchbook.com/profiles/company/182556-82))
- LexisNexis Location Intelligence for Commercial launch ([PR Newswire, June 2025](https://www.prnewswire.com/news-releases/lexisnexis-risk-solutions-launches-location-intelligence-a-first-of-its-kind-underwriting-solution-for-us-commercial-property-risk-assessment-302485445.html))
- Insurance analytics market size ([Yahoo Finance / Research and Markets, March 2026](https://sg.finance.yahoo.com/news/insurance-analytics-market-triple-size-105400299.html))
- Federal workforce reductions and statistical agency impact ([GAO, Feb 2026](https://www.gao.gov/products/gao-26-108719); [CBPP, Jan 2026](https://www.cbpp.org/research/federal-budget/administrations-radical-personnel-cuts-bypassed-congress-and-lacked); [Wikipedia compilation](https://en.wikipedia.org/wiki/2025_United_States_federal_mass_layoffs))
- Geospatial AI funding context ([Climate Proof, June 2025](https://www.climateproof.news/p/inside-the-geospatial-ai-boom-reshaping-climate-risk-analysis))
