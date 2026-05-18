# ReguLens — Project Status

> **Last Updated:** 2026-05-17
> **Updated By:** Kareem Mohammed
> **Version:** v3.0 (Live Deployment — Caveman Prompts execution in progress)

---

## CRITICAL RULES — READ BEFORE TOUCHING ANYTHING

1. **NEVER use "Tech Mahindra" in any output.** Always substitute: **"MNC Client"**
2. **Never `cp -r .` for backups** — it hangs on `node_modules`. Use git tags instead:
   `git add -A && git commit -m "PRE: [description]" && git tag [tag-name]`
3. **Rollback protocol:** `git revert HEAD --no-edit && git push origin main` → wait 90s → verify health endpoint
4. **Render free tier sleeps after 15 min.** Always wake before testing:
   `curl -s https://regulens-api-bnlw.onrender.com/api/health`
5. **frontend-v2 is the ONLY frontend.** The legacy `frontend/` directory has been deleted. Do not recreate it.
6. **All prompts execute against the live site.** There is no localhost testing step.

---

## Live URLs

| Service | URL |
|---|---|
| **API (Render)** | https://regulens-api-bnlw.onrender.com |
| **Health Check** | https://regulens-api-bnlw.onrender.com/api/health |
| **Query Endpoint** | https://regulens-api-bnlw.onrender.com/api/query |
| **Frontend (GitHub Pages)** | https://kmnyc.github.io/ReguLens-TechM/ |
| **Repository** | https://github.com/kmnyc/ReguLens-TechM |

---

## Architecture Overview

**ReguLens** is a Tri-Agentic AI Compliance Intelligence Platform covering EU AI Act, NIST AI RMF, and ISO 42001.

### Three Agents
| Agent | Role | Implementation |
|---|---|---|
| **Agent I — Horizon Ingestion** | Regulatory document ingestion and chunking | FastAPI + Neon pgvector |
| **Agent II — Persona Synthesis** | Query synthesis calibrated to persona threshold | Groq Llama 3.3 70B |
| **Agent III — Zero-Trust Critic** | Claim-level NLI verification with verdict scoring | DeBERTa-v3 / NLI pipeline |

### Persona Thresholds
| Persona | Confidence Threshold |
|---|---|
| `lead_auditor` | 0.96 |
| `legal_counsel` | 0.96 |
| `ml_engineer` | 0.88 |

### Verdict Routing
- **< 30% failure** → RESPOND
- **30–50% failure + retry < 2** → RETRY_RETRIEVE
- **> 50% failure** → GAP_REPORT

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI on Render (free tier) |
| **Database** | Neon PostgreSQL + pgvector |
| **Vector Store** | pgvector (in Neon) |
| **LLM** | Groq Llama 3.3 70B (free tier) |
| **Frontend** | GitHub Pages (static, `frontend-v2/`) |
| **Orchestration** | LangGraph StateGraph (being added — Prompt 2) |
| **Observability** | Opik / Comet (being added — Prompt 3) |
| **Prompt Optimization** | DSPy (being added — Prompt 4) |
| **Audit Trail** | SHA-256 hash-chained `audit_events` in Neon PostgreSQL (being added — Prompt 1) |

### Key Environment Variables (set in Render Dashboard)
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `GROQ_API_KEY` | Groq LLM inference |
| `OPIK_API_KEY` | Opik observability (added in Prompt 3) |
| `OPIK_WORKSPACE` | Opik workspace name (added in Prompt 3) |
| `OPIK_PROJECT_NAME` | Set to `regulens` (added in Prompt 3) |

---

## Repository Structure

---

## Caveman Prompts v3 — Execution Status

**Execution started:** 2026-05-17
**Pre-execution tag:** `pre-caveman-v3` (commit `a900d4e`)
**Current state:** Prompt 1 complete — 2 audit events confirmed, chain intact

| # | Prompt | Risk | Status |
|---|---|---|---|
| **1** | SHA-256 Hash Chain Audit Trail | LOW | ✅ COMPLETE |
| **2** | LangGraph StateGraph | MEDIUM | ⬜ PENDING |
| **3** | Opik Observability | LOW | ⬜ PENDING |
| **4** | DSPy Modules | MEDIUM | ⬜ PENDING |
| **5** | DSPy + Opik Integration | LOW | ⬜ PENDING |
| **6** | End-to-End Validation | NONE | ⬜ PENDING |

### Prompt 1 Acceptance Criteria
- [x] Live POST `/api/query` returns same results as before
- [x] Live GET `/api/audit/verify` returns chain_valid: true
- [x] 2 audit events confirmed with hash chaining
- [x] skip_legacy flag added — pre-existing rows excluded from chain check
- [x] Frontend at https://kmnyc.github.io/ReguLens-TechM/ still works
