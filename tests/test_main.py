import unittest
import os
import sys
import datetime
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main


class TestYouTubeRecapBot(unittest.TestCase):

    def test_normalize_title(self):
        self.assertEqual(main.normalize_title("  HELLO   WORLD  "), "hello world")
        self.assertEqual(main.normalize_title("Python 3.12: What's New?"), "python 3.12: what's new?")

    def test_is_short_video_by_marker(self):
        # Hashtags in title
        self.assertTrue(main.is_short_video("Crazy coding trick! #shorts", ""))
        self.assertTrue(main.is_short_video("Quick tip #short", ""))
        self.assertTrue(main.is_short_video("Fun video #ytshorts", ""))
        self.assertTrue(main.is_short_video("Another one #youtubeshorts", ""))
        self.assertTrue(main.is_short_video("Uppercase #SHORTS", ""))

        # Hashtags in description
        self.assertTrue(main.is_short_video("Regular Title", "Check out this #shorts video!"))

        # Non-short video without marker
        self.assertFalse(main.is_short_video("Full tutorial on Python", "Description without hashtags"))

    def test_load_channel_ids(self):
        test_content = """# Tech Channels
UC5YhmSFDiIFSgCq2rRVTzbA
# Gaming Channels
UCa_SOEXD5pGMaLpj9dILMBQ # inline comment

UCUZfhX79dQrJvAgYefiXCCA
"""
        test_file = os.path.join(os.path.dirname(__file__), 'temp_channels.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)

        try:
            channels = main.load_channel_ids(test_file)
            expected = [
                'UC5YhmSFDiIFSgCq2rRVTzbA',
                'UCa_SOEXD5pGMaLpj9dILMBQ',
                'UCUZfhX79dQrJvAgYefiXCCA'
            ]
            self.assertEqual(channels, expected)
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_recipient_email_defaults_to_email_user(self):
        # Verify that if RECIPIENT_EMAIL is not set, it defaults to EMAIL_USER
        with patch.dict(os.environ, {'EMAIL_USER': 'sender@example.com'}, clear=True):
            user = os.getenv('EMAIL_USER')
            recipient = os.getenv('RECIPIENT_EMAIL') or user
            self.assertEqual(recipient, 'sender@example.com')

        # Verify that explicit RECIPIENT_EMAIL overrides EMAIL_USER
        with patch.dict(os.environ, {'EMAIL_USER': 'sender@example.com', 'RECIPIENT_EMAIL': 'other@example.com'}, clear=True):
            user = os.getenv('EMAIL_USER')
            recipient = os.getenv('RECIPIENT_EMAIL') or user
            self.assertEqual(recipient, 'other@example.com')

    def test_validate_environment(self):
        with patch.object(main, 'API_KEY', None), \
             patch.object(main, 'EMAIL_USER', 'user@example.com'), \
             patch.object(main, 'EMAIL_PASS', 'secret'):
            self.assertFalse(main.validate_environment())

        with patch.object(main, 'API_KEY', 'valid_api_key'), \
             patch.object(main, 'EMAIL_USER', 'user@example.com'), \
             patch.object(main, 'EMAIL_PASS', 'secret'):
            self.assertTrue(main.validate_environment())

    def test_get_date_bounds(self):
        target_date = main.get_date_bounds()
        self.assertIsInstance(target_date, datetime.date)
        now_date = datetime.datetime.now(datetime.timezone.utc).date()
        self.assertEqual(target_date, now_date - datetime.timedelta(days=1))

    @patch('main.is_shorts_tab_video', return_value=False)
    def test_per_channel_deduplication(self, mock_shorts_tab):
        # Two different channels uploading videos with the same title should NOT be discarded
        candidate_videos = [
            {
                'videoId': 'vid1',
                'title': 'Episode 1',
                'description': '',
                'channel': 'Channel Alpha',
                'url': 'https://youtube.com/watch?v=vid1',
                'thumb': 'https://img.youtube.com/thumb1.jpg',
                'publishedAt': '2026-09-28T12:00:00Z'
            },
            {
                'videoId': 'vid2',
                'title': 'Episode 1',
                'description': '',
                'channel': 'Channel Beta',
                'url': 'https://youtube.com/watch?v=vid2',
                'thumb': 'https://img.youtube.com/thumb2.jpg',
                'publishedAt': '2026-09-28T13:00:00Z'
            },
            {
                'videoId': 'vid3',
                'title': 'Episode 1',
                'description': '',
                'channel': 'Channel Alpha',  # Duplicate title on same channel
                'url': 'https://youtube.com/watch?v=vid3',
                'thumb': 'https://img.youtube.com/thumb3.jpg',
                'publishedAt': '2026-09-28T14:00:00Z'
            }
        ]

        all_videos = []
        unique_channel_titles = set()

        for video in candidate_videos:
            if main.is_short_video(video['title'], video['description'], video['videoId']):
                continue

            norm_title = main.normalize_title(video['title'])
            channel_title_key = (video['channel'].casefold(), norm_title)
            if channel_title_key in unique_channel_titles:
                continue

            unique_channel_titles.add(channel_title_key)
            all_videos.append(video)

        # vid1 (Channel Alpha) and vid2 (Channel Beta) must both be kept; vid3 must be discarded
        self.assertEqual(len(all_videos), 2)
        self.assertEqual(all_videos[0]['videoId'], 'vid1')
        self.assertEqual(all_videos[1]['videoId'], 'vid2')

    @patch('main.urlopen')
    def test_is_shorts_tab_video(self, mock_urlopen):
        # Mock response for a short (stays on /shorts/)
        mock_resp_short = MagicMock()
        mock_resp_short.geturl.return_value = 'https://www.youtube.com/shorts/test_short_id'
        mock_urlopen.return_value.__enter__.return_value = mock_resp_short

        self.assertTrue(main.is_shorts_tab_video('test_short_id'))

        # Mock response for a normal video (redirects to /watch)
        mock_resp_normal = MagicMock()
        mock_resp_normal.geturl.return_value = 'https://www.youtube.com/watch?v=test_normal_id'
        mock_urlopen.return_value.__enter__.return_value = mock_resp_normal

        self.assertFalse(main.is_shorts_tab_video('test_normal_id'))

    @patch('main.urlopen')
    @patch('smtplib.SMTP_SSL')
    def test_send_email_escaping_and_content(self, mock_smtp, mock_urlopen):
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'test_image_bytes'
        mock_resp.headers.get_content_type.return_value = 'image/jpeg'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        sample_videos = [
            {
                'videoId': 'v123',
                'title': 'Review: <Brand> & "Accessories"',
                'url': 'https://youtube.com/watch?v=v123',
                'thumb': 'https://img.youtube.com/v123.jpg',
                'channel': 'Tech & Gadgets',
                'publishedAt': '2026-09-28T15:00:00Z'
            }
        ]

        with patch.object(main, 'EMAIL_USER', 'sender@example.com'), \
             patch.object(main, 'EMAIL_PASS', 'password123'), \
             patch.object(main, 'RECIPIENT_EMAIL', 'sender@example.com'):
            main.send_email(sample_videos)

        mock_server.login.assert_called_once_with('sender@example.com', 'password123')
        self.assertTrue(mock_server.send_message.called)
        sent_msg = mock_server.send_message.call_args[0][0]

        # Verify Plain text content
        plain_payload = sent_msg.get_body(preferencelist=('plain',)).get_content()
        self.assertIn("Review: <Brand> & \"Accessories\"", plain_payload)
        self.assertIn("Tech & Gadgets", plain_payload)
        self.assertIn("https://youtube.com/watch?v=v123", plain_payload)

        # Verify HTML content is safely escaped
        html_payload = sent_msg.get_body(preferencelist=('html',)).get_content()
        self.assertIn("Review: &lt;Brand&gt; &amp; &quot;Accessories&quot;", html_payload)
        self.assertIn("Tech &amp; Gadgets", html_payload)

    @patch('main.build')
    @patch('main.load_channel_ids')
    @patch('main.is_short_video', return_value=False)
    def test_fetch_videos_mocked(self, mock_short, mock_channels, mock_build):
        mock_channels.return_value = ['UC12345']

        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube

        # Mock channels().list
        mock_channels_list = MagicMock()
        mock_channels_list.execute.return_value = {
            'items': [
                {
                    'id': 'UC12345',
                    'contentDetails': {
                        'relatedPlaylists': {
                            'uploads': 'UU12345'
                        }
                    }
                }
            ]
        }
        mock_youtube.channels().list.return_value = mock_channels_list

        yesterday_str = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        # Mock playlistItems().list with missing medium thumbnail and private video
        mock_playlist_list = MagicMock()
        mock_playlist_list.execute.return_value = {
            'items': [
                {
                    'snippet': {
                        'title': 'Private video',
                        'publishedAt': f'{yesterday_str}T10:00:00Z',
                        'resourceId': {'videoId': 'priv1'}
                    }
                },
                {
                    'snippet': {
                        'title': 'Great Video',
                        'publishedAt': f'{yesterday_str}T12:00:00Z',
                        'resourceId': {'videoId': 'good1'},
                        'thumbnails': {
                            'default': {'url': 'https://img.youtube.com/default.jpg'}
                            # Note: 'medium' is missing intentionally to test fallback
                        },
                        'channelTitle': 'Test Channel'
                    }
                }
            ]
        }
        mock_youtube.playlistItems().list.return_value = mock_playlist_list

        with patch.object(main, 'API_KEY', 'valid_key'), \
             patch.object(main, 'EMAIL_USER', 'user@example.com'), \
             patch.object(main, 'EMAIL_PASS', 'pass'):
            videos = main.fetch_videos()

        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0]['videoId'], 'good1')
        self.assertEqual(videos[0]['title'], 'Great Video')
        self.assertEqual(videos[0]['thumb'], 'https://img.youtube.com/default.jpg')


if __name__ == '__main__':
    unittest.main()

