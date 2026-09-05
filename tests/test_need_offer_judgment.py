"""Tests for bounded NGO-side Need/resource interpretation."""

from agent.reasoning.need_offer_judgment import judge_need_offer


FACTS = {
    "available_quantity": 5000,
    "requested_quantity": None,
    "requested_quantity_specified": False,
    "unit_match": True,
    "unit_mismatch": False,
    "type_match": True,
    "sufficiency": "unknown",
}


def test_hallucinated_number_is_discarded():
    result = judge_need_offer(
        FACTS,
        title="Food needed at Camp B",
        llm=lambda prompt: {"note": "The need likely requires 9000 kg.", "confidence": "likely_sufficient"},
    )
    assert result["facts"] == FACTS
    assert result["interpretation"]["available"] is False
    assert "ungrounded number" in result["interpretation"]["validation_warning"]
    assert "9000" not in str(result)


def test_llm_unavailable_preserves_layer_one_facts():
    def unavailable(prompt):
        raise RuntimeError("Ollama unavailable")

    result = judge_need_offer(FACTS, llm=unavailable)
    assert result["facts"] == FACTS
    assert result["interpretation"]["confidence"] == "unclear"
    assert result["interpretation"]["available"] is False


def test_output_separates_facts_and_interpretation():
    result = judge_need_offer(
        FACTS,
        llm=lambda prompt: {"note": "Generic food appears relevant, but dietary details are unclear.", "confidence": "unclear"},
    )
    assert result["facts"] == FACTS
    assert result["interpretation"]["confidence"] == "unclear"
    assert "note" in result["interpretation"]
    assert "available_quantity" not in result["interpretation"]
