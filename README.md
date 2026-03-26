# S2 Client Operations Template

A clean, reusable workspace template for client delivery operations.

## Purpose

This repository is the public-safe template version of an internal S2 workspace.
It includes folder conventions, starter documents, and light automation scripts
without any client data, transcripts, exports, or sensitive content.

## Quick Start

1. Clone this repository.
2. Run `./scripts/new-client.sh "Client Name"` to create a new client folder.
3. Fill in `context.md` and `context-ai.md`.
4. Add transcripts and deliverables in your private project repo only.

## Layout

- `TEMPLATE_CLIENT/` reusable client folder scaffold
- `docs/` process and policy documents
- `scripts/` helper scripts

## Data Safety Rules

- Never commit real client transcripts.
- Never commit CRM exports (`.csv`, `.xlsx`, `.json` exports).
- Never commit secrets or tokens.
- Use this repo as a template, then do active work in a private repo.
