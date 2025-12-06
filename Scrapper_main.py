import sys,telethon,inspect,re,os,configparser,asyncio,logging,argparse
from decouple import config
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
import yt_dlp
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.errors import (
    FileReferenceExpiredError,
    FloodWaitError,
    SessionPasswordNeededError,
)
# CRITICAL: Import these for URL entities
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
from telethon.network.connection.tcpfull import ConnectionTcpFull
import io

# Ensure stdout uses UTF-8 encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
print(f"Scraper is using Python executable: {sys.executable}")
print(f"Telethon version in scraper: {telethon.__version__}")
print(f"Telethon module path: {telethon.__file__}")
print(inspect.signature(telethon.client.messages.MessageMethods.iter_messages))

# Determine the base directory
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

api_id = config("api_id")
api_hash = config("api_hash")

# Safe decode
def safe_decode(text):
    if not text:
        return ""
    try:
        return text.encode('utf-8', errors='replace').decode('utf-8', errors='ignore')
    except Exception as e:
        logging.error(f"Error decoding text: {e}")
        return str(text)

# === 1. EXTRACT CLEAN URLs (enhanced for t.me, removes junk, dedupes) ===
def extract_urls(message):
    urls = set()
    raw_text = message.message or message.text or ""

    # From Telegram entities (buttons, formatted links, t.me invites)
    if message.entities:
        for entity in message.entities:
            if isinstance(entity, (MessageEntityTextUrl, MessageEntityUrl)):
                try:
                    if isinstance(entity, MessageEntityTextUrl):
                        url = entity.url
                    else:
                        url = raw_text[entity.offset:entity.offset + entity.length]
                    if url:
                        clean = url.strip().split("?")[0].split("#")[0]
                        if clean:
                            urls.add(clean)
                except:
                    pass

    # Regex fallback (catches plain text URLs + t.me/shortlinks)
    if raw_text:
        matches = re.findall(r'(?i)(https?://[^\s<>"{}|\\^`\[\]]+|www\.[^\s<>"{}|\\^`\[\]]+|t\.me/[a-zA-Z0-9_]+(?:/[0-9]+)?)', raw_text)
        for m in matches:
            url = m.strip()
            if url.lower().startswith("www."):
                url = "https://" + url
            elif url.lower().startswith("t.me/"):
                url = "https://" + url.split("?")[0]
            url = re.sub(r'[.,;:!?)\]]+$', '', url)  # remove trailing punctuation
            if url:
                urls.add(url)

    return sorted(list(urls))

# === ADD THIS FUNCTION (you said you don't have it yet) ===
def get_link_context(message, url, max_chars=180):
    """
    Returns the surrounding text (context) around a URL.
    Shows what the person actually wrote before and after the link.
    """
    text = message.message or message.text or ""
    if not text:
        return "No text in message"

    # Try to find the exact URL
    pos = text.lower().find(url.lower())
    if pos == -1:
        # Try without https://
        short = url.replace("https://", "").replace("http://", "").split("/")[0]
        pos = text.lower().find(short.lower())

    if pos == -1:
        # Fallback: return trimmed full message
        trimmed = text.replace("\n", " ").strip()
        return trimmed[:max_chars] + ("..." if len(trimmed) > max_chars else "")

    # Extract context around the URL
    start = max(0, pos - 70)
    end = min(len(text), pos + len(url) + 110)

    context = text[start:end]
    if start > 0:
        context = "..." + context
    if end < len(text):
        context += "..."

    return context.replace("\n", " ").strip()

# Handle media
async def handle_media(client, message, media_folder, media_type):
    media_filename = f"{message.id}.{media_type}"
    media_path = os.path.join(media_folder, media_filename)
    if not os.path.exists(media_path):
        try:
            await client.download_media(message, file=media_path)
            file_size = os.path.getsize(media_path)
            print(f"BYTES_DOWNLOADED:{file_size}")
        except FileReferenceExpiredError:
            try:
                # 🔄 Refresh the message (gets new file reference)
                message = await client.get_messages(message.chat_id, ids=message.id)

                # Retry download
                await client.download_media(message, file=media_path)
                file_size = os.path.getsize(media_path)
                print(f"BYTES_DOWNLOADED:{file_size}")
                return media_path

            except Exception as e:
                logging.error(f"[Refetch Failed] message {message.id}: {e}")
                return None
        except Exception as e:
            logging.error(f"Download failed for message {message.id}: {e}")
            return None
    return media_path

def update_scraping_status(status, group_name, data_type):
    logging.info(f"Status update: {status} - Group: {group_name}, Data Type: {data_type}")

