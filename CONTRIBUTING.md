# Contributing to Slimybug

This is a guide for a human contributing an experiment or change. It covers
the judgment calls that aren't mechanical — for setup, running experiments,
and scaffolding a new one, see the root [README](README.md). For the
project's engineering philosophy and long-term vision, see
[CLAUDE.md](CLAUDE.md) — that document is written for an AI collaborator,
but the principles apply equally to human contributors.

## Picking a question

Check the experiments table in the README first — a new experiment should
ask something the existing ones haven't answered. A good question:

- investigates one systems question
- changes one primary variable, with everything else held fixed
- is falsifiable — you should be able to state in advance what result would
  contradict your hypothesis, not just what would confirm it

If you're not sure whether a question is worth running, look at how the
closed experiments frame theirs (`hypothesis`, `question`, and
`primary_variable` in each `experiment.py`) as a model.

## Research-grade vs reference-grade

Default to **research-grade** (`experiments/`) — one causal question,
single run per condition, optimized for learning quickly. This is the
right choice for almost all new work.

Use **reference-grade** (`reference/`) only when you are validating a
*specific claim an already-closed experiment made*, for a skeptical
external reader rather than a returning collaborator — not for asking a
new question. A reference-grade entry replicates runs, reports variance,
and never reopens or revises the original experiment, which stays exactly
as published. See the README's "Reference-grade evidence" section and
`reference/R001-pool-capacity-validation/` for the model.

## Running and writing up

Mechanics (commands, artifact layout, scaffolding a new experiment) live
in the README — don't duplicate them here.

When writing the finding:

- separate mechanism from outcome; don't claim causation beyond what the
  evidence supports
- prefer "the evidence is consistent with..." over "this proves..."
- document limitations, including ones that weaken your own hypothesis
- an inconclusive or negative result is a valid, publishable outcome (see
  Experiment 008) — report it as honestly as a successful one

## What review checks for

- exactly one primary variable changed versus the fixed baseline
- raw artifacts preserved under `runs/`, not just the summary
- the README's question/hypothesis/method/finding are filled in before merge
- no post-hoc adjustment of a fixed design-choice parameter (e.g. a
  threshold or half-life) after seeing results — if a result is
  surprising, that surprise is itself the finding, not a signal to retune
  and rerun
