Run the GTM Tag Assistant log summarizer on the provided file.

Usage: /gtm <path-to-tag-assistant-export.json>

Execute this command and print the output:

```bash
s2 gtm "$ARGUMENTS" --md
```

The script extracts tag firing data locally without sending the file to an LLM. It outputs:
- Which containers were recorded
- Which tags fired, on which GTM events, and on which pages
- Consent state at time of each firing
- Full event sequence with counts

After printing the summary, offer to highlight any tags that fired before consent was granted (i.e., on gtm.init_consent or gtm.init with "all denied" consent state).
