"""REx search and two experimental extensions. No model training is performed."""
from dataclasses import dataclass, field
import hashlib
import random
import re
import time

METHODS = ('resample', 'greedy', 'rex', 'rex_progress', 'rex_cost', 'rex_progress_cost')


@dataclass
class Evaluation:
    passed: list[bool]
    feedback: list[str]

    @property
    def h(self):
        return sum(self.passed) / len(self.passed)

    @property
    def solved(self):
        return bool(self.passed) and all(self.passed)


@dataclass
class Node:
    code: str | None
    evaluation: Evaluation | None
    alpha: float
    beta: float
    depth: int = 0
    calls: int = 0

    @property
    def h(self):
        return self.evaluation.h if self.evaluation else 0.0


def make_node(code, evaluation, constant=20, depth=0):
    # The empty-program arm is Beta(1, 1), NOT Beta(1, 1+C).
    if code is None:
        return Node(None, None, 1.0, 1.0)
    return Node(code, evaluation, 1 + constant * evaluation.h,
                1 + constant * (1 - evaluation.h), depth)


def shaped_reward(parent, child_eval, eta):
    if child_eval.solved:
        return 1.0
    # New generation has no preceding program; keep the original root update.
    if parent.code is None:
        return 0.0
    return eta * max(0.0, child_eval.h - parent.h)


def update(parent, child_eval, eta=0.0):
    reward = shaped_reward(parent, child_eval, eta)
    parent.alpha += reward
    parent.beta += 1 - reward
    parent.calls += 1
    return reward


def code_key(code):
    # Exact source identity; different formatting remains a different arm.
    return hashlib.sha256(code.encode()).hexdigest()


def extract_code(text):
    blocks = re.findall(r'```(?:python|py)?\s*\n(.*?)```', text, flags=re.S)
    return (blocks[0] if blocks else text).strip()


def prompt_for(statement, parent, rng):
    prompt = ('Write a complete Python 3 program using only the standard library. Read from standard input and '
              'write only the required answer to standard output. '
              'Return only the complete program in a python code block.\n\n'
              + statement)
    if parent.code is not None:
        failures = [f for ok, f in zip(parent.evaluation.passed,
                                      parent.evaluation.feedback) if not ok]
        failure = rng.choice(failures)
        prompt += ('\n\nThis candidate is incorrect:\n```python\n' + parent.code
                   + '\n```\nOne failed repair test:\n' + failure
                   + '\nRepair the program for the full specification, including edge cases.')
    return prompt


@dataclass
class CostEstimator:
    """Pre-call estimate, calibrated only with previous actual usage counts."""
    chars_per_token: float = 4.0
    output_tokens: float = 512.0

    def predict(self, prompt):
        return max(1.0, len(prompt) / self.chars_per_token + self.output_tokens)

    def observe(self, prompt, input_tokens, output_tokens):
        if input_tokens > 0:
            ratio = min(10.0, max(1.0, len(prompt) / input_tokens))
            self.chars_per_token = .8 * self.chars_per_token + .2 * ratio
        self.output_tokens = .8 * self.output_tokens + .2 * output_tokens


def search(statement, repair_tests, model, evaluator, method='rex', seed=0,
           max_calls=16, constant=20, eta=.5, gamma=.5, on_event=None):
    """Only repair_tests enter search. Hidden evaluation is a separate command.

    model.generate(prompt, seed) -> {text, input_tokens, output_tokens}
    evaluator(code, repair_tests) -> Evaluation

    Progress updates are fractional pseudo-counts, a heuristic extension;
    they are not the original exact Beta-Bernoulli success posterior.
    """
    if method not in METHODS:
        raise ValueError(f'Unknown method: {method}')
    if not repair_tests or max_calls < 1 or constant < 0:
        raise ValueError('Need repair tests, positive budget and nonnegative C.')
    if not 0 <= eta <= 1 or not 0 <= gamma <= 1:
        raise ValueError('eta and gamma must lie in [0,1].')
    rng = random.Random(seed)
    feedback_rng = random.Random(seed ^ 0x1947)
    generation_rng = random.Random(seed ^ 0xA52B)
    root = make_node(None, None)
    nodes = [root]
    seen = {}
    events = []
    estimator = CostEstimator()
    total_tokens = 0
    best = None
    start = time.monotonic()
    for call in range(1, max_calls + 1):
        # Same prompt construction for all methods. Cost estimates are pre-call.
        prompts = [prompt_for(statement, n, feedback_rng) for n in nodes]
        estimates = [estimator.predict(p) for p in prompts]
        if method == 'resample' or len(nodes) == 1:
            index = 0
        elif method == 'greedy':
            # A standard best-score greedy baseline, with seeded random ties.
            top = max(n.h for n in nodes[1:])
            index = rng.choice([i for i, n in enumerate(nodes) if i and n.h == top])
        else:
            exponent = gamma if method in ('rex_cost', 'rex_progress_cost') else 0.0
            scores = [rng.betavariate(n.alpha, n.beta) / c ** exponent
                      for n, c in zip(nodes, estimates)]
            index = max(range(len(nodes)), key=scores.__getitem__)
        parent, prompt = nodes[index], prompts[index]
        response = model.generate(prompt, generation_rng.randrange(2**31))
        code = extract_code(response['text'])
        key = code_key(code)
        duplicate = key in seen
        ev = nodes[seen[key]].evaluation if duplicate else evaluator(code, repair_tests)
        if len(ev.passed) != len(repair_tests) or len(ev.feedback) != len(repair_tests):
            raise ValueError('Evaluator returned a different number of test outcomes.')
        input_tokens, output_tokens = response['input_tokens'], response['output_tokens']
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError('Negative token usage.')
        total_tokens += input_tokens + output_tokens
        estimator.observe(prompt, input_tokens, output_tokens)
        credit = eta if method in ('rex_progress', 'rex_progress_cost') else 0.0
        reward = update(parent, ev, credit)
        if not duplicate:
            child = make_node(code, ev, constant, parent.depth + 1)
            nodes.append(child)
            seen[key] = len(nodes) - 1
        else:
            child = nodes[seen[key]]
        # Preserve statistics of duplicate arms. Charge the generation anyway.
        if best is None or child.h > nodes[best].h:
            best = seen[key]  # ties keep the earlier visible-best candidate
        event = {
            'call': call, 'parent_index': index, 'child_index': seen[key],
            'depth': child.depth, 'parent_h': parent.h, 'child_h': ev.h,
            'best_h': nodes[best].h, 'reward': reward, 'duplicate': duplicate,
            'input_tokens': input_tokens, 'output_tokens': output_tokens,
            'total_tokens': total_tokens, 'estimated_tokens': estimates[index],
            'elapsed_seconds': time.monotonic() - start,
            'parent_alpha': parent.alpha, 'parent_beta': parent.beta,
            'visible_solved': ev.solved, 'candidate_code': code,
            'selected_code': nodes[best].code,
        }
        events.append(event)
        if on_event:
            on_event(event)
        if ev.solved:
            break  # A hidden failure must never resume this search.
    return {'events': events, 'selected_code': nodes[best].code,
            'visible_solved': nodes[best].evaluation.solved,
            'calls': len(events), 'total_tokens': total_tokens}
