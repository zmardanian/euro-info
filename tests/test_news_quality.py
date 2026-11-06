import support  # noqa: F401  (must come first: isolates user folders)
import time
import unittest

from euroinfo.core import feeds as backend
from euroinfo.core.quality import (technology_topics, provenance_report, evidence_label,
                         rank_articles, canonical_link, coverage_audit, freshness, update_label)
from euroinfo.core.workspace import build_evidence_text, analysis_options


class NewsQualityTests(unittest.TestCase):
    def article(self, title='Linux kernel update', source='Example', **kwargs):
        return dict(title=title, source=source, link='https://example.org/'+source,
                    timestamp=time.time()-3600, **kwargs)

    def test_technology_is_independent_of_geographic_origin(self):
        article=self.article('Inteligența artificială schimbă medicina', source_region='ROMANIA')
        self.assertEqual(backend.classify_article(article),'TECHNOLOGY')
        self.assertIn('AI',technology_topics(article))

    def test_linux_specialist_without_linux_in_title_is_included(self):
        article=self.article('Weekly edition', source_topic='TECHNOLOGY',specialty='Linux')
        self.assertIn('Linux',technology_topics(article))

    def test_ai_does_not_match_inside_said(self):
        self.assertEqual(technology_topics(self.article('Minister said elections are coming')),[])

    def test_biotech_and_breakthroughs_have_distinct_topics(self):
        self.assertIn('Biotech',technology_topics(self.article('Gene therapy enters a clinical trial')))
        self.assertIn('Breakthroughs',technology_topics(self.article('Quantum battery breakthrough')))

    def test_specialist_catalogue_includes_linux_and_primary_sources(self):
        sources={item['name']:item for item in backend.NEWS_SOURCES}
        for name in ('Phoronix','LWN','Fedora Magazine','Kernel Releases'):
            self.assertEqual(sources[name]['specialty'],'Linux')
        self.assertEqual(sources['Kernel Releases']['kind'],'Project publication')
        self.assertEqual(sources['LWN']['access'],'May require subscription')

    def test_same_publisher_editions_are_one_family(self):
        articles=[self.article(source='BBC World'),self.article(source='BBC Europe')]
        self.assertEqual(provenance_report(articles)['families'],1)
        self.assertEqual(provenance_report(articles)['independence'],'Not verified')

    def test_shared_agency_mentions_do_not_certify_independence(self):
        articles=[self.article(source=name,summary='Reuters reports that the parliament approved a policy.') for name in ('A','B','C')]
        report=provenance_report(articles)
        self.assertEqual(report['shared_attributions'],{'Reuters':3})
        self.assertEqual(report['independence'],'Not verified')

    def test_identical_excerpts_are_identified_without_matching_short_teasers(self):
        summary='The committee published its full assessment of the proposed infrastructure programme following consultations with regional authorities and representatives from several independent engineering and research organisations.'
        self.assertEqual(provenance_report([self.article(source='A',summary=summary),self.article(source='B',summary=summary)])['repeated_excerpts'],1)
        self.assertEqual(provenance_report([self.article(summary='Read more')]*2)['repeated_excerpts'],0)

    def test_evidence_types_never_claim_complete_article(self):
        self.assertEqual(evidence_label(self.article()),'Headline only')
        self.assertEqual(evidence_label(self.article(summary='Text')),'RSS excerpt')
        self.assertEqual(evidence_label(self.article(reader_text='Article body')),'Publisher page extract')

    def test_linux_priority_and_publisher_variety_preserve_all_articles(self):
        linux=[self.article(f'Linux update {i}',source='Linux outlet') for i in range(12)]
        other=[self.article('AI benchmark release',source='AI desk'),self.article('Gene therapy trial',source='Biotech desk')]
        articles=other+linux
        result=rank_articles(articles,technology=True)
        self.assertIn('Linux',technology_topics(result[0]))
        self.assertTrue(any(item['source']=='AI desk' for item in result[:6]))
        self.assertEqual({id(item) for item in result},{id(item) for item in articles})
        self.assertEqual(len(result),len(articles))

    def test_tracking_parameters_removed_but_case_sensitive_paths_preserved(self):
        self.assertEqual(canonical_link('https://EXAMPLE.org/Story?id=1&utm_source=x#top'),'https://example.org/Story?id=1')
        self.assertNotEqual(canonical_link('https://example.org/Story'),canonical_link('https://example.org/story'))
        articles=[{'link':'https://example.org/story?utm_source=a'},{'link':'https://example.org/story?utm_source=b'}]
        self.assertEqual(len(backend.remove_duplicates(articles)),1)

    def test_event_grouping_does_not_join_months_apart(self):
        articles=[self.article('Germany military aid Ukraine parliament vote'),self.article('Germany military aid Ukraine parliament vote',source='Second')]
        self.assertEqual(len(backend.cluster_stories(articles)),1)
        articles[1]['timestamp']-=30*86400
        self.assertEqual(len(backend.cluster_stories(articles)),2)
        self.assertEqual(backend.related_articles(articles[0],articles),[articles[0]])

    def test_unknown_and_future_dates_do_not_gain_freshness(self):
        self.assertEqual(freshness({'timestamp':0})[0],'Unknown date')
        self.assertEqual(freshness({'timestamp':time.time()+86400})[0],'Future date')
        self.assertEqual(freshness({'timestamp':float('nan')})[0],'Unknown date')
        self.assertEqual(update_label({'updated_timestamp':'invalid'}),'')
        self.assertEqual(update_label({'title':'Correction: initial estimate was inaccurate'}),'Update/correction mentioned')

    def test_audit_exposes_gaps_and_cached_failures(self):
        catalogue=[dict(name='Example',url='https://example.org/feed',region='EUROPE',language='en')]
        report=coverage_audit([self.article(source_region='EUROPE',source_language='en')],catalogue,
                              {'Example':dict(error='Offline',cached=True,checked=1)},country_terms={'DE':('germany',),'RO':('romania',)})
        self.assertIn('Military',report['missing_frames'])
        self.assertEqual(report['sources'][0]['feed_error'],'Offline')
        self.assertTrue(report['sources'][0]['cached'])
        self.assertEqual(report['country_mentions'],{'DE':0,'RO':0})

    def test_ai_evidence_contains_observed_provenance_with_bounded_sources(self):
        articles=[self.article(f'AI study {index}',source=f'Outlet {index}',summary='According to Reuters, results remain preliminary. '*30) for index in range(12)]
        efficient=build_evidence_text(articles,analysis_options(profile='efficient'))
        self.assertIn('Family: Outlet 0',efficient)
        self.assertIn('origin mentions: Reuters',efficient)
        self.assertIn('evidence: RSS excerpt',efficient)
        self.assertNotIn('[7]',efficient)
        options=analysis_options(profile='efficient')
        self.assertLessEqual(len(efficient),max(1800,int((options['num_ctx']-options['num_predict']-1300)*2.8)))

    def test_ordinary_words_do_not_become_linux_or_ai_news(self):
        for title in ('Cristiano Ronaldo, mesaj pentru Lionel Messi', 'Cei mai buni jucători ai României', 'Schiphol airport flight update', 'Police investigation in Mesa'):
            self.assertEqual(technology_topics(self.article(title)),[],title)
