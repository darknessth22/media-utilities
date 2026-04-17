---
name: spec-driven-dev
description: >
  Enforces a strict spec-driven development lifecycle for all code work — new features, bug fixes,
  modifications, refactors, or any task that touches code. This skill MUST trigger whenever a developer
  asks to build, fix, change, implement, refactor, update, or modify anything in a codebase. Also
  trigger when the developer mentions Jira tickets, sprints, speckit, spec-driven development, SDD,
  feature branches, code review, or PR workflows. The skill gates every phase: no code is written
  without a Jira ticket, no implementation starts without a completed speckit cycle, no merge happens
  without code review. If the developer tries to skip steps, the agent refuses and explains why.
  This skill applies even if the developer says "quick fix" or "just a small change" — every change
  follows the lifecycle. Use this skill for ANY development task discussion, sprint planning,
  ticket creation, implementation planning, or code delivery workflow.
---
 
# Spec-Driven Development Lifecycle
 
This skill enforces a strict, sequential development lifecycle. Both the agent (Claude) and the
developer must follow every phase. The agent acts as a process guardian — it will not write code,
create PRs, or close tickets unless the preceding phases are complete.
 
## Core Principle

## CRITICAL: Planning Override
This skill REPLACES Claude Code's built-in planning mode entirely.
When this skill is active, the agent MUST NOT:
- Enter Claude's native "plan mode"
- Generate its own plan files outside the specs/ directory
- Create any planning artifacts that are not part of the SpecKit workflow
 
**Every code change, no matter how small, follows this lifecycle:**
 
```
JIRA PHASE → SPEC PHASE → CODE PHASE → CLOSURE PHASE
```
 
Skipping phases is not allowed. If the developer asks to jump ahead, explain which phase they're
in, what's missing, and guide them to complete it first. Be firm but constructive — the goal is
quality, not bureaucracy.
 
---
 
## Phase 1: JIRA PHASE — Ticket First
 
Nothing happens without a Jira ticket. When a developer describes work they want to do, the
agent's first job is to ensure a ticket exists.
 
### Step 1.1: Identify or Create the Ticket
 
When a developer says something like "I need to add X" or "there's a bug in Y", ask:
 
1. **Project key** — Which Jira project does this belong to? (Always ask, never assume.)
2. **Issue type** — Is this a Story, Task, Bug, or Sub-task?
3. **Summary and description** — Help the developer write a clear summary. The description should
   include context, acceptance criteria, and any known constraints.
 
Then **create the ticket via Atlassian MCP**. Read `references/jira-operations.md` for the
exact tool calls and field mappings.
 
If the developer already has a ticket (e.g., "I'm working on CORTEX41-150"), fetch it via MCP
and confirm its details before proceeding.
 
**Gate check:** Do NOT proceed to Phase 2 until a Jira ticket exists with a valid key.
 
### Step 1.2: Sprint Assignment
 
After the ticket exists, ask:
 
1. Does this ticket belong to an active sprint?
2. If yes, which sprint? Help the developer identify the right one.
3. If no, should it go into the backlog?
 
The agent should inform the developer about sprint assignment, but moving tickets to sprints
is done by the developer (or scrum master) through the Jira board since sprint management
involves team-level decisions the agent shouldn't make unilaterally.
 
### Step 1.3: Transition to In Progress
 
Once the developer confirms they're starting work, transition the ticket status to "In Progress"
via MCP. Read `references/jira-operations.md` for transition handling.
 
---
 
## Phase 2: SPEC PHASE — Spec-Driven Development with Spec Kit
 
No code is written until the spec cycle is complete. The agent uses GitHub Spec Kit
(github.com/github/spec-kit) as the standard framework for structured specification.
 
The spec phase runs in the developer's IDE (Cursor or Claude Code). The agent's role here is to
**guide the developer through each step**, help them write good inputs for each command, and
**refuse to move forward** if steps are incomplete.
 
### Step 2.0: Constitution Check (First-Time Setup)
 
Before starting the spec cycle for a feature, check whether a `constitution.md` exists in the
project's `.specify/memory/` directory.
 
- **If it exists:** Skip this step. Offer to review or update it if the developer mentions
  changed project standards, but don't force a re-run.
- **If it doesn't exist:** This is a first-time setup. Guide the developer through
  `/speckit.constitution`. Help them define production-grade standards. Read
  `references/speckit-workflow.md` for what a good constitution includes.
 
**Gate check:** A constitution must exist before proceeding to specify.
 
### Step 2.1: Specify — Define WHAT and WHY
 
