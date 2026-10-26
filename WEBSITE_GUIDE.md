# The project website, explained from the beginning

This guide assumes you have never studied language models, bandits, or benchmarking. Read it with the website open beside it.

**Website:** <https://code-repair-project-notes.purplestork34.chatgpt.site>

**The central idea:** a language model writes a program. The system tests it. It then decides whether to ask for a fresh program or repair an earlier attempt. We compared three ways of making that decision.

**The measured result:** on five development problems, resampling passed every hidden test on one problem. Baseline REx and the progress-plus-cost extension each did so on four problems. The extension matched REx; it did not improve on REx in this pilot.

The project contains an implemented modification and a working evaluation system. A modification can be real even when a particular experiment produces the same result as its baseline.

## Contents

1. [First understand the basic story](#1-first-understand-the-basic-story)
2. [The words you need](#2-the-words-you-need)
3. [How to navigate the site](#3-how-to-navigate-the-site)
4. [Page 1: Overview](#4-page-1-overview)
5. [Page 2: Methods](#5-page-2-methods)
6. [Page 3: Results](#6-page-3-results)
7. [Page 4: Testing](#7-page-4-testing)
8. [Page 5: Progress](#8-page-5-progress)
9. [Page 6: Files and evidence](#9-page-6-files-and-evidence)
10. [What was different from original REx?](#10-what-was-different-from-original-rex)
11. [A complete presentation route](#11-a-complete-presentation-route)
12. [Questions you may be asked](#12-questions-you-may-be-asked)
13. [Numbers to remember](#13-numbers-to-remember)
14. [Quick rehearsal checklist](#14-quick-rehearsal-checklist)

---

## 1. First understand the basic story

### 1.1 What problem are we trying to solve?

A language model can write code that looks sensible but produces a wrong answer, crashes, or fails on an unusual input.

Suppose we ask it to write a program that adds two numbers. It might write:

```python
a, b = map(int, input().split())
print(a - b)
```

The code runs, but it subtracts instead of adding. A test with input `2 3` expects `5`; the program prints `-1`.

There are two obvious next steps:

1. Ask the model to write a new solution from the problem statement.
2. Show it the earlier program and a failing test, and ask it to repair the program.

This tiny addition example is only an explanation. The real pilot used five competition-programming problems.

### 1.2 Why is choosing the next step a research problem?

One failed attempt may be almost correct. Another may have a fundamentally wrong approach. Repeatedly repairing the wrong approach can waste requests. Repeatedly starting from scratch can throw away useful progress.

The question becomes:

> “With a limited number of model requests, which existing attempt should we improve, and when should we start again?”

That is the search problem this project studies.

### 1.3 What did we build?

We built a system that:

1. Loads a programming problem and its permitted repair tests.
2. Asks a local language model for code.
3. Extracts the code from the response.
4. Runs the program in an isolated environment.
5. Records which repair tests passed.
6. Uses a search policy to choose the next request.
7. Returns the best eligible program according to repair-test performance.
8. Evaluates that already-selected return against a separate hidden suite.
9. Produces recorded results, costs, graphs, and replayable traces.

The website explains and displays this work. **The website itself does not run the language model or execute a visitor’s code.** Its controls display previously saved measurements.

### 1.4 What are the three methods?

| Method | Simple explanation |
| --- | --- |
| Resampling | Keep asking for fresh solutions. |
| REx | Choose between generating fresh code and repairing earlier candidates using a bandit search policy. |
| Progress + cost | Keep the REx framework, but modify its update rule and selection priority using partial progress and estimated token cost. |

**Say this first:**

> “The model is shared across the comparison. What changes is the policy that decides how to use the model’s next request.”

---

## 2. The words you need

| Word | Meaning in this project |
| --- | --- |
| Language model / LLM | A model that generates text, including source code, from a prompt. |
| Qwen2.5-Coder 7B | The existing code-oriented language model used here. “7B” means roughly seven billion model parameters. |
| Parameter / weight | A numerical value inside the trained model. We did not train or change these weights. |
| Inference | Using an already-trained model to generate a response. |
| Prompt | The input sent to the model: the problem, or a program plus repair feedback. |
| Request / call | One attempt to obtain a model response. A returned response can be useful, malformed, or incorrect. |
| Token | A piece of text counted by the model. It is not necessarily one word or one character. |
| Input tokens | Tokens in what we send to the model. Repair prompts include earlier code and feedback, so they can be longer. |
| Output tokens | Tokens generated by the model. |
| Candidate | One generated program that the system can examine or refine. |
| Repair / refinement | Asking the model to improve an earlier candidate using feedback. |
| Root | The option to generate a fresh program from the problem statement. It is not an earlier candidate program. |
| Arm | A selectable action in the bandit search. Here, a program is represented as an arm for possible refinement, with a root arm for fresh generation. |
| Policy | The rule that decides which arm to select next. |
| Repair test | An input and expected output that the search is allowed to use as feedback. |
| Hidden test | A separate test used after search; it does not guide candidate selection or repair. |
| Judge | The component that runs a program and compares its output with the expected answer. |
| Trial | One task evaluated with one method and one seed. |
| Seed | A number used to initialize randomness. Seed 0 was used in this pilot. It does not prove all backend execution is perfectly reproducible. |
| Budget | An allowance, such as a number of calls or a token threshold. |
| Checkpoint | A saved point in the recorded search, such as after two calls. |
| Baseline | An existing method used as a comparison. Baseline REx is the direct reference for the extension. |
| Pilot | A small preliminary study, useful for checking the system and observing behavior. |
| Benchmark | A defined evaluation using specified tasks, settings, and metrics. |
| APPS | A programming-problem dataset. This pilot uses a reserved development subset; it is not a full official APPS evaluation. |
| Artifact | A saved output, such as a response, code file, test outcome, graph, or report. |
| Trace | A record of what happened during search: selections, code, feedback, and costs. |
| Mock / synthetic fixture | A deliberately prepared example with predictable behavior for testing software. It is separate from real model-performance evidence. |

### One distinction that prevents many mistakes

**A problem, a test case, a trial, and a model call are different things.**

For example:

- One programming problem can have five hidden test cases.
- Running three methods on that problem creates three trials.
- Each trial can make several model calls.
- Evaluating a saved program against five hidden inputs creates five individual test executions.

Do not describe the experiment as “15 programming problems.” It contains **five problems and fifteen selected trials**.

---

## 3. How to navigate the site

The left-hand menu contains six pages. Follow them in this order:

```text
Overview → Methods → Results → Testing → Progress → Files & evidence
```

On a narrow screen, the menu is behind the navigation button at the top.

- **How it works** opens Methods.
- **See the full comparison** opens Results.
- Method tabs switch between flowcharts.
- Dropdowns on Results display saved checkpoints and filter task rows.
- The test search box filters recorded test names.
- Clicking a graph enlarges it. Use Close or Escape to return.
- Expandable rows reveal extra implementation details.
- Evidence links open records or download files.

The site started as an offline build and was then hosted publicly. The small “Local, offline copy” label describes that original build; the published URL is accessible online.

---

## 4. Page 1: Overview

**Link:** <https://code-repair-project-notes.purplestork34.chatgpt.site/index.html>

**Purpose:** explain the question, the implemented changes, and the main measured result before introducing technical detail.

### 4.1 “Code repair with a search budget”

“Code repair” means improving a generated program. “Search budget” means we cannot keep asking indefinitely in a controlled comparison.

The main comparison targets up to eight nominal calls per task/method trial. Full repair success can stop a trial earlier. The implementation also has a separate coverage-extension ceiling, discussed on Methods.

**Say:**

> “We study how to spend a limited number of requests when a model’s first program may be wrong. The system can generate a fresh solution or repair a previous attempt.”

### 4.2 “Latest pilot result”

The three bars show:

| Method | Problems passing every hidden test | Rate |
| --- | --- | --- |
| Resampling | 1 out of 5 | 20% |
| REx | 4 out of 5 | 80% |
| Progress + cost | 4 out of 5 | 80% |

The percentage is calculated across **problems**:

```text
hidden-suite success rate = successful problems / total problems
4 / 5 = 0.8 = 80%
```

It does not mean “80% of the source code is correct” or “this model is 80% accurate in general.” A successful problem here means its returned program passed all five hidden tests in this pilot.

**Say:**

> “The repair-based methods passed every hidden test on four of the five problems, compared with one problem for repeated sampling. The combined extension matched baseline REx.”

### 4.3 The four numbers beneath the introduction

| Number | Meaning |
| --- | --- |
| 5 problems | Five different programming tasks. |
| 3 methods | Resampling, REx, and progress-plus-cost REx. |
| 15 completed trials | Five tasks × three methods × one seed. |
| 108 model requests | The requests represented by the fifteen selected trial records. |

Why not 120 calls, since `15 × 8 = 120`? Both REx variants stopped after two calls on one task instead of using eight. That saved six calls for each variant:

```text
Resampling:          8 + 8 + 8 + 8 + 8 = 40
REx:                 8 + 8 + 8 + 2 + 8 = 34
Progress + cost:     8 + 8 + 8 + 2 + 8 = 34
Total:                               108
```

The 108 calls are the selected comparison, not all setup, interrupted, discarded, or archived work.

### 4.4 “What we changed”

There are two algorithmic changes:

1. **Progress feedback:** give fractional credit to a nonterminal repair that improves its parent.
2. **Estimated token cost:** adjust which arm is selected using an estimate of the next request’s cost.

We changed the surrounding search policy, not the language model’s weights.

**Say:**

> “My extension changes how the system rewards partial repair progress and how it chooses a candidate when the next requests have different estimated costs.”

### 4.5 “From problem to result” pipeline

Read its five boxes from left to right:

1. **Frozen tasks:** fix the tasks and repair/hidden split before evaluation.
2. **Search:** generate programs, execute repair tests, and select further attempts.
3. **Seal:** freeze the selected search evidence and returned programs using recorded hashes.
4. **Hidden evaluation:** test those fixed returns using the separate hidden suites.
5. **Analysis:** compare success and cost across the same tasks.

“Seal” means **freeze**, not “fix the bugs.”

**Say:**

> “The repair tests guide search. We fix the returned programs before evaluating hidden tests, so the hidden scores do not influence the search decisions.”

### 4.6 “The work, in detail” and “About this result”

These links take the visitor to the detailed pages. The note at the bottom places the result in context: this is a five-task development pilot, not the larger final study.

You can finish this page with:

> “I’ll first explain the selection methods, then the measured results, and finally the testing and saved evidence.”

---

## 5. Page 2: Methods

**Link:** <https://code-repair-project-notes.purplestork34.chatgpt.site/methods.html>

**Purpose:** show what the algorithms actually do and identify the implemented changes precisely.

### 5.1 The opening definitions: program, arm, root, and h

The repair score `h` is:

```text
h = repair tests passed / repair tests attempted
```

If a program passes three of five repair tests, `h = 0.6`.

- The current program is the **parent** when we ask for a repair.
- The generated repair is its **child**.
- A branch is a sequence of such refinements.
- The root lets the search start another fresh candidate.

Visualize the search like this:

```text
Root
├── Program A
│   ├── Repair A1
│   └── Repair A2
└── Program B
    └── Repair B1
```

Trying a fresh program explores a new approach. Repairing a promising program exploits information already obtained.

### 5.2 Model and parameter row

| Label | Meaning |
| --- | --- |
| Qwen2.5-Coder 7B | Existing model used to generate and repair code. |
| C = 20 | Strength of the initial repair-score-based Beta prior. |
| η = 0.5 | Weight on positive partial progress. Read η as “eta.” |
| γ = 0.5 | Exponent used to scale the estimated cost. Read γ as “gamma.” |

These are settings of the experiment, not results discovered by the experiment. We did not establish that they are universally optimal.

### 5.3 First tab: Resampling

**Click:** Resampling.

Read its flowchart:

1. Start with the programming problem.
2. Ask the model for a fresh solution.
3. Extract and execute the code against repair tests.
4. If all repair tests pass, return that program.
5. Otherwise, remember the best eligible completed candidate and try another fresh generation while the budget permits.
6. At the stopping point, return the best candidate by repair score.

Earlier candidates are not selected for repair in this method. However, repair-test scores are still used to select the final return.

**Say:**

> “Resampling is the control method. It repeatedly generates new solutions instead of refining an earlier program. We still test its candidates and return the one with the best repair score.”

### 5.4 Second tab: REx

**Click:** REx.

The flowchart is a loop:

1. Maintain the candidate bank, including the root option.
2. Sample a priority for every eligible arm.
3. Choose the largest priority.
4. If the root was chosen, request fresh code.
5. Otherwise, provide the chosen program and one failing repair case and request a correction.
6. Parse the response and execute repair tests.
7. On full repair success, save the program and stop.
8. Otherwise, add the new arm, update the parent as appropriate, retain the best eligible code, and continue while the budget permits.

#### What is a bandit?

Imagine several options whose usefulness is uncertain. You must choose which one to try next, while learning from earlier attempts. This is the basic bandit idea.

Here, the options are candidate programs to refine and the root option for fresh generation. New programs introduce new options, so the set of arms grows during search.

#### What is Thompson sampling?

The policy keeps a distribution for each arm. It draws one value from each distribution and selects the largest draw.

The draw introduces exploration: a less-established candidate can occasionally be selected. The distribution also favors candidates supported by stronger evidence.

**Say:**

> “REx uses Thompson sampling to balance exploration and exploitation. It samples from each arm’s distribution and selects the arm with the largest sampled value.”

#### What does Beta mean?

`Beta(α, β)` is a distribution over values between zero and one. Read α as “alpha” and β as “beta.”

For ordinary candidate arms, initialization is:

```text
alpha = 1 + C × h
beta  = 1 + C × (1 − h)
```

With `C = 20` and `h = 0.6`:

```text
alpha = 1 + 20 × 0.6 = 13
beta  = 1 + 20 × 0.4 = 9
```

You do not need to derive the Beta density function. Explain that the repair score initializes the arm’s distribution and that `C` controls how strongly it influences the initial values.

**Important exception:** the root starts at `Beta(1, 1)`. Do not apply the ordinary candidate formula to the root as though it were a program with `h = 0`.

Also, a Beta sample is a policy score, not the language model’s own confidence that its code is correct. The pass-fraction prior and the extension are heuristic choices; do not interpret them as a certified probability of program correctness.

### 5.5 Third tab: Progress + cost

**Click:** Progress + cost.

The overall loop is the same. The highlighted differences are:

1. Scale the sampled priority using estimated token cost.
2. Credit a positive nonterminal repair improvement in the parent update.

Everything else in the controlled comparison remains shared.

**Say:**

> “The extension keeps the REx search structure. I changed two decisions inside it: the update after a partial improvement and the priority used to choose the next arm.”

### 5.6 Change A: “Give credit to an improvement”

The formula is:

```text
r = eta × max(0, h_child − h_parent)

alpha ← alpha + r
beta  ← beta + (1 − r)
```

Read the first line as:

> “Reward equals eta times the positive improvement in repair score.”

Suppose a parent scores `0.3` and an incomplete child scores `0.7`:

```text
improvement = 0.7 − 0.3 = 0.4
reward      = 0.5 × 0.4 = 0.2
```

The parent receives an alpha increase of `0.2` and a beta increase of `0.8`. This is partial credit rather than treating every incomplete repair identically.

If the child is worse or equal, `max(0, difference)` makes the progress reward zero. These updates do not use negative progress rewards.

#### A subtle but important point

Baseline REx **already uses partial repair performance to initialize newly acquired arms**. Our extension does not introduce partial test information from nothing.

The difference is in the **parent update after an incomplete refinement**: baseline REx gives that incomplete attempt zero success credit; the extension can assign fractional positive credit when it improved the parent.

The fractional update applies to non-root, nonterminal repairs. Root partial generations receive zero progress credit. Full repair success is saved and stops before updating the parent, following the upstream terminal rule.

### 5.7 Change B: “Account for the next request’s cost”

The formula is:

```text
priority = theta / max(1, estimated_tokens)^gamma
theta is sampled from Beta(alpha, beta)
```

Read θ as “theta.” Here it is the sampled arm score.

With `gamma = 0.5`, the denominator is the square root of estimated tokens. An arm requiring a longer estimated request gets a larger denominator, which lowers its priority relative to an otherwise similar arm.

`max(1, estimated_tokens)` prevents a zero or tiny denominator.

This is a **preference in the selection formula**, not a guarantee that the complete experiment will use fewer tokens.

#### Where does the estimate come from?

Initially:

```text
estimated tokens = prompt characters / 4 + 512
```

The first part roughly estimates input size; 512 is the initial output estimate. The estimator adapts using observed input/output counts within the same trial.

An exponential moving average puts some weight on the new observation while retaining older information. In this implementation, the update gives the new observation weight `0.2`.

**Crucial distinction:** estimated tokens guide selection. **Actual backend token counts** are used for reported costs.

### 5.8 The interactive worked example

**Click and move:** the parent-score and child-score sliders.

The default values `0.30` and `0.70` produce reward `0.20`. Move the child below the parent and the reward becomes zero.

The example keeps both scores below one so you are demonstrating the nonterminal rule rather than the full-success stopping case.

The second example gives two arms:

| Arm | Sampled score | Estimated tokens |
| --- | --- | --- |
| A | 0.60 | 1,000 |
| B | 0.70 | 4,000 |

Baseline REx chooses B because `0.70 > 0.60`.

The extension calculates:

```text
A: 0.60 / sqrt(1000) ≈ 0.0190
B: 0.70 / sqrt(4000) ≈ 0.0111
```

Now A has the larger priority.

**Say:**

> “This is a worked example showing how the formula can change a selection. These values are illustrative, not measurements from the benchmark.”

That distinction matters: the example shows a functional difference in the rules, while the real pilot happened to produce identical baseline and extension trajectories.

### 5.9 Shared rules and expandable implementation details

Explain the list at the bottom:

- The model, prompts, tests, parser, and judge limits are shared across methods.
- A repair prompt includes one selected failing case for the current parent, not the hidden suite.
- The best eligible program is selected by repair score, with earlier creation breaking ties.
- “Eligible” means actual extracted code that can be returned; a malformed completion cannot become the returned code merely by tying at score zero.
- Invalid and duplicate generations still use budget.
- Full repair success stops a trial early.
- Nominal call coverage is eight calls. The separate sixteen-call ceiling allows token-coverage extensions where needed. **The selected pilot used zero extension calls.**
- Hidden outcomes never choose the return.

Under **Implementation and original source**, the code links show the actual policy and estimator. The paper link provides the source REx method. The scheduler reproduction is not a claim to reproduce the paper’s entire historical model, prompting stack, or all benchmark domains.

---

## 6. Page 3: Results

**Link:** <https://code-repair-project-notes.purplestork34.chatgpt.site/results.html>

**Purpose:** show what happened in the measured experiment, not just what the method was designed to do.

### 6.1 Headline and final table

| Method | Hidden-suite success | Calls across five tasks | Actual tokens | Tokens per hidden success |
| --- | --- | --- | --- | --- |
| Resampling | 1/5 = 20% | 40 | 25,819 | 25,819 |
| REx | 4/5 = 80% | 34 | 27,247 | 6,811.75, displayed rounded to 6,812 |
| Progress + cost | 4/5 = 80% | 34 | 27,247 | 6,811.75, displayed rounded to 6,812 |

#### How to explain each column

- **Hidden success:** the number of tasks whose returned program passed every hidden test.
- **Calls:** the total model requests used by that method across five tasks.
- **Actual tokens:** observed input plus output tokens across those selected trials.
- **Tokens per hidden success:** total tokens across successful and unsuccessful tasks divided by the number of successful tasks.

For REx, `27,247 / 4 = 6,811.75`. This is an aggregate efficiency ratio, not a statement that every successful program individually cost exactly that much.

### 6.2 The two percentages below the table

**15% fewer calls:**

```text
(40 − 34) / 40 × 100 = 15%
```

**About 5.5% more total tokens:**

```text
(27,247 − 25,819) / 25,819 × 100 ≈ 5.5%
```

A repair request includes earlier code and test feedback, so fewer requests can still contain more text overall.

**Say:**

> “The REx-based methods solved more problems with fewer calls than resampling in this pilot. They used slightly more total tokens. The extension’s success and token totals matched baseline REx.”

Both REx variants having the same efficiency does not establish a unique saving caused by the extension.

### 6.3 “Explore the recorded checkpoints”

**Click:** Budget type → Model calls. Then choose a checkpoint.

You are asking: “What returned solution would be available after this many completed calls per trial?” The website reads saved evaluation rows; it is not rerunning the experiment.

The recorded hidden-suite rates are:

| Call checkpoint | Resampling | REx | Progress + cost |
| --- | --- | --- | --- |
| 1 | 0% | 0% | 0% |
| 2 | 0% | 60% | 60% |
| 3 | 0% | 60% | 60% |
| 4 | 0% | 60% | 60% |
| 5 | 0% | 60% | 60% |
| 6 | 0% | 60% | 60% |
| 7 | 0% | 60% | 60% |
| 8 | 20% | 80% | 80% |

At checkpoint two, 60% means three of the five returned programs pass their hidden suites. It does not mean three trials had already stopped: a program can pass the small hidden suite while still failing some repair cases.

The table below the bars shows **prefix calls** and **prefix tokens**. A prefix is the completed portion of a trial up to the selected checkpoint.

A trial that stops on full repair success after two calls retains that return at later checkpoints; it does not need six imaginary extra calls.

### 6.4 The actual-token-threshold option

**Click:** Budget type → Actual token threshold.

There are two recorded thresholds: 1,024 and 2,048 tokens per trial.

| Token threshold | Resampling | REx | Progress + cost |
| --- | --- | --- | --- |
| 1,024 | 0% | 40% | 40% |
| 2,048 | 0% | 40% | 40% |

These are completed-generation prefix comparisons. If one generation takes cumulative tokens from 900 to 1,200, it is not eligible at the 1,024 checkpoint: it had not completed within that threshold. Its cost is still counted in the overall campaign.

The system does not cut a program halfway through and pretend that partial output is a completed solution. These token plots are not evidence of a strict live token cap.

### 6.5 “Per-problem results”

The method filter hides rows for other methods; it does not alter any measurement.

Each row contains:

1. **Problem:** a dataset identifier, such as `test/0163`.
2. **Method:** which policy ran the trial.
3. **Repair tests:** how many feedback tests the returned program passed.
4. **Hidden tests:** how many separate evaluation tests it passed.
5. **Calls:** requests consumed in that trial.
6. **Tokens:** actual observed input plus output tokens.

The five problems concern:

| Identifier | Plain-language description |
| --- | --- |
| `test/0107` | Whether a binary string can be reduced to a positive binary number divisible by 64. |
| `test/0136` | Comparing two very long nonnegative integers, allowing leading zeroes. |
| `test/0146` | Choosing a repeating group of browser tabs to close to maximize the remaining type imbalance. |
| `test/0163` | Whether a grasshopper can reach an insect using fixed-length jumps and avoiding blocked landing cells. |
| `test/0173` | Whether every junction is reachable from every other junction in a grid of one-way streets. |

The `test/` prefix belongs to the source dataset. These tasks were explicitly reserved for development; calling this a development pilot does not rename the source partition to “train.”

#### The complete hidden-test matrix

| Problem | Resampling | REx | Progress + cost |
| --- | --- | --- | --- |
| `test/0107` | 4/5 | 5/5 | 5/5 |
| `test/0136` | 0/5 | 5/5 | 5/5 |
| `test/0146` | 5/5 | 5/5 | 5/5 |
| `test/0163` | 3/5 | 5/5 | 5/5 |
| `test/0173` | 3/5 | 3/5 | 3/5 |

Only a full `5/5` counts as a solved hidden suite. A `4/5` is not a successful task under this metric.

#### A useful row to demonstrate

Show `test/0163`:

- Resampling used eight calls and passed three of five hidden tests.
- Each REx variant used two calls and passed all five hidden tests.

**Say:**

> “This task is a concrete example where repair-based search produced a hidden-suite success using fewer calls than fresh sampling.”

#### Why can repair and hidden scores disagree?

They contain different input cases. For instance, a REx return on `test/0136` passed three of five repair tests and all five hidden tests.

That is possible because neither suite covers every possible input. It is also why “passed this hidden suite” is more precise than “proved fully correct.” The model did not see those hidden tests during search.

### 6.6 “Curves and diagnostics”

#### Graph 1: success versus calls

- Horizontal axis: completed model-call budget per trial.
- Vertical axis: fraction of tasks with a hidden-suite-successful return.
- Lines: the three methods.
- Shading: descriptive 95% task-bootstrap intervals.

The baseline and extension lines overlap because they have identical measured outcomes. The graph deliberately uses different line styles so both are visible.

**Say:**

> “The call curve shows how quickly successful returned programs became available. Both REx variants reached three out of five at two calls and four out of five by eight calls.”

#### Graph 2: success versus tokens

The horizontal axis is the recorded token threshold, not the number of calls. Read it using the completed-prefix rule above. There are only two configured token checkpoints; do not describe the line as a dense measurement over every token value.

#### Graph 3: per-task heatmap

Rows are tasks and columns are methods. The number in each cell is hidden tests passed out of five. Darker cells correspond to more passed tests; use the written number, not just the colour.

#### What is a bootstrap interval?

It estimates how sensitive a statistic is to the observed task sample by repeatedly resampling tasks with replacement and recomputing the statistic. Methods stay paired on the same resampled tasks. The configured analysis uses 10,000 bootstrap draws.

With only five tasks and one seed, interpret the intervals cautiously. They do not turn this small pilot into a large study. An extension-minus-REx interval of zero comes from identical observed outcomes and is not proof that the methods are equivalent on all future problems.

### 6.7 “What the traces show”

The recorded sequences show that REx and the extension:

- Chose the same parents on all five tasks.
- Generated the same code sequences: 34 generations each.
- Used identical actual token totals.
- Produced identical final hidden-test results.

The extension received two positive nonterminal progress updates, but they did not change those chosen trajectories.

Possible explanations include sparse repair feedback, the short budget, and strong initial priors. These are reasonable hypotheses; the pilot did not isolate which explanation caused the tie.

**Say:**

> “The code changes are implemented, but the trace analysis shows they did not change the selected branches in this particular pilot. Separate component runs and a larger study would be needed to evaluate when they help.”

### 6.8 “Comparison cost and total work”

| Scope | Requests | Known tokens | Unknown usage |
| --- | --- | --- | --- |
| Selected comparison | 108 | 80,313 | None |
| All GPU pilot work, including discarded trials | 131 | 101,706 | One request |
| Archived CPU pilot | 18 | 16,103 | None |
| All pilot work | 149 | 117,809 | One request |

The selected comparison is the set used for the method results. The larger totals preserve the cost of earlier and discarded work. Do not add the selected row to the all-GPU row: the selected work is already contained in that GPU total.

One interrupted original request has no saved response, so its exact usage remains unknown. Therefore 117,809 is a **known-token sum**, not a complete exact total. Setup, smoke checks, audits, and hidden judging are separate work too.

### 6.9 AUC, if someone opens the CSV

The method-results file includes normalized call AUC. Here, it is the mean hidden success across the eight integer call checkpoints, a measure of how early the method produces successful returns.

```text
Resampling: (0 + 0 + 0 + 0 + 0 + 0 + 0 + 0.2) / 8 = 0.025
REx:        (0 + 0.6 + 0.6 + 0.6 + 0.6 + 0.6 + 0.6 + 0.8) / 8 = 0.55
Extension:  same as REx = 0.55
```

It is not another measure of final accuracy. It summarizes success over the call budget.

---

## 7. Page 4: Testing

**Link:** <https://code-repair-project-notes.purplestork34.chatgpt.site/testing.html>

**Purpose:** explain how the software and experiment were checked. This page is different from Results: testing the harness is not the same as measuring model performance.

### 7.1 The top four numbers

| Number | Meaning |
| --- | --- |
| 97 offline tests | Passing software unit/integration checks, excluding the real Docker and live-model test marks. |
| 15 real Docker tests | Passing tests that actually exercised isolated Linux containers. |
| 150 hidden checkpoints | The saved task/method/budget combinations that were evaluated. |
| 0 evaluation infrastructure errors | The hidden evaluator completed without runner failures. |

Zero infrastructure errors does not mean every generated program was correct. Wrong answers are normal measured outcomes; an unavailable or broken judge would be an infrastructure problem.

**Say:**

> “We checked the evaluation machinery separately from the model results. The offline suite checks software behavior, the Docker suite checks execution behavior, and the hidden benchmark measures returned-program success.”

### 7.2 The verification table

#### Offline suite: 97 passed

These tests check logic such as policies, metrics, dataset handling, recovery, reconciliation, and pipeline behavior without requiring real model inference or the real Docker mark.

Some use mock responses with known outcomes. That is useful for detecting a bug: if the expected response and score are known, we can check the software exactly. Those prepared examples are not presented as real model benchmark results.

#### Real Docker suite: 15 passed

These checks execute actual fixture programs inside Linux containers. They cover correct output, wrong output, syntax/runtime failures, limits, isolation, and cleanup.

The 15 Docker tests are **not** the same thing as the 15 task/method trials.

#### Live-model smoke: one passed

A smoke test is a small end-to-end check: can we contact the installed model and exercise the intended path? It establishes basic integration, not high accuracy.

This record predates the website verification. It was not rerun just to create the page; the site labels it as an earlier recorded check.

#### Scheduler conformance: six matched

The implementation was compared with the pinned upstream REx scheduler on controlled fake domains. A fake domain is a prepared environment with predictable behavior.

Matching traces checks algorithm behavior such as selections and updates. It does not mean reproducing the original paper’s performance on every task or using the original model stack.

#### Reference audit: 92 executions

Before treating the chosen test suites as useful, vetted reference solutions were run against them. The recorded audit covers five tasks and 92 individual reference-test executions.

These are not 92 generated model solutions or 92 benchmark tasks.

#### Hidden evaluation: 750 executions

The arithmetic is:

```text
5 tasks × 3 methods × 1 seed = 15 trials
8 call checkpoints + 2 token checkpoints = 10 checkpoints per trial
15 × 10 = 150 checkpoint evaluations
150 × 5 hidden test cases = 750 individual test executions
```

The same task’s hidden inputs are reused across methods and checkpoints. Therefore **750 executions are not 750 independent problems or 750 unique hidden cases**. There are five hidden cases per task, or 25 task-specific hidden cases in the dataset.

### 7.3 Dates and durations

The website records current offline and Docker runs from 26 October 2026, around 10:03 local time. Their recorded durations were about 61 seconds and 30 seconds, respectively.

These durations refer to the software test suites, not the full model campaign or hidden evaluation.

### 7.4 “How programs were tested”

#### What is Docker?

Docker provides isolated containers in which a program can run with a controlled environment and limits. Think of each test receiving a fresh temporary execution room.

It is useful because generated code may crash, loop forever, print excessive output, or create processes.

The runner uses:

- A pinned Linux runner image: a recorded version of the execution environment.
- No network inside the test container.
- Non-root execution: the generated program is not an administrator inside the container.
- A read-only source mount: source is supplied without giving broad writable access to the project.
- Memory, CPU, process, time, and output limits.
- Compilation checking before program execution.
- Cleanup after tests, including descendant processes.

The expected output remains on the host, rather than being mounted as an answer file for the generated program to read. A repair prompt can still legitimately include the expected output of its selected failed repair case.

These controls provide bounded isolation evidence. Avoid claiming that no possible malicious program could ever escape under any circumstances.

### 7.5 Failure cases covered

| Case | Simple example or meaning |
| --- | --- |
| Correct output | Program prints the expected answer. |
| Wrong answer | Program runs, but its answer differs. |
| Syntax error | Code is not valid Python, for example a missing colon. |
| Runtime error | Valid code fails while running, for example an exception. |
| CPU/time limit | Program consumes too much execution time. |
| Memory limit | Program allocates more memory than allowed. |
| Output limit | Program prints too much text. |
| Cleanup | Processes and containers do not remain active after a test. |
| Cancellation | An interrupted judging operation removes its owned container. |

### 7.6 “Execution limits and model setup”

Open this expandable row if someone asks for the environment.

| Setting | How to explain it |
| --- | --- |
| Q4_K_M | The model’s quantized representation, using a lower-precision storage scheme to reduce memory requirements. It is not a model we trained. |
| Ollama | The local service used to run the model and return generation/usage information. |
| Vulkan | The GPU backend used for the measured GPU pilot. |
| RTX 4060 Laptop | The GPU used for local inference. |
| Context 16,384 | Configured context size for requests. |
| Output limit 2,048 | Configured maximum generated output-token allowance per request. |
| Temperature 1.0 | A model sampling setting. It is shared across compared methods. |
| Seed 0 | The seed used in the pilot. One seed does not measure variation across many random runs. |
| 256 MiB | The configured per-test memory allowance. |
| 2 CPU seconds / 5 seconds wall limit | Configured program resource limits. CPU time and elapsed wall time are different measurements. |
| One worker / one request | Work is scheduled serially rather than making simultaneous model requests. |

For a precise technical answer, the runner shares an execution deadline across its compile/run work. Do not rely on the page’s abbreviated “per phase” wording to claim a fresh independent five-second allowance for each phase.

The container’s “no network” rule applies to candidate execution. It does not mean the published website is offline or that the host cannot communicate with the local model service.

### 7.7 “From saved response to hidden score”

#### Durable request accounting

“Durable” means saved so that it can survive an interrupted process.

The important order is:

```text
Save request intent
    → make model request
    → save raw response
    → parse code
    → judge repair tests
    → commit the search update
```

Saving the raw response before later work allows recovery without generating a different response again.

If a request was dispatched but its response is missing, the system cannot know exactly what happened. It records an unknown outcome instead of calling it free or silently repeating it.

#### Completed-resume check

A completed smoke run was resumed. It had two calls before and two after, with 2,010 tokens before and after. No extra inference was introduced by resuming an already-completed run.

#### Sealed evaluation

A hash is a fingerprint of data. A seal records fingerprints for the plan, setup, tasks, artifacts, and logical database state.

Checking the seal before and after evaluation helps detect changed evidence. It does not independently prove that the algorithm is good; it protects the identity of the measured record.

#### No censored checkpoints

A censored checkpoint is one for which required evidence or coverage is insufficient. The selected analysis has no missing/censored checkpoints and no unknown selected usage.

The original interrupted campaign still has its unknown request; it was not erased just because the separate selected view is complete.

### 7.8 “Inspect the test cases”

**Click:** choose Real Docker tests or Offline tests. Search for words such as `memory`, `recovery`, `policy`, or `reconcile`.

The list shows recorded test names and their results. It does not execute a test when you search. The XML Record links contain the underlying test-run reports.

### 7.9 Final note: what a passing test means

Do not merge all these counts into one accuracy number:

- Software fixtures check the harness.
- Docker fixtures check real execution behavior.
- Reference audits check the chosen data/test setup.
- Hidden evaluation measures generated-program outcomes.

They support different parts of the project.

---

## 8. Page 5: Progress

**Link:** <https://code-repair-project-notes.purplestork34.chatgpt.site/progress.html>

**Purpose:** explain the sequence of work and separate completed implementation/pilot work from the unexecuted larger study.

### 8.1 Current position

“The small pilot is complete” refers to the fifteen selected trial records and their hidden evaluation. It does not say the original interrupted campaign magically became complete or that the full final study has finished.

### 8.2 The eight milestones

| Milestone | Plain explanation |
| --- | --- |
| Source and contracts | Preserve the starting project, identify the upstream scheduler version, and define the formats exchanged by components. A software “contract” here is a data/interface rule, not a legal agreement. |
| Dataset and reference audit | Choose tasks, separate repair/hidden tests, and check reference solutions against those tests. |
| Runner and backend | Connect the local model and the isolated program executor. Check usage fields and enable GPU inference. |
| Search policies | Implement the methods and the progress/cost changes. |
| Recovery and accounting | Save requests, responses, outcomes, and costs; handle uncertainty after crashes. |
| Development pilot | Complete the selected task/method comparison, including the all-method replacement task. |
| Hidden evaluation and analysis | Evaluate fixed returns and generate summaries, cost records, and traces. |
| Larger held-out study | Planned but not run: 30 tasks, six methods, three seeds. |

“Backend” means the component that connects the harness to the model. “Runner” means the component that executes generated code.

**Say:**

> “The implementation and local pilot are complete. The larger held-out study is future work, so I separate it from the results shown here.”

### 8.3 “The interrupted task”

An original GPU request on `test/0146` lost its response during interruption. We preserved that unknown request and its earlier records.

Before replacement inference and hidden judging, a rule was fixed to rerun the whole affected task for all three methods. The selected comparison uses:

```text
12 unaffected original trials
+ 3 fresh trials for the affected task
= 15 completed selected trials
```

All three fresh affected-task trials were used regardless of scores. We did not choose whichever old or new result looked best after hidden evaluation.

“Source mappings” record where each trial came from. “Provenance” is the general word for this origin/history information.

**Say:**

> “One response was lost. We preserved the original record and reran the affected problem for all methods under a fixed rule. The report identifies the three replacement trials and includes discarded work in total-cost accounting.”

### 8.4 “What to measure next”

1. **Separate the components:** run progress-only and cost-only policies. This is a component ablation: change one part at a time to understand its effect.
2. **More tasks and seeds:** measure whether the result changes across more problem types and random runs.
3. **Freeze a final protocol:** decide the dataset, settings, budgets, and metrics before inspecting held-out final results.

The planned six-method comparison includes resampling, greedy selection, REx, progress-only REx, cost-only REx, and the combined extension. Only three of those were in this measured pilot.

“Held-out” means reserved from tuning. After selecting settings on development data, final evaluation should not be used as a feedback loop for more parameter choices presented as an untouched test.

---

## 9. Page 6: Files and evidence

**Link:** <https://code-repair-project-notes.purplestork34.chatgpt.site/files.html>

**Purpose:** let someone inspect the records behind the page instead of relying only on a summary.

### 9.1 File formats in normal language

| Format | What it is |
| --- | --- |
| Markdown / `.md` | A readable text document with headings and tables. This guide is an example. |
| JSON | Structured data with named fields, readable by software and humans. |
| CSV | Rows and columns of data that can be opened in a spreadsheet. |
| XML | Structured text used here for test reports. |
| Python / `.py` | Source code for implementation logic. |
| ZIP | A compressed bundle of multiple files. |
| HTML | A webpage, including the saved trace replays. |

You do not need to memorize or read every raw file during the presentation. Know which file answers which question.

### 9.2 Group 1: Results and measurements

| Website link | What to explain |
| --- | --- |
| Comparison report | The written findings, setup, provenance and limits. Open this for the overall experiment story. |
| Verified findings · JSON | Key measured counts and method outcomes in machine-readable form. |
| Method results · CSV | One row per method, including success, calls, tokens and normalized call AUC. |
| Per-problem results · CSV | Detailed repair/hidden outcomes for every selected trial. |
| All checkpoints · CSV | Results across call/token thresholds, including intervals and differences. |
| Work accounting · CSV | Source campaign request counts, known tokens and unresolved usage. |

Some tiny files show “0 KB” because the website rounds their size to whole kilobytes. It does not mean the file is empty.

### 9.3 Group 2: Testing records

| Website link | What it supports |
| --- | --- |
| Offline suite · XML | The recorded 97-test offline run. |
| Real Docker suite · XML | The recorded 15-test real-container run. |
| Installed-model smoke · XML | The earlier passing installed-model test. |
| Scheduler conformance · JSON | The six controlled upstream scheduler comparisons. |
| Reference audit · JSON | The five-task reference audit summary. |
| Benchmark integrity checks · JSON | Complete selected coverage, source immutability and seal checks. |

A test report describes what was executed and whether it passed. It is useful evidence, but a harness test report is not itself proof of improved model accuracy.

### 9.4 Group 3: Provenance and reproducibility

| Website link | What it means |
| --- | --- |
| Trial source mapping | Identifies the source campaign for each selected trial. |
| Replacement protocol | Records the affected-task rerun rule before replacement inference and hidden evaluation. |
| Search seal | The recorded fingerprints and coverage of the analysis view. |
| Resolved model and judge | Exact model, sampling, environment and runner settings. |
| Policy implementation | Actual arm initialization, selection and update source code. |
| Cost estimation | The initial estimate, its adaptation, and actual-usage charging logic. |
| Sealed benchmark bundle | Analysis database, content-addressed artifacts, evaluation records and source mappings. |

The database is SQLite: a local database stored in a file. It contains structured request, generation, outcome and event records. Content-addressed artifacts use their content hashes as identifiers.

The bundle is evidence for inspection and analysis; it does not include the model’s multi-gigabyte weights or a one-click environment installer. Reproducing inference also requires the appropriate environment and pinned model.

### 9.5 Group 4: Recorded search traces

There are three links:

1. **Representative trace:** a selected recorded search to inspect in detail.
2. **Hidden-success trace:** a recorded returned program that passed every hidden test.
3. **Hidden-failure trace:** a recorded returned program that did not.

A trace opens another local/static HTML report. It does not contact the model or execute the displayed code.

Inside a replay, explain:

- **Problem:** the programming question being solved.
- **Root:** the fresh-generation option.
- **Arm nodes:** generated candidates in creation order.
- **Edges:** which parent produced which refinement.
- **h value:** repair pass fraction for that candidate.
- **Depth:** distance from the root; a deeper node has more refinement steps in its ancestry.
- **Code:** the exact extracted program, or an invalid-completion label when no eligible code was extracted.
- **Estimated/actual tokens:** the policy estimate versus measured backend usage.
- **Selection draws and priors:** the values used to choose the next arm.
- **Exact prompt and feedback:** what was supplied to the model for that step.
- **Ledger:** accumulated resource accounting.
- **Hidden annotations:** post-search evaluation records; these did not guide the recorded search.

**Say while opening a trace:**

> “This is an actual saved search. The nodes show generated programs, and the edges show which candidate was refined. The report includes the code, feedback, selection information and measured cost for each step.”

### 9.6 Snapshot identifiers

The two long strings identify:

- The sealed search record.
- The specific hidden evaluation version.

They are not passwords, model scores, or numbers you should memorize. Explain them as fingerprints that tie the displayed analysis to a particular recorded snapshot.

**Close the page with:**

> “The claims on the site can be traced to per-task measurements, test reports, raw search records and a sealed analysis bundle.”

---

## 10. What was different from original REx?

This is likely the most important question in a viva.

### The existing idea

The source REx method frames refinement as an exploration/exploitation problem and uses a growing bank of arms with Thompson sampling. Credit that existing method rather than presenting it as your invention.

### The implemented algorithmic extension

| Part | Baseline REx in this controlled harness | Combined extension |
| --- | --- | --- |
| New-arm prior | Based on repair pass fraction | Same |
| Arm score for selection | Beta sample | Beta sample divided by estimated token cost raised to gamma |
| Incomplete non-root refinement | Zero success credit to parent | Fractional positive progress credit when child score improves |
| Root option | Fresh generation remains available | Same |
| Model weights | Fixed | Fixed |
| Return and hidden evaluation | Shared rules | Same |

### The engineering work

The project also implements a common controlled harness, isolated judging, frozen task records, usage accounting, crash-aware persistence, hidden evaluation, analysis and trace replay. Those are concrete implemented parts of the work, even though they are different from proving a new algorithmic performance gain.

### The measured conclusion

The combined extension achieved 80% hidden-suite success and matched baseline REx. The positive measured comparison is against resampling, which achieved 20%.

The 15% reduction in calls against resampling was shared by baseline REx and the extension. It is not an additional reduction uniquely produced by the extension.

**A complete answer:**

> “I reproduced the REx scheduler in a controlled code-repair harness and implemented two modifications: positive partial-progress credit and estimated-token-cost normalization. In the five-task pilot, the combined method passed all hidden tests on four tasks, versus one for resampling, using 34 rather than 40 calls. It matched original REx in this setting. The traces show that the modified rules did not change the selected branches under this budget and seed.”

That answer distinguishes implementation, measurement, and interpretation without suggesting the work was useless or claiming a gain the experiment did not show.

---

## 11. A complete presentation route

### 11.1 If you have about eight minutes

| Time | Page | Focus |
| --- | --- | --- |
| 0:00–1:00 | Overview | The generate-versus-repair question and the pilot result. |
| 1:00–3:15 | Methods | Root/arm idea, REx flow, progress reward and cost priority. |
| 3:15–5:15 | Results | Main table, two-call/eight-call checkpoint, and `test/0163`. |
| 5:15–6:15 | Testing | Separate harness tests from model performance; explain 750 executions. |
| 6:15–7:00 | Progress | Completed pilot, replacement rule, larger study not run. |
| 7:00–8:00 | Files & evidence | Open a recorded trace; point to raw measurements and close. |

Do not read every paragraph aloud. Point at one relevant item and explain it in your own words.

### 11.2 Opening script

> “This project studies how to use a limited request budget for language-model code repair. A model can generate several solutions, but deciding which attempt to refine is important. I implemented a shared evaluation system for resampling, baseline REx, and a progress-and-cost-aware extension. The model stays frozen. The current evidence is a five-problem development pilot with one seed.”

### 11.3 Moving to Methods

> “A candidate program is represented as an arm. The root means generate a new solution. REx samples a score for each arm to balance exploration and refinement. My extension adds partial-progress credit after an improving incomplete repair, and normalizes the selection priority by estimated token cost.”

Show the reward slider, then the two-arm cost example. Label them as worked examples.

### 11.4 Moving to Results

> “Both REx variants passed every hidden test on four of five problems, compared with one for resampling. They used 34 calls instead of 40, but slightly more total tokens. The combined extension matched baseline REx. Looking at the saved trajectories, both policies selected the same branches in this pilot.”

### 11.5 Moving to Testing

> “I tested the machinery separately from measuring generated-code quality. The current software checks have 97 offline tests and 15 real Docker tests passing. The fixed returned programs were evaluated at 150 checkpoints, producing 750 individual hidden-test executions without infrastructure errors.”

### 11.6 Closing script

> “The result demonstrates a working, recorded code-repair pipeline and a positive comparison of repair-based search against resampling in this small setting. The implemented extension did not add an observed improvement over REx here. The next work is separate component ablations, more tasks and seeds, and a frozen held-out evaluation.”

### 11.7 If you only have two minutes

1. Overview: state the question in one sentence.
2. Methods: point to the two changes.
3. Results: show 20%, 80%, 80% and the 40/34/34 call counts.
4. Testing: mention separate test evidence and sealed hidden evaluation.
5. Close with the small-pilot scope and the next experiment.

---

## 12. Questions you may be asked

### “Did you train the language model?”

No. The existing Qwen2.5-Coder model’s weights remained frozen. We changed inference-time search around the model.

### “Is this reinforcement learning?”

It uses an online bandit policy with rewards and exploration/exploitation, following the REx framing. It is not gradient-based model training, RLHF, or a trained deep-RL policy. The added progress update is a heuristic pseudo-count rule.

### “What is exploration versus exploitation?”

Exploration tries a fresh approach or a less-established arm. Exploitation refines an already promising candidate. The policy balances the two rather than always doing one.

### “Why use Beta distributions?”

They provide a convenient distribution over scores between zero and one for Thompson-style sampling. Candidate repair scores initialize their parameters. The extension’s fractional shaping should not be described as an exact Bayesian posterior guarantee.

### “Why not just repair the highest-scoring candidate every time?”

That is a greedy approach. The currently best repair score can be misleading, so a stochastic exploration policy can also try other candidates or the root. The measured pilot did not include a separate greedy baseline; do not claim an experimental win over it here.

### “Does baseline REx already use partial test scores?”

Yes, in the initialization of new arms. The extension additionally uses positive child-minus-parent improvement in the parent’s nonterminal update.

### “Did your proposed modification improve original REx?”

Not in the measured pilot. It matched REx at 80%, with the same selected code trajectories and tokens. The implemented formulas differ, but their choices coincided on these five tasks and this seed.

### “Then what worked?”

The full repair system completed a recorded comparison and hidden evaluation. Both repair-based variants achieved four hidden-suite successes versus one for resampling, using fewer calls. The extension was implemented and tested; the experiment identified a setting where it did not change baseline behavior.

### “Why could the extension have no extra effect?”

The traces show only two positive partial-progress updates, with unchanged selections. Sparse feedback, strong priors and the eight-call budget are plausible reasons. Those explanations need controlled follow-up experiments rather than being asserted as proven causes.

### “Did the cost-aware method reduce tokens?”

Not relative to baseline REx; their totals were equal. Both consumed about 5.5% more total tokens than resampling, despite fewer calls. Token normalization is a selection mechanism, not an automatic guarantee of lower total spending.

### “Could you still compare tokens per successful task?”

Yes. The observed aggregate ratio was about 6,812 tokens per hidden success for each REx variant, versus 25,819 for resampling. It includes failed-task spending and is highly sample-dependent, especially when resampling has only one success.

### “How do we know hidden tests did not guide the result?”

Search used repair tests only, selected the return using repair score, and sealed the record before hidden judging. Hidden outcomes did not rerank returns or generate more repairs.

### “Is the hidden set guaranteed unknown to the model from training?”

No. We control access during this experiment, not the model’s original pretraining data. These are public-source tasks, so training contamination cannot be ruled out from this pilot.

### “Why does a program pass hidden tests while failing repair tests?”

The suites contain different input cases and both are small. Passing one finite suite does not imply passing the other or proving correctness for every input.

### “Were there 750 independent benchmark problems?”

No. There were five tasks. The 750 executions arise from testing saved returns across three methods and ten checkpoints with five hidden cases each. They are repeated evaluations, not 750 independent problem samples.

### “Why only one seed?”

This was a small development pilot under local compute and time constraints. Multiple seeds are needed to measure randomness-related variation. One seed is a limitation, not proof of general stability.

### “What did you do after the interruption?”

Preserved the unknown request and all source evidence, then reran the affected task for all methods under a rule fixed before new inference and hidden evaluation. The selected view identifies the replacement trials and keeps discarded spending in accounting.

### “Does a hash prove the result is true?”

A hash helps verify that the recorded data has not changed. Scientific confidence also depends on the methodology, source records, executed tests, and study size. The seal does not substitute for those.

### “Is the website doing live AI inference?”

No. It is a static research website that displays saved data, diagrams and traces. Its interactive controls recalculate displays from recorded rows.

### “What would you do with more time?”

Run progress-only and cost-only ablations, use richer development feedback, add tasks and seeds, choose settings on development data, and freeze a separate final evaluation protocol.

---

## 13. Numbers to remember

### Essential experiment numbers

| Item | Value |
| --- | --- |
| Tasks | 5 |
| Compared methods | 3 |
| Seeds | 1, using seed 0 |
| Selected trials | 15 |
| Nominal call budget | 8 per trial, with earlier stop on full repair success |
| Selected requests | 108 |
| Selected actual tokens | 80,313 |
| Resampling hidden-suite success | 1/5, or 20% |
| REx hidden-suite success | 4/5, or 80% |
| Extension hidden-suite success | 4/5, or 80% |
| Calls by method | 40, 34, 34 |
| Tokens by method | 25,819; 27,247; 27,247 |
| REx variants’ call reduction vs resampling | 15% |
| REx variants’ extra total tokens vs resampling | About 5.5% |
| Repair tests per problem | 3–6 |
| Hidden tests per problem | 5 |
| Hidden checkpoint evaluations | 150 |
| Individual hidden-test executions | 750 |
| Hidden evaluator infrastructure errors | 0 |

### Essential verification and method numbers

| Item | Value |
| --- | --- |
| Current offline software tests passed | 97 |
| Current real Docker tests passed | 15 |
| Earlier installed-model test passed | 1 |
| Controlled scheduler traces matched | 6 |
| Reference-test executions | 92 |
| Prior strength C | 20 |
| Progress weight eta | 0.5 |
| Cost exponent gamma | 0.5 |
| Positive partial-progress updates in combined policy | 2 |
| REx / extension selected generations each | 34 |
| Token checkpoints | 1,024 and 2,048 |
| Normalized call AUC | 0.025 resampling; 0.55 REx; 0.55 extension |
| All pilot requests including discarded GPU and archived CPU work | 149 |
| All pilot known tokens | 117,809, plus one request with unknown usage |

### Four distinctions to remember under pressure

1. **Implementation difference is not automatically a measured performance improvement.**
2. **Software tests are not the same as model benchmark trials.**
3. **Fewer calls are not automatically fewer tokens.**
4. **Passing five hidden tests is not proof of correctness on every input.**

---

## 14. Quick rehearsal checklist

Before presenting, make sure you can do these without reading a paragraph:

- [ ] Explain the generate-versus-repair question in one sentence.
- [ ] Distinguish an arm, root, parent, child, trial, and call.
- [ ] Calculate a repair score, such as `3/5 = 0.6`.
- [ ] Explain the REx loop using its flowchart.
- [ ] Calculate the default progress example: `0.5 × (0.7 − 0.3) = 0.2`.
- [ ] Explain why dividing by estimated cost can change an arm’s priority.
- [ ] Label the worked example as illustrative.
- [ ] Show the final `20%, 80%, 80%` results and the `40, 34, 34` call counts.
- [ ] Explain why tokens increased slightly despite fewer calls.
- [ ] Demonstrate `test/0163` as a concrete successful repair-search example.
- [ ] Explain that the extension matched REx in this pilot.
- [ ] Distinguish 97 software tests, 15 Docker tests, 15 trials, and 750 executions.
- [ ] Open one trace and point to its parent/child code and feedback.
- [ ] Explain the fixed all-method replacement rule after interruption.
- [ ] State that the larger held-out study has not been run.

If you forget a detail, use a short accurate sentence rather than guessing:

> “That setting is recorded in the resolved configuration; I would check the exact value rather than invent one.”

The main story to remember is:

> “I implemented and evaluated a progress-and-cost-aware extension around an existing REx search method. The system produced a complete, recorded five-task comparison. Both repair-based methods achieved 80% hidden-suite success versus 20% for resampling, while the extension matched baseline REx in this pilot.”

---

## Source records for this guide

This document explains the published six-page snapshot using its local hosted source and saved measurements:

- `site_hosting/dist/index.html`, `methods.html`, `results.html`, `testing.html`, `progress.html`, and `files.html`.
- `website/assets/site.js` for the behavior of the interactive controls.
- `reports/development_pilot_final/FINDINGS.md`, `findings.json`, `method_results.csv`, `per_task_results.csv`, `summary.csv`, `auc.json`, and `mechanism_diagnostics.json`.
- `reports/verification/site_current_offline.xml`, `site_current_docker.xml`, and `live_model_installed.xml`.
- `src/rexbench/policies/__init__.py`, `budgets.py`, and the pinned upstream scheduler for method details.
- Original method reference: [Code Repair with LLMs gives an Exploration-Exploitation Tradeoff](https://arxiv.org/abs/2405.17503).

This guide does not add new benchmark runs or change the website’s measured results.
