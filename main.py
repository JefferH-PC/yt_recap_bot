import os
import sys
import datetime
import re
import html
import logging
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import smtplib
from email.message import EmailMessage

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Base directory for resolving relative file paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNELS_FILE = os.getenv('CHANNELS_FILE', os.path.join(BASE_DIR, 'channels.txt'))

# Credentials and Email Configuration
API_KEY = os.getenv('YOUTUBE_API_KEY')
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')

# NOTE: The recipient email defaults to the same as EMAIL_USER (the user)
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL') or EMAIL_USER

# Optional SMTP & Behavior Configuration
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '465'))
SEND_EMPTY_EMAIL = os.getenv('SEND_EMPTY_EMAIL', 'false').lower() in ('1', 'true', 'yes')
TIMEZONE_STR = os.getenv('TIMEZONE', 'UTC')


def validate_environment():
    """
    Validates that required environment variables are set before proceeding.
    """
    missing = []
    if not API_KEY:
        missing.append('YOUTUBE_API_KEY')
    if not EMAIL_USER:
        missing.append('EMAIL_USER')
    if not EMAIL_PASS:
        missing.append('EMAIL_PASS')

    if missing:
        logger.error(f"Missing required environment variable(s): {', '.join(missing)}")
        logger.error("Please configure these in your environment, secrets, or a .env file.")
        return False
    return True


def get_date_bounds():
    """
    Determines yesterday's date based on the configured timezone (defaults to UTC).
    """
    tz = None
    if TIMEZONE_STR and TIMEZONE_STR.upper() not in ('UTC', 'Z'):
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(TIMEZONE_STR)
        except Exception as e:
            logger.warning(f"Could not load timezone '{TIMEZONE_STR}': {e}. Defaulting to UTC.")
            tz = datetime.timezone.utc
    else:
        tz = datetime.timezone.utc

    now = datetime.datetime.now(tz)
    yesterday_date = (now - datetime.timedelta(days=1)).date()
    return yesterday_date


def load_channel_ids(filepath=CHANNELS_FILE):
    """
    Loads channel IDs from file, skipping blank lines and comments (#).
    """
    if not os.path.exists(filepath):
        logger.error(f"Channels file not found at: {filepath}")
        return []

    channel_ids = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            clean_line = line.strip()
            if not clean_line or clean_line.startswith('#'):
                continue
            # Strip inline comments if present
            cid = clean_line.split('#')[0].strip()
            if cid:
                channel_ids.append(cid)

    logger.info(f"Loaded {len(channel_ids)} channel ID(s) from {filepath}")
    return channel_ids


def normalize_title(title):
    """
    Normalizes a title string for comparison by collapsing whitespace and casefolding.
    """
    return re.sub(r'\s+', ' ', title).strip().casefold()


