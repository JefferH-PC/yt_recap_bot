import os
import datetime
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from googleapiclient.discovery import build
import smtplib
from email.message import EmailMessage

API_KEY = os.getenv('YOUTUBE_API_KEY')
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
RECIPIENT_EMAIL = os.getenv('EMAIL_USER')


def get_date_bounds():
    today = datetime.datetime.today()
    yesterday = today - datetime.timedelta(days=1)
    day_before_yesterday = today - datetime.timedelta(days=2)

    yesterday_date = yesterday.date()
    return yesterday_date


def normalize_title(title):
    return re.sub(r'\s+', ' ', title).strip().casefold()


def is_shorts_tab_video(video_id):
    shorts_url = f'https://www.youtube.com/shorts/{video_id}'
    request = Request(shorts_url, headers={'User-Agent': 'Mozilla/5.0'})

    try:
        with urlopen(request, timeout=10) as response:
            final_path = urlsplit(response.geturl()).path.rstrip('/')
    except Exception:
        return False

    return final_path.startswith('/shorts/')


def is_short_video(title, description='', video_id=None):
    text = normalize_title(f'{title} {description}')
    has_shorts_marker = re.search(r'(?<!\w)#shorts?\b', text) is not None
    return has_shorts_marker or (
        video_id is not None and is_shorts_tab_video(video_id)
    )


def fetch_videos():
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    yesterday_date = get_date_bounds()
    candidate_videos = []
    unique_video_ids = set()

    if not os.path.exists('channels.txt'):
        print("channels.txt not found.")
        return []

    with open('channels.txt', 'r') as f:
        channels_ids = [line.strip() for line in f if line.strip()]

    for channel_id in channels_ids:
        channel_response = youtube.channels().list(
            part='contentDetails',
            id=channel_id
        ).execute()

        if not channel_response.get('items'):
            continue

        uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

        next_page_token = None
        should_stop_channel = False

        while not should_stop_channel:
            playlist_response = youtube.playlistItems().list(
                part='snippet',
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            items = playlist_response.get('items', [])
            if not items:
                break

            for item in items:
                published_at_str = item['snippet']['publishedAt']
                published_at_dt = datetime.datetime.fromisoformat(published_at_str.replace('Z', '+00:00')).date()
                video_id = item['snippet']['resourceId']['videoId']

                if published_at_dt == yesterday_date:
                    if video_id not in unique_video_ids:
                        candidate_videos.append({
                            'videoId': video_id,
                            'title': item['snippet']['title'],
                            'description': item['snippet'].get('description', ''),
                            'url': f"https://www.youtube.com/watch?v={video_id}",
                            'thumb': item['snippet']['thumbnails']['medium']['url'],
                            'channel': item['snippet']['channelTitle'],
                            'publishedAt': published_at_str
                        })
                        unique_video_ids.add(video_id)

                elif published_at_dt < yesterday_date:
                    should_stop_channel = True
                    break

            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token:
                break

    all_videos = []
    unique_titles = set()
    for video in candidate_videos:
        if is_short_video(video['title'], video['description'], video['videoId']):
            continue

        normalized_title = normalize_title(video['title'])
        if normalized_title in unique_titles:
            continue

        unique_titles.add(normalized_title)
        video.pop('videoId')
        video.pop('description')
        all_videos.append(video)

    return all_videos


def send_email(videos):
    count = len(videos)
    date_display = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%d.%m.%Y')

    msg = EmailMessage()
    msg['Subject'] = f"Youtube Recap - {date_display}"
    msg['From'] = EMAIL_USER
    msg['To'] = RECIPIENT_EMAIL

    videos.sort(key=lambda x: x['publishedAt'], reverse=True)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: Arial, sans-serif;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%">
            <tr>
                <td align="center" style="padding: 20px 0;">
                    <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border-radius: 8px; border: 1px solid #dee2e6;">
                        <tr>
                            <td align="center" style="background-color: #343a40; padding: 30px 20px; border-bottom: 4px solid #28a745;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 24px;">YouTube Daily Recap</h1>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 30px 20px;">
                                <p style="font-size: 18px; color: #343a40; margin: 0;">
                                    <strong>{count}</strong> videos found from {date_display}.
                                </p>
                                <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
    """

    for v in videos:
        html_content += f"""
                                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 25px; border-bottom: 1px solid #eee; padding-bottom: 20px;">
                                    <tr>
                                        <td width="200" valign="top">
                                            <a href="{v['url']}"><img src="{v['thumb']}" width="180" style="border-radius: 6px; border: 1px solid #ddd;"></a>
                                        </td>
                                        <td valign="top" style="padding-left: 15px;">
                                            <div style="color: #28a745; font-size: 11px; font-weight: bold; text-transform: uppercase;">{v['channel']}</div>
                                            <div style="font-size: 16px; font-weight: 600; color: #343a40; margin: 5px 0;">{v['title']}</div>
                                            <a href="{v['url']}" style="display: inline-block; padding: 7px 14px; background-color: #28a745; color: #ffffff; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold;">Watch Video</a>
                                        </td>
                                    </tr>
                                </table>
        """

    html_content += """
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    msg.set_content(f"YouTube Recap: {count} videos found.")
    msg.add_alternative(html_content, subtype='html')

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)


if __name__ == '__main__':
    videos_found = fetch_videos()
    send_email(videos_found)