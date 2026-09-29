# YouTube Daily Recap

A Python script that automatically fetches videos uploaded yesterday from a list of YouTube channels and sends a beautiful HTML email digest.

<img src="YT_Project_Share.png">

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

**YouTube Daily Recap** is a Python automation tool that:
- Reads a list of YouTube channel IDs from `channels.txt`.
- Fetches all videos uploaded by those channels on the **previous day**.
- Compiles them into a clean, responsive HTML email.
- Sends the email via Gmail’s SMTP server (or any SMTP provider).

This is perfect for content curators, marketers, or anyone who wants a daily digest of new videos from their favorite creators.

---

## Features

✅ **Automated daily run** – schedule with cron or Task Scheduler.  
✅ **YouTube Data API v3** – fetches channel uploads efficiently.  
✅ **Duplicate prevention** – ignores repeated video IDs and duplicate titles.
✅ **Shorts filtering** – excludes videos marked with `#short` or `#shorts` in the title or description.
✅ **Rich HTML email** – includes thumbnails, titles, channel names, and “Watch Video” buttons.  
✅ **Plain text fallback** – for email clients that don’t support HTML.  
✅ **Environment variables** – secure storage for API keys and credentials.  
✅ **Error handling** – gracefully handles missing channels or API errors.

---

## Prerequisites

Before you begin, ensure you have the following:

- **Python 3.9+** installed on your system.
- A **Google Cloud Project** with the **YouTube Data API v3** enabled and an **API key**.
- A **Gmail account** (or any SMTP provider) with an **App Password** (Note: Google discontinued "Less secure apps" access; an App Password generated with 2-Step Verification is required for Gmail SMTP).

---

## Installation

1. **Clone this repository:**
   ```bash
   git clone https://github.com/JefferH-PC/yt_recap_bot.git
   cd yt_recap_bot
   ```
2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # On Linux/macOS:
   source .venv/bin/activate
   # On Windows:
   .venv\Scripts\activate
   ```
3. **Install required dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Update `channels.txt` with the channels you want.** (Supports `#` comments and empty lines).
5. **Set up environment variables:**
   Copy `.env.example` to `.env` and fill in your credentials.

---

## Configuration

### 1. YouTube API Key
- Go to [Google Cloud Console](https://console.cloud.google.com/).
- Create a new project (or select an existing one).
- Enable **YouTube Data API v3**.
- Create an **API key** under Credentials and optionally restrict it to the YouTube API.
- Copy the key.

### 2. Email Credentials
- For Gmail: Enable **2-Step Verification** on your Google Account, then generate an **App Password** (under Security > 2-Step Verification > App Passwords).
- Use this 16-character App Password as your `EMAIL_PASS`.

### 3. Environment Variables
Set the following environment variables in your shell, CI runner secrets, or a local `.env` file:

| Variable           | Description                                                                              | Default            |
|--------------------|------------------------------------------------------------------------------------------|--------------------|
| `YOUTUBE_API_KEY`  | Your YouTube Data API v3 key. *(Required)*                                               | —                  |
| `EMAIL_USER`       | The sender email address. *(Required)*                                                   | —                  |
| `EMAIL_PASS`       | The sender email password or App Password. *(Required)*                                  | —                  |
| `RECIPIENT_EMAIL`  | The recipient email address. *(Defaults to the same as `EMAIL_USER` if not specified)*   | `EMAIL_USER`       |
| `SMTP_HOST`        | SMTP host server. *(Optional)*                                                           | `smtp.gmail.com`   |
| `SMTP_PORT`        | SMTP SSL port. *(Optional)*                                                              | `465`              |
| `TIMEZONE`         | Timezone name for calculating "yesterday" (e.g. `UTC`, `America/Sao_Paulo`). *(Optional)* | `UTC`              |
| `SEND_EMPTY_EMAIL` | Whether to send an email when 0 videos were uploaded yesterday (`true`/`false`).         | `false`            |
| `CHANNELS_FILE`    | Custom path to channels list file. *(Optional)*                                          | `channels.txt`     |

---

## Customization

### Email Subject & Content
- To change the email subject, modify the `msg['Subject']` line in `send_email()`.
- The HTML email template is embedded in `send_email()`. You can customize styles, colors, or fonts.
- Dynamic values (titles, channel names, URLs) are securely HTML-escaped.
- A full plain-text fallback summary is included for notification previews and text-only email clients.

### Time Zone
The script defaults to `UTC`. To align with your local time, set the `TIMEZONE` environment variable (e.g. `TIMEZONE=America/New_York` or `TIMEZONE=America/Sao_Paulo`).

### Add More Channels Dynamically
Edit `channels.txt` at any time; the script reads it fresh on each run. You can organize your list with `#` comments and sections.

---

## Troubleshooting

| Issue | Possible Solution |
|-------|-------------------|
| **`Missing required environment variables`** | Ensure `YOUTUBE_API_KEY`, `EMAIL_USER`, and `EMAIL_PASS` are defined in your environment or `.env`. |
| **`channels.txt not found`** | Ensure `channels.txt` is located in the project directory or set `CHANNELS_FILE` to its absolute path. |
| **No videos found** | Verify that channels posted regular videos (non-Shorts) yesterday. The script checks `UTC` dates by default. |
| **`SMTPAuthenticationError`** | For Gmail, ensure you are using an **App Password** (not your standard Google account password). Verify 2-Step Verification is active. |
| **Rate limiting / Quota** | The script batches channel requests (50 per API call) to preserve your daily 10,000 unit quota. |

Run the script from the terminal to see structured logs and status updates:
```bash
python main.py
```

---

## License

**You are free to:**
- Use, copy, modify or merge. 
- Use it in commercial projects.
- Do so with **no royalty or fee**.

**However:**
- **No warranty** – the software is provided "as is", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and noninfringement.
- **No liability** – in no event shall the authors or copyright holders be liable for any claim, damages, or other liability arising from the software.

In short, you can do almost anything with this code, but you use it at your own risk.
