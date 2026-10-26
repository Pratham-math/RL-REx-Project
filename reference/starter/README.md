# REx project: reproduction and two testable extensions

**Status:** The search algorithms and experiment pipeline are implemented. Offline correctness
tests have been run. No real LLM benchmark has been run and there are no measured performance
claims in this package. Docker and Ollama integration must be checked on your machine.

**Project question:** Can giving credit to productive partial repairs and accounting for their
estimated token cost improve the efficiency of REx on programming problems?

Use this as a small-scale algorithm reproduction plus an empirical extension. It is not an
exact numerical reproduction of all the paper's experiments. The model, subset, budget,
held-out evaluation protocol and restricted evaluator differ from the published study.

## What the paper does

Tang et al., *Code Repair with LLMs gives an Exploration-Exploitation Tradeoff*, NeurIPS 2024,
introduce REx: Refine, Explore, Exploit. Each candidate program is a bandit arm; selecting
an arm asks a frozen LLM for a repair. Newly generated programs become new arms.

For a program with repair-test pass fraction h and N unsuccessful refinements, REx draws:

    theta ~ Beta(1 + C*h, 1 + C*(1-h) + N)

It refines the program with the largest sample. All-test success stops search. A new program
gets a prior based on its own h. The empty-program arm generates from scratch and starts
at Beta(1,1), not Beta(1,1+C). C=20 is a reasonable paper-based starting setting.

The LLM weights are not updated. The learning component is the online bandit/search policy,
which falls within the RL project scope as bandit-based sequential decision making.

Implementation note: the mean implied by the Beta parameters in equations 7-10 is
(1+C*h)/(2+C+N). Equation 11 in the supplied v3 prints 2+2C+N instead. This implementation
uses the Beta parameters and the authors' code, not that inconsistent denominator.

## Changes implemented

### 1. Credit productive partial repairs

REx already uses partial test scores to initialize new arms. The change here is specifically
the evidence credited to the selected PARENT after it produces an incomplete child.

Let h_parent and h_child be pass fractions on the same fixed repair tests:

    r = 1                                    if the child passes every repair test
        eta * max(0, h_child - h_parent)      otherwise, for an existing program
        0                                    for an unsuccessful from-scratch generation

Then update the selected arm:

    alpha += r
    beta  += 1-r

For example, moving from 4/10 to 7/10 tests passed gives r=0.15 when eta=0.5. Original REx
gives this parent reward 0. Both methods still add the improved child as a new arm.
Regressions and unchanged scores receive zero credit. Full success still terminates search.
The root retains REx's original update because it has no preceding program to improve.

This is a **heuristic fractional pseudo-count update**, not an exact Beta-Bernoulli posterior
over complete-solution probability. It also does not have a potential-based reward-shaping
optimal-policy guarantee. It may overvalue incremental improvements or overfit repair tests.
Its usefulness must be established with the ablation and held-out measurements below.

### 2. Account for predicted token cost before choosing an arm

    priority = sampled_theta / estimated_tokens**gamma

estimated_tokens is an estimate of prompt tokens plus output tokens. Before the first call,
the estimator uses characters/4 and 512 output tokens. Afterwards it updates these estimates
from PREVIOUS observed token usage using exponential smoothing. It never uses the candidate's
future actual completion length to make its selection. Actual Ollama input/output token counts,
not the estimate, determine reported cost. gamma=0 recovers ordinary selection; gamma=0.5 is
a starting hypothesis. Token counts are an efficiency proxy, not API prices or latency.

This can prefer cheaper useful repairs, but can also avoid longer repairs that are necessary.
There is no claim that the ratio is an optimal budgeted-bandit policy.

### Six methods

| Method | Parent partial-progress credit | Estimated-cost adjustment |
|---|---:|---:|
| resample | No repairs; generate fresh code each time | No |
| greedy | Refine the highest-scoring candidate; random tied choice | No |
| rex | No | No |
| rex_progress | Yes | No |
| rex_cost | No | Yes |
| rex_progress_cost | Yes | Yes |

The same prompt, model settings, repair tests, evaluator, exact-code evaluation cache and
stopping rule are used for all methods. A duplicate generation still costs a model call and
tokens; its cached deterministic test score and existing arm statistics are reused. Caching
and deduplication are shared infrastructure, not a claimed research contribution.

