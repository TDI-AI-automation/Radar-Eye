# Engineering Guidelines

Cross-cutting engineering policy that applies repository-wide, independent
of any single milestone. Distinct from `CLAUDE.md` (project instructions
and architecture rules) and `docs/IMPLEMENTATION_ROADMAP.md` (milestone
sequencing) — this document records durable engineering practice, the way
`docs/PERFORMANCE_OPTIMIZATION_PROGRAM.md` records the optimization
workstream's own rules.

---

## Permanent Engineering Evidence

Validation artifacts designated as permanent engineering evidence must
always be committed, even if generic repository ignore rules would
normally exclude similar files by pattern (e.g. a blanket `logs/` or
`*.log` rule intended for transient runtime output).

This distinction was established following RM-11's Development System
Integration Validation: the repository's generic `.gitignore` rules
(`logs/`, `*.log`) silently excluded `runtime.log` and
`execution_timeline.log` — the two most important evidence files in that
session's archive — from the artifact directory's first commit. Both were
force-added in follow-up commits rather than left out. The generic
`.gitignore` rules themselves were correctly left unmodified, since they
remain appropriate for the transient logs they were written for.

**Examples of permanent engineering evidence** (not exhaustive — judge new
cases against the principle below, not just this list):

- Runtime logs captured for milestone validation
- Execution timelines
- Benchmark reports
- Profiling reports
- Validation screenshots
- Recordings
- Engineering review documents

**The distinction that matters:** a transient runtime log (e.g. a
development server's stdout, a local debug session, `siv_run_*.log`
produced by an ad hoc manual run) exists to help someone in the moment and
has no lasting reference value once that moment has passed — it correctly
stays ignored. A file that becomes the evidentiary basis for a milestone
sign-off, an engineering review's conclusions, or a baseline that future
work will be measured against is not transient, regardless of its file
extension or which directory pattern it happens to match. Ignore rules are
written by filename pattern; permanent-evidence status is a property of
what the file *is*, not what it's named — the two do not always agree, and
when they conflict, evidence status wins.

**In practice:** before committing a validation/benchmark/review artifact
directory, check whether any of its files are silently caught by an
existing `.gitignore` pattern (`git check-ignore -v <path>` or `git status
--ignored`). If a file is permanent engineering evidence, force-add it
(`git add -f`) rather than either leaving it uncommitted or broadening a
generic ignore rule to accommodate it. Do not modify a generic ignore rule
to fit one archive's needs — the rule likely exists correctly for other,
genuinely transient files elsewhere in the repository.

---

## Branch Management for Committed Baselines

Once a branch carrying a permanent engineering baseline (validation
evidence, an engineering review, an approved milestone's artifacts) has
been merged through the project's normal review process:

- The baseline must remain reproducible — the exact commit it lives on
  must stay reachable in history.
- History containing baseline/evidence commits must not be rewritten.
- Such commits must not be squashed away if doing so would obscure the
  audit trail connecting a conclusion (a review, a sign-off) to the
  evidence it was drawn from.

Preserving engineering traceability takes priority over maintaining a
perfectly linear commit history.
