# RAGPilot Full Spectrum Test Questions

Use `examples/ragpilot_full_spectrum_test_data.txt` for these questions.

## Semantic RAG

- What does AsterCloud Research Collective do?
- What is ClimateLens used for?
- Explain what HarborFlow does.
- What is the purpose of DocuNest?
- Why does AsterCloud want a retrieval system that avoids huge context windows?

## SQL RAG

- How many active products are listed?
- Which team owns ClimateLens?
- List all speakers for the field event.
- What venue is used for the Secure Field Data Workshop?
- Which endpoint belongs to GuardRail?
- What is the total revenue for 2026-Q2?
- Which product has the highest monthly users?
- How many P1 tickets are open?

## Graph RAG

- Which products depend on ClimateLens?
- Which systems are connected to DocuNest?
- What does GuardRail protect?
- How is FieldPulse connected to CivicBoard?
- Which people work together on incident response?
- Which customers are connected to HarborFlow?

## Keyword / BM25 RAG

- What is SEC-ASTER-404?
- What is HR-ASTER-ONB-12?
- What is the ClimateLens model ID?
- What is the emergency hotline?
- What is the security escalation email?
- What is KEY-GUARD-501?
- What room is Sentinel Room?
- What is the runbook folder?

## Hierarchical RAG

- Summarize the new engineer onboarding policy.
- What happens during week one of onboarding?
- What are the graduation criteria for new engineers?
- Why does the onboarding policy require engineers to understand product dependencies?
- Summarize the security incident policy.

## Hybrid RAG

- Compare ClimateLens and HarborFlow using both product descriptions and structured records.
- Which active products are protected by GuardRail, and who owns them?
- Explain how DocuNest supports customer support using narrative and relationship evidence.
- Which event sessions involve product leaders, and what products or teams are they connected to?
- What should happen if a GuardRail P1 incident occurs, and which ticket examples match that pattern?

## Casual Chat Check

- hi
- thanks
- hello

Expected behavior: RAGPilot should answer casually and skip retrieval.