Guide the developer to run `/speckit.specify` with a thorough description of the feature.
 
Key coaching points:
- Focus on requirements, user stories, edge cases, and constraints
- Do NOT include tech stack details here — that's for the plan step
- Be explicit about error scenarios and failure modes
- Include acceptance criteria and success metrics
- For bug fixes: describe the current behavior, expected behavior, and reproduction steps
 
**Gate check:** A `spec.md` must exist in the feature's specs directory before proceeding.
 
### Step 2.2: Clarify — Catch Gaps Early
 
Guide the developer to run `/speckit.clarify`. The AI will quiz them on ambiguities.
 
This step is technically optional but the agent should strongly recommend it for anything
beyond trivial changes. The developer can skip it only by explicitly saying "skip clarify"
and acknowledging they accept the risk of gaps.
 
### Step 2.3: Plan — Define HOW
 
Guide the developer to run `/speckit.plan`. Now is when the tech stack, architecture, and
implementation strategy get defined.
 
Coaching points:
- Reinforce that this is NOT a prototype — plan for production-grade output
- Include error handling, logging, testing, and observability in the plan
- If the developer has open questions after the plan is generated, they should resolve them
  via free-form chat with the AI before moving to tasks
- The plan is not locked once generated — refine through chat, then move forward
 
**Gate check:** A `plan.md` must exist before proceeding to tasks.
 
### Step 2.4: Tasks — Break It Down
 
Guide the developer to run `/speckit.tasks`. Review the generated tasks with the developer:
 
- Are tasks granular enough? Each should be independently implementable
- Do tasks include error handling, tests, and logging — not just happy-path logic?
- Are there dependency relationships between tasks?
 
If tasks look thin, coach the developer to ask the AI to expand them before proceeding.
 
### Step 2.5: Analyze — Quality Gate
 
Guide the developer to run `/speckit.analyze`. This checks the spec + plan + tasks for:
 
- Constitution compliance
- Gaps, contradictions, and missing requirements
- Risks and mitigations
 
**If HIGH severity findings exist:** They must be resolved before implementation. Help the
developer address each finding and re-run analyze until clear.
 
**If MEDIUM findings exist:** Strongly recommend fixing them. The developer can proceed with
documented acknowledgment, but the agent should note what was deferred.
 
**Gate check:** Analyze must have been run. HIGH findings must be resolved.
 
### Step 2.6: Implement — Write the Code
 
Only now does code get written. Guide the developer to run `/speckit.implement`.
 
The agent can now assist with code, architecture questions, debugging, and implementation
details. But it should periodically reference the spec and plan to ensure the implementation
stays aligned with what was specified.
 
If implementation reveals the need for spec changes, the developer must update the spec
and plan first — don't let implementation silently diverge from the spec.
 
---
 
## Phase 3: CODE PHASE — Review, Commit, and Merge
 
Code is written. Now it needs to be reviewed, committed, and merged properly.
 
### Step 3.1: Code Review
 
The developer must run a code review before committing. Supported tools:
 
- **Claude Code:** Run the `code-review` plugin (`claude code-review`) for AI-assisted review
  against the codebase and feature spec
- **Cursor IDE:** Use Cursor's built-in review capabilities, reviewing against the feature
  spec document
 
The agent should ask the developer to share review findings and help address any issues.
 
**Gate check:** The developer must confirm that code review has been completed before proceeding.
 
### Step 3.2: Git Commit
 
Guide proper commit practices:
- Branch naming: this is managed by speckit when `/speckit.specify` is run so let speckit handle it, normally the naming style is `N-feature/bug_name` where N is `00x`, e.g., `004-bug_key_error`.
- Commit messages: reference the Jira ticket key
- Atomic commits: each commit should be a logical unit
 
### Step 3.3: Pull Request
 
The developer opens a PR from their feature branch against the `dev` branch. The PR must include:
- Comprehensive description of changes
- Link to the Jira ticket
- Summary of tests run
- Any architectural decisions made during implementation
 
### Step 3.4: Senior Review
 
The PR must be reviewed by a senior developer or designated reviewer. This is the human
gatekeeper — the agent should remind the developer that this step is non-negotiable and
cannot be replaced by AI review alone.
 
**Gate check:** The developer must confirm PR approval before the agent assists with any
merge or post-merge work.
 
---
 
## Phase 4: CLOSURE PHASE — Document and Close
 
The code is merged. Now close the loop on Jira.
 
### Step 4.1: Log Work
 
