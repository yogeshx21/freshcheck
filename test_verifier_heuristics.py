"""Offline tests for quote matching and heuristic hostname categories."""
import json
import unittest
from unittest.mock import patch

from config import parse_json
from extractor import extract_claims
from verifier import classify, clean_search_results, quote_ok, verify_claim


class QuoteMatchingTests(unittest.TestCase):
    def test_normalized_contiguous_phrase_matches(self):
        self.assertTrue(quote_ok("Pluto is a dwarf planet.", "NASA: Pluto is a dwarf planet, with five known moons."))

    def test_phrase_inside_larger_word_does_not_match(self):
        self.assertFalse(quote_ok("record and logbook", "records and logbook may help"))

    def test_short_quote_is_not_accepted(self):
        self.assertFalse(quote_ok("short", "a short quote appears here"))

    def test_non_text_quote_inputs_are_rejected(self):
        self.assertFalse(quote_ok({"quote": "bad"}, "some text"))
        self.assertFalse(quote_ok("some words here", 42))

    def test_search_results_are_schema_checked_and_bounded(self):
        raw = [None, {"url": ["bad"], "content": "ignore"},
               {"url": "file:///tmp/a", "content": "ignore"},
               {"url": "https://example.org/a", "content": "x" * 25000}]
        cleaned = clean_search_results(raw)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(len(cleaned[0]["content"]), 20000)

    def test_search_results_with_embedded_credentials_are_rejected(self):
        self.assertEqual(clean_search_results([
            {"url": "https://user:secret@example.org/page", "content": "source"}
        ]), [])

    def test_search_results_with_bad_port_or_malformed_authority_are_rejected(self):
        self.assertEqual(clean_search_results([
            {"url": "https://example.org:bad/page", "content": "source"},
            {"url": "https://bad host/page", "content": "source"},
        ]), [])

    def test_search_result_count_is_bounded(self):
        raw = [{"url": f"https://example.org/{i}", "content": "source"} for i in range(50)]
        self.assertEqual(len(clean_search_results(raw)), 8)

    def test_non_object_json_is_rejected(self):
        self.assertEqual(parse_json("[1, 2, 3]"), {})

    def test_unmatched_quote_clears_model_reason_and_replacement(self):
        claim = {"claim": "Pluto is the ninth planet", "search_query": "Pluto planet status", "type": "other"}
        result = [{"url": "https://example.com", "content": "Pluto is a dwarf planet."}]
        model = {"verdict": "stale", "correct_value": "Pluto is a dwarf planet",
                 "reason": "The source proves this", "evidence_quote": "This quote is absent",
                 "evidence_source": 1, "conflict": True, "conflict_note": "model disagreement"}
        with patch("verifier.gather_results", return_value=result), \
             patch("verifier.chat", return_value=json.dumps(model)):
            out = verify_claim(claim, claim["claim"])
        self.assertEqual(out["verdict"], "unclear")
        self.assertFalse(out["evidence_quote_matched"])
        self.assertEqual(out["correct_value"], "")
        self.assertFalse(out["conflict"])
        self.assertIn("No model-supplied excerpt matched", out["reason"])

    def test_empty_search_results_get_accurate_reason(self):
        claim = {"claim": "Pluto is the ninth planet", "search_query": "Pluto planet status", "type": "other"}
        model = {"verdict": "stale", "correct_value": "Pluto is a dwarf planet",
                 "reason": "The source proves this", "evidence_quote": "A quote is here"}
        with patch("verifier.gather_results", return_value=[]), \
             patch("verifier.chat", return_value=json.dumps(model)):
            out = verify_claim(claim, claim["claim"])
        self.assertIn("No search-result text was available", out["reason"])
        self.assertEqual(out["verdict"], "unclear")

    def test_extractor_rejects_unbounded_claim_and_query_and_omits_long_exact_text(self):
        response = {"claims": [
            {"claim": "x" * 501, "search_query": "usable query"},
            {"claim": "A concise claim", "search_query": "y" * 301},
            {"claim": "A useful claim", "search_query": "useful search query", "exact_text": "z" * 1001},
        ]}
        with patch("extractor.chat", return_value=json.dumps(response)):
            claims = extract_claims("A useful claim")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["exact_text"], "")

    def test_extractor_discards_malformed_model_fields(self):
        response = {"claims": [
            {"claim": ["not text"], "search_query": "ignore this", "type": "version"},
            {"claim": "A useful claim", "search_query": "  useful search query  ",
             "type": ["unhashable"], "exact_text": {"unexpected": "object"}},
        ]}
        with patch("extractor.chat", return_value=json.dumps(response)):
            claims = extract_claims("A useful claim")
        self.assertEqual(claims, [{
            "claim": "A useful claim", "search_query": "useful search query",
            "type": "other", "exact_text": "",
        }])


class HostCategoryTests(unittest.TestCase):
    def test_known_official_domain_and_subdomain(self):
        self.assertEqual(classify("https://science.nasa.gov/planets/pluto/"), "official")
        self.assertEqual(classify("https://docs.python.org/3/"), "official")

    def test_lookalike_subdomains_are_not_official(self):
        self.assertEqual(classify("https://docs.example.com/"), "blog")
        self.assertEqual(classify("https://example.gov.attacker.com/"), "blog")
        self.assertEqual(classify("https://example.edu.attacker.com/"), "blog")

    def test_malformed_urls_use_neutral_category(self):
        self.assertEqual(classify("https://[broken"), "blog")
        self.assertEqual(classify(123), "blog")

    def test_news_domains_require_a_domain_boundary(self):
        self.assertEqual(classify("https://www.bbc.co.uk/news"), "news")
        self.assertEqual(classify("https://fake-reuters.com/story"), "blog")

    def test_reference_domains_require_a_domain_boundary(self):
        self.assertEqual(classify("https://en.wikipedia.org/wiki/Pluto"), "reference")
        self.assertEqual(classify("https://notwikipedia.org/"), "blog")


if __name__ == "__main__":
    unittest.main()
