# Client A — AWS to GCP Migration

#project #client #architecture

## Status

In progress. Phase 1 (analysis and plan) complete. Phase 2 (pipeline migration) underway.

## Context

Client A is a digital media company with a data platform built on AWS (S3, Redshift, Glue). They want to migrate to GCP (BigQuery, Dataflow, Cloud Storage) primarily for cost savings and better native ML support.

## Current architecture (AWS)

```
S3 (raw) → Glue ETL → Redshift → Tableau
                ↓
           SageMaker (recommendation models)
```

## Proposed architecture (GCP)

```
Cloud Storage (raw) → Dataflow → BigQuery → Looker Studio
                          ↓
                    Vertex AI (recommendation models)
```

## Identified risks

1. **S3 egress cost**: moving ~40 TB could cost $3,600 USD. Negotiate waiver with AWS.
2. **Redshift → BigQuery**: different SQL dialect, ~200 production queries need rewriting.
3. **SageMaker → Vertex AI**: models are in pkl format, need retraining or different serialization.
4. **Downtime**: client cannot tolerate more than a 4-hour maintenance window.

## Timeline

- **2026-05-15** — Phase 1 complete ✓
- **2026-06-30** — Phase 2: batch pipeline migration
- **2026-07-31** — Phase 3: ML model migration
- **2026-08-15** — Go-live and handoff

## Contacts

- Eng lead: Roberto V.
- PM: Carla M.
- Weekly meeting: Tuesday 8 AM

## Notes from last meeting (2026-05-20)

Aligned on Phase 2 scope. Roberto confirmed two engineers are available to help. Pending: define the rollback strategy if something breaks in production.
