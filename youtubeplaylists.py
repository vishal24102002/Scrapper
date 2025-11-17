import requests
from decouple import config

# Your YouTube Data API key
API_KEY = config("API_KEY")

# Channel username
channel_username = config("CH_USER")

# Step 1: Get the channel ID using the channel username
def get_channel_id(api_key, username):
    url = f"https://www.googleapis.com/youtube/v3/channels?part=id&forUsername={username}&key={api_key}"
    response = requests.get(url)
    data = response.json()
    if "items" in data and len(data["items"]) > 0:
        return data["items"][0]["id"]
    else:
        raise Exception("Channel ID not found. Check the username or API key.")

# Step 2: Get all video IDs from the channel
def get_video_ids(api_key, channel_id):
    video_ids = []
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&maxResults=50&type=video&key={api_key}"
    while url:
        response = requests.get(url)
        data = response.json()
        video_ids.extend([item["id"]["videoId"] for item in data.get("items", [])])
        # Check if there's a next page
        url = f"https://www.googleapis.com/youtube/v3/search?pageToken={data.get('nextPageToken')}&part=snippet&channelId={channel_id}&maxResults=50&type=video&key={api_key}" if "nextPageToken" in data else None
    return video_ids

# Step 3: Get video titles
def get_video_titles(api_key, video_ids):
    titles = []
    for i in range(0, len(video_ids), 50):  # API allows a max of 50 video IDs per request
        ids = ",".join(video_ids[i:i+50])
        url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={ids}&key={api_key}"
        response = requests.get(url)
        data = response.json()
        titles.extend([item["snippet"]["title"] for item in data.get("items", [])])
    return titles

# Main script
try:
    channel_id = get_channel_id(API_KEY, channel_username)
    print(f"Channel ID: {channel_id}")
    
    video_ids = get_video_ids(API_KEY, channel_id)
    print(f"Found {len(video_ids)} videos.")
    
    video_titles = get_video_titles(API_KEY, video_ids)
    print("Video Titles:")
    for title in video_titles:
        print(title)
except Exception as e:
    print(f"Error: {e}")
