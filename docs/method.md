# Method

h is the equal-weight repair pass fraction. Root generates from the statement and remains available. REx priors are Beta(1+C*h,1+C*(1-h)); rootBeta(1,1). Incomplete children increment parent beta by1. Fresh NumPy draws follow arm creation order. Success logs the child and stops before parent update, matching upstream terminal behavior.

Progress credit is eta*max(0,h_child-h_parent) for non-root incomplete refinements, else0 for root partial results. Update alpha+=r,beta+=1-r. C20/eta0.5 are defaults. This is heuristic fractional pseudo-count shaping, with no exact Bernoulli or optimality claim.

Cost priority divides the same Beta draw by max(1,estimated_tokens)**gamma (default0.5). Prepare prompts first; initially estimate chars/4+512, then use current-trial past counts with EWMA weight0.2 and chars/token bounded[1,10]. Actual costs use backend usage, never estimates. Zero eta/gamma recover original behavior.

Greedy includes root0.5 and seeded random ties. Resample only selects root. BFS has finite branching2/FIFO; fixed-width starts4 chains then replaces endpoints round-robin even after regressions. No free initial batch. Malformed/duplicate completions consume calls/tokens. All methods share model/settings/prompts/parser/tests/limits.

Feedback uniformly selects one failed repair test using an independent keyed SHA-256 stream. Fields cap input/expected/actual at2000 characters, stderr at1000; truncation is explicit. Judge compares full original outputs. Only the current parent enters a repair prompt, without expanding dialogue history.

Return highest h among completed eligible programs; earliest creation breaks ties. Hidden outcomes never rerank/stop/search. Integer call checkpoints and last-completed-at-or-below token thresholds define curves. Crossing/extension work stays charged to campaign. Visible success is absorbing even on later hidden failure; unresolved insufficient traces are censored and block final claims.

SQLite/artifact transitions separate preparation, dispatch intent, raw response, judgment and atomic policy commit. Unknown dispatch outcomes pause without free retry. Saved responses/judgments recover only their own request. Hidden evaluation is separately loaded and versioned; report/replay are read-only and inert.

This stdio APPS study is a documented extension, not full historical-model/task/prompt reproduction. No real comparative performance has been measured.