# === SAVE YOUTUBE TRANSCRIPT USING TITLE + FALLBACK WITH DESCRIPTION ===
def save_youtube_transcript_to_file(url, transcript_folder):
    """
    Saves transcript using video title.
    If transcript fails → saves error + FULL VIDEO DESCRIPTION.
    """
    os.makedirs(transcript_folder, exist_ok=True)

    # Extract video ID
    video_id = None
    match = re.search(r'(?:v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([^&\n?#]+)', url)
    if match:
        video_id = match.group(1)
    if not video_id:
        return "Not a YouTube link"

    # === GET VIDEO INFO (title + description) USING yt-dlp ===
    title = "Unknown_Title"
    description = "No description available"
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', info.get('alt_title', 'Unknown_Title'))
            description = info.get('description', 'No description available')
    except Exception as e:
        title = video_id
        description = f"Failed to fetch video info: {str(e)}"

    # Clean title for filename
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title.strip())
    safe_title = re.sub(r'_+', '_', safe_title)[:150]
    if not safe_title.strip():
        safe_title = video_id

    filename = f"{safe_title}.txt"
    filepath = os.path.join(transcript_folder, filename)

    # If file already exists → skip
    if os.path.exists(filepath):
        return filename
    
    # === TRY TO GET TRANSCRIPT ===
    transcript_success = False
    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        try:
            transcript = transcript_list.find_transcript(['en'])
        except:
            try:
                transcript = transcript_list.find_generated_transcript(['en'])
            except:
                transcript = next(iter(transcript_list._manually_created_transcripts.values()), None)
                if not transcript:
                    transcript = next(iter(transcript_list._generated_transcripts.values()), None)
                if not transcript:
                    raise NoTranscriptFound
        data = transcript.fetch()
        transcript_success = True

    except Exception as e:
        error_msg = f"Failed to get transcript: {str(e)}"
        transcript_success = False
    else:
        error_msg = ""

    # === WRITE TO FILE (transcript OR error + description) ===
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"URL: {url}\n")
        f.write(f"Video ID: {video_id}\n")
        f.write(f"Title: {title}\n")
        f.write(f"Saved: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S IST')}\n\n")

        if transcript_success:
            f.write("TRANSCRIPT:\n")
            for entry in data:
                text = entry.text.replace('\n', ' ').strip()
                f.write(f"{text}\n")
        else:
            f.write(f"{error_msg}\n\n")
            f.write("FULL VIDEO DESCRIPTION:\n")
            f.write("-" * 50 + "\n")
            f.write(description.strip() if description else "No description")
            f.write("\n" + "-" * 50 + "\n")

    return filename

