# HubSpot Solutions Architect Workspace

A workspace for HubSpot solutions architects, built on VS Code and Claude Code. Meeting transcripts
turn into a per-client index and `context.md`, so you can ramp back up on any client in minutes.
Project agents and skills keep HubSpot builds grounded in what the client said and what the portal
actually holds.

## Start here

1. Install VS Code from https://code.visualstudio.com.
2. Open Terminal and paste this line. It installs what is missing, downloads the workspace, and runs setup:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/kevinsundeen/hs-solutions-architect-workspace/main/install.sh | bash -s -- --overlay <owner>/<private-overlay-repo>
   ```

   The `--overlay` part is optional: it adds a team's private overlay repo, and the person who invites you sends the full line. Without an overlay, drop everything from `--` onward (keep `| bash`).
3. When VS Code opens, read `ONBOARDING.md`.

## Manual setup

You need Python 3.11+, Git, the Claude Code CLI (`npm install -g @anthropic-ai/claude-code`), and
VS Code with its `code` command on your PATH (or just open `s2.code-workspace` from VS Code).
The GitHub CLI (`gh`) is optional. The HubSpot library scripts need `pip install requests python-dotenv`.

```bash
git clone https://github.com/kevinsundeen/hs-solutions-architect-workspace.git
cd hs-solutions-architect-workspace
code s2.code-workspace
bin/s2 setup
```

`bin/s2 setup` creates `.env` from `.env.example`, writes `.mcp.json`, and runs a smoke test on a
throwaway `Demo` client. Expect `✓ smoke test PASS`. Setup is safe to re-run.

## Daily loop

1. `bin/s2 wrap-up` pulls new Fathom transcripts into `_inbox/`, renames and indexes them, and
   refreshes every client's `context.md`.
2. `bin/s2 context <client>` gives a full refresh for one client (AI summary if a key is set).
3. Open the folder in Claude Code and ask. Use the agents: `grounder` for what the client said,
   `portal-reader` for what the portal holds, `hs-docs` for how HubSpot works.

New client: `bin/s2 new client <Name>`. Search transcripts: `bin/s2 find <client> "query"`.
Run `bin/s2 help` for every command.

## What's inside

| Path | Purpose |
|---|---|
| `bin/s2` | Command entry point; dispatches to `_meta/scripts/` |
| `_meta/scripts` | Python (stdlib only, except the HubSpot library): transcript indexing, context, setup, playbooks, Drive linkage, tests |
| `_meta/library/hubspot` | HubSpot API client, schema puller, workflow grabber, reference docs |
| `.claude/agents` | `grounder`, `portal-reader`, `hs-docs`, `classifier`, `builder`, `adversary`, `shipper` |
| `.claude/skills` | `hs-build`, `grill`, `grill-deep`, `portal-discovery`, `context-update` |
| `.claude/commands` | `/gtm`, `/gtm-workspace`, `/marketo`, `/schema`, `/workflows` |
| `.vscode` | Workspace settings, extension list, tasks |

## Keys

Every key is optional. Put them in `.env`; each one unlocks a feature.

| Key | Unlocks |
|---|---|
| `S2_FATHOM_API_KEY`, `S2_FATHOM_RECORDED_BY` | `s2 fetch` and `s2 wrap-up` transcript pulls |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | AI context summary (`context-ai.md`), smarter transcript names |
| `SLACK_USER_TOKEN`, `SLACK_BOT_TOKEN` | Slack DMs from playbooks (otherwise output prints) |
| `TEAMWORK_SITE`, `TEAMWORK_API_KEY` | Teamwork commands from an overlay |
| `HUBSPOT_ACCESS_TOKEN`, `HUBSPOT_HUB_ID` | HubSpot library scripts (`grab_schema.py`, `grab_workflows.py`). Put them in the client folder's `.env`; the scripts look there first, then in the root `.env` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Optional Google Docs MCP (`.mcp.json.example`); it also needs its own `google-docs-mcp` install |

Tracked files are limited to the template; client folders stay local (see `.gitignore`).

## Overlays

A team can keep company-specific agents, skills, and commands in a private overlay repo, cloned
next to this one (for example `../s2-workspace-overlay`). Run
`bin/s2 setup --overlay ../s2-workspace-overlay` to symlink its `agents/`, `skills/`, and
`scripts/` into this workspace. Each `scripts/cmd/<name>.sh` becomes the command `s2 <name>`.
Access to a team's private overlay is granted by its owner via a GitHub collaborator invite.
