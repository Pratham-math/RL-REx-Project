import pytest

from rexbench.search import run_trial
from rexbench.store import Store
from rexbench.types import EvaluationResult, Status, TestOutcome as Outcome
from conftest import fixture_backend, fixture_judge, initialize


class Crash(BaseException):
    pass


@pytest.mark.parametrize("boundary", ["before_dispatch", "after_response", "after_judge", "during_update", "after_commit"])
def test_crash_recovery_exact_policy_and_no_regeneration(tmp_path, task, job, config, boundary):
    reference = initialize(tmp_path / "reference", job)
    backend = fixture_backend()
    uninterrupted = run_trial(reference, task, job, config, backend, fixture_judge(), "experiment")
    expected = reference.snapshots(job["id"])
    store = initialize(tmp_path / "crashed", job)
    first_backend = fixture_backend()
    fired = False

    def fault(point):
        nonlocal fired
        if point == boundary and not fired:
            fired = True
            raise Crash()

    with pytest.raises(Crash):
        run_trial(store, task, job, config, first_backend, fixture_judge(), "experiment", fault=fault)
    store.close()
    resumed_backend = fixture_backend()
    store = Store(tmp_path / "crashed")
    recovered = run_trial(store, task, job, config, resumed_backend, fixture_judge(), "experiment")
    assert store.snapshots(job["id"]) == expected
    assert first_backend.calls + resumed_backend.calls == 4
    assert [a.model_dump() for a in recovered.arms] == [a.model_dump() for a in uninterrupted.arms]
    assert recovered.rng_state == uninterrupted.rng_state
    assert recovered.ledger.tokens == 240
    assert recovered.ledger.inference_attempts == 4
    assert len(store.rows("SELECT * FROM generations")) == 4
    store.close()
    reference.close()


def test_unknown_inflight_is_never_retried(tmp_path, task, job, config):
    store, backend = initialize(tmp_path, job), fixture_backend()
    def fault(point):
        if point == "after_dispatch":
            raise Crash()
    with pytest.raises(Crash):
        run_trial(store, task, job, config, backend, fixture_judge(), "e", fault=fault)
    assert backend.calls == 1
    run_trial(store, task, job, config, backend, fixture_judge(), "e")
    assert backend.calls == 1
    assert store.pending(job["id"])["state"] == "unknown"
    assert store.load(job["id"]).ledger.reservations == 1
    assert store.rows("SELECT status,stop_reason FROM trial_states")[0] == {"status": "paused", "stop_reason": "REQUEST_OUTCOME_UNKNOWN"}


def test_infrastructure_rejudges_response_without_inference(tmp_path, task, job, config):
    store, backend = initialize(tmp_path, job), fixture_backend()
    class BrokenJudge:
        def evaluate(self, code, cases, comparator, limits):
            return EvaluationResult(outcomes=[Outcome(case_id=c.id, status=Status.INFRA_ERROR) for c in cases],
                                    execution_fingerprint="broken")
    run_trial(store, task, job, config, backend, BrokenJudge(), "e")
    assert backend.calls == 1
    assert store.load(job["id"]).arms[0].beta == 1
    assert store.pending(job["id"])["response_blob"]
    run_trial(store, task, job, config, backend, fixture_judge(), "e")
    assert backend.calls == 4
    assert store.load(job["id"]).ledger.policy_steps == 4


def test_invalid_duplicates_charged_and_arms_distinct(tmp_path, task, job, config):
    from rexbench.backends.mock import MockBackend
    backend = MockBackend([{"text": "", "input_tokens": 40, "output_tokens": 20},
                           {"text": "print(0)", "input_tokens": 40, "output_tokens": 20}])
    store = initialize(tmp_path, job)
    result = run_trial(store, task, job, config, backend, fixture_judge(), "e")
    assert result.ledger.tokens == 240
    assert len(result.arms) == 5
    assert result.arms[2].code_hash == result.arms[4].code_hash
    assert result.arms[2].arm_id != result.arms[4].arm_id
    assert len(store.snapshots(job["id"])) == 4


def test_earliest_best_tie_and_no_candidate_checkpoint(tmp_path, task, job, config):
    from rexbench.backends.mock import MockBackend
    from rexbench.judge.mock import MockJudge
    backend = MockBackend([{"text": "", "input_tokens": 1, "output_tokens": 1},
                           {"text": "print(0)", "input_tokens": 1, "output_tokens": 1},
                           {"text": "print(1)", "input_tokens": 1, "output_tokens": 1}])
    judge = MockJudge({"print(0)": ["PASS", "WRONG_ANSWER", "WRONG_ANSWER"],
                       "print(1)": ["PASS", "WRONG_ANSWER", "WRONG_ANSWER"]})
    store = initialize(tmp_path, job)
    state = run_trial(store, task, job, config, backend, judge, "e")
    assert store.snapshots(job["id"])[0]["code_hash"] is None
    assert state.best_id == "arm-2"


def test_token_coverage_extension_preserves_earlier_prefix(tmp_path, task, job, config):
    normal = initialize(tmp_path / "normal", job)
    run_trial(normal, task, job, config, fixture_backend(), fixture_judge(), "e")
    prefixes = normal.snapshots(job["id"])
    extended = initialize(tmp_path / "extended", job)
    config.budgets.token_checkpoints = [400]
    config.budgets.coverage_extension_call_ceiling = 8
    result = run_trial(extended, task, job, config, fixture_backend(), fixture_judge(), "e")
    assert extended.snapshots(job["id"])[:4] == prefixes
    assert result.ledger.inference_attempts == 7 and result.ledger.tokens == 420
    assert result.stop_reason == "checkpoints_covered"


def test_ceiling_explicitly_incomplete(tmp_path, task, job, config):
    store = initialize(tmp_path, job)
    config.budgets.token_checkpoints = [1000]
    result = run_trial(store, task, job, config, fixture_backend(), fixture_judge(), "e")
    assert result.stop_reason == "extension_ceiling"
    assert store.rows("SELECT status FROM trial_states")[0]["status"] == "incomplete"
