import support  # noqa: F401  (must come first: isolates user folders)
import json
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from euroinfo.core.workspace import ReaderWorkspace, analysis_key, analysis_options, matches_query, query_tokens, export_articles, validate_library_backup, build_evidence_text


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name)/'research.sqlite3'
        self.workspace = ReaderWorkspace(self.path)
        self.article = {'title':'European energy policy', 'source':'Example News', 'link':'https://example.org/energy', 'summary':'Energy costs and public policy.', 'timestamp':1700000000}

    def tearDown(self):
        self.folder.cleanup()

    def test_publisher_text_is_budgeted_and_replaces_the_short_rss_excerpt(self):
        article=dict(self.article,reader_text='Publisher article detail. '*1000)
        options=analysis_options()
        text=build_evidence_text([article,dict(self.article,source='Other News')],options)
        self.assertIn('Publisher page extract:',text)
        self.assertIn('Other News',text)
        self.assertLess(len(text),6000)
        self.workspace.save_story('full',article,read=True)
        self.assertNotIn('reader_text',self.workspace.history_articles()[0])

    def test_notes_tags_and_read_history_survive_reopening(self):
        self.workspace.save_story('story', self.article, notes='Compare voting records.', tags=['Energy', 'energy', 'Policy'], read=True)
        second = ReaderWorkspace(self.path)
        state = second.metadata()['story']
        self.assertEqual(state['notes'], 'Compare voting records.')
        self.assertEqual(state['tags'], ['energy','policy'])
        self.assertGreater(state['read_at'], 0)
        second.save_story('story', self.article, read=False)
        self.assertEqual(second.metadata()['story']['read_at'], 0)
        self.assertEqual(second.research_articles(), [self.article])

    def test_history_only_records_do_not_enter_research_library(self):
        self.workspace.save_story('read', self.article, read=True)
        self.assertEqual(self.workspace.research_articles(), [])

    def test_recently_opened_articles_remain_available_after_leaving_the_feed(self):
        self.workspace.save_story('read', self.article, read=True)
        self.assertEqual(self.workspace.history_articles(), [self.article])
        self.workspace.save_story('read', self.article, read=False)
        self.assertEqual(self.workspace.history_articles(), [])

    def test_saved_searches_roundtrip_and_remove(self):
        self.workspace.save_watch('Energy', '"energy policy" -source:other')
        self.assertEqual(self.workspace.watches(), {'Energy':'"energy policy" -source:other'})
        self.workspace.remove_watch('Energy')
        self.assertEqual(self.workspace.watches(), {})
        with self.assertRaises(ValueError):
            self.workspace.save_watch('', 'query')

    def test_cache_expires_and_is_bounded(self):
        self.workspace.put_analysis('old', 'Answer')
        with patch('euroinfo.core.workspace.time.time', return_value=time.time()+49*3600):
            self.assertIsNone(self.workspace.get_analysis('old'))
        for index in range(105):
            self.workspace.put_analysis(str(index), 'Answer')
        with closing(self.workspace.connect()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM analyses').fetchone()[0],100)
        self.workspace.clear_analyses()
        self.assertIsNone(self.workspace.get_analysis('104'))

    def test_concurrent_note_writes_do_not_cross_articles(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(self.workspace.save_story,str(i),self.article,notes=f'Note {i}') for i in range(20)]
            for future in futures:
                future.result()
        states=self.workspace.metadata()
        self.assertEqual(len(states),20)
        self.assertEqual(states['12']['notes'],'Note 12')

    def test_evidence_language_and_profile_change_cache_key(self):
        options=analysis_options()
        original=analysis_key('Evidence','Romanian',options)
        self.assertNotEqual(original,analysis_key('Changed evidence','Romanian',options))
        self.assertNotEqual(original,analysis_key('Evidence','German',options))
        self.assertNotEqual(original,analysis_key('Evidence','Romanian',analysis_options(profile='deep')))

    def test_search_phrases_negation_fields_and_notes(self):
        state={'notes':'Compare voting records', 'tags':['energy'], 'read_at':0}
        self.assertTrue(matches_query(self.article,query_tokens('"energy policy" source:"Example News" tag:energy is:unread is:noted'),state))
        self.assertFalse(matches_query(self.article,query_tokens('-source:example'),state))
        self.assertFalse(matches_query(self.article,query_tokens('is:read'),state))
        self.assertTrue(matches_query(self.article,query_tokens('voting'),state))
        self.assertTrue(matches_query(self.article,query_tokens('is:saved'),state,True))

    def test_csv_preserves_commas_and_blocks_formulas(self):
        article=dict(self.article,title='=HYPERLINK("evil")',source='News, Europe')
        exported=export_articles([article],{'k':{'notes':'@command','tags':['policy']}},lambda _: 'k','csv')
        self.assertIn("'=HYPERLINK",exported)
        self.assertIn('"News, Europe"',exported)
        self.assertIn("'@command",exported)

    def test_backup_validated_before_import_and_rejects_unsafe_urls(self):
        path=Path(self.folder.name)/'library.json'
        payload={'schema':2,'stories':[self.article],'saved_keys':['k'],'metadata':{'k':{'notes':'Note','tags':['energy']}},'watches':{'Energy':'energy'}}
        path.write_text(json.dumps(payload))
        self.assertEqual(validate_library_backup(path),payload)
        payload['stories'][0]['link']='file:///etc/passwd'
        path.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            validate_library_backup(path)
        self.assertEqual(self.workspace.metadata(),{})
