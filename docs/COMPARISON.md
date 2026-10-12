# AIAD vs. ACP and UCP

*Retrieved 2026-10-12. Specs move fast: re-check every field below against the linked sources before you quote it in a proposal.*

## 1. Positioning

OpenAI/Stripe's **Agentic Commerce Protocol (ACP)** and Google's **Universal Commerce Protocol (UCP)** already define how merchants hand product data to AI agents and how agents complete a purchase. AIAD does not compete with them. It adds a **trust layer** they do not define: who a product is *not* for, how much evidence backs each claim, how paid placement is disclosed to the human, how reviews are weighted by proof of purchase, and rules for how an agent must present all of this. The goal is to propose AIAD's fields as an optional extension to ACP and UCP, not to replace them.

There are two different "ACP feeds", and they are compared separately below:
- **OpenAI product feed spec** (developers.openai.com): the flat field list merchants send to ChatGPT shopping.
- **ACP repo feed schema** (`spec/2026-04-17/json-schema/schema.feed.json`): the protocol's JSON Schema with `Product` and `Variant` objects. Both objects set `additionalProperties: false`, so new fields need a spec change or an extension.

## 2. Field mapping

| AIAD field | OpenAI product feed | ACP `schema.feed.json` (2026-04-17) | UCP catalog Product |
|---|---|---|---|
| `offers[].id` | `item_id` | `Product.id` / `Variant.id` | `id` |
| `title` | `title` | `title` | `title` |
| `summary` (facts only, ≤280 chars) | `description` (no facts-only rule) | `description` | `description` |
| `url` | `url` | `url` | `url` |
| `price` (decimal **string** + ISO 4217) | `price`, `sale_price` | `Variant.price`, `list_price`, `unit_price` | `price_range`, `list_price_range` |
| `price.conditions` | none (`sale_price_effective_date` covers dates only) | none | none |
| `region` | `target_countries` (requires setup) | `target_country` in feed metadata only | none seen |
| `specs[]` with a shared category vocabulary and units | partial: `material`, `color`, `size`, `weight`, `dimensions`… | partial: `variant_options`, `condition`, `categories` | `options`, `tags`, `metadata` (free-form) |
| `claims[]` with evidence level L0–L3 | **none** | **none** | **none** |
| `suitable_for[]` | **none** (`age_group`, `gender` are attributes) | **none** | **none** |
| `not_suitable_for[]` (required) | **none** | **none** | **none** |
| `valid_from` / `valid_until` | `expiration_date`, `availability_date` | none | none seen |
| `sponsorship` (paid, payer, disclosure text) | **none** for disclosure. `is_ads_eligible` and `ads_metadata` control ad processing, not what the human is told | **none** | **none** |
| Reviews: verified purchase (weight 1.0) | **none**. Only aggregate `review_count`, `star_rating`, `store_review_count`, `store_star_rating`; no proof-of-purchase distinction | **none** | `rating` {`value`, `scale_min`, `scale_max`, `count`}; no proof-of-purchase distinction |
| Reviews: unverified (weight 0.001) | **none** | **none** | **none** |
| Reviews: editorial (listed, not scored) | **none** | **none** | **none** |
| Agent presentation rules (A1–A8) | none | none | none |
| Instruction-injection rule for merchant text (P1–P4) | none found | none found | none found. UCP has request signatures, which prove who sent data, not whether text tries to instruct the agent |

The OpenAI feed reference states explicitly that "raw review entries and question-and-answer lists are not part of this discovery contract".

## 3. What AIAD adds

1. **`not_suitable_for` (required).** Every offer must name at least one person or situation it does not fit. This lets an agent filter honestly.
2. **Evidence levels on claims.** L0 is the seller's word, L1 the seller's own document, L2 a named third-party test, L3 a registry entry with a reference number. Agents word each claim by its level.
3. **Sponsorship disclosure to the human.** Covers whether an offer is paid, who paid, and the exact label. Paid offers may not change organic ranking (rule A2).
4. **Review weighting by proof of purchase.** Proof comes from the platform reading the merchant's order source read-only and inviting *every* buyer, so merchants cannot cherry-pick. Unverified reviews count 0.001, and editorial reviews are listed but never scored.
5. **Shared spec vocabulary and standard test protocols per category.** A test run by a named tester becomes an L2 claim.
6. **Agent rules A1–A8 and a public compliance score (S3)** from mystery-shopper tests.
7. **Decimal-string prices** (`"19.90"`, never a float).

## 4. Integration sketches

### 4a. ACP: optional feed fields (SEP candidate)

The ACP feed `Product`/`Variant` objects are closed (`additionalProperties: false`), so this needs a SEP. ACP's extension framework (`schema.extension.json`) allows third-party reverse-domain extensions such as `com.example.custom`, but its examples only extend checkout objects (`$.CheckoutSession.discounts`). Whether feed objects can be extended this way is **unverified**.

Proposed optional fields, added to `Product`:

