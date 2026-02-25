# Family Foqos Developer Guidelines

This file provides guidelines for agentic coding assistants working on this codebase.

## Key rules agents often forget but must ALWAYS follow:

  - **NEVER** force commit or amend commits. Ever. Always create new commits for fixes, and use Git's revert feature to undo changes if needed. This preserves the integrity of the commit history and allows for proper code review.
  - **ALWAYS request code review before merging any changes.** This ensures that all changes are vetted for quality, correctness, and adherence to project standards.
  - **NEVER use worktrees**. Always work on feature branches. This prevents accidental changes to the main branch and allows for better organization of work.


**ALWAYS:** use the `requesting-code-review` skill and address the review feedback properly:
  > - after each phase
  > - before committing

**ALWAYS:** use the `verification-before-completion` skill to verify that the implementation meets the success criteria defined in this plan before marking a plan as complete.

**ALWAYS:** stick to the instructions in `AGENTS.md`. They override any conflicting instructions in any plan or in skills. If you find any contradictions between `AGENTS.md` and a plan or skill, follow `AGENTS.md`.
