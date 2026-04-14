import os
import datetime
from googleapiclient.discovery import build
import smtplib
from email.message import EmailMessage

API_KEY = os.getenv('YOUTUBE_API_KEY')
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
RECIPIENT_EMAIL = os.getenv('EMAIL_USER')

def get_yesterday_date():
    yesterday = datetime.datetime.today() - datetime.timedelta(days=1)
    start_time = datetime.datetime.combine(yesterday, datetime.time.min).isoformat() + "Z"
    end_time = datetime.datetime.combine(yesterday, datetime.time.max).isoformat() + "Z"
    return start_time, end_time


def fetch_videos():
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    start_time, end_time = get_yesterday_date()
    all_videos = []

    with open('channels.txt', 'r') as f:
        channels_ids = [line.strip() for line in f if line.strip()]

    for channel_id in channels_ids:
        channel_response = youtube.channels().list(
            part='contentDetails',
            id=channel_id
        ).execute()

        if not channel_response.get('items'):
            continue

        uploads_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

        playlist_response = youtube.playlistItems().list(
            part='snippet',
            playlistId=uploads_id,
            maxResults=10
        ).execute()

        for item in playlist_response.get('items', []):
            published_at = item['snippet']['publishedAt']

            if start_time <= published_at <= end_time:
                all_videos.append({
                    'title': item['snippet']['title'],
                    'url': f"https://www.youtube.com/watch?v={item['snippet']['resourceId']['videoId']}",
                    'thumb': item['snippet']['thumbnails']['medium']['url'],
                    'channel': item['snippet']['channelTitle'],
                })
    return all_videos

def send_email(videos):
    msg = EmailMessage()
    msg['Subject'] = f"Youtube Recap - {(datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%d.%m.%Y')}"
    msg['From'] = EMAIL_USER
    msg['To'] = RECIPIENT_EMAIL

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: 'Segoe UI', Arial, sans-serif;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%">
            <tr>
                <td align="center" style="padding: 20px 0;">
                    <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #dee2e6; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">

                        <tr>
                            <td align="center" style="background-color: #343a40; padding: 30px 20px; border-bottom: 4px solid #28a745;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 24px; text-transform: uppercase; letter-spacing: 2px;">YouTube Daily Recap</h1>
                            </td>
                        </tr>

                        <tr>
                            <td style="padding: 30px 20px;">
                                <h2 style="color: #343a40; font-size: 18px; margin-bottom: 20px; border-left: 4px solid #28a745; padding-left: 10px;">New Videos from Yesterday:</h2>
    """

    for v in videos:
        html_content += f"""
                                <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 25px; border-bottom: 1px solid #eee; padding-bottom: 20px;">
                                    <tr>
                                        <td width="200" valign="top">
                                            <a href="{v['url']}" target="_blank" style="display:block; text-decoration:none;">
                                                <img src="{v['thumb']}" width="180" alt="" style="border-radius: 6px; display: block; border: 1px solid #ddd;">
                                            </a>
                                        </td>
                                        <td valign="top" style="padding-left: 15px;">
                                            <div style="color: #28a745; font-size: 11px; font-weight: bold; text-transform: uppercase; margin-bottom: 4px;">{v['channel']}</div>
                                            <div style="font-size: 16px; font-weight: 600; line-height: 1.3; margin-bottom: 10px; color: #343a40;">{v['title']}</div>
                                            <a href="{v['url']}" target="_blank" style="display: inline-block; padding: 7px 14px; background-color: #28a745; color: #ffffff; text-decoration: none; font-size: 12px; border-radius: 4px; font-weight: bold;">Watch Video</a>
                                        </td>
                                    </tr>
                                </table>
        """

    html_content += f"""
                            </td>
                        </tr>

                        <tr>
                            <td align="center" style="background-color: #f8f9fa; padding: 20px; color: #6c757d; font-size: 12px; border-top: 1px solid #dee2e6;">
                                <p style="margin: 0;">You are receiving this because you subscribed to these channel updates.</p>
                                <p style="margin: 5px 0 0 0;">&copy; {datetime.datetime.now().year} YouTube Digest Bot. All rights reserved.</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    msg.set_content(f"Youtube Recap - {(datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%d.%m.%Y')}")
    msg.add_alternative(html_content, subtype='html')

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)

if __name__ == '__main__':
    videos_found = fetch_videos()
    send_email(videos_found)