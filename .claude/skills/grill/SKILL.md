---
name: grill
description: Use when a HubSpot build spec, plan, migration plan, architecture doc, or SOW draft needs its open decisions settled with the user before work starts — "/grill <file>", "grill me on this", "what do you need from me before building", "clarify this spec". Also stage 3 of /hs-build. For a loose idea with nothing written down, use /grill-deep.
---

# Grill (light)

A short interview that settles the decisions a spec leaves open. Adapted from
`grill-deep` (mattpocock/skills `grilling`, MIT) and kept light: 2 rounds of at most 4
questions, with facts looked up rather than asked.

**Input:** a file path (spec, plan, or doc). If none is given, use the most recent spec
discussed in this conversation, and name it.

## 1 · Build the design tree
Read the file. List every decision it makes or implies. For each one, record whether it is
**settled** (a source or a recorded Decision backs it), **factual** (the answer exists in
calls, the SOW, or the portal), or **open** (only the user or the client can decide).

HubSpot builds usually leave these open. Check each one:
1. Derived or manual: is the value computed by a workflow, or set by a person?
2. Object model: which object holds it, and which associations it needs.
3. Existing records: backfill, and what happens to records already in the portal.
4. Failure paths: unknown value, a duplicate, a missing association.
5. After go-live: who owns it on the client side, and which steps are UI-only.

## 2 · Look up the facts yourself
Send every **factual** item out at once, in parallel:
- what was said or agreed → the `grounder` agent
- what is configured or how many records exist → the `portal-reader` agent

For a spec with more than about 10 decisions, also send the file to the `adversary` agent
and add its **Open questions** to the tree.

Don't wait for all of them to come back. Items that depend on a pending lookup stay out of
the round until it returns.

## 3 · Ask the frontier
The frontier is every open decision whose prerequisites are settled. Filter it:
- Drop any question where both answers lead to the same build.
- Rank the rest by blast radius: a wrong answer on object model beats a wrong answer on a
  label.

Ask the top 4 in one `AskUserQuestion` call. For each one:
- header: the decision, in 12 characters or fewer
- question: the decision, plus one line of evidence: `ACME 08-20 [00:14:32] the user: "..."`,
  or `portal: 120 of 400 tickets have no owner`
- options: 2–4 concrete choices, the one the evidence favors first, labeled `(Recommended)`

the user can pick an option or type "Other". A typed answer that opens a new branch goes into
the tree.

## 4 · Second round, then stop
Recompute the frontier with the answers in. Ask at most one more round of 4. Stop when:
- the frontier is empty, or
- everything left is a nit, or
- 2 rounds are done. Anything still open is listed under **Still open**, with the default
  you would build if nobody decides.

## 5 · Record the decisions
Append to the input file, or update its section if one exists:

```markdown
## Decisions
- **<decision>:** <answer>. Source: the user, /grill YYYY-MM-DD | <transcript cite> | portal
- ...

### Still open
- **<decision>:** default if undecided: <choice>. Needs: the user | client (<name>)
```

Settled facts go in with their source. Then show the user only what changed in the spec, and
ask whether it's approved to build. **Approval is the user's explicit yes, not the end of the
grill.**
