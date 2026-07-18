"""Multi-generation scoring: nondeterministic routes re-run, deterministic don't."""

from harness.agent.baseline import AgentAnswer
from harness.synth.questions import Question
from harness.evalkit.runner import run_eval


def _q(qid="q1"):
    return Question(qid=qid, family="revenue", stratum="single_table",
                    text="What was X?", answer_type="scalar", expected=100.0)


class FlipAgent:
    """LLM-routed agent that alternates right/wrong answers."""

    def __init__(self):
        self.calls = 0

    def answer(self, text, qid=""):
        self.calls += 1
        value = 100.0 if self.calls % 2 == 1 else 999.0
        return AgentAnswer("scalar", value, "nl2sql")


class SteadyVQRAgent:
    def __init__(self):
        self.calls = 0

    def answer(self, text, qid=""):
        self.calls += 1
        return AgentAnswer("scalar", 100.0, "vqr:vq-test")


def test_nondeterministic_route_averages_over_generations():
    agent = FlipAgent()
    report = run_eval(agent, [_q()], "vtest", "unit", generations=4)
    assert agent.calls == 4
    assert report["per_question"][0]["score"] == 0.5
    assert report["accuracy"] == 0.5


def test_deterministic_route_runs_once():
    agent = SteadyVQRAgent()
    report = run_eval(agent, [_q()], "vtest", "unit", generations=4)
    assert agent.calls == 1
    assert report["per_question"][0]["generations"] == 1
    assert report["accuracy"] == 1.0
