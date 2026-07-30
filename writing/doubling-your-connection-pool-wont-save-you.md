# Why Doubling Your Database Connection Pool Doesn't Make Overload Safer

*By Shikha Pandey, creator of [FaultLab](https://github.com)*

I expected a larger connection pool to buy me something besides raw
capacity.

Maybe slower degradation. Maybe a wider safety margin — a little more
warning before things fell apart, instead of everything fine one second
and everything broken the next.

It didn't. And the more I pushed on it, the more that refusal to budge
started to feel less like a footnote and more like the actual finding.

## The setup

I ran a series of controlled overload experiments against a small API
service backed by Postgres, injecting a fixed 400ms of latency between
the service and the database — enough to make each query noticeably slow
without being pathological — then driving load at a range of requests
per second and watching what happened as offered load approached, then
exceeded, what the connection pool could sustain.

I tested this at three pool sizes: 10, 20, and 40 connections — a
control point plus two clean doublings. My assumption going in was
ordinary: a bigger pool should mean more headroom, and more headroom
should mean a softer landing when things go wrong.

## The cliff refused to blur

At every pool size, there was a request rate where everything was
completely fine — 0% errors, every request served — immediately followed
by a request rate, one step higher, where the system collapsed to
near-total failure. Not a slope. A cliff, exactly one step wide.

I kept expecting that cliff to soften as the pool grew — more
connections, more give, a wider transition zone between fine and broken.
It never did. Every time I doubled the pool, the cliff simply moved to
the right. The shape refused to change.

| Pool size | Last fully healthy RPS | First collapsed RPS | Clean-edge ratio | Collapse ratio |
|---|---|---|---|---|
| 10 | 12 | 14 | 1.2 | 1.4 |
| 20 | 24 | 28 | 1.2 | 1.4 |
| 40 | 48 | 56 | 1.2 | 1.4 |

Both ratios held *exactly*, at every pool size, across a 4x range.
Doubling the pool from 10 to 20 doubled both edges of the cliff precisely
— 12 became 24, 14 became 28. Doubling again from 20 to 40 did the same
thing again, with no curvature anywhere in between.

That part actually matches the intuition I started with: a bigger pool
does raise the ceiling, proportionally. Where the intuition breaks is
what happens once you cross it.

At each pool size's collapse point, client-visible success didn't
degrade a little — it cratered to near zero (0.00%, 0.16%, and 0.22%
success, across the three pool sizes). Meanwhile the database itself
kept doing roughly the same amount of real work — the completed-query
count actually rose slightly at collapse compared to the clean edge, and
scaled 2x with each pool doubling, just like everything else. The
queries were finishing. They just weren't finishing *in time* — nearly
every one of them completed just a few milliseconds after the client had
already given up and timed out at its fixed 2-second limit.

So a bigger pool doesn't degrade more gracefully. It moves the exact same
all-or-nothing cliff to a higher request rate, at a fixed, precise ratio,
and does nothing to soften what happens once you're past it.

## Making sure it wasn't a fluke

The numbers above come from one run per condition — normal for
exploratory work, but not something I wanted to stake a claim on without
checking. A single clean-looking result can just be a lucky draw.

So I went back and re-ran the six critical measurements — the clean edge
and the collapse point, at all three pool sizes — five independent times
each, 30 runs total, with the order randomized so nothing like
time-of-day or machine warm-up could quietly bias one condition over
another.

The result held up almost exactly:

- Every one of the 15 "clean edge" runs came back at precisely 0.00%
  error. No exceptions, no near-misses.
- Every one of the 15 "collapse point" runs landed within a fraction of
  a percentage point of total failure — the tightest spread was under
  0.1 percentage points at every pool size.

I want to be precise about what this replication does and doesn't show.
It doesn't independently re-discover *where* the cliff sits — I
deliberately re-measured the same points I'd already found, rather than
searching again from scratch. What it does show is that the behavior at
those points is real and stable, not an artifact of one lucky (or
unlucky) run. That's a narrower claim than "the original result was
proven right," but I think it's the more useful one: it tells you this
isn't noise.

## What this means in practice

If your mental model of "add more connections" is "the system will
handle overload better," I think this data argues against that. What a
bigger pool actually gets you is a higher ceiling before the cliff — a
real and valuable thing — not a softer landing when you go over it.

If your system might exceed its connection pool's capacity even
occasionally, the size of that pool tells you *where* the cliff is, not
*how bad* falling off it will be. Those are different engineering
problems, and they need different solutions — a bigger pool solves the
first one; something like admission control, load shedding, or timeouts
tuned to fail fast solves the second. Sizing your pool generously and
calling the overload problem solved is solving only half of it.

## What this doesn't show

This was one failure mode (a saturated connection pool under injected
latency), one database, one topology, and one range of pool sizes (10 to
40, well under Postgres's default connection ceiling). Whether the same
sharp-cliff-not-gradual-slope behavior holds at very different latency
profiles, very different pool sizes, or entirely different databases is
an open question, not something this data speaks to. I'd treat this as a
specific, well-measured data point — not a universal law.

## Where this came from

This experiment is part of FaultLab, a project I'm building to
understand overload behavior through controlled experiments. This was
the first finding that made me stop and rethink an assumption I thought
was obvious.

I suspect it won't be the last.
