# Governance & Regulatory Risk

**Status:** Living document. Laws change. Get qualified legal counsel before entering
each regulated vertical (insurance, healthcare, lending). This document identifies
risks and asks the right questions — it is not legal advice.

---

## Risk Overview

| Risk Area | Severity | Timeline | Affects |
|---|---|---|---|
| Federal data terms of use | Medium | Now | All ingestion |
| Fair use of geographic data (FCRA, FHA, ECOA) | High | Before first paying customer | Insurance, lending, RE customers |
| GDPR / EU data transfer | High | Before EU expansion | All international |
| State privacy laws (CCPA etc.) | Medium | Now (platform users) | User data on our platform |
| HIPAA adjacent risks | Medium | Before healthcare sales | Healthcare vertical |
| Algorithmic fairness / AI Act | Medium | 1–2 years | All ML/scoring products |
| Data licensing / copyright | Medium | Now | Every dataset ingested |
| Government contracting (FedRAMP) | Low–Medium | Year 2+ | Federal sales track |
| Data broker registration | Low | Year 1 | If definition expands |
| Securities / insider trading adjacent | Low | If hedge fund customers | Financial vertical |

---

## 1. Federal Data Licensing — What "Public" Actually Means

**The assumption most people make:** US government data is public domain, so you can do anything with it.

**The reality:** Partially true, and it varies.

**What IS public domain:**
- Works created entirely by US federal employees in their official capacity (17 U.S.C. § 105)
- Census Bureau, BLS, BEA, EPA, CDC, USDA federal datasets are generally public domain
- No copyright, no restriction on commercial use or redistribution

**What is NOT automatically public domain:**
- **State government data** — states are not covered by § 105. California, New York, etc. retain copyright over their data. Many state datasets on data.gov are contributed by states and carry state-level terms.
- **Data with API terms of service** — CDC Socrata API, FCC API, CMS APIs all have ToS. Most permit commercial use with attribution but prohibit misrepresentation of the data source.
- **Third-party data mixed into federal portals** — MIT Election Lab (CC-BY), Vera Institute (CC-BY), Eviction Lab (CC-BY-NC-4.0 — **non-commercial**). Non-commercial licenses are incompatible with a paid product.
- **International government data** — UK ONS, Eurostat, Statistics Canada all retain copyright and have specific open data licenses (usually permitting commercial use with attribution, but read each one).

**Immediate actions:**
- Audit every ingested dataset for its specific license before monetizing
- Track licenses in the `datasets` table (add a `license` and `redistribution_ok` column)
- Flag any CC-BY-NC or similar non-commercial datasets — either exclude from paid tiers or get explicit permission
- For Eurostat: use the `cc-by` licensed products, not the restricted ones
- Read the terms for every Socrata and CMS API used

---

## 2. Fair Use of Geographic Data — The Biggest Legal Risk

This is the highest-stakes area because violations can result in federal enforcement, class actions, and reputational damage.

### FCRA — Fair Credit Reporting Act

**What it is:** The FCRA regulates "consumer reporting agencies" — entities that assemble or evaluate consumer information for use in credit, employment, housing, or insurance decisions.

**The risk:** If a customer uses our data to make or inform decisions about **individual consumers** (credit approval, insurance pricing, employment screening), and our data is a factor in an adverse outcome, we could be deemed a consumer reporting agency — with obligations for permissible purpose, adverse action notices, and dispute rights we are not designed to fulfill.

**Our position:** County-level aggregate data cannot identify individuals. A county's median income is not a "consumer report" on any specific person. But:
- The FTC has taken an expansive view of what constitutes a consumer report
- If a customer **combines** our geographic data with individual data to make individual decisions, FCRA applies to **them**, not us — but we should not facilitate or encourage this
- If we ever offer ZIP-code or census-tract level data, the risk increases sharply

**Mitigation:**
- Terms of Use must explicitly prohibit using our data as a direct input into individual-level credit, employment, housing, or insurance decisions
- Add this to customer agreements as a hard restriction
- Do not market the product for individual screening use cases

### Fair Housing Act & ECOA — Redlining Risk

**What it is:** It is illegal to discriminate in housing or lending based on race, color, national origin, religion, sex, familial status, or disability. Geographic data can be a proxy for race.

**The risk:** If a mortgage lender, landlord, or insurer uses our geographic data (census tract demographics, poverty rates, crime rates) to deny loans, set insurance rates, or reject rental applications in ways that correlate with race — that is digital redlining, and both the customer and potentially the data provider can face liability.

