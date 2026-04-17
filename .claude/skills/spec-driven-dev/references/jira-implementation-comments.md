# Jira implementation comments (spec-grounded)

This reference describes **how to write and post structured implementation comments** on Jira issues during **Phase 4 — Closure** of spec-driven development. It complements **[jira-operations.md](jira-operations.md)** (MCP tool names and fields).

---

## Goals

- Tie each Jira comment to **repository truth**: the **`specs/`** tree, **branch**, **changed files**, and **tests**.
- Make QA and reviewers able to verify work without opening the PR first.
- Support **one ticket → one spec folder**, **one spec → several tickets** (e.g. user stories), and **umbrella tickets** that span multiple caveats.

---

## When to use

- After implementation is merged or ready for review, when the developer asks to **document what was done on Jira**.
- When posting **one comment per issue** for a batch of related keys (e.g. `PROJ-162`, `PROJ-166`, `PROJ-167`).

---

## Prerequisites

1. **Valid Jira issue key(s)** and **Atlassian MCP** configured (Cursor: `plugin-atlassian-atlassian`; Claude Code: Atlassian integration).
2. **`cloudId`** for the site: use **`getAccessibleAtlassianResources`** (or the team’s documented UUID) — do not guess.
3. **Tool schema**: before calling **`addCommentToJiraIssue`**, read the MCP tool descriptor for **`commentBody`**, **`contentFormat`** (`markdown` recommended), and required IDs.

---

## Procedure

### 1. Locate the spec directory for this work

The canonical artifact root is:

```text
specs/<NNN-short-slug>/
```

Examples: `specs/012-fix-pipeline-mgmt-bugs/`, `specs/010-bugs_managemet_temp/`.

Resolve the folder by:

| Signal | Action |
|--------|--------|
| **Feature branch name** | Often matches the slug (e.g. branch `012-fix-pipeline-mgmt-bugs` → `specs/012-fix-pipeline-mgmt-bugs/`). |
| **Jira description** | May reference a path like `specs/rtsp_trt_pipeline/` or a numbered folder. |
| **Ambiguity** | Ask the developer which **`specs/NNN-*`** folder governs the ticket, or search the repo for the ticket key in `specs/**/*.md` (if the team links keys in docs). |

**Read at minimum:**

- **`spec.md`** — user stories, functional requirements (FR-xxx), acceptance criteria.
- **`tasks.md`** — task IDs (Txxx), file touch lists, checkpoints.

Use **`plan.md`**, **`quickstart.md`**, or **`contracts/`** when the ticket is integration-heavy.

### 2. Fetch each Jira issue (recommended)

Use **`getJiraIssue`** with `fields` such as `summary`, `description`, `status` so the comment **addresses the actual acceptance criteria** on that key, not a guess from memory.

### 3. Ground the comment in code and git

- **Code:** Name the **modules/files** that implement each acceptance block (paths relative to repo root, e.g. `Utils/rtsp_config.py`, `templates/management.html`).
- **Git (optional but valuable):** `git log`, `git log -S 'symbol' -- path`, or the PR link — note **branch name** and **commit/PR** for audit trail.

### 4. Map tickets to spec scope

| Pattern | What to write |
|---------|----------------|
| **One ticket = whole spec** | Top of comment: “Delivered per `specs/NNN-…/spec.md` (branch `NNN-…`).” Then sections aligned to user stories or FR IDs. |
| **Several tickets, one spec** | Per ticket: only sections that apply to **that issue’s summary/description**; still cite the **same** `specs/NNN-…/` path for traceability. |
| **Ticket has no spec folder** | Say so explicitly; cite **files + PR** and any **inline** requirements from the Jira description. |

### 5. Structure the comment (Markdown)

Use **`contentFormat: "markdown"`** when posting.

Recommended skeleton:

```markdown
## Implementation summary

One paragraph: outcome + link to spec folder and branch/feature name.

---

### [Area name] (maps to USx / FR-00x / ticket caveat)

| Item | Detail |
|------|--------|
| **Requirement** | … |
| **Implementation** | … |
| **Verify** | … |

---

### Traceability

- **Spec:** `specs/NNN-slug/spec.md`, `tasks.md`
- **Branch / PR:** …
- **Key files:** `path/a`, `path/b`

---

### QA checklist

- [ ] …
- [ ] …
```

**Tables** work well for symptom / root cause / fix / verification (especially bugs).

**Checklists** (`- [ ]`) give reviewers copy-paste QA; if the Jira renderer escapes them, use bullet questions instead.

### 6. Post the comment

- Call **`addCommentToJiraIssue`** with **`cloudId`**, **`issueIdOrKey`**, and **`commentBody`** (full Markdown string).
- One API call **per issue** when documenting multiple tickets.

### 7. Status hygiene

If the comment states work is complete, remind the developer to **transition** the issue when appropriate (see **Transitions** in [jira-operations.md](jira-operations.md)).

---

## Relationship to other templates

Short templates for “spec complete” and “implementation complete” live under **Adding Comments** in **[jira-operations.md](jira-operations.md)**. Use **this document** when the comment must be **longer, spec-referenced, and file-level accurate** (typical for complex bugs and multi-file features).

---

## Checklist for the agent

- [ ] Identified correct **`specs/NNN-…/`** directory for the work.
- [ ] Read **`spec.md`** / **`tasks.md`** (and plan/quickstart if needed).
- [ ] Fetched Jira **summary/description** for each key being updated.
- [ ] Comment includes **relative spec paths**, **branch or PR**, and **concrete file paths**.
- [ ] Used **`addCommentToJiraIssue`** with **`contentFormat: "markdown"`** after verifying MCP tool schema.
