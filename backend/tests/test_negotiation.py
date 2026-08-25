import pytest

from app.environments.negotiation import NegotiationEnvironment

AGENTS = ["agent_a", "agent_b"]


def make_env(**kwargs) -> NegotiationEnvironment:
    return NegotiationEnvironment(seed=42, **kwargs)


def test_reset_requires_two_agents():
    env = make_env()
    with pytest.raises(ValueError):
        env.reset(["only_one"])


def test_reset_rejects_duplicate_agent_ids():
    with pytest.raises(ValueError, match="unique"):
        make_env().reset(["same", "same"])


def test_reset_builds_private_valuations_for_each_agent():
    env = make_env()
    state = env.reset(AGENTS)
    assert set(state["valuations"]) == set(AGENTS)
    for agent_id in AGENTS:
        assert set(state["valuations"][agent_id]) == set(state["items"])
        maximum = sum(
            state["valuations"][agent_id][item] * quantity
            for item, quantity in state["items"].items()
        )
        assert maximum == pytest.approx(100)


def test_observe_excludes_other_agents_valuation():
    env = make_env()
    state = env.reset(AGENTS)
    obs = env.observe(state, "agent_a")
    assert obs["valuation"] == state["valuations"]["agent_a"]
    assert "agent_b" not in str(obs.get("valuation"))
    assert "valuations" not in obs


def test_public_view_never_leaks_valuations():
    env = make_env()
    state = env.reset(AGENTS)
    view = env.public_view(state)
    assert "valuations" not in view
    assert "valuation" not in view


def test_offer_sets_standing_offer_and_history():
    env = make_env()
    state = env.reset(AGENTS)
    result = env.step(state, "agent_a", {"type": "offer", "split": {"books": 2, "hats": 0, "balls": 0}})
    assert result.state["standing_offer"] == {
        "agent_id": "agent_a",
        "split": {"books": 2, "hats": 0, "balls": 0},
    }
    assert len(result.state["history"]) == 1
    # step must not mutate the input state (orchestrator retries rely on this)
    assert state["standing_offer"] is None


def test_offer_out_of_range_is_illegal():
    env = make_env()
    state = env.reset(AGENTS)
    with pytest.raises(ValueError):
        env.step(state, "agent_a", {"type": "offer", "split": {"books": 99}})


def test_accept_without_standing_offer_is_illegal():
    env = make_env()
    state = env.reset(AGENTS)
    with pytest.raises(ValueError):
        env.step(state, "agent_a", {"type": "accept"})


def test_accept_own_offer_is_illegal():
    env = make_env()
    state = env.reset(AGENTS)
    offered = env.step(state, "agent_a", {"type": "offer", "split": {"books": 1}}).state
    with pytest.raises(ValueError):
        env.step(offered, "agent_a", {"type": "accept"})


def test_accept_computes_allocations_and_scores():
    env = make_env()
    state = env.reset(AGENTS)
    split = {"books": 3, "hats": 0, "balls": 0}
    offered = env.step(state, "agent_a", {"type": "offer", "split": split}).state
    accepted = env.step(offered, "agent_b", {"type": "accept"}).state

    assert accepted["status"] == "agreement"
    assert accepted["allocations"]["agent_a"] == split
    assert accepted["allocations"]["agent_b"] == {"books": 0, "hats": 2, "balls": 1}
    assert env.is_terminal(accepted)

    scores = env.score(accepted)
    valuations = accepted["valuations"]
    expected_a = sum(valuations["agent_a"][item] * qty for item, qty in split.items())
    assert scores["agent_a"] == expected_a
    assert set(scores) == set(AGENTS)


def test_partial_offer_is_normalized_and_scores_without_error():
    env = make_env()
    state = env.reset(AGENTS)
    offered = env.step(
        state, "agent_a", {"type": "offer", "split": {"books": 1}}
    ).state

    assert offered["standing_offer"]["split"] == {"books": 1, "hats": 0, "balls": 0}

    accepted = env.step(offered, "agent_b", {"type": "accept"}).state
    scores = env.score(accepted)

    assert accepted["allocations"]["agent_a"] == {"books": 1, "hats": 0, "balls": 0}
    assert set(scores) == set(AGENTS)


def test_walk_ends_match_with_zero_scores():
    env = make_env()
    state = env.reset(AGENTS)
    walked = env.step(state, "agent_a", {"type": "walk"}).state
    assert walked["status"] == "walked"
    assert env.is_terminal(walked)
    assert env.score(walked) == {"agent_a": 0.0, "agent_b": 0.0}


def test_round_limit_is_terminal_without_agreement():
    env = make_env(max_turns=2)
    state = env.reset(AGENTS)
    state = env.step(state, "agent_a", {"type": "offer", "split": {"books": 1}}).state
    state = env.step(state, "agent_b", {"type": "offer", "split": {"books": 1}}).state
    assert env.is_terminal(state)
    assert state["status"] == "open"
    assert env.score(state) == {"agent_a": 0.0, "agent_b": 0.0}
