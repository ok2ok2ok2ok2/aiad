# Architecture

How data moves through an AIAD platform: merchants publish verifiable product data, the platform validates it and attaches weighted reviews, AI agents query it and must present it honestly.

The same architecture in machine-readable form: [`architecture/architecture.ai.json`](architecture/architecture.ai.json).

## Overview

```mermaid
flowchart LR
  M["Merchant"] -->|"hosts"| F["/.well-known/ai-ads.json"]
  F -->|"fetch"| C["Crawler"]
  C --> V{"Validator"}
  V -->|"fails: reject whole file"| M
  V -->|"passes"| I[("Index")]
  M -->|"read-only grant"| O["Order connector<br/>Shopify / WooCommerce / Stripe"]
  O -->|"invite every order"| B["Buyer"]
  B -->|"verified purchase x1.0"| R[("Review store")]
  X["No purchase proof"] -.->|"x0.001, count only"| R
  E["Editorial reviews"] -.->|"listed, not scored"| R
  A["Anomaly detection"] -->|"lowers weights"| R
  T["Tester"] -->|"standard test -> L2"| I
  U["Person"] -->|"asks"| G["AI agent"]
  G -->|"MCP / HTTP query"| Q["Query API"]
  I --> Q
  R --> Q
  Q -->|"data + scores + evidence levels + sponsorship"| G
  G -->|"answers under rules A1-A6"| U
  S["Mystery shopper"] -.->|"audits rule compliance"| G
```

## Three scores

| Score | Measures | Lowered when | Charged to |
|---|---|---|---|
| **S1** product rating | Verified-purchase reviews only | Anomaly detection flags reviews | — |
| **S2** merchant data accuracy | Does the listing match reality | A verified buyer reports "not as described" and it is confirmed | Merchant account |
| **S3** agent rule compliance | Does the agent follow A1–A6 | Mystery-shopper test fails | Account that owns the agent |

## Identity

Every actor is tied to an accountable human account. One rule for everyone: penalties land on the account owner.

| Actor | Bound to | Can | Penalties go to |
|---|---|---|---|
| Buyer | Google account | Review, report "not as described" | Self |
| Merchant | Google account + domain ownership (DNS TXT or token in `ai-ads.json`) | Publish offers, connect order source | Account owner |
| AI agent | API key registered under a Google account | Query, relay | Account owner |

Out of scope for this draft: many Google accounts created from many phone numbers, merchants paying for fake orders (brushing), returns.

## Flow 1 — Publish

```mermaid
flowchart LR
  M["Merchant writes file"] --> F["Hosts it on own domain"] --> C["Platform fetches"] --> V{"Validate"}
  V -->|"pass"| I[("Index")]
  V -->|"fail"| N["Reject whole file, notify merchant"]
```

Validation = JSON Schema + category vocabulary + date checks + domain binding + a scan for text aimed at AI. Run it yourself with [`tools/aiad_validate.py`](tools/aiad_validate.py).

## Flow 2 — Reviews

```mermaid
flowchart LR
  M["Merchant grants read-only order access"] --> O["Platform reads orders"] --> B["Every buyer is invited"] --> R["Review x1.0"]
  R --> A{"Anomaly detection"} --> S1["S1 product rating"]
  B -->|"not as described, confirmed"| S2["S2 penalty"]
```

The platform, not the merchant, sends review invitations. If merchants issued purchase proofs, they could invite only happy customers: every review would be genuine and the score would still be inflated.

## Flow 3 — Answer

```mermaid
flowchart LR
  U["Person asks"] --> G["AI agent"] --> Q["Query: specs, region, price, needs"]
  Q --> D["Returns: offers, S1, S2, editorial reviews, evidence levels, sponsorship"]
  D --> G2["Agent answers: labels paid offers, keeps them out of its ranking, states conflicts"] --> U2["Person"]
```

## Flow 4 — Audit

```mermaid
flowchart LR
  S["Mystery shopper sends test questions"] --> G["Agents answer"] --> J{"Rules A1-A6 followed?"} --> S3["S3 published ranking"]
```

## Flow 5 — Standard tests

```mermaid
flowchart LR
  T["Tester"] --> P["Runs a protocol from vocab/categories.json"] --> L2["Result becomes an L2 claim"] --> I[("Attached to the offer")]
```

Same method for every product in a category, so results can be compared directly. The idea comes from car review platforms that test every car under identical conditions.