## Run on a local machine

Requirements: Python 3.10+, Docker running in Linux-container mode, and Ollama. A local GPU
is useful; many thousands of generations on CPU can be slow. No paid API key is required by
this implementation. The paper's original large model experiments are not assumed feasible
on a student laptop. Start with the pilot.

Install the plotting dependency, fetch the fixed coding model and runner image:

```bash
python -m pip install -r requirements.txt
ollama pull qwen2.5-coder:7b
docker pull python:3.11-slim
python -m unittest -v test_project.py
```

Start the Ollama service if it is not already running (`ollama serve`). For a smaller pilot
you may use another locally available model via --model, but every comparison must use the
same model. Model configuration and Docker image ID are saved with each experiment.

Smoke-test the real runner before spending time generating code:

```bash
python -c "from runtime import DockerEvaluator; r=DockerEvaluator()('print(sum(map(int,input().split())))',[{'input':'2 3\n','output':'5\n'}]); print(r.passed); assert r.solved"
```

The runner executes candidate code inside a container with no network, no host credentials,
an unprivileged user, resource limits and only the candidate source mounted read-only. Test
inputs arrive on stdin. Expected outputs and hidden test files are never mounted. Use a
disposable environment for benchmark execution. Docker startup contributes to the measured
wall time, so token/call efficiency is the primary comparison in this starter.

### Prepare a fixed APPS subset

Download/extract APPS using the official dataset instructions linked below. Point the command
at an extracted split directory containing task folders with question.txt, metadata.json and
input_output.json. The script does not download anything or use reference solutions.

```bash
python prepare_apps.py --apps-root /path/to/APPS/test --out data --count 30 --dev-count 10 --difficulty interview --seed 2026
```

This selects tasks in a fixed shuffled order BEFORE any model is run, using documented
eligibility criteria. Development and evaluation task IDs are disjoint. It writes separate
repair and hidden files; run.py refuses task records containing hidden tests or a solution.

Restrictions: standard-input/output tasks only; string inputs and a single string expected
output; whitespace-token equality; standard-library Python; at least three repair and three
held-out cases after duplicate/example filtering; at most 20 cases selected per task; input
and output size at most 20,000 characters per case. The task manifest records filters, IDs
and file hashes. Function-call tasks, alternative valid outputs, numerical-tolerance judging
and special judges need a richer evaluator. Therefore this is **not the official APPS score**.

Inputs appearing literally after whitespace normalization in the statement are assigned to
repair tests. Manually audit the fixed subset for paraphrased examples and unusual judging
requirements before running methods. Do not remove tasks afterwards because a method fails.
APPS is public and model training contamination is possible; this experiment cannot prove
the model has never seen the problems. State that limitation in the report.

### Pilot, then freeze settings

```bash
python run.py --tasks data/dev_repair.jsonl --out runs/pilot --methods resample rex rex_progress_cost --seeds 0 --budget 8
python evaluate.py --runs runs/pilot --hidden data/dev_hidden.jsonl --call-budgets 1 2 4 8
python report.py --runs runs/pilot
```

The default pilot above is at most 10*3*1*8 = 240 calls. Check generation quality, enough
nontrivial tasks, token costs, runner behavior and visible/hidden gaps. Do all hyperparameter
selection on development tasks. For example, consider eta in {0.25,0.5,1} and gamma in
{0.25,0.5,1}, or use the defaults without claiming optimal tuning. If tuning C, give the
original REx baseline the same development opportunity. Record every setting tried.

### Main comparison

```bash
python run.py --tasks data/eval_repair.jsonl --out runs/final --seeds 0 1 2 --budget 16 --constant 20 --eta 0.5 --gamma 0.5
python evaluate.py --runs runs/final --hidden data/eval_hidden.jsonl --call-budgets 1 2 4 8 16
python report.py --runs runs/final
```

For 30 evaluation tasks this is at most 30*6*3*16 = 8,640 model calls. For 50 tasks it is
14,400 calls. Early stopping reduces these totals. Scale tasks or seeds down for an exploratory
study, and label the sample size honestly. Do not estimate affordability from call count
alone: inspect the pilot's actual tokens and elapsed time.

