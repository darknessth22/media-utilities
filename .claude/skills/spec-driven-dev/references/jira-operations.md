# Jira Operations via Atlassian MCP

This reference covers the exact tool calls for Jira operations used throughout the lifecycle.

## Prerequisites

Before any Jira operation, you need the **cloudId**. If you don't have it cached from a
previous call in the conversation, fetch it:

```
Tool: Atlassian:getAccessibleAtlassianResources
```

Use the returned cloudId for all subsequent calls.

---

## Creating a Ticket

Use `Atlassian:createJiraIssue` with these fields:

| Field | Required | Notes |
|---|---|---|
| cloudId | Yes | From getAccessibleAtlassianResources |
| projectKey | Yes | e.g., "CORTEX41" — always ask the developer |
| issueTypeName | Yes | "Story", "Task", "Bug", or "Sub-task" |
| summary | Yes | Clear, concise title (5-12 words) |
| description | Recommended | Include context, acceptance criteria, constraints |
| contentFormat | Use "markdown" | For readable descriptions |

For **sub-tasks**, also include:
- `parent`: the parent issue key (e.g., "CORTEX41-150")

Example description format for the ticket body:

```markdown
## Context
[Why this work is needed]

## Acceptance Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]

## Constraints
- [Any technical or business constraints]

## Related
- Parent: [if subtask]
- Depends on: [blocking tickets]
```

After creation, confirm the ticket key with the developer and display it.

---

## Fetching a Ticket

Use `Atlassian:getJiraIssue` to retrieve an existing ticket:

```
cloudId: <cloudId>
issueIdOrKey: "CORTEX41-150"
responseContentFormat: "markdown"
```

Check the returned status, assignee, sprint, and description to determine where the
developer is in the lifecycle.

---

## Transitioning Ticket Status

Status transitions require a transition ID. Get available transitions first:

```
Tool: Atlassian:getTransitionsForJiraIssue
cloudId: <cloudId>
issueIdOrKey: "CORTEX41-150"
```

This returns available transitions with their IDs. Common transitions:

| Target Status | When to Use |
|---|---|
| In Progress | Developer confirms they're starting work (Step 1.3) |
| In Review | Code review / PR submitted (Step 3.3) |
| Done | Task fully complete and merged (Step 4.3) |

Then transition:

```
Tool: Atlassian:transitionJiraIssue
cloudId: <cloudId>
issueIdOrKey: "CORTEX41-150"
transition: { "id": "<transition_id>" }
```

**Important:** Transition names and IDs vary by project workflow. Always fetch transitions
first rather than hardcoding IDs.

---

## Logging Work

Use `Atlassian:addWorklogToJiraIssue` to log time. Load this tool via tool_search first.

Ask the developer:
1. How many hours did this take?
2. Any breakdown notes? (e.g., "2h research, 5h implementation, 1h review")

Format the time as seconds for the API (hours × 3600).

Include a descriptive comment summarizing the work done.

---

## Adding Comments

Use `Atlassian:addCommentToJiraIssue` to add implementation details. Load via tool_search first.

Use `contentFormat: "markdown"` for readable comments.

**Spec-grounded implementation comments** (link work to `specs/NNN-*`, files, branch/PR, and per-ticket acceptance criteria): follow **[jira-implementation-comments.md](jira-implementation-comments.md)**. Use that reference when the developer asks for detailed structured comments or when closing multi-file features and bugs.

### Comment Templates

**Spec Completion Comment:**
```markdown
## Spec-Driven Development — Spec Phase Complete

**Speckit artifacts generated:**
- constitution.md — [existed / created / updated]
- spec.md — [feature spec with X user stories, Y requirements]
- plan.md — [Z tasks across N phases]
- tasks.md — [task breakdown]
- analyze — [PASS / findings resolved]

**Key decisions:**
- [Decision 1]
- [Decision 2]

**Ready for implementation.**
```

**Implementation Complete Comment:**
```markdown
## Implementation Summary

**Branch:** `feature/PROJ-XXX-description`
**PR:** [link or number]

**What was built:**
- [Brief architectural summary]

**Key decisions during implementation:**
- [Decision and rationale]

**Deviations from spec:**
- [Any deviations and why, or "None"]

**Tests:**
- [Test coverage summary]

**Follow-up items:**
- [Any items identified for future work, or "None"]
```

---

## Searching for Existing Tickets

If the developer isn't sure whether a ticket exists, use JQL search:

```
Tool: Atlassian:searchJiraIssuesUsingJql
cloudId: <cloudId>
jql: "project = CORTEX41 AND summary ~ 'websocket notification' ORDER BY created DESC"
maxResults: 10
```

This helps avoid duplicate ticket creation.

---

## Getting Project and Sprint Info

To list available projects:
```
Tool: Atlassian:getVisibleJiraProjects
cloudId: <cloudId>
```

Sprint management (viewing active sprints, moving tickets to sprints) is typically done by
the developer through the Jira board UI, since sprint assignment involves team-level planning
decisions. The agent should ask about sprint assignment and remind the developer to handle it,
but should not unilaterally move tickets into sprints.