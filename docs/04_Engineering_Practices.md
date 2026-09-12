# SkyPoints — Development Process Specification

Defines the required development cycle, commit policy, and AI-output review policy for building the SkyPoints pipeline. Applies to every component listed in `03_Technical_Build_Plan.md`.

---

## 1. Development Cycle

Each component is built in the following fixed sequence — no step is skipped or reordered:

1. **Red** — write the failing test/assertion that defines correctness for the component, before any implementation exists.
2. **Green** — implement the minimum code required to pass that test.
3. **Refactor** — clean up (dedupe, rename, extract a macro) once green, as its own step, independent of whether anything external requested it.
4. **Review** — read the resulting diff line by line against `01_Design_Specification.md` / `02_Tech_Stack_Specification.md` / `03_Technical_Build_Plan.md` before it is committed. A diff that merely executes without error does not pass review; it must match the specified design and be backed by a test.
5. **Commit** — land on trunk directly, in a small, independently-describable step. No long-lived feature branch.

---

## 2. Principle → Requirement Mapping

| Source principle | Requirement in this repo |
|---|---|
| Tests before code | Step 1 (Red) is mandatory for every component in the inventory (`03_Technical_Build_Plan.md` §3) before its implementation is written |
| Unprompted refactor | Step 3 is mandatory and committed separately from the Green commit |
| AI output reviewed like a teammate's | Step 4 is mandatory for every AI-generated change, with explicit reference to the design/tech-stack/build-plan documents, not just "it runs" |
| Problem discussed before implementation | Design and tech-stack decisions are recorded in `01_Design_Specification.md` / `02_Tech_Stack_Specification.md` before the corresponding code is written |
| Trunk-based, small commits | Step 5 — single branch, one logical change per commit |

---

## 3. Definition of Done

Applies to every component in `03_Technical_Build_Plan.md` §3 (dbt models, macros, snapshots, tests, DAG, Docker/CI configuration):

- [ ] Failing test/assertion written and confirmed red
- [ ] Implementation added, test passes
- [ ] Refactor pass completed and committed separately
- [ ] Diff reviewed against `01_Design_Specification.md` / `02_Tech_Stack_Specification.md` / `03_Technical_Build_Plan.md`
- [ ] Committed to trunk in a single, independently-describable step
- [ ] Any deviation from a prior spec decision is written back into the relevant `docs/` file before the code that depends on it is committed

---

## 4. Commit Policy

- Single trunk branch. No feature branches surviving longer than one component's development cycle.
- One commit = one logical change (a failing test, a passing implementation, or a refactor) — never a batch of unrelated changes.
- Commit messages state what changed and why in one line (e.g., "add failing test: stale_member_flag null when last_flight_date null").

---

## 5. AI-Output Review Policy

Every AI-generated SQL/Python change is checked against:
- The relevant rule(s) in `01_Design_Specification.md`.
- The relevant component definition in `03_Technical_Build_Plan.md` §3.
- The presence of a test proving the change (§1, step 1).

A change that satisfies none of the above is not committed, regardless of whether it executes successfully.