Use fresh output directories for each configuration. Logs flush after each successful call.
An infrastructure error leaves an experiment marked incomplete, and hidden evaluation refuses
to run on it. Automatic resume and automatic API retries are intentionally not included;
failed/incomplete experiments must be documented rather than quietly excluded.

## Evaluation and results to present

At each budget the returned candidate is the highest repair-test scorer found so far; ties
keep the earliest candidate. All methods stop on the first candidate that passes every repair
test. Hidden tests are applied OFFLINE to these already-selected snapshots. If that candidate
fails hidden tests, it stays a failure; the run is not resumed or reranked using hidden results.

The default token budgets are 2,048 through 65,536. To avoid a misleading comparison, a token
budget is omitted from the aggregate curves if ANY unsolved run hit its call cap before that
token budget. Increase the uniform call cap or select lower token checkpoints using development
data when needed. Early stopping on visible success is a policy outcome, not censoring.

report.py produces:

- summary.csv: hidden-test success, task-bootstrap 95% intervals, paired differences from
  REx, mean expenditure, total tokens / successful runs (including spending on failures),
  and visible-pass/hidden-fail frequency.
- success_vs_calls.png: returned-solution correctness at equal call budgets.
- success_vs_tokens.png: returned-solution correctness at equal token budgets, where complete.

Repeated seeds are averaged within each task before task-level bootstrap resampling; seeds
are not treated as independent new problems. Pairing uses identical tasks and seeds across
methods. Backend seeds reduce variability but do not promise bit-for-bit GPU reproducibility.
The curves are not the iid pass@k estimator, since refinement samples are adaptive. Success
can decrease with budget if a higher-visible-scoring candidate generalizes worse.

For the presentation, add one actual repair tree from a recorded run: code versions, parent
edges, visible scores, selection order and accumulated tokens. Include both a successful case
and a case where the proposed method loses to REx. Optional fixed-width/BFS baselines can be
added later; they are not implemented here, so do not claim to reproduce every paper baseline.

Suggested result table (fill only with measured results):

| Method | Hidden success at 16 calls | Hidden success at a common token budget | Total tokens per hidden success |
|---|---|---|---|
| Resample | measured | measured | measured |
| Greedy | measured | measured | measured |
| REx | measured | measured | measured |
| REx + progress | measured | measured | measured |
| REx + cost | measured | measured | measured |
| REx + both | measured | measured | measured |

Interpretation: higher accuracy at the same token budget supports improved budget efficiency;
equal accuracy at fewer tokens supports an efficiency improvement. Gains only against greedy
do not establish improvement over REx. A confidence interval spanning zero is inconclusive
at that sample size. A negative result is still a valid reproduction-and-ablation project.

## What you can say about the contribution

Proposed title: **Progress- and Cost-Aware Code Repair with Bandit Search**.

Accurate pre-results description: We implement REx for Python programming tasks and test two
extensions: partial-progress credit for parent programs and token-cost-adjusted selection.
We evaluate each component separately under a fixed model and held-out test protocol.

Say the method is different now; say it is better only on the metrics/datasets where real
measurements support that statement. These are project extensions relative to this paper,
not an established claim of global research novelty. Execution-feedback and richer-reward
approaches exist in later literature, including domain-specific extensions of bandit repair.

## Source references

- Paper (the supplied v3): https://arxiv.org/abs/2405.17503v3
- Official REx repository: https://github.com/haotang1995/REx
- Original scheduler: https://github.com/haotang1995/REx/blob/main/acr/scheduler/rex.py
- APPS dataset and evaluation tools: https://github.com/hendrycks/apps
- Ollama chat endpoint and usage counts: https://docs.ollama.com/api/chat
- Local model listing: https://ollama.com/library/qwen2.5-coder
- Container execution controls: https://docs.docker.com/reference/cli/docker/container/run/
- Related later work, PCBSchemaGen: https://arxiv.org/abs/2602.00510

The implementation here is a standalone starter based on the paper's algorithm; it does not
vendor the authors' code or data. Cite the original paper and APPS in your report.
