# Onboarding

## What you just installed

The installer put this workspace on your Mac, along with Homebrew, Python 3.12, Node, the GitHub CLI
and Claude Code if you did not have them. The workspace is a folder of client folders. Meeting
transcripts go in, and `bin/s2` turns them into a per-client transcript index and `context.md`.
Claude Code runs inside the folder, with three project agents that keep HubSpot work grounded:
`grounder` (what the client said), `portal-reader` (what the portal holds) and `hs-docs` (how
HubSpot works). If you passed `--overlay`, your team's extra agents, skills and commands are linked in.

## First 15 minutes

Run commands from the workspace folder (`hs-solutions-architect-workspace`). VS Code has it open;
use Terminal > New Terminal.

1. **Log in to Claude Code.** Run `claude` once and follow the login prompts.
2. **Fill `.env`.** Re-run `bin/s2 setup` to be prompted for each empty key, or edit `.env` directly.
   Every key is optional; press Enter to skip. See the table below.
3. **Create your first client.** `bin/s2 new client <Name>` makes the folder and a `context.md`. Put
   transcripts in `<Name>/transcripts/` named `YYYY-MM-DD_client_attendees_topic.txt`.
4. **Pull transcripts.** `bin/s2 wrap-up` fetches new Fathom transcripts into `_inbox/`, files and
   indexes them, and refreshes each client's `context.md`. It needs the Fathom keys. Without them, drop
   transcript files into the client folder and run `bin/s2 sync`.
5. **Ask the agents.** In `claude`, name the agent in your request: "Use grounder to find what
   the client said about lead routing", "Use portal-reader to list the deal properties", "Use hs-docs
   to check the limit on custom objects". `bin/s2 help` lists every command.

## Keys

All keys live in `.env` (created by setup, never committed). None are required.

| Key | What it unlocks | Where to get it |
|---|---|---|
| `S2_FATHOM_API_KEY` | `bin/s2 fetch` and `wrap-up` transcript pulls | See Fathom's help docs for creating an API key |
| `S2_FATHOM_RECORDED_BY` | Whose recordings to pull (comma-separated emails) | Your own work email address |
| `ANTHROPIC_API_KEY` | AI summary (`context-ai.md`), smarter transcript names | See Anthropic's help docs for creating an API key |
| `OPENAI_API_KEY` | Same features, as an alternative | See OpenAI's help docs for creating an API key |
| `SLACK_USER_TOKEN`, `SLACK_BOT_TOKEN` | Slack DMs from playbooks (otherwise output prints) | See Slack's help docs for creating an app and tokens |
| `HUBSPOT_ACCESS_TOKEN`, `HUBSPOT_HUB_ID` | HubSpot library scripts (`grab_schema.py`, `grab_workflows.py`) | See HubSpot's help docs for creating a private app token; the Hub ID is your portal ID |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Optional Google Docs MCP (also needs its own `google-docs-mcp` install) | See Google's help docs for creating OAuth credentials |
| `TEAMWORK_SITE`, `TEAMWORK_API_KEY` | Teamwork commands, only if your overlay provides them | See Teamwork's help docs for creating an API key |

HubSpot tokens are per portal, so usually put them in each client folder's own `.env`
(`<Client>/.env`). The scripts read that file first, then fall back to the root `.env`. The scripts
also need `pip install requests python-dotenv`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Python 3.11+ required` | The macOS built-in Python is 3.9. Run `brew install python@3.12`; `bin/s2` finds it on its own. |
| Overlay clone says no access | Ask the overlay's owner for a GitHub collaborator invite, accept it, then re-run the same install line. If `gh auth status` fails, run `gh auth login --web --git-protocol https -h github.com`. |
| `code: command not found` | Not needed. Open `s2.code-workspace` from VS Code (File > Open Workspace from File). |
| Setup stopped or you want to change keys | Re-run `bin/s2 setup`. It never overwrites your files or filled values. Re-running the install line is also safe; it pulls updates. |
| Files go missing or look empty | If the workspace sits in an iCloud-synced Documents folder, macOS may offload files to the cloud. Install into a non-synced folder instead, for example `~/Code`, using `--dir`. |
