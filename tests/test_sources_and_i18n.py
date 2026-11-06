import support  # noqa: F401  (must come first: isolates user folders)
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from euroinfo.core import feeds as backend
from euroinfo.core import i18n


class SourceCatalogueTests(unittest.TestCase):
    def test_catalogue_covers_europe_us_and_global_technology(self):
        regions = {region: 0 for region in ("EUROPE", "US", "GLOBAL")}
        countries = set()
        for source in backend.NEWS_SOURCES:
            regions[source["region"]] += 1
            countries.add(source["country"])
            self.assertTrue(source["url"].startswith("https://"))
            self.assertIn(source["topic"], ("", "POLITICS", "ECONOMY", "TECHNOLOGY"))
        self.assertEqual(len({source["name"] for source in backend.NEWS_SOURCES}), len(backend.NEWS_SOURCES))
        self.assertGreaterEqual(regions["EUROPE"], 40)
        self.assertGreaterEqual(regions["US"], 10)
        self.assertGreaterEqual(len(countries & set(backend.COUNTRY_TERMS)), 20)  # many European countries
        self.assertTrue({"EU", "US"} <= countries)

    def test_default_selection_is_english_plus_the_readers_language(self):
        from euroinfo.core import sources
        english = sources.default_selection("en")
        romanian = sources.default_selection("ro")
        self.assertIn("POLITICO Europe", english)
        self.assertNotIn("Digi24", english)
        self.assertIn("Digi24", romanian)
        self.assertNotIn("Tagesschau", romanian)

    def test_normalized_rss_article_carries_region_language_and_excerpt(self):
        entry = {
            "title": "<b>European</b> report",
            "link": "/story",
            "summary": "<p>Short <b>summary</b>.</p>",
        }
        source = {"name": "Digi24", "region": "ROMANIA", "language": "ro"}
        article = backend._normalize_entry(entry, source, "https://example.org/feed")
        self.assertEqual(article["title"], "European report")
        self.assertEqual(article["summary"], "Short summary.")
        self.assertEqual(article["source_region"], "ROMANIA")
        self.assertEqual(article["source_language"], "ro")

    def test_location_priority_reorders_without_dropping_or_mutating_stories(self):
        stories = [
            {"title": "Global markets report", "source": "BBC World"},
            {"title": "Berlin transport update", "source": "BBC World"},
            {"title": "International report", "source": "Digi24"},
        ]
        ordered = backend.prioritize_articles(stories, "DE")
        self.assertEqual(ordered[0], stories[1])
        self.assertEqual(len(ordered), len(stories))
        self.assertEqual({id(item) for item in ordered}, {id(item) for item in stories})
        self.assertEqual(ordered[1:], [stories[0], stories[2]])

    def test_location_ranking_is_stable_for_unknown_or_europe_focus(self):
        stories = [{"title": "A"}, {"title": "B"}]
        self.assertEqual(backend.prioritize_articles(stories, "EU"), stories)
        self.assertEqual(backend.prioritize_articles(stories, "XX"), stories)

    def test_country_focus_covers_eu_and_nearby_european_countries(self):
        self.assertTrue(set("AT BE BG HR CY CZ DK DE EE FI FR GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split()).issubset(backend.COUNTRY_TERMS))
        stories = [{"title": "Global news"}, {"title": "Amsterdam housing report"}]
        self.assertEqual(backend.prioritize_articles(stories, "NL")[0], stories[1])


class ExchangeRateTests(unittest.TestCase):
    def test_fetches_only_selected_ecb_reference_rates(self):
        response = Mock()
        response.json.return_value = [
            {"date": "2026-10-05", "base": "EUR", "quote": "USD", "rate": 1.12},
            {"date": "2026-10-05", "base": "EUR", "quote": "RON", "rate": 5.33},
            {"date": "2026-10-05", "base": "EUR", "quote": "XYZ", "rate": 12.0},
        ]
        session = Mock()
        session.get.return_value = response

        with patch.object(backend, "session", return_value=session):
            result = backend.get_exchange_rates()

        self.assertEqual(result["date"], "2026-10-05")
        self.assertEqual(result["rates"], {"USD": 1.12, "RON": 5.33})
        session.get.assert_called_once_with(
            backend.EXCHANGE_RATES_URL,
            params={"base": "EUR", "quotes": ",".join(backend.EXCHANGE_RATE_CURRENCIES)},
            timeout=backend.FEED_TIMEOUT,
        )

    def test_exchange_rate_failure_is_nonfatal(self):
        session = Mock()
        session.get.side_effect = backend.requests.RequestException("offline")
        with patch.object(backend, "session", return_value=session):
            result = backend.get_exchange_rates()

        self.assertEqual(result["rates"], {})
        self.assertIn("offline", result["error"])


class InterfaceTranslationTests(unittest.TestCase):
    def test_ai_output_language_instruction_covers_every_ui_language(self):
        self.assertEqual(set(i18n.AI_OUTPUT_LANGUAGES), set(i18n.LANGUAGES))
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                instruction = i18n.ai_output_language_instruction(language)
                self.assertIn(i18n.AI_OUTPUT_LANGUAGES[language], instruction)
                self.assertIn("Write every section", instruction)
                self.assertIn("Do not switch or mix languages", instruction)

    def test_interface_catalogue_covers_requested_languages(self):
        for language in ("fr", "de", "it", "ro", "pl", "es"):
            self.assertNotEqual(i18n.tr("Latest news", language), "Latest news")

    def test_context_provenance_label_is_translated(self):
        label = "Wider context — separate report; not corroboration"
        for language in ("fr", "de", "it", "ro", "pl", "es"):
            with self.subTest(language=language):
                self.assertNotEqual(i18n.tr(label, language), label)

    def test_new_dashboard_labels_are_translated(self):
        labels = (
            "Weather",
            "Lead story · European briefing",
            "Daily ECB reference rates, not live trading quotes",
            "Daily ECB reference rate; not a live trading quote",
            "ECB reference-rate date",
            "Rates unavailable",
            "Updating weather, rates and news…",
            "Reader tools",
            "Daily reader brief",
            "Copy headlines",
            "Reset filters",
            "Local stories first · all headlines stay available",
        )
        for language in ("fr", "de", "it", "ro", "pl", "es"):
            for label in labels:
                with self.subTest(language=language, label=label):
                    self.assertNotEqual(i18n.tr(label, language), label)

    def test_translation_result_is_cached(self):
        from euroinfo.core import translation
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "translations.json"
            with patch.object(translation, "cache_file", return_value=cache_path), \
                    patch.object(translation, "_cache", None):
                response = Mock()
                response.json.return_value = [[["Bonjour le monde", "Hello world"]]]
                with patch.object(translation.requests, "get", return_value=response) as get:
                    self.assertEqual(translation.google_translate("Hello world", "fr"), "Bonjour le monde")
                    self.assertEqual(translation.google_translate("Hello world", "fr"), "Bonjour le monde")
                    get.assert_called_once()
                translation.save_cache()
                self.assertTrue(cache_path.exists())


if __name__ == "__main__":
    unittest.main()

class NewsQualityTranslations(unittest.TestCase):
    def test_news_quality_labels_cover_all_interface_languages(self):
        for language in ('fr','de','it','ro','pl','es'):
            for label in ('Technology','All technology','Biotech','Breakthroughs','Coverage & sources','Why featured','Reporting independence is not verified.','Country mentions','Shared agency attribution','Publisher page extract'):
                with self.subTest(language=language,label=label):
                    self.assertNotEqual(i18n.tr(label,language),label)
