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
from evaluate_compare import qa_namespace  # noqa: E402
from kgrag_api import BenchmarkRequest  # noqa: E402
from latency_benchmark import agent_gate  # noqa: E402
from qa_profiles import apply_qa_profile  # noqa: E402
from retrieval_diagnostics import summarize as summarize_diagnostics  # noqa: E402


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

    def test_natural_query_rewrite_extracts_domain_hints(self):
        cases = {
            "如果量表正常，是否就不需要专业评估了？": {"评估", "专业评估"},
            "两三岁孩子社交反应少，家长想先做个筛查": {"筛查", "M-CHAT"},
            "孩子语言少、不太看人，是不是就能判断为自闭症？": {"ASD", "诊断"},
            "家庭训练和学校融合支持能否套用同一套孤独症干预方案？": {"家庭", "学校", "干预"},
            "孤独症孩子睡不好还特别好动": {"睡眠", "注意力", "ADHD"},
            "饮食干预是否可以治愈 ASD？": {"饮食干预", "治愈"},
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertTrue(expected.issubset(set(kgrag_answer.auto_keywords(query))))

    def test_natural_query_rewrite_drops_conversational_fragments(self):
        keywords = kgrag_answer.auto_keywords("回答 ASD 知识问题时为什么需要说明文献证据来源？")

        self.assertNotIn("回答", keywords)
        self.assertIn("证据", keywords)

    def test_natural_query_rewrite_prefers_specific_intervention(self):
        keywords = kgrag_answer.auto_keywords("饮食干预是否可以治愈 ASD？")

        self.assertIn("饮食干预", keywords)
        self.assertNotIn("干预", keywords)


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

    def test_full_evaluation_allows_fifty_questions(self):
        request = BenchmarkRequest(question_limit=50)

        self.assertEqual(request.question_limit, 50)


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

    def test_expected_term_can_be_found_in_retrieved_chunk_text(self):
        evaluated = evaluate_result(
            {"id": "q1", "query": "question", "expect_graph_terms": ["ADI-R"]},
            {
                "dry_run": True,
                "context": {
                    "contexts": [{"citation_id": "C1", "text": "ADI-R 用于结构化访谈。"}],
                    "relations": [],
                },
            },
            1.0,
        )

        self.assertTrue(evaluated["checks"]["expected_term_seen"])

    def test_expected_term_uses_aliases_and_evidence_metadata(self):
        alias_evaluated = evaluate_result(
            {"id": "q1", "query": "question", "expect_graph_terms": ["高压氧"]},
            {
                "dry_run": True,
                "context": {
                    "contexts": [{"citation_id": "C1", "text": "Hyperbaric oxygen therapy trial."}],
                    "relations": [],
                },
            },
            1.0,
        )
        evidence_evaluated = evaluate_result(
            {"id": "q2", "query": "question", "expect_graph_terms": ["证据"]},
            {
                "dry_run": True,
                "context": {
                    "contexts": [{"citation_id": "C1", "evidence_level": "B"}],
                    "relations": [],
                },
            },
            1.0,
        )

        self.assertTrue(alias_evaluated["checks"]["expected_term_seen"])
        self.assertTrue(evidence_evaluated["checks"]["expected_term_seen"])

    def test_compare_can_ignore_curated_question_keywords(self):
        args = SimpleNamespace(
            ignore_question_keywords=True,
            context_k=4,
            graph_evidence_k=2,
            retrieval_k=20,
            relation_k=30,
            relation_evidence_k=6,
            graph_evidence_pool_k=30,
            max_chars_per_chunk=600,
        )

        namespace = qa_namespace(
            {"query": "ADOS 是什么", "keywords": ["ADOS", "ASD"]},
            args,
        )

        self.assertEqual(namespace.keywords, [])

    def test_diagnostic_summary_collects_failures_and_governance_candidates(self):
        rows = [
            {
                "id": "q1",
                "category": "assessment",
                "failures": ["expected_term_seen"],
                "final_contexts": [{"retrieval": "vector"}],
                "matched_entities": [
                    {
                        "entity_id": "e1",
                        "name": "ADOS",
                        "source_chunk_count": 1,
                        "quality_flags": ["low_support"],
                        "is_isolated": False,
                    }
                ],
            }
        ]

        summary = summarize_diagnostics(rows)

        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["check_failures"]["expected_term_seen"], 1)
        self.assertEqual(summary["retrieval_modes"]["vector"], 1)
        self.assertEqual(summary["governance_candidates"][0]["entity_id"], "e1")


if __name__ == "__main__":
    unittest.main()
