"""Plain-language errors (viewer feedback, 24 Nov: "failed link fetching", "full storage", "missing FFmpeg").

yt-dlp, FFmpeg and Python raise long technical messages. This turns the common ones into one short sentence that says what happened
and the first thing to try, in simple English with a short Hinglish line. Anything it does not know is passed through unchanged (the
Report a problem button still sends the original text).
"""
import re

RULES = [
    (r'no space left|errno 28|not enough space|disk full|there is not enough space',
     'Your disk is full. Open Storage in the left sidebar and press the clean-up buttons, or delete old clips.',
     'Disk bhar gayi hai. Left mein Storage kholo aur clean-up dabao.'),
    (r'private video|this video is private',
     'This video is private, so nobody can download it. Ask the owner to make it public or unlisted, or upload the MP4 file.',
     'Video private hai. Public/unlisted karwao ya MP4 file upload karo.'),
    (r'members[- ]only|join this channel|available to this channel.s members',
     'This video is for channel members only. Upload the MP4 file instead.',
     'Ye sirf members ke liye hai. MP4 upload karo.'),
    (r'confirm your age|age[- ]restricted|inappropriate for some users',
     'This video is age-restricted. Settings is not enough: sign in to YouTube in your browser, choose that browser under "YouTube blocked the download?" in Advanced, then try again, or upload the MP4.',
     'Age-restricted video hai. Browser mein YouTube login karke Advanced mein wo browser chuno, ya MP4 upload karo.'),
    (r'not available in your country|not made this video available in your country|blocked it in your country|geo.?restrict',
     'This video is blocked in your country. Turn on GitHub proxies + auto-rotation under "YouTube blocked or country-restricted?" below (pick the video\'s country, e.g. India), or upload the MP4 file instead.',
     'Ye video aapke desh mein blocked hai. Neeche GitHub proxies + auto-rotation (India chuno) ON karo ya MP4 upload karo.'),
    (r'video unavailable|video is unavailable|this video is not available|has been removed|no longer available|does not exist|http error 404',
     'This video is not available any more (removed, deleted or wrong link). Check the link by opening it in your browser.',
     'Video ab available nahi hai ya link galat hai. Browser mein link kholke check karo.'),
    (r'unsupported url|no video formats found|is not a valid url|unable to extract',
     'This link is not a video NeonClipping can read. Paste the link of one video (YouTube, Twitch or Kick), not a channel, search or playlist page.',
     'Ye link video ka nahi hai. Ek video ka seedha link paste karo.'),
    (r'getaddrinfo|name resolution|network is unreachable|connection (?:reset|refused|aborted)|timed out|timeout|remote end closed|ssl|connection error|failed to connect',
     'No internet, or a very slow connection, so the video could not be fetched. Check your internet and press Make clips again. On mobile data or a VPN YouTube may also block downloads: try Wi-Fi.',
     'Internet nahi hai ya bahut slow hai. Internet check karke dobara Make clips dabao. Wi-Fi try karo.'),
    (r'ffmpeg.{0,40}not found|ffprobe.{0,40}not found|no such file or directory.{0,30}ff(?:mpeg|probe)|winerror 2.{0,80}ff(?:mpeg|probe)',
     'FFmpeg (the video cutter) is missing on this PC. Click the red FFmpeg chip at the top of the page to install it, or run NeonClipping-Setup.bat again.',
     'FFmpeg nahi mila. Upar laal FFmpeg wale chip par click karo ya Setup.bat dobara chalao.'),
    (r'live (?:event|stream) will begin|premieres in|this live event|is_upcoming',
     'This is a live stream that has not ended. Use Live clipping for it, or wait until it finishes and use Make clips on the finished video.',
     'Ye live stream abhi chal rahi hai. Khatam hone ke baad Make clips use karo.'),
    (r'copyright|blocked it on copyright grounds',
     'YouTube blocks downloading this video (a rights holder restriction). Upload the MP4 file you own instead.',
     'Ye video download block hai. Apni MP4 file upload karo.'),
]
_COMPILED = [(re.compile(p, re.I), en, hi) for p, en, hi in RULES]


def explain(error):
    """(plain text, original text) for an error or message. Unknown errors keep their own text; the bot-check message from ytdl.py is already plain."""
    original = str(error or '').strip()
    low = original.lower()
    if 'youtube blocked this download' in low:      # ytdl.GUIDE: already readable and specific
        return original, original
    for rx, en, hi in _COMPILED:
        if rx.search(original):
            return f'{en}\n{hi}', original
    return original, original
