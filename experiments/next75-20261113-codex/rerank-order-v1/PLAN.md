# N7: source-preserving focus order

This is a new research branch from the exact protected N2, not from N6.
No competition submission is authorized. Baseline N2 stays unchanged.

Observation: N2 selects relevant chunks, then `ordered()` returns source order.
In saved problem families, a rank-1 decisive passage can become the twentieth
passage in the variable document context. Prior oracle experiments changed the
source set as well as its order, so they cannot isolate ordering.

Hypothesis: place the four highest-ranked already-selected non-static passages
first, with their complete headings and text, then retain the source order of
all remaining passages. This may help use of relevant facts without removing
exceptions. Four is an initial fixed implementation choice, not optimized on
labels. There are no question IDs, reference answers or corpus facts in code.

Competing explanation: full-document reading order or proximity to the final
question is more helpful; promotion can bury another important condition.
An improved passage position alone is not a model-quality improvement.

Pre-generation revision: independent source review found a real backward
reference, "см. выше", in the solar placement section. The initial unrun
implementation is retained as `candidate-rejected-v0`. Version 1 excludes a
document's selected prefix up to a backward-reference passage, or suffix from
a forward-reference passage, from promotion. This conservative generic rule
keeps all potential antecedents in source order; it is not a guarantee to
detect every implicit semantic dependency. Four eligible passages are promoted.

Before generation: check exact equality of source-ID/text multisets and prompt
character lengths on known development/regression panels (123 + 67 + 12),
record every earlier/later/tied required-source placement and code hashes.
These panels have been inspected already and are not independent holdout.

If resources permit, use four fixed known error families for a new paired
experiment: hold01, hold17, n11, bill17. Use identical model, kwargs, messages
except block order, alternate first variant, record every HTTP request and
response. These are diagnosis cases, not a generalization estimate. Stop on
critical memory pressure or transport failure; do not stop someone else's
model. If genuine inference is unavailable, do not claim a quality win or
recommend a platform attempt from static checks alone.

Neural reranker is a separate hypothesis. Previous B/B2 had reranking off;
their platform scores do not establish a reranker effect. The previous CPU
Qwen3-Reranker-0.6B attempt was slow and unfinished. API availability, CPU time,
and distribution within the contest ZIP must be established before making it
a runtime dependency. No new remote recipient of questions/KB is authorized.
