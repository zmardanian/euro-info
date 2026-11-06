import support  # noqa: F401  (must come first: isolates user folders)
import time
import unittest

from euroinfo.core import feeds as backend

from euroinfo.core.reasoning import analysis_instructions, build_analysis_articles, build_investigation_map
from euroinfo.core.workspace import analysis_options, build_evidence_text


class NewsReasoningTests(unittest.TestCase):
    def article(self, title, source, timestamp, **extra):
        return {'title': title, 'source': source, 'timestamp': timestamp,
                'time': f'{timestamp}', 'summary': extra.pop('summary', ''), **extra}

    def test_map_provides_ordered_leads_and_uncertainty(self):
        now = time.time()
        articles = [
            self.article('Poland blocks Ukraine aid package after budget vote', 'Outlet One', now),
            self.article('Poland approves Ukraine aid package after new budget vote', 'Outlet Two', now + 60),
        ]
        result = build_investigation_map(articles)
        self.assertIn('[1][2] shared headline terms:', result)
        self.assertIn('not causal proof', result)
        self.assertIn('oldest-to-newest', result)
        self.assertIn('never a proxy for event time', result)
        self.assertIn('Missing sources', result)

    def test_map_does_not_invent_connections_for_unrelated_headlines(self):
        now = time.time()
        articles = [self.article('Romania launches new flood warning system', 'A', now),
                    self.article('Japan central bank keeps interest rates unchanged', 'B', now)]
        result = build_investigation_map(articles)
        self.assertIn('No strong shared headline anchors', result)
        self.assertNotIn('Possible story links', result)

    def test_map_is_character_bounded_and_handles_invalid_timestamps(self):
        article = self.article('News', 'Outlet', 10**100)
        self.assertLessEqual(len(build_investigation_map([article], max_chars=180)), 180)

    def test_investigative_prompt_weighs_evidence_and_alternatives(self):
        prompt = analysis_instructions(focus_article={'title': 'Parliament votes on aid'}, profile='deep')
        self.assertIn('best alternative', prompt)
        self.assertIn('exactly two', prompt)
        self.assertIn('private chain-of-thought', prompt)
        self.assertIn('only when it is explicit', prompt)
        self.assertIn('do not guess or fill gaps from memory', prompt)
        self.assertIn('Never infer an event date from a publication date', prompt)
        self.assertIn('reverse the oldest-to-newest publication order', prompt)
        self.assertIn('label one-source details as such', prompt)
        self.assertIn('required language', prompt)


    def test_related_search_uses_excerpt_when_headlines_use_different_words(self):
        now = time.time()
        target = self.article('Can Europe get tough on China?', 'POLITICO Europe', now,
                              summary='Commissioner Maros Sefcovic visits Beijing; France and Germany favor tougher trade measures.')
        related = self.article('Trade envoy lands in Beijing for talks', 'RFI Europe', now+60,
                               summary='Maroš Sefcovic meets China officials on trade deficit and exports.')
        result = backend.related_articles(target, [target, related], limit=4)
        self.assertEqual(result, [target, related])

    def test_analysis_adds_distinct_strategic_context_and_avoids_wire_double_count(self):
        now = time.time()
        target = self.article('Can Europe get tough on China?', 'POLITICO Europe', now,
                              summary='Maroš Sefcovic visits Beijing. France and Germany seek tougher trade measures amid industrial dependency.')
        same_event = self.article('EU trade envoy meets China in Beijing', 'RFI Europe', now+60,
                                  summary='Sefcovic discusses trade deficit, export controls and rare earths.')
        context = self.article('US and Russia discuss Nord Stream investors', 'News Desk A', now+120,
                               summary='Reuters: US special envoy Jared Kushner, Donald Trump’s son-in-law, spoke with Putin aide about US investors in German gas pipelines during the Ukraine war; sanctions and military security remain obstacles.')
        copied_context = self.article('Trump son-in-law in Nord Stream investment talks', 'News Desk B', now+180,
                                      summary='Reuters reports Kushner discussed a US investment in Germany gas pipelines with Russia during the Ukraine war.')
        unrelated = self.article('Floods disrupt regional transport', 'Local News', now+240,
                                 summary='Severe weather closes roads and railways.')
        chosen = build_analysis_articles(target, [target, same_event, context, copied_context, unrelated], 'balanced')
        self.assertIn(same_event, chosen)
        contexts = [item for item in chosen if item.get('_analysis_role')]
        self.assertEqual(len(contexts), 1)
        self.assertIn('Nord Stream', contexts[0]['title'])
        self.assertIn('Germany', contexts[0]['_context_entities'])
        self.assertIn('not corroboration', contexts[0]['_analysis_role'])
        evidence = build_evidence_text(chosen, analysis_options(profile='balanced'))
        self.assertIn('Analysis role: Wider context', evidence)
        self.assertIn('Jared Kushner', evidence)
        map_text = build_investigation_map(chosen, limit=len(chosen), max_chars=1500)
        self.assertIn('wider-context lead', map_text)
        self.assertIn('Jared Kushner', map_text)
        self.assertIn('Donald Trump', map_text)
        self.assertIn('public-duty/commercial-interest lead', map_text)
        self.assertIn('material apparent conflict-of-interest risk', map_text)
        self.assertIn('personal ownership, profit or corruption is not established', map_text)
        self.assertIn('son-in-law of Donald Trump', map_text)
        self.assertIn('Separate event', map_text)

    def test_prompt_demands_interests_and_evidence_to_inference_links(self):
        prompt = analysis_instructions(focus_article={'title': 'EU trade policy'})
        for phrase in ('who benefits or bears costs', 'financial stakes', 'Separate direct evidence from a structural inference',
                       'proven misconduct', 'strongest counterpoint', 'Discuss EACH item labeled Wider context',
                       'public-duty/commercial-interest review lead', 'If the reports do not connect their events, say so plainly',
                       'Do not manufacture a connection', 'Do not claim personal ownership, profit, influence or corruption without evidence',
                       'do not portray actors as aligned', 'Never transfer suspicion', 'unless the sources explicitly support that bridge',
                       'separate confidence for reported facts', 'Do not fill sections with generic lists of missing details'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prompt)

    def test_prompts_stay_compact_for_a_small_local_model(self):
        self.assertLess(len(analysis_instructions(focus_article={'title': 'EU trade policy'})), 3600)

    def test_technology_prompt_uses_stage_and_validation(self):
        prompt = analysis_instructions(focus_article={'title': 'Linux kernel release fixes security flaw'}, profile='balanced')
        self.assertIn('Linux', prompt)
        self.assertIn('independent validation', prompt)

    def test_evidence_context_respects_profile_budget(self):
        articles = [self.article(f'AI study {i}', f'Outlet {i}', time.time()-i,
                                 summary='A relevant excerpt about preliminary results. '*100)
                    for i in range(12)]
        for profile in ('efficient', 'balanced', 'deep'):
            options = analysis_options(profile=profile)
            text = build_evidence_text(articles, options)
            budget = max(1800, int((options['num_ctx'] - options['num_predict'] - 1300) * 2.8))
            self.assertLessEqual(len(text), budget)
            self.assertIn('EVIDENCE MAP', text)
            self.assertIn('Family: Outlet 0', text)
            max_sources = {'efficient': 6, 'balanced': 8, 'deep': 12}[profile]
            self.assertNotIn(f'[{max_sources+1}]', text)


if __name__ == '__main__':
    unittest.main()
