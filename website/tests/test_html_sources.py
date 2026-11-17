"""Synthetic provider pages and bounded parser/decoder regressions; no network."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import requests
from website import agenda_pasar, berita_global, ramai_dibahas
from website.html_parser import parse_html, fetch_html, read_response, MAX_HTML_BYTES, MAX_DEPTH
from website import news_links


class Response:
    def __init__(self, body=b'', status=200, headers=None):
        self.body=body.encode('utf-8') if isinstance(body,str) else body
        self.status_code=status;self.headers=headers or {};self.closed=False

    def raise_for_status(self):
        if self.status_code>=400:raise requests.HTTPError('fixture response')

    def iter_content(self, chunk_size):
        for i in range(0,len(self.body),chunk_size):yield self.body[i:i+chunk_size]

    def close(self):self.closed=True


class HtmlTests(unittest.TestCase):
    def test_utf8_entities_and_nested_text(self):
        tree=parse_html('<p class="lead">Bursa <b>naik</b> &amp; pasar stabil — contoh</p>')
        self.assertEqual(tree.css_first('.lead').text(separator=' ',strip=True),
                         'Bursa naik & pasar stabil — contoh')

    def test_oversized_and_deep_documents_are_rejected(self):
        with self.assertRaises(ValueError):parse_html(b'x'*(MAX_HTML_BYTES+1))
        with self.assertRaises(ValueError):parse_html('<div>'*(MAX_DEPTH+1)+'x'+'</div>'*(MAX_DEPTH+1))
        with patch('website.html_parser.MAX_ELEMENTS',3):
            with self.assertRaises(ValueError):parse_html('<br><br><br><br>')

    def test_malformed_input_does_not_bypass_depth_budget(self):
        with self.assertRaises(ValueError):parse_html('<div>'*(MAX_DEPTH+1))
        tree=parse_html('<div><p>Fixture <b>text</div>')
        self.assertIn('Fixture',tree.text())

    def test_stream_budget_rejects_declared_and_actual_oversize(self):
        for response in [Response(b'x',headers={'Content-Length':str(MAX_HTML_BYTES+1)}),
                         Response(b'x',headers={'Content-Length':'-1'}),
                         Response(b'x'*(MAX_HTML_BYTES+1))]:
            with self.assertRaises(ValueError):read_response(response)
        response=Response('valid')
        self.assertEqual(read_response(response),b'valid')

    def test_fetch_closes_responses_and_does_not_follow_redirects(self):
        for status in [200,302,500]:
            response=Response('<p>fixture</p>',status=status)
            with patch('website.html_parser.requests.get',return_value=response) as get:
                if status==200:self.assertEqual(fetch_html('https://example.invalid'),response.body)
                else:
                    with self.assertRaises((ValueError,requests.HTTPError)):fetch_html('https://example.invalid')
            self.assertTrue(response.closed)
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            self.assertTrue(get.call_args.kwargs['stream'])

    def test_elapsed_response_budget(self):
        with patch('website.html_parser.time.monotonic',side_effect=[0,31]):
            with self.assertRaises(ValueError):read_response(Response('fixture'))

    def test_removed_parser_stack_is_not_installed(self):
        for name in ['bs4','soupsieve','googlenewsdecoder']:
            self.assertIsNone(importlib.util.find_spec(name),name)


class ProviderTests(unittest.TestCase):
    def test_fed_calendar(self):
        html='''<div class="panel"><h3 class="panel-heading">2026 FOMC Meetings</h3>
          <div class="fomc-meeting"><span class="fomc-meeting__month">January</span>
          <span class="fomc-meeting__date">27-28</span></div></div>'''
        with patch.object(agenda_pasar,'fetch_html',return_value=html):rows=agenda_pasar.fed()
        self.assertEqual([x['tanggal'] for x in rows],['2026-01-28'])

    def test_bea_calendar_keeps_new_york_to_jakarta_timing(self):
        html='''<table><thead><tr><th>2026 Releases</th></tr></thead><tbody><tr>
          <td class="release-title">Personal Income and Outlays</td>
          <td class="release-date">July 31</td><td><small>8:30 AM</small></td>
          </tr></tbody></table>'''
        with patch.object(agenda_pasar,'fetch_html',return_value=html):rows=agenda_pasar.bea()
        self.assertTrue(rows[0]['waktu'].startswith('2026-07-31T19:30:00'))

    def test_ksei_ticker_date_and_relative_document_url(self):
        html='''<table><tbody><tr><td>1</td><td>Dividen (ADRO)
          <a href="/files/fixture.pdf">Lihat</a></td><td>12 November 2026</td>
          </tr></tbody></table>'''
        with patch.object(agenda_pasar,'fetch_html',return_value=html), \
             patch.object(agenda_pasar,'pdf_events',side_effect=lambda row:[row]):
            rows=agenda_pasar.ksei('cash-dividend','Dividen')
        self.assertEqual(rows[0]['ticker'],'ADRO')
        self.assertEqual(rows[0]['tanggal'],'2026-11-12')
        self.assertEqual(rows[0]['url'],'https://web.ksei.co.id/files/fixture.pdf')

    def test_missing_optional_pdf_reader_keeps_announcement(self):
        with patch.dict('sys.modules',{'pdfplumber':None}):
            rows=agenda_pasar.pdf_events({'url':'https://example.invalid/fixture.pdf'})
        self.assertEqual(rows[0]['jenis_tanggal'],'Pengumuman')

    def test_publisher_search_extracts_titles_and_links(self):
        html='''<div class="card__post__title"><h2>
          <a href="https://www.antaranews.com/fixture">The Fed &amp; pasar</a>
          </h2></div>'''
        with patch.object(berita_global,'fetch_html',return_value=html):
            rows=berita_global._cari_penerbit(('The Fed','fixture'))
        self.assertEqual(rows[0]['judul'],'The Fed & pasar')
        self.assertEqual(rows[0]['url'],'https://www.antaranews.com/fixture')

    def test_publisher_article_excludes_nested_boilerplate(self):
        stamp=datetime.now(timezone.utc).isoformat()
        html=f'''<meta property="article:published_time" content="{stamp}">
          <div class="post-content"><aside>BOILERPLATE<script>UNTRUSTED</script></aside>
          <p>The Fed mempertahankan suku bunga dan memberikan panduan kebijakan terbaru.</p></div>'''
        with patch.object(berita_global,'fetch_html',return_value=html):
            row=berita_global._ekstrak({'url':'https://www.antaranews.com/fixture','kategori':'The Fed'})
        self.assertIn('The Fed',row['isi']);self.assertNotIn('BOILERPLATE',row['isi'])
        self.assertNotIn('UNTRUSTED',row['isi'])

    def test_telegram_public_message_text_timestamp_and_views(self):
        html='''<div class="tgme_widget_message" data-post="fixture_channel/42">
          <time datetime="2026-11-17T01:00:00+00:00"></time>
          <div class="tgme_widget_message_text"><b>ADRO</b> &amp; BBRI</div>
          <span class="tgme_widget_message_views">1.2K</span></div>'''
        with patch('website.html_parser.fetch_html',return_value=html):
            rows=ramai_dibahas._halaman_channel('fixture_channel')
        self.assertEqual(rows[0]['id'],42)
        self.assertEqual(rows[0]['waktu'].hour,8)
        self.assertEqual(rows[0]['teks'],'ADRO & BBRI')
        self.assertEqual(rows[0]['tayang'],1200)


class NewsLinkTests(unittest.TestCase):
    def metadata(self,signature='fixture-signature',timestamp='1700000000'):
        return f'<c-wiz><div jscontroller="fixture" data-n-a-sg="{signature}" data-n-a-ts="{timestamp}"></div></c-wiz>'

    def rpc(self,url='https://publisher.example/fixture'):
        result=['garturlres',url]
        return ")]}'\n\n123\n"+json.dumps([['wrb.fr','Fbv4je',json.dumps(result)]])+ '\n'

    def test_valid_framed_response_and_bounded_requests(self):
        response=Response(self.rpc())
        with patch.object(news_links,'fetch_html',return_value=self.metadata()), \
             patch.object(news_links.requests,'post',return_value=response) as post:
            result=news_links.decode_google_news('https://news.google.com/rss/articles/CBMi-fixture',interval=1)
        self.assertEqual(result,{'status':True,'decoded_url':'https://publisher.example/fixture'})
        self.assertTrue(response.closed)
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        frame=json.loads(post.call_args.kwargs['data']['f.req'])
        payload=json.loads(frame[0][0][1])
        self.assertEqual(payload[2:],[ 'CBMi-fixture',1700000000,'fixture-signature'])

    def test_invalid_google_urls_never_make_requests(self):
        for url in ['http://news.google.com/articles/x','https://news.google.com.evil.example/articles/x',
                    'https://user@news.google.com/articles/x','https://news.google.com/other/x',
                    'https://news.google.com/articles/%2fetc',None]:
            with patch.object(news_links,'fetch_html') as get:
                self.assertFalse(news_links.decode_google_news(url)['status'])
                get.assert_not_called()

    def test_missing_metadata_and_invalid_timestamps_are_unavailable(self):
        for html in ['<p>Layout changed</p>',self.metadata(timestamp='invalid')]:
            with patch.object(news_links,'fetch_html',return_value=html),patch.object(news_links.requests,'post') as post:
                self.assertFalse(news_links.decode_google_news('https://news.google.com/articles/fixture')['status'])
                post.assert_not_called()

    def test_private_and_non_web_publisher_urls_are_rejected(self):
        for value in ['http://127.0.0.1/','http://[::1]/','http://localhost/','http://localhost./','file:///tmp/example',
                      'https://name:secret@publisher.example/','https://publisher.example:8765/']:
            with self.assertRaises(ValueError):news_links._rpc_result(self.rpc(value).encode())

    def test_network_and_protocol_failures_are_unavailable(self):
        with patch.object(news_links,'fetch_html',side_effect=requests.Timeout):
            self.assertFalse(news_links.decode_google_news('https://news.google.com/articles/fixture')['status'])
        for body in ['not json',json.dumps([['wrb.fr','OTHER',json.dumps(['garturlres','https://publisher.example'])]])]:
            with self.assertRaises(ValueError):news_links._rpc_result(body.encode())


if __name__=='__main__':unittest.main()