**Real precedents:**
- HUD sued Facebook in 2019 for allowing advertisers to exclude users by "ethnic affinity" in housing ads
- CFPB has issued guidance on using zip codes in credit models
- Illinois, California have enacted laws restricting geographic factors in insurance pricing

**Mitigation:**
- Terms of Use must prohibit use of our data for individual housing, credit, or insurance decisions that discriminate on protected characteristics
- When selling to insurance or lending customers specifically, require them to represent that they have their own fair lending compliance program
- Do not build products specifically designed for individual-level insurance underwriting or lending decisions without counsel
- Document our data does not include race at individual level (we have aggregate % by county, which is different)

### State Insurance Regulations

Insurance is **state-regulated**. Each of the 50 states has its own insurance department with its own rules on rating factors.

- **Price optimization bans:** 20+ states prohibit using non-risk-correlated factors (including geographic factors correlated with income) in insurance pricing
- **Geographic rating restrictions:** Some states restrict or ban using zip codes or counties as primary rating factors
- **Credit score bans:** Several states ban credit-based insurance scores for auto or home insurance
- California, Michigan, Massachusetts are among the most restrictive

**Mitigation:**
- When building for insurance customers, the product should surface data and let the insurer handle compliance with their state regulations
- Do not create pre-built "risk scores" that claim to be insurance-grade without actuarial certification and state approval
- Frame our data as research/analysis inputs, not rating factors

---

## 3. GDPR and International Privacy

**The moment we have EU customers or process data about EU residents, GDPR applies.**

### Key Principles That Affect Us

**Lawful basis:** We need a lawful basis to process any personal data. For aggregate county-level data about the US, this is not an issue — it is not personal data. For data about EU residents at fine granularity, it becomes one.

**Data minimization:** Only collect what's necessary. This affects our user data (API key holders, dashboard users), not the geographic data itself.

**Right to erasure:** Applies to user accounts, not to published government statistics. But if a user wants their account deleted, we must honor it.

**Data transfer restrictions (Chapter V / Schrems II):** Transferring EU personal data to US servers requires either:
- Standard Contractual Clauses (SCCs) — the standard mechanism, requires a Transfer Impact Assessment (TIA)
- EU-US Data Privacy Framework (the current adequacy decision, certified July 2023 — may face legal challenge)
- Binding Corporate Rules (complex, for large multinationals)

For **aggregate government statistics about EU geographies** (Eurostat NUTS data), this is not an issue — it is not personal data. For **user data of EU customers** using our platform, SCCs are the right mechanism.

**For the UK:** Post-Brexit, UK has its own "UK GDPR" — nearly identical, separate adequacy decision. Treat the same as EU.

### GDPR for the Data Itself (Geographic Aggregates)

Eurostat and ONS data is **not personal data** — it describes geographic regions, not individuals. GDPR does not apply to the data itself.

**Exception:** At very fine granularity (census tract level with demographic breakdowns), there is a theoretical re-identification risk for small populations. For county-level, this is not a concern. For tract-level, apply statistical disclosure review (suppress cells with <3 residents, which the Census Bureau already does).

### Practical steps before EU launch:
- Draft Privacy Policy covering GDPR rights for EU users
- Implement SCCs for any EU user data stored on US servers
- Appoint a GDPR representative in the EU (required if no EU establishment)
- Conduct a legitimate interests assessment (LIA) or identify appropriate lawful basis for user data
- Register with relevant Data Protection Authority if required by member state

---

## 4. State Privacy Laws (US)

The US has no federal comprehensive privacy law but a growing patchwork of state laws:

| State | Law | Effective | Key Threshold | Applies to Us |
|---|---|---|---|---|
| California | CCPA / CPRA | 2020 / 2023 | 100k consumers OR $25M revenue | Yes — CA users of platform |
| Virginia | VCDPA | 2023 | 100k consumers | Yes if VA users |
| Colorado | CPA | 2023 | 100k consumers | Yes if CO users |
| Texas | TDPSA | 2024 | All sizes processing personal data | Yes if TX users |
| Connecticut, Utah, Oregon, Montana | Various | 2023–2024 | Similar thresholds | Watch |

