import support  # noqa: F401  (must come first: isolates user folders)
import unittest
from unittest.mock import Mock, patch
from euroinfo.core import feeds as backend


class FeedRefreshTests(unittest.TestCase):
    def setUp(self):
        self.source={'name':'Test Outlet','url':'https://example.org/test-feed','region':'EUROPE','language':'en'}
        self.old_validators=backend._FEED_VALIDATORS
        self.old_health=backend._FEED_HEALTH
        backend._FEED_VALIDATORS={}
        backend._FEED_HEALTH={}

    def tearDown(self):
        backend._FEED_VALIDATORS=self.old_validators
        backend._FEED_HEALTH=self.old_health

    def response(self, status=200):
        result=Mock(status_code=status,content=b'Feed',url=self.source['url'],headers={'ETag':'"version1"','Last-Modified':'Wed, 07 Oct 2026 00:00:00 GMT'})
        return result

    def test_conditional_refresh_avoids_parsing_and_returns_fresh_copies(self):
        article={'title':'Story','link':'https://example.org/story','source':'Test Outlet'}
        feed=Mock(bozo=False,entries=[{}])
        session=Mock()
        session.get.side_effect=[self.response(), self.response(304)]
        with patch.object(backend,'session',return_value=session), patch.object(backend.feedparser,'parse',return_value=feed) as parse, patch.object(backend,'_normalize_entry',return_value=article):
            first=backend._fetch_feed(self.source)
            first[0]['localized_title']='Translated'
            second=backend._fetch_feed(self.source)
        self.assertEqual(parse.call_count,1)
        self.assertNotIn('localized_title',second[0])
        self.assertEqual(session.get.call_args.kwargs['headers']['If-None-Match'],'"version1"')
        self.assertTrue(backend.feed_health_snapshot()['Test Outlet']['cached'])

    def test_failure_preserves_available_feed_and_records_error(self):
        backend._FEED_VALIDATORS[self.source['url']]={'etag':'x','modified':'','fetched':backend.time.time(),'articles':[{'title':'Cached'}]}
        session=Mock()
        session.get.side_effect=backend.requests.RequestException('offline')
        with patch.object(backend,'session',return_value=session):
            result=backend._fetch_feed(self.source)
        self.assertEqual(result,[{'title':'Cached'}])
        self.assertEqual(backend.feed_health_snapshot()['Test Outlet']['error'],'offline')
