# Experiment 005 -- Connection pool capacity as the collapse lever

**Status.** open

**Question.** Experiments 001-004 all converged on Service B's fixed 10-connection pool as the binding constraint once the system saturates. Does increasing the pool size shift the collapse boundary to a higher offered load, or does the bottleneck just relocate elsewhere (e.g. the database itself)?

**Hypothesis.** Raising POOL_MAX_SIZE will push the collapse boundary to a higher RPS, up to the point where some other resource (DB CPU/connections, network) becomes the new binding constraint.

**Primary variable.** pool_size

**Method.** _TODO: describe the fixed parameters and run matrix._

**Finding.** _TODO: fill in once the experiment is closed._
