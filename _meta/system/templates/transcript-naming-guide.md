# Transcript Naming Convention

## Format

```
[YYYY-MM-DD]_[client-name]_[topic-keywords].txt
```

## Components

1. **Date:** `YYYY-MM-DD` format (e.g., `2026-02-09`)
2. **Client Name:** Lowercase (e.g., `acme`, `globex`)
3. **Topic Keywords:** Descriptive topic (e.g., `weekly-sync`, `discovery-integrations`, `rep-mapping`)

## Examples

- `2026-02-09_acme_weekly-sync.txt`
- `2026-01-15_globex_discovery-integrations.txt`
- `2026-02-03_acme_rep-mapping.txt`

## Transcript Content Structure

Each transcript file should include:

1. **Header:** Date, attendees, duration, recording link (if available)
2. **Summary:** 2-3 sentence summary of the call (if provided by Fathom)
3. **Full Transcript:** Complete transcript text

## Processing

When a transcript is added to a client's `transcripts/` folder:
- The context update script will automatically:
  - Add it to the transcript index
  - Update the context.md file with the new transcript entry
  - Extract key decisions and action items (if summary is available)
