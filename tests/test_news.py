from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.ledger import Ledger
from agent.news import NewsEntityResolver, NewsScorer, _dedupe_items, _extract_article_text
from models import NewsItem


class NewsScorerTest(unittest.TestCase):
    def test_short_ticker_does_not_match_ordinary_words(self) -> None:
        item = NewsItem(
            title="Stocks rise after Fed comments",
            summary="Investors look for earnings strength across the market.",
        )

        context = NewsScorer().context_for_symbol("F", [item])

        self.assertEqual(context.items, ())
        self.assertEqual(context.sentiment_score, 0.0)

    def test_short_ticker_matches_explicit_cashtag(self) -> None:
        item = NewsItem(title="$F rallies after stronger vehicle demand")

        context = NewsScorer().context_for_symbol("F", [item])

        self.assertEqual(len(context.items), 1)
        self.assertGreater(context.sentiment_score, 0.0)

    def test_three_letter_ticker_does_not_match_lowercase_word(self) -> None:
        item = NewsItem(title="Company has stronger demand", summary="Management met analysts.")

        self.assertEqual(NewsScorer().context_for_symbol("HAS", [item]).items, ())
        self.assertEqual(NewsScorer().context_for_symbol("MET", [item]).items, ())

    def test_article_text_extractor_keeps_paragraph_text(self) -> None:
        html = """
        <html><body><article>
          <script>ignore()</script>
          <p>Company beats revenue expectations.</p>
          <p>Guidance was raised for next quarter.</p>
        </article></body></html>
        """

        text = _extract_article_text(html)

        self.assertIn("beats revenue", text)
        self.assertIn("Guidance was raised", text)

    def test_high_reliability_source_outweighs_social_chatter(self) -> None:
        items = [
            NewsItem(
                title="$AAPL strong demand chatter",
                summary="Social posts say demand is strong and guidance may rise.",
                source="twitter",
            ),
            NewsItem(
                title="AAPL warning after regulator probe",
                summary="Reuters reports a regulator probe and risk to demand.",
                source="reuters.com",
            ),
        ]

        context = NewsScorer().context_for_symbol("AAPL", items)

        self.assertLess(context.sentiment_score, 0.0)
        self.assertGreater(context.catalyst_score, 0.0)

    def test_duplicate_headlines_are_counted_once(self) -> None:
        duplicate = NewsItem(
            title="$MSFT raises guidance after strong cloud demand",
            summary="Microsoft raises guidance after strong demand.",
            source="example",
        )

        deduped = _dedupe_items([duplicate, duplicate])

        self.assertEqual(len(deduped), 1)

    def test_entity_resolver_maps_products_executives_and_suppliers(self) -> None:
        items = [
            NewsItem(
                title="Tim Cook says iPhone demand is strong",
                summary="Apple supplier Foxconn raises guidance after strong orders.",
                source="reuters.com",
            ),
            NewsItem(
                title="TSMC supplier issue may delay advanced packaging",
                summary="Taiwan Semiconductor reports a delay and risk for major customers.",
                source="reuters.com",
            ),
        ]

        aapl_context = NewsScorer().context_for_symbol("AAPL", items)
        tsm_context = NewsScorer().context_for_symbol("TSM", items)

        self.assertEqual(len(aapl_context.items), 2)
        self.assertGreater(aapl_context.catalyst_score, 0.0)
        self.assertGreaterEqual(len(tsm_context.items), 1)
        self.assertLessEqual(tsm_context.sentiment_score, 0.0)

    def test_custom_entity_map_can_add_company_aliases(self) -> None:
        resolver = NewsEntityResolver(
            {
                "SHOP": {
                    "company_names": ["Shopify"],
                    "products": ["Shop Pay"],
                    "executives": ["Tobi Lutke"],
                }
            }
        )
        item = NewsItem(title="Shop Pay demand expands after Tobi Lutke comments")

        context = NewsScorer(resolver).context_for_symbol("SHOP", [item])

        self.assertEqual(len(context.items), 1)
        self.assertGreater(context.sentiment_score, 0.0)

    def test_source_credibility_learns_from_trade_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Ledger(str(Path(tmpdir) / "agent.sqlite3"), str(Path(tmpdir) / "audit.jsonl"))
            ledger.record_trade_outcome(
                symbol="AAPL",
                pnl_usd=25,
                return_pct=0.025,
                holding_days=2,
                source="unit_test",
                raw={
                    "entry_context": {
                        "features": {
                            "news_sources": "reuters.com",
                            "news_sentiment": 0.8,
                            "news_catalyst": 0.7,
                            "news_avg_item_age_hours": 2.0,
                        }
                    }
                },
            )
            ledger.record_trade_outcome(
                symbol="AAPL",
                pnl_usd=-20,
                return_pct=-0.02,
                holding_days=2,
                source="unit_test",
                raw={
                    "entry_context": {
                        "features": {
                            "news_sources": "noisy-social",
                            "news_sentiment": 0.9,
                            "news_catalyst": 0.7,
                            "news_avg_item_age_hours": 1.0,
                        }
                    }
                },
            )
            profiles = ledger.news_source_credibility_profiles()

            self.assertGreater(profiles["reuters.com"]["reliability_score"], profiles["noisy-social"]["reliability_score"])
            self.assertGreater(profiles["reuters.com"]["credibility_multiplier"], profiles["noisy-social"]["credibility_multiplier"])

    def test_learned_source_credibility_changes_weighted_sentiment(self) -> None:
        items = [
            NewsItem(title="$AAPL strong demand", summary="Strong demand and guidance raise.", source="trusted"),
            NewsItem(title="$AAPL warning", summary="Warning and risk after probe.", source="noisy"),
        ]
        scorer = NewsScorer(
            source_credibility={
                "trusted": {"credibility_multiplier": 1.45, "reliability_score": 0.9},
                "noisy": {"credibility_multiplier": 0.45, "reliability_score": 0.1},
            }
        )

        context = scorer.context_for_symbol("AAPL", items)

        self.assertGreater(context.sentiment_score, 0.0)


if __name__ == "__main__":
    unittest.main()