def is_shorts_tab_video(video_id):
    """
    Checks if a video is a YouTube Short by inspecting redirect headers via a lightweight HEAD request.
    Normal videos redirect to /watch, whereas Shorts remain on /shorts/.
    """
    shorts_url = f'https://www.youtube.com/shorts/{video_id}'
    request = Request(shorts_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    request.get_method = lambda: 'HEAD'

    try:
        with urlopen(request, timeout=5) as response:
            final_path = urlsplit(response.geturl()).path.rstrip('/')
            return final_path.startswith('/shorts/')
    except Exception as e:
        logger.debug(f"HEAD check error for video {video_id}: {e}")
        if hasattr(e, 'close'):
            try:
                e.close()
            except Exception:
                pass
        return False


def is_short_video(title, description='', video_id=None):
    """
    Identifies whether a video is a YouTube Short based on title/description hashtags or URL inspection.
    """
    text = normalize_title(f'{title} {description}')
    has_shorts_marker = re.search(r'(?<!\w)#(?:shorts?|ytshorts|youtubeshorts)\b', text) is not None
    if has_shorts_marker:
        return True

    if video_id is not None:
        return is_shorts_tab_video(video_id)

    return False


def fetch_videos():
    """
    Queries the YouTube Data API to fetch non-Short videos uploaded on yesterday's date
    for all channels listed in the channels file.
    """
    channels_ids = load_channel_ids()
    if not channels_ids:
        return []

    try:
        youtube = build('youtube', 'v3', developerKey=API_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize YouTube API client: {e}")
        return []

    yesterday_date = get_date_bounds()
    logger.info(f"Target date for recap: {yesterday_date} ({TIMEZONE_STR})")

    # Step 1: Batch-query channel uploads playlist IDs (up to 50 channels per request)
    channel_to_playlist = {}
    batch_size = 50

    for i in range(0, len(channels_ids), batch_size):
        batch = channels_ids[i:i + batch_size]
        try:
            channel_response = youtube.channels().list(
                part='contentDetails',
                id=','.join(batch)
            ).execute()

            for item in channel_response.get('items', []):
                ch_id = item['id']
                uploads_id = item.get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads')
                if uploads_id:
                    channel_to_playlist[ch_id] = uploads_id
        except HttpError as e:
            logger.error(f"Error fetching channel metadata for batch {batch}: {e}")
            # Fallback for standard channel IDs starting with 'UC' -> 'UU'
            for ch_id in batch:
                if ch_id.startswith('UC'):
                    channel_to_playlist[ch_id] = 'UU' + ch_id[2:]

    candidate_videos = []
    unique_video_ids = set()

    # Step 2: Fetch playlist items for each channel's uploads playlist
    for channel_id, uploads_playlist_id in channel_to_playlist.items():
        next_page_token = None
        should_stop_channel = False

        while not should_stop_channel:
            try:
                playlist_response = youtube.playlistItems().list(
                    part='snippet',
                    playlistId=uploads_playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                ).execute()
            except HttpError as e:
                logger.warning(f"Error fetching playlist items for playlist {uploads_playlist_id}: {e}")
                break

            items = playlist_response.get('items', [])
            if not items:
                break

            page_has_yesterday = False
            all_items_older = True

            for item in items:
                snippet = item.get('snippet', {})
                published_at_str = snippet.get('publishedAt')
                if not published_at_str:
                    continue

                try:
                    published_at_dt = datetime.datetime.fromisoformat(
                        published_at_str.replace('Z', '+00:00')
                    ).date()
                except Exception:
                    continue

                video_id = snippet.get('resourceId', {}).get('videoId')
                if not video_id:
                    continue

                title = snippet.get('title', '')
                # Skip private and deleted videos
                if title in ('Private video', 'Deleted video'):
                    continue

                if published_at_dt == yesterday_date:
                    page_has_yesterday = True
                    all_items_older = False
                    if video_id not in unique_video_ids:
                        thumbnails = snippet.get('thumbnails', {})
                        thumb_url = (
                            thumbnails.get('medium', {}).get('url') or
                            thumbnails.get('high', {}).get('url') or
                            thumbnails.get('default', {}).get('url') or
                            thumbnails.get('standard', {}).get('url') or
                            f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
                        )

                        candidate_videos.append({
                            'videoId': video_id,
                            'title': title,
                            'description': snippet.get('description', ''),
                            'url': f"https://www.youtube.com/watch?v={video_id}",
                            'thumb': thumb_url,
                            'channel': snippet.get('channelTitle', ''),
                            'publishedAt': published_at_str
                        })
                        unique_video_ids.add(video_id)

                elif published_at_dt > yesterday_date:
                    all_items_older = False
                # If published_at_dt < yesterday_date, it leaves all_items_older as True for this item

            # Only stop paginating when all items on this page are strictly older than yesterday
            if all_items_older and not page_has_yesterday:
                should_stop_channel = True
                break

            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token:
                break

    logger.info(f"Discovered {len(candidate_videos)} candidate video(s) from {yesterday_date}")

    # Step 3: Filter YouTube Shorts and per-channel duplicate titles
    all_videos = []
    unique_channel_titles = set()

    for video in candidate_videos:
        if is_short_video(video['title'], video['description'], video['videoId']):
            logger.info(f"Filtered Short: {video['title']} ({video['videoId']})")
            continue

        normalized_title = normalize_title(video['title'])
        channel_title_key = (video['channel'].casefold(), normalized_title)
        if channel_title_key in unique_channel_titles:
            logger.info(f"Filtered duplicate title for channel {video['channel']}: {video['title']}")
            continue

        unique_channel_titles.add(channel_title_key)
        video_data = dict(video)
        video_data.pop('description', None)
        all_videos.append(video_data)

    logger.info(f"Final video count ready for digest: {len(all_videos)}")
    return all_videos


def send_email(videos):
    """
    Compiles and sends the HTML and plain-text email digest to RECIPIENT_EMAIL.
    """
    count = len(videos)
    date_display = get_date_bounds().strftime('%d.%m.%Y')

    msg = EmailMessage()
    msg['Subject'] = f"YouTube Recap - {date_display}"
    msg['From'] = EMAIL_USER
    msg['To'] = RECIPIENT_EMAIL

    videos.sort(key=lambda x: x['publishedAt'], reverse=True)

    # 1. Download thumbnails for inline embedding (bypasses email client proxy & ad-blocker blocks)
    cid_map = {}
    for i, v in enumerate(videos):
        cid = f"thumb_{i}"
        thumb_url = v.get('thumb', '').replace('http://', 'https://')
        if thumb_url:
            try:
                req = Request(thumb_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
                with urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        img_bytes = resp.read()
                        content_type = resp.headers.get_content_type()
                        subtype = 'jpeg' if ('jpeg' in content_type or 'jpg' in content_type) else 'png'
                        cid_map[v['url']] = (cid, img_bytes, subtype)
            except Exception as e:
                logger.debug(f"Could not download thumbnail for inline embedding ({thumb_url}): {e}")
                if hasattr(e, 'close'):
                    try:
                        e.close()
                    except Exception:
                        pass

    # 2. Plain text fallback with full details
    plain_lines = [
        f"YouTube Daily Recap - {date_display}",
        f"{count} video(s) found from {date_display}.\n"
    ]
    for v in videos:
        plain_lines.append(f"• {v['title']} ({v['channel']})")
        plain_lines.append(f"  {v['url']}\n")
    plain_content = "\n".join(plain_lines)
    msg.set_content(plain_content)

    # 3. Rich HTML email template
    html_content = f"""<!DOCTYPE html>
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
                                <strong>{count}</strong> video(s) found from {date_display}.
                            </p>
                            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
"""

    for v in videos:
        safe_title = html.escape(v['title'])
        safe_channel = html.escape(v['channel'])
        safe_url = html.escape(v['url'])
        # Use CID inline reference if downloaded, else fallback to safe external HTTPS URL
        if v['url'] in cid_map:
            img_src = f"cid:{cid_map[v['url']][0]}"
        else:
            img_src = html.escape(v['thumb'].replace('http://', 'https://'))

        html_content += f"""
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 25px; border-bottom: 1px solid #eee; padding-bottom: 20px;">
                                <tr>
                                    <td width="200" valign="top">
                                        <a href="{safe_url}"><img src="{img_src}" width="180" style="display: block; border-radius: 6px; border: 1px solid #ddd; max-width: 100%; height: auto;" alt="Thumbnail"></a>
                                    </td>
                                    <td valign="top" style="padding-left: 15px;">
                                        <div style="color: #28a745; font-size: 11px; font-weight: bold; text-transform: uppercase;">{safe_channel}</div>
                                        <div style="font-size: 16px; font-weight: 600; color: #343a40; margin: 5px 0;">{safe_title}</div>
                                        <a href="{safe_url}" style="display: inline-block; padding: 7px 14px; background-color: #28a745; color: #ffffff; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold;">Watch Video</a>
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

    msg.add_alternative(html_content, subtype='html')

    # Attach inline CID images to the HTML body
    html_part = msg.get_body(preferencelist=('html',))
    if html_part:
        for cid, img_bytes, subtype in cid_map.values():
            html_part.add_related(img_bytes, 'image', subtype, cid=f"<{cid}>")

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        logger.info(f"Recap email successfully sent to {RECIPIENT_EMAIL} with {count} video(s).")
    except Exception as e:
        logger.error(f"Failed to send email via {SMTP_HOST}:{SMTP_PORT} to {RECIPIENT_EMAIL}: {e}")
        raise


if __name__ == '__main__':
    if not validate_environment():
        sys.exit(1)

    videos_found = fetch_videos()

    if not videos_found and not SEND_EMPTY_EMAIL:
        logger.info(f"No videos found for yesterday. SEND_EMPTY_EMAIL is disabled; skipping email.")
    else:
        send_email(videos_found)