```jsonc
"trust": {
  "not_suitable_for": ["string"],          // ≥1 when "trust" is present
  "suitable_for":     ["string"],
  "claims": [{
    "statement": "string",
    "level": "L0|L1|L2|L3",
    "evidence_url": "uri",                 // required for L1–L3
    "verifier": "string",                  // required for L2–L3
    "reference_id": "string",              // required for L3
    "expires": "date"
  }],
  "sponsorship": { "paid": "boolean", "payer": "string", "disclosure": "string" },
  "reviews": {
    "verified_purchase": { "count": "integer", "score": "number|null" },
    "unverified_count": "integer"
  },
  "valid_until": "date-time"
}
```

### 4b. UCP: vendor extension of the catalog capability

UCP allows vendor capabilities under the vendor's own reverse-domain namespace. The `dev.ucp.*` namespace is reserved for the UCP governing body. An extension declares its parent with `extends`, and its schema must include a `$defs` entry for each parent. A declared schema URL's origin **must match** the namespace authority, otherwise platforms must reject it.

Sketch for the business profile at `/.well-known/ucp`:

```json
"<reverse-domain>.aiad.trust": {
  "version": "2026-10-12",
  "spec": "https://<domain>/aiad/spec",
  "schema": "https://<domain>/aiad/trust.schema.json",
  "extends": ["dev.ucp.shopping.catalog.search", "dev.ucp.shopping.catalog.lookup"]
}
```

- **Blocker: the namespace needs a domain the authors own.** That domain is still to be decided. A `github.io` origin would only work if the reverse-domain matched it, which is **unverified**.
- Shopify's `dev.shopify.catalog` extension of the same two catalog capabilities is a working precedent for adding product fields.
- UCP Product also has a free-form `metadata` field ("business-defined custom data"). It could carry AIAD data without any extension, but agents would have no contract to rely on, so this is a fallback only.
- The parent capability names above are taken from Shopify's extension docs. Confirm them against ucp.dev before use.

## 5. Where to propose

| | ACP | UCP |
|---|---|---|
| Repo | https://github.com/agentic-commerce-protocol/agentic-commerce-protocol (Apache-2.0, about 1.6k stars) | https://github.com/Universal-Commerce-Protocol/ucp (Apache-2.0, about 3.4k stars) |
| Start here | GitHub Discussions: https://github.com/agentic-commerce-protocol/agentic-commerce-protocol/discussions | GitHub Discussions: https://github.com/Universal-Commerce-Protocol/ucp/discussions |
| Formal process | **SEP**: a GitHub Issue tagged `SEP` and `proposal`. Needs a sponsor (Founding Maintainer), and is closed as dormant after 3 months without one. Required sections: Preamble, Abstract, Motivation, Specification (with PR), Rationale, Backward Compatibility, Reference Implementation, Security Implications. Acceptance needs a prototype implementation, clear ecosystem benefit and community consensus. | **Enhancement Proposal** (issue template `enhancement-proposal.yml`). Required for any JSON schema change. Template sections: Summary, Motivation, Detailed Design, Risks, Test Plan, Graduation Criteria. Tech Council votes it from Proposal to Provisional to Implemented. |
| CLA | **Required**: CLA Assistant bot on the first PR | **Required**: Google CLA (https://cla.developers.google.com/) |
| No CLA needed for | Discussions, issues | Discussions, issues; a vendor extension under your own namespace needs no approval at all |

Suggested order: open a Discussion in each repo that links this file and the AIAD validator. Ship the UCP vendor extension first, because it needs no approval, only a domain. Then write the ACP SEP once someone offers to sponsor it.

## 6. Sources

- OpenAI product feed spec: https://developers.openai.com/commerce/specs/feed/
- OpenAI commerce docs (LLM-readable): https://developers.openai.com/commerce/llms-full.txt
- ACP repo: https://github.com/agentic-commerce-protocol/agentic-commerce-protocol
- ACP feed schema: https://github.com/agentic-commerce-protocol/agentic-commerce-protocol/blob/main/spec/2026-04-17/json-schema/schema.feed.json
- ACP extension schema: https://github.com/agentic-commerce-protocol/agentic-commerce-protocol/blob/main/spec/2026-04-17/json-schema/schema.extension.json
- ACP SEP guidelines: https://github.com/agentic-commerce-protocol/agentic-commerce-protocol/blob/main/docs/sep-guidelines.md
- ACP CONTRIBUTING (CLA): https://github.com/agentic-commerce-protocol/agentic-commerce-protocol/blob/main/CONTRIBUTING.md
- UCP spec overview (extensions, namespaces): https://ucp.dev/specification/overview/
- UCP schema reference (catalog Product): https://ucp.dev/specification/reference/
- UCP repo: https://github.com/Universal-Commerce-Protocol/ucp
- UCP CONTRIBUTING (CLA, Enhancement Proposals): https://github.com/Universal-Commerce-Protocol/.github/blob/main/CONTRIBUTING.md
- Shopify `dev.shopify.catalog` extension: https://shopify.dev/docs/agents/catalog/storefront-catalog-extension

### Not verified
- The full UCP `Variant` field list (the reference page was truncated).
- Whether ACP's extension framework can target feed objects.
- Exact UCP catalog capability names. They come from Shopify docs, not ucp.dev.
- Whether UCP's `lodging` vertical (`docs/specification/lodging/`) has fields relevant to suitability.