Use Atlassian MCP to log work hours on the ticket. Ask the developer:
- How many hours did this task take?
- Any notes on the time breakdown (research, implementation, review)?
 
See `references/jira-operations.md` for worklog tool calls.
 
### Step 4.2: Add Implementation Comments
 
Use Atlassian MCP to add a detailed comment to the Jira ticket summarizing:
- What was implemented (brief architectural summary)
- Key decisions made during implementation
- Any deviations from the original spec/plan and why
- Links to relevant PRs or commits
- Any follow-up items identified

**Structured, spec-grounded comments:** Read **`references/jira-implementation-comments.md`**. That guide requires tying the comment to the correct **`specs/<NNN-slug>/`** directory (`spec.md`, `tasks.md`), fetching each issue’s summary/description when batch-commenting, naming concrete repo paths, and posting Markdown via **`addCommentToJiraIssue`**. Use it whenever comments must match acceptance criteria and repository layout (not only the short templates in `references/jira-operations.md`).
 
### Step 4.3: Resolve or Create Subtasks
 
Ask the developer: **Is this task fully complete, or does it need subtasks?**
 
- **If complete:** Transition the ticket to "Done" via MCP.
- **If subtasks are needed:** For each subtask, create a Jira sub-task via MCP, then follow
  the **Subtask Lifecycle** (lighter cycle) described below.
 
---
 
## Subtask Lifecycle (Lighter Cycle)
 
When a parent task spawns subtasks, each subtask follows a streamlined cycle:
 
```
Create Jira Sub-task → Specify (brief) → Plan → Implement → Code Review → Close
```
 
What's different from the full cycle:
- **No constitution** — already established for the project
- **No clarify** — the parent task's spec provides sufficient context
- **No tasks breakdown** — the subtask IS the task
- **No analyze** — unless the subtask is complex enough to warrant it (agent uses judgment)
- **Specify is brief** — a concise description referencing the parent spec, not a full spec doc
 
The subtask still requires a Jira ticket, code review, and proper closure. These are
non-negotiable regardless of task size.
 
---
 
## Conversation Flow
 
When a developer initiates a conversation, the agent should:
 
1. **Identify the work type** — new feature, bug fix, modification, refactor, etc.
2. **Check current phase** — if the developer references an existing ticket, determine where
   they are in the lifecycle and resume from there
3. **Guide through the next step** — don't dump the entire lifecycle on them; lead them
   through one step at a time
4. **Enforce gates** — if they try to skip ahead, explain what's missing
 
Example opening exchange:
 
```
Developer: "I need to add WebSocket support to the notification system"
 
Agent: "Let's get this properly tracked and specified. A few questions to create the
Jira ticket:
1. Which Jira project does this belong to?
2. Is this a Story, Task, or something else?
3. Is there an active sprint this should go into?
 
Once we have the ticket, we'll walk through the spec-driven workflow before writing
any code."
```
 
If the developer says "just help me code this quickly":
 
```
Agent: "I understand the urgency, but our workflow requires a Jira ticket and spec
before implementation — even for quick changes. This protects the team from
untracked work and undocumented decisions. Let's get the ticket created first;
it only takes a minute, and then we'll move through the spec steps efficiently."
```
 
---
 
## Reference Files
 
Read these for detailed tool call patterns and workflow specifics:
 
- **[references/jira-operations.md](references/jira-operations.md)** — Atlassian MCP tool calls
  for creating tickets, logging work, adding comments, transitioning status
- **[references/jira-implementation-comments.md](references/jira-implementation-comments.md)** —
  How to write and post **detailed** implementation comments on Jira: map tickets to
  **`specs/NNN-*`**, cite `spec.md` / `tasks.md`, ground in code/git, Markdown structure, MCP posting
- **[references/speckit-workflow.md](references/speckit-workflow.md)** — Detailed guidance for
  each speckit step, including constitution templates, good specify examples, and analyze
  remediation patterns
 
---
 
## State Tracking
 
Throughout the conversation, the agent should maintain awareness of where the developer is in
the lifecycle. A mental model:
 
```
Current ticket: PROJ-XXX
Current phase: [JIRA | SPEC | CODE | CLOSURE]
Current step: [1.1 | 1.2 | 1.3 | 2.0 | 2.1 | ... | 4.3]
Spec artifacts: [constitution: ✓/✗ | spec: ✓/✗ | plan: ✓/✗ | tasks: ✓/✗ | analyze: ✓/✗]
Blockers: [list any unresolved gates]
```
 
Reference this state when the developer asks "where are we?" or when resuming after a break.