**What this means for us:** These laws govern how we handle **user personal data** (name, email, API usage data, billing info) — not the geographic aggregate data we serve. But we must:
- Have a privacy policy that discloses what user data we collect
- Offer opt-out of "sale" of personal data (even if we don't sell it, the definition is broad)
- Honor deletion requests
- Conduct data protection assessments for high-risk processing

**The aggregate geographic data we serve is generally not personal data under any state law** — county-level statistics do not identify individuals. This is our strongest protection.

---

## 5. HIPAA — Adjacent Risk in Healthcare Vertical

HIPAA protects **individually identifiable health information (PHI)**. County-level health statistics (CDC PLACES county obesity rate = 32%) are **not PHI** — they describe a population, not an individual.

**Where risk arises:**

**Business Associate Agreements (BAAs):** If a hospital system uses our platform to analyze their patient populations alongside our public data, and they share any PHI with us in the process, we become a Business Associate and HIPAA applies to us. We must never allow customers to upload PHI to our platform without a BAA in place.

**Mental health and substance use data:** 42 CFR Part 2 provides extra protections for substance use disorder records — stricter than HIPAA. SAMHSA data we ingest is aggregate (facility counts, not patient records), so this does not apply. But a healthcare customer using our API alongside 42 CFR-protected data must manage that on their end.

**Practical steps for healthcare vertical:**
- Platform Terms must prohibit uploading PHI
- If a hospital wants to use our API to enrich their internal patient analytics, require a BAA before providing that service
- Frame our platform as providing population-level context, not patient-level analysis
- Get healthcare counsel review before the first hospital system contract

---

## 6. Algorithmic Fairness and AI Regulations

A rapidly evolving area. Three years ago this was academic; today it carries real legal risk.

### EU AI Act (Effective 2025–2026)

The EU AI Act classifies AI systems by risk level. **High-risk** systems include those used in:
- Credit scoring and creditworthiness assessment
- Insurance underwriting
- Employment screening
- Access to essential services

If a customer uses our data as an input to a high-risk AI system, **they** bear the primary compliance burden. But if we offer a pre-built scoring product (e.g., a "community risk score"), it may itself be classified as high-risk.

**Mitigation:** Frame our product as raw data infrastructure, not a decision-making system. Let customers build models on top of our data; don't pre-bake scoring into the product until we understand the regulatory environment.

### US Algorithmic Accountability

- **NYC Local Law 144 (2023):** Employers in NYC using automated employment decision tools must conduct annual bias audits. Customers using our data in hiring models must comply.
- **CFPB guidance:** Has signaled scrutiny of "black box" models in credit decisions that use geographic proxies for protected characteristics
- **FTC:** Has broad authority under Section 5 (unfair or deceptive practices) to regulate AI that causes harm, including discriminatory outcomes from geographic data

### Practical implications:

If we build a "county risk score" for insurance or lending, we need:
- Disparate impact analysis (does the score correlate with race/protected class?)
- Documentation of the methodology
- An adverse action process if used in individual decisions

If we only provide the raw data and the customer builds the score, this burden falls on them. The design decision of "data infrastructure" vs "scoring product" is not just a product choice — it's a compliance choice.

---

## 7. Government Contracting — FedRAMP

To sell software services to US federal agencies, FedRAMP authorization is typically required.

**What it involves:**
- A security assessment against NIST SP 800-53 controls (hundreds of controls)
- Authorization by a federal agency sponsor or through the FedRAMP Marketplace
- Ongoing continuous monitoring
- Cost: $100k–500k for initial assessment + ongoing annual costs
- Timeline: 6–18 months minimum

**When to start thinking about this:** When federal agency sales become a realistic near-term goal (Year 2–3). Prioritize commercial sales first.

**Shortcut:** Partner with a FedRAMP-authorized cloud platform (AWS GovCloud, Azure Government) to host the government-facing product. This satisfies the infrastructure layer; we still need application-level authorization but the timeline shrinks.

**Section 508 Accessibility:** Federal contracts also require that software meets Section 508 accessibility standards (WCAG 2.1 AA equivalent). Build this into the dashboard from the start — retrofitting is expensive.

---

## 8. Data Sovereignty and Cross-Border Concerns

| Country/Region | Key Rule | Practical Impact |
|---|---|---|
| **EU** | GDPR Chapter V — data transfer restrictions | SCCs required for EU user personal data on US servers. Aggregate geographic data is not affected. |
| **Germany** | Strict interpretation of GDPR + BSI security requirements | Some German enterprise customers may require EU data residency. |
| **China** | Cybersecurity Law, Data Security Law, PIPL | Cannot operate in China without data localization. Not worth pursuing until substantial scale. |
| **Russia** | Roskomnadzor data localization | All Russian user data must be stored in Russia. Avoid entirely. |
| **India** | DPDP Act (2023) | Personal data localization coming. Aggregate public data not affected. |
| **Canada** | PIPEDA + provincial laws (Quebec Law 25 strictest) | Similar to GDPR for user data. Aggregate Statistics Canada data is fine. |
| **Brazil** | LGPD (similar to GDPR) | User data requires lawful basis. Aggregate IBGE data is fine. |

**For aggregate government statistics:** Data sovereignty is generally not an issue. A German county's unemployment rate is public information — Germany doesn't restrict its publication abroad.

**For user data:** Host EU customer personal data on EU servers (AWS eu-west or similar). This satisfies most EU data residency concerns without full multi-region architecture complexity.

---

## 9. Open Data Licenses — Track Every Dataset

| License Type | Commercial Use? | Redistribution? | Share-Alike? | Action Required |
|---|---|---|---|---|
| US Federal (§ 105) | ✅ Yes | ✅ Yes | ❌ No | None — public domain |
| CC-BY 4.0 | ✅ Yes | ✅ Yes | ❌ No | Attribute the source |
| CC-BY-SA 4.0 | ✅ Yes | ✅ Yes | ✅ Yes | Derivative work must also be CC-BY-SA — **review carefully** |
| CC-BY-NC 4.0 | ❌ No commercial | ✅ Yes | ❌ No | **Cannot use in paid product without permission** |
| ODbL (Open Database License) | ✅ Yes | ✅ Yes | ✅ Yes | Derivative database must remain ODbL — **review carefully** |
| Custom government terms | Varies | Varies | Varies | Read each dataset's terms individually |

**Datasets to audit immediately:**
- Eviction Lab: CC-BY-NC — **non-commercial**. Cannot include in paid API tiers without contacting Princeton.
- MIT Election Lab: CC-BY — commercial OK, attribution required.
- Vera Institute: CC-BY — commercial OK.
- Eurostat: Custom open license permitting commercial use with attribution.
- ONS (UK): Open Government License v3 — commercial OK, attribution required.

**Practical implementation:**
- Add `license_spdx`, `attribution_required`, `commercial_ok`, `share_alike` columns to `datasets` table
- Surface attribution strings in API responses (`_attribution` field per source key)
- Block datasets with `commercial_ok = false` from paid API tiers

---

## 10. Specific Sector Watch List

### Financial Services
- **FCRA** — described above. Most critical for any individual-level decision use case.
- **GLBA (Gramm-Leach-Bliley Act)** — financial institutions that are customers have their own data security obligations when using our API.
- **CRA (Community Reinvestment Act)** — our data can actually help banks document CRA compliance. Opportunity, not risk.

### Real Estate
- **Fair Housing Act** — geographic data as a proxy for protected class. Same redlining risk as lending.
- **RESPA (Real Estate Settlement Procedures Act)** — doesn't directly apply to data, but real estate customers need to be aware.

### Healthcare
- **HIPAA** — no PHI on our platform. BAA required if customers want to bring their PHI.
- **State health data privacy laws** — some states (Texas, California) have health data privacy laws stricter than HIPAA.

### Government / Public Sector
- **FedRAMP** — required for federal cloud services.
- **State and local procurement rules** — vary by jurisdiction; often require vendor registration.

---

## 11. What To Do Now vs. Later

### Do Now (before first paying customer)
- [ ] Audit all ingested datasets for license type; add license tracking to `datasets` table
- [ ] Draft Terms of Use prohibiting use of data for individual-level credit, insurance, or housing decisions
- [ ] Draft Privacy Policy covering platform user data under CCPA/state privacy laws
- [ ] Flag all CC-BY-NC or ODbL datasets as restricted in paid tiers
- [ ] Add `_attribution` metadata to API responses for CC-BY licensed sources

### Do Before Healthcare/Insurance Vertical (Year 1)
- [ ] Engage healthcare/insurance regulatory counsel for vertical-specific terms
- [ ] Draft Business Associate Agreement template for healthcare customers
- [ ] Disparate impact documentation for any pre-built scoring features
- [ ] Review state insurance regulations in target markets before selling insurance underwriting use cases

### Do Before EU Launch (Year 2)
- [ ] Implement Standard Contractual Clauses (SCCs) for EU user data
- [ ] EU data residency for user personal data (EU-hosted infrastructure)
- [ ] Appoint EU GDPR representative
- [ ] License audit for all Eurostat and European open data sources
- [ ] Update Privacy Policy for GDPR compliance

### Do Before Federal Sales (Year 2–3)
- [ ] FedRAMP readiness assessment
- [ ] Section 508 accessibility audit of dashboard
- [ ] SAM.gov registration
- [ ] CAGE code and DUNS/UEI number

### Monitor Continuously
- EU AI Act implementation guidance (effective 2025–2026 by risk tier)
- State algorithmic accountability laws (NYC model spreading to other jurisdictions)
- FTC enforcement actions on data brokers and geographic data use
- CFPB guidance on machine learning in credit decisions
- State data broker registration expansion