# Main processing function
async def process_chat(client, chat, scrape_date_folder, datatype_filter, scrape_date):
    folders = {
        "Images": os.path.join(scrape_date_folder, chat, "Images"),
        "Videos": os.path.join(scrape_date_folder, chat, "Videos"),
        "Audios": os.path.join(scrape_date_folder, chat, "Audios"),
        "Text": os.path.join(scrape_date_folder, chat, "Text"),
        "Links": os.path.join(scrape_date_folder, chat, "Links"),
    }

    selected_folders = {k: v for k, v in folders.items() if k in datatype_filter}
    for folder in selected_folders.values():
        os.makedirs(folder, exist_ok=True)

    logging.info(f"Folders created for {chat}: {', '.join(selected_folders.keys())}")

    text_file = None
    links_file = None
    text_file_path = selected_folders.get("Text")
    links_file_path = selected_folders.get("Links")

    if text_file_path:
        text_file = open(os.path.join(text_file_path, "messages.txt"), "a", encoding="utf-8")
    if links_file_path:
        links_file = open(os.path.join(links_file_path, "links.txt"), "a", encoding="utf-8")

    link_count = 0  # NOW DEFINED!

    try:
        entity = await client.get_entity(chat)
        logging.info(f"Connected to group: {entity.title}")

        start_datetime = datetime.combine(scrape_date, datetime.min.time(), tzinfo=timezone.utc)
        end_datetime = datetime.combine(scrape_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

        async for message in client.iter_messages(
            entity,
            offset_date=end_datetime,
            reverse=False,
        ):
            if message.date < start_datetime:
                break

            message_text = safe_decode(message.message or message.text or "")
            sender_id = message.sender_id or "Unknown"

            processed = False

            # LINKS + CONTEXT + TRANSCRIPT SAVED BY TITLE
            urls = extract_urls(message)
            if urls and "Links" in datatype_filter and links_file:
                transcript_folder = os.path.join(selected_folders["Links"], "Transcripts")
                
                for url in urls:
                    context = get_link_context(message, url)
                    transcript_note = ""

                    if "youtube.com" in url or "youtu.be" in url:
                        print(f"Fetching transcript for: {url}")
                        filename = save_youtube_transcript_to_file(url, transcript_folder)
                        transcript_note = f" → Transcript saved: Transcripts/{filename}"

                    entry = f"[{message.date.strftime('%Y-%m-%d %H:%M:%S')}] Sender ID: {sender_id} | URL: {url}\n"
                    entry += f"Context: {context}\n"
                    if transcript_note:
                        entry += transcript_note + "\n"
                    entry += "\n" + "-"*80 + "\n\n"
                    
                    links_file.write(entry)
                    links_file.flush()
                
                link_count += len(urls)
                processed = True

            # === MEDIA & TEXT HANDLING ===
            try:
                if message.photo and "Images" in datatype_filter:
                    await handle_media(client, message, selected_folders["Images"], "jpg")
                    processed = True

                elif message.video and "Videos" in datatype_filter:
                    await handle_media(client, message, selected_folders["Videos"], "mp4")
                    processed = True

                elif (message.audio or message.voice or message.video_note) and "Audios" in datatype_filter:
                    ext = "ogg" if message.voice else "mp3" if message.audio else "mp4"
                    await handle_media(client, message, selected_folders["Audios"], ext)
                    processed = True

                elif "Text" in datatype_filter and message_text.strip() and message.message:
                    if text_file:
                        entry = f"[{message.date.strftime('%Y-%m-%d %H:%M:%S')}] Sender ID: {sender_id}\n{message_text}\n\n"
                        text_file.write(entry)
                        text_file.flush()
                    processed = True

                if not processed:
                    logging.debug(f"Skipped message {message.id} (no matching type)")

            except FileReferenceExpiredError:
                logging.info(f"File reference expired: {message.id}")
            except Exception as e:
                logging.exception(f"Error processing message {message.id}: {e}")

        print(f"Finished {chat} -> {link_count} links saved!")
        logging.info(f"Scraping completed for {chat} on {scrape_date.strftime('%Y-%m-%d')}.")

    except FloodWaitError as e:
        logging.warning(f"FloodWait: sleeping {e.seconds}s")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logging.exception(f"Failed to process chat {chat}: {e}")
    finally:
        if text_file:
            text_file.close()
        if links_file:
            links_file.close()

# Main scraper
async def start_scraping(selected_groups, selected_datatypes, scrape_dates, target_folder, api_id, api_hash):
    async with TelegramClient(
        'session_name', 
        api_id, 
        api_hash,
        connection=ConnectionTcpFull,
        request_retries=10,
        connection_retries=10,
        retry_delay=2,
        proxy=None,
        system_version="Windows",
        timeout=20) as client:
        try:
            await client.start()
        except SessionPasswordNeededError:
            password = input("2FA Password: ")
            await client.start(password=password)

        for scrape_date in scrape_dates:
            date_folder = os.path.join(target_folder, scrape_date.strftime("%Y-%m-%d"))
            os.makedirs(date_folder, exist_ok=True)

            for chat in selected_groups:
                print(f"Scraping {chat} | {scrape_date.strftime('%Y-%m-%d')}")
                await process_chat(client, chat, date_folder, selected_datatypes, scrape_date)

# CLI
if __name__ == '__main__':
    print("===== Telegram Scraper + Links Started =====")

    parser = argparse.ArgumentParser(description="Telegram Scraper with Link Extraction")
    parser.add_argument("--groups", type=str, required=True, help="group1,group2")
    parser.add_argument("--datatypes", type=str, required=True, help="Images,Videos,Audios,Text,Links")
    parser.add_argument("--dates", type=str, required=True, help="2025-11-09,2025-11-10")
    parser.add_argument("--target_folder", type=str, default=os.path.join(BASE_DIR, "Database"))

    args = parser.parse_args()

    selected_groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    selected_datatypes = [d.strip() for d in args.datatypes.split(",") if d.strip()]

    dates_list = []
    for d in args.dates.split(","):
        try:
            date_obj = datetime.strptime(d.strip(), "%Y-%m-%d").date()
            if date_obj > datetime.utcnow().date():
                logging.warning(f"Skipping future date: {date_obj}")
                continue
            dates_list.append(date_obj)
        except ValueError:
            logging.error(f"Invalid date: {d}")

    if not dates_list:
        logging.error("No valid dates!")
        sys.exit(1)

    asyncio.run(start_scraping(selected_groups, selected_datatypes, dates_list, args.target_folder, api_id, api_hash))