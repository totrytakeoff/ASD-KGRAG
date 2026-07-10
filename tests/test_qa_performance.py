from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "qa"))

import kgrag_answer  # noqa: E402
import qa_settings  # noqa: E402
from evaluate_qa import evaluate_result  # noqa: E402
from latency_benchmark import agent_gate  # noqa: E402
from qa_profiles import apply_qa_profile  # noqa: E402


class QaProfileTests(unittest.TestCase):
    def test_balanced_profile_and_explicit_override(self):
        ns = SimpleNamespace()
        apply_qa_profile(ns, "balanced", context_k=5)
        self.assertEqual(ns.qa_profile, "balanced")
        self.assertEqual(ns.context_k, 5)
        self.assertEqual(ns.graph_evidence_k, 2)
        self.assertEqual(ns.max_chars_per_chunk, 600)
        self.assertEqual(ns.llm_max_tokens, 800)

    def test_qwen3_disables_thinking_for_interactive_qa(self):
        self.assertEqual(
            kgrag_answer.model_request_options("Qwen/Qwen3.5-9B"),
            {"enable_thinking": False},
        )
        self.assertEqual(kgrag_answer.model_request_options("zai-org/GLM-4.5-Air"), {})


class RetrievalCacheTests(unittest.TestCase):
    def setUp(self):
        with kgrag_answer._RETRIEVAL_CACHE_LOCK:
            kgrag_answer._RETRIEVAL_CACHE.clear()

    def test_retrieval_cache_returns_deep_copy(self):
        args = SimpleNamespace(
            query="ADOS 是什么",
            keywords=[],
            collection="chunks",
            retrieval_k=20,
            context_k=4,
            relation_k=30,
            relation_evidence_k=6,
            graph_evidence_k=2,
            graph_evidence_pool_k=30,
        )
        context = {"contexts": [{"chunk_id": "c1"}], "relations": []}
        with patch.object(kgrag_answer, "retrieve_context", return_value=context) as retrieve:
            first, first_hit = kgrag_answer.retrieve_context_cached(args)
            first["contexts"][0]["chunk_id"] = "changed"
            second, second_hit = kgrag_answer.retrieve_context_cached(args)

        self.assertFalse(first_hit)
        self.assertTrue(second_hit)
        self.assertEqual(second["contexts"][0]["chunk_id"], "c1")
        retrieve.assert_called_once()

    def test_retrieval_cache_can_be_disabled_for_benchmarks(self):
        args = SimpleNamespace(disable_retrieval_cache=True)
        context = {"contexts": [], "relations": []}
        with patch.object(kgrag_answer, "retrieve_context", return_value=context) as retrieve:
            first, first_hit = kgrag_answer.retrieve_context_cached(args)
            second, second_hit = kgrag_answer.retrieve_context_cached(args)

        self.assertEqual(first, context)
        self.assertEqual(second, context)
        self.assertFalse(first_hit)
        self.assertFalse(second_hit)
        self.assertEqual(retrieve.call_count, 2)


class EvidenceFallbackTests(unittest.TestCase):
    def test_fallback_contains_citations_and_graph_relations(self):
        text = kgrag_answer.build_evidence_fallback(
            {
                "contexts": [
                    {
                        "citation_id": "C1",
                        "title": "Assessment of Autism Spectrum Disorder",
                        "year": 2023,
                        "evidence_level": "B",
                    }
                ],
                "relations": [
                    {
                        "graph_id": "G1",
                        "source": "孤独症",
                        "relation": "MEASURED_BY",
                        "target": "ADOS-2",
                        "support_count": 3,
                        "confidence": 0.93,
                    }
                ],
            }
        )
        self.assertIn("[C1]", text)
        self.assertIn("[G1]", text)
        self.assertIn("不能视为完整医学结论", text)


class SettingsSecretTests(unittest.TestCase):
    def test_masked_eval_key_is_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "qa_settings.json"
            original_path = qa_settings.SETTINGS_PATH
            qa_settings.SETTINGS_PATH = settings_path
            try:
                qa_settings.add_eval_model(
                    {"name": "model", "base_url": "https://example.test/v1", "api_key": "secret-key-value"}
                )
                public = qa_settings.get_public_eval_models()
                index = len(public) - 1
                qa_settings.update_eval_model(index, {"api_key": public[index]["api_key"], "enabled": False})
                stored = qa_settings.get_eval_models()[index]
            finally:
                qa_settings.SETTINGS_PATH = original_path

        self.assertEqual(stored["api_key"], "secret-key-value")
        self.assertFalse(stored["enabled"])


class AgentGateTests(unittest.TestCase):
    def test_agent_gate_accepts_quality_parity_within_latency_budget(self):
        summary = [
            {
                "model": "model",
                "profile": "balanced",
                "pipeline": "standard",
                "successes": 5,
                "quality_passes": 4,
                "total_p50": 10.0,
            },
            {
                "model": "model",
                "profile": "balanced",
                "pipeline": "agent",
                "successes": 5,
                "quality_passes": 4,
                "total_p50": 11.5,
            },
        ]

        gates = agent_gate(summary)

        self.assertEqual(len(gates), 1)
        self.assertTrue(gates[0]["passed"])
        self.assertEqual(gates[0]["latency_overhead_rate"], 0.15)


class EvaluationTests(unittest.TestCase):
    def test_non_dry_run_empty_answer_fails_quality(self):
        evaluated = evaluate_result(
            {"id": "q1", "query": "question", "requires_guardrail": False},
            {
                "dry_run": False,
                "answer": "",
                "context": {"contexts": [{"citation_id": "C1"}], "relations": []},
            },
            1.0,
        )

        self.assertFalse(evaluated["ok"])
        self.assertFalse(evaluated["checks"]["answer_present"])
        self.assertFalse(evaluated["checks"]["answer_cited"])


if __name__ == "__main__":
    unittest.main()
