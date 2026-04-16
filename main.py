import os
import datetime
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

    start_yesterday = datetime.datetime.combine(yesterday, datetime.time.min).isoformat() + "Z"
    end_yesterday = datetime.datetime.combine(yesterday, datetime.time.max).isoformat() + "Z"

    cutoff_time = datetime.datetime.combine(day_before_yesterday, datetime.time.max).isoformat() + "Z"

    return start_yesterday, end_yesterday, cutoff_time


def fetch_videos():
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    start_yesterday, end_yesterday, cutoff_time = get_date_bounds()
    all_videos = []

    if not os.path.exists('channels.txt'):
        print("channels.txt not found.")
        return []

    with open('channels.txt', 'r') as f:
        channels_ids = [line.strip() for line in f if line.strip()]

    for channel_id in channels_ids:
        next_page_token = None
        should_stop_channel = False

        while not should_stop_channel:
            response = youtube.activities().list(
                part='snippet,contentDetails',
                channelId=channel_id,
                maxResults=10,
                pageToken=next_page_token
            ).execute()

            if not response.get('items'):
                break

            for item in response['items']:
                if item['snippet']['type'] != 'upload':
                    continue

                published_at = item['snippet']['publishedAt']
                video_id = item['contentDetails']['upload']['videoId']

                if published_at <= cutoff_time:
                    should_stop_channel = True
                    break

                if start_yesterday <= published_at <= end_yesterday:
                    all_videos.append({
                        'title': item['snippet']['title'],
                        'url': f"https://www.youtube.com/watch?v={video_id}",
                        'thumb': item['snippet']['thumbnails']['medium']['url'],
                        'channel': item['snippet']['channelTitle'],
                    })

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

    return all_videos


def send_email(videos):
    count = len(videos)
    date_str = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%d.%m.%Y')

    msg = EmailMessage()
    msg['Subject'] = f"Youtube Recap - {date_str}"
    msg['From'] = EMAIL_USER
    msg['To'] = RECIPIENT_EMAIL

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: Arial, sans-serif;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%">
            <tr>
                <td align="center" style="padding: 20px 0;">
                    <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border-radius: 8px; border: 1px solid #dee2e6;">
                        <tr>
                            <td align="center" style="background-color: #343a40; padding: 30px 20px;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 24px;">YouTube Daily Recap</h1>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 20px;">
                                <p style="font-size: 16px; color: #666;">
                                    <strong>Results:</strong> Found {count} new videos from {date_str}.
                                </p>
                                <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
    """

    for v in videos:
        html_content += f"""
                                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 25px;">
                                    <tr>
                                        <td width="200" valign="top">
                                            <img src="{v['thumb']}" width="180" style="border-radius: 6px; border: 1px solid #ddd;">
                                        </td>
                                        <td valign="top" style="padding-left: 15px;">
                                            <div style="color: #28a745; font-size: 11px; font-weight: bold;">{v['channel']}</div>
                                            <div style="font-size: 16px; font-weight: 600; color: #343a40;">{v['title']}</div>
                                            <a href="{v['url']}" style="display: inline-block; margin-top: 10px; padding: 7px 14px; background-color: #28a745; color: #ffffff; text-decoration: none; border-radius: 4px;">Watch</a>
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

    msg.set_content(f"Found {count} videos from yesterday.")
    msg.add_alternative(html_content, subtype='html')

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)


if __name__ == '__main__':
    videos_found = fetch_videos()
    send_email(videos_found)