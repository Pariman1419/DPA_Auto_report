# DPA — Obsidian Vault Home

> **DPA** is a QA report management system for semiconductor package reliability testing.
> It generates PowerPoint (PPTX) reports from test data in PostgreSQL and images from a Windows file share.

---

## Navigation

| Hub | What's Inside |
|-----|---------------|
| [[Claude Code]] | Project notes, tech patterns, architecture patterns |
| [[Claude Chats]] | All session transcripts, decisions, and debug logs |

---

## Quick Links

- [[DPA]] — Full project note (status, architecture, routes, known bugs, roadmap)
- [[All Sessions]] — Session index with dates and classifications
- [[Tech Patterns]] — Reusable patterns detected in the codebase
- [[Architecture Patterns]] — System design decisions and structural rules

---

## Project at a Glance

| Item | Value |
|------|-------|
| Backend | FastAPI (Python) · port **9090** |
| Frontend | React 18 + Vite · port **5190** |
| Database | PostgreSQL @ `10.151.28.2` |
| Report output | PPTX via `python-pptx` |
| Auth | JWT in `httpOnly` cookie (`dpa_token`) |
| Status | **Active** — core flows working; UI image fixes in progress |

---

*Vault generated 2026-05-28. See [[DPA]] for full roadmap and [[All Sessions]] for history.*
