# Spec Kit Workflow Reference

Detailed guidance for each step of the Spec Kit workflow. The agent guides the developer
through these steps in their IDE (Cursor Chat or Claude Code).

## Tool: GitHub Spec Kit

- Repository: github.com/github/spec-kit
- Installation: `uvx --from git+https://github.com/github/spec-kit.git specify init .`
- IDE integration: Select "Cursor" when prompted (generates `.cursor/rules` and `.specify/`)
- Commands are run in **Cursor Chat** (Cmd/Ctrl + L) or Claude Code terminal

---

## Step 0: Constitution — Project Standards

**Command:** `/speckit.constitution`

The constitution is a project-level document, not per-feature. It lives at
`.specify/memory/constitution.md` and acts as the persistent "system prompt" for all
spec-driven work in the project.

### When to create

- First time using speckit in a project
- When the developer mentions the constitution is blank or outdated

### When to skip

- Constitution already exists and the developer hasn't flagged changes
- Offer to review: "Your project already has a constitution. Want me to review it, or
  should we proceed with the current one?"

### What makes a good constitution

A production-grade constitution includes:

**Code standards:**
- Error handling philosophy (retries, graceful degradation, circuit breakers)
- Logging requirements (structured logging, correlation IDs, log levels)
- Type hints and documentation requirements
- Testing requirements (unit, integration, coverage thresholds)

**Architecture rules:**
- Singleton/shared resource patterns (e.g., "No direct model instantiation outside factory")
- Configuration management (env vars, config files, schema validation, explicit defaults)
- Timestamp handling (single source of truth)
- Auth and security requirements

**Operational standards:**
- Observability (metrics, tracing, health checks)
- Performance targets (latency, throughput)
- Rollback and backward compatibility requirements

**Example constitution prompt for an AI platform:**
```
/speckit.constitution

Define production principles:
- No direct model instantiation outside get_shared_model()
- All GPU config must happen before model load
- get_current_timestamp() is the only timestamp source
- All endpoints covered by auth middleware
- Structured logging with correlation IDs on every async path
- ContextVar propagation required for any create_task() sub-task
- All config keys must have explicit defaults and schema validation
- Rollback path must remain functional during development
- Minimum 80% test coverage
- Docker-ready with health checks and graceful shutdown
```

---

## Step 1: Specify — WHAT and WHY

**Command:** `/speckit.specify <description>`

### Coaching the developer

The specify step defines requirements, NOT implementation. Common mistakes to catch:

**Wrong (includes tech stack):**
```
/speckit.specify Build a WebSocket server using FastAPI with Redis pub/sub
for real-time notifications
```

**Right (requirements only):**
```
/speckit.specify Build a real-time notification system that pushes alerts to
connected dashboard clients within 500ms of detection. Support multiple
concurrent clients per device view. Handle client disconnection and
reconnection gracefully. Notifications include: new detection alerts,
device status changes, and system health warnings.
```

### What to include in specify

- User stories ("As a X, I want Y, so that Z")
- Functional requirements with IDs (FR-001, FR-002, etc.)
- Edge cases and error scenarios
- Acceptance criteria with measurable success metrics
- For bug fixes: current behavior, expected behavior, reproduction steps
- Constraints (performance, compatibility, security)

### Output

Creates a numbered feature branch and `specs/<feature>/spec.md` with user stories
and functional requirements.

---

## Step 2: Clarify — Catch Gaps

**Command:** `/speckit.clarify`

The AI walks through the spec and asks structured questions about underspecified areas.
Answers get recorded in a Clarifications section of the spec.

### When to skip

- Only for trivial changes where the spec is already unambiguous
- Developer must explicitly acknowledge: "skip clarify"
- Agent should push back at least once: "Clarify typically catches gaps that save hours
  during implementation. Are you sure?"

### After clarify

The developer can also do free-form refinement by chatting with the AI to add details
they forgot. Then ask it to validate the Review & Acceptance Checklist in the spec.

---

## Step 3: Plan — HOW

**Command:** `/speckit.plan`

Now the tech stack, architecture, and implementation strategy get defined. The AI combines
constitution + spec to produce a detailed technical plan.

### Coaching the developer

Reinforce production-grade expectations:
```
/speckit.plan
This is NOT a prototype. Generate production-grade architecture with full error
handling, logging, tests, and documentation. No TODOs, no placeholder implementations.
```

### Handling open points

Plans often have open points or questions. The developer should resolve these via
free-form chat BEFORE moving to tasks:

```
Update the plan with these clarifications:
1. For concurrency: Use ThreadPoolExecutor for detector fan-out
2. Config file: Add to .gitignore, use .yaml.example template
3. [etc.]
```

### Output

Creates `specs/<feature>/plan.md` with constitution check, phased implementation,
risks and mitigations.

---

## Step 4: Tasks — Break It Down

**Command:** `/speckit.tasks`

### Review checklist

Before proceeding, review the generated tasks with the developer:

- Are tasks granular enough? Each should be independently implementable
- Do tasks include error handling, tests, and logging — not just happy-path logic?
- Are dependency relationships clear?
- If tasks look thin (e.g., "implement face detection" as a single task), tell the
  developer to ask the AI to expand them

### Output

Creates `specs/<feature>/tasks.md` with numbered tasks, dependencies, and phases.

---

## Step 5: Analyze — Quality Gate

**Command:** `/speckit.analyze`

This is the critical quality gate. Analyze checks the spec + plan + tasks for:

- Constitution compliance (CON findings)
- Architectural issues (A findings)
- Completeness gaps (C findings)
- Duplication issues (D findings)

### Handling findings

**HIGH severity:** Must be resolved before implementation. No exceptions.

Help the developer fix each finding:
```
Fix these HIGH issues:
- CON1: Constitution is blank → run /speckit.constitution with [standards]
- A1: No auth middleware on new endpoints → add to task T028
```

**MEDIUM severity:** Strongly recommend fixing. Developer can proceed with documented
acknowledgment, but agent should note what was deferred for the Jira comment.

After fixes, re-run `/speckit.analyze` to confirm resolution.

### Output

Analysis report with findings by severity. Must reach a state where all HIGHs are clear.

---

## Step 6: Implement — Write the Code

**Command:** `/speckit.implement`

Only now does code get written. The implementation should generate code from the tasks,
following the plan and respecting the constitution.

### Agent's role during implementation

- Help with code questions, debugging, architecture decisions
- Periodically reference the spec and plan to prevent drift
- If implementation reveals the need for spec changes: update spec and plan FIRST,
  don't let code silently diverge
- Track which tasks from tasks.md are being completed

### Post-implementation

Before moving to code review, the developer should verify:
- All tasks from tasks.md are addressed
- Tests pass
- Code aligns with the spec and plan
- No TODOs or placeholder implementations remain

---

## Resuming an In-Progress Spec Cycle

If a developer returns and says something like "I was working on the RTSP pipeline spec"
or "continue where we left off on CORTEX41-141", the agent should:

1. Fetch the Jira ticket via MCP to get current status
2. Ask what spec artifacts exist (or check if the developer can share them)
3. Determine which step they're on
4. Resume from there — don't restart the cycle

The speckit slash commands are checkpoints, but between them the developer can have as
much free-form conversation as needed. The important thing is that each checkpoint's
artifact exists before moving to the next.