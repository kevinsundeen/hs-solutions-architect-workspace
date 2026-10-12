Run the GTM workspace/container export summarizer on the provided file.

Usage: /gtm-workspace <path-to-workspace-export.json>

Execute this command and print the output:

```bash
s2 gtm-workspace "$ARGUMENTS" --md
```

The script extracts the full container config locally without sending the file to an LLM. It outputs:
- Container metadata (public ID, name, version)
- All active tags grouped by folder, with firing triggers, blocking triggers, and consent requirements
- Paused tags (flagged separately — these are inactive but still in the container)
- All triggers grouped by type, with their firing conditions
- All variables by type
- Custom templates

After printing the summary, offer to:
1. List all tags that have no consent check set (potential compliance gaps)
2. List tags in folders named "Paused" or "Recommend removal" that are still technically active
3. Cross-reference against a Tag Assistant log if the user has one
