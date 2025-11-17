import datetime,requests,re,os
from decouple import config
from collections import Counter

# Function to fetch Google Trends for worldwide trends
def fetch_google_trends(date):
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq()
        print(f"Fetching Google Trends (Worldwide) for {date}...")
        pytrends.build_payload([], timeframe=f'{date} 1-d')  # Fetch trends for the specific date
        trending = pytrends.trending_searches(pn='worldwide')
        # Extract hashtags from the trending searches
        hashtags = [re.findall(r'#\w+', topic) for topic in trending[0].tolist()]
        return [hashtag for sublist in hashtags for hashtag in sublist]  # Flatten the list
    except Exception as e:
        print(f"Error fetching Google trends: {e}")
        return []

# Function to fetch YouTube Trends globally
def fetch_youtube_trends(api_key, date):
    try:
        print(f"Fetching YouTube Trends (Global) for {date}...")
        url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&chart=mostPopular&regionCode=global&key={api_key}"
        response = requests.get(url).json()
        print(f"YouTube API Response: {response}")  # Log the response for debugging
        if 'items' in response:
            # Extract hashtags from the video descriptions or titles
            hashtags = []
            for item in response['items']:
                hashtags.extend(re.findall(r'#\w+', item['snippet']['title']))
                hashtags.extend(re.findall(r'#\w+', item['snippet']['description']))
            return hashtags
        else:
            print("No YouTube trends found.")
            return []
    except Exception as e:
        print(f"Error fetching YouTube trends: {e}")
        return []

# Function to fetch Twitter Trends globally (using a global location ID for major cities)
def fetch_twitter_trends(bearer_token, date):
    try:
        print(f"Fetching Twitter Trends (Global) for {date}...")
        location_id = 1  # Worldwide location ID (or you can try major cities as an approximation)
        url = f"https://api.twitter.com/1.1/trends/place.json?id={location_id}"
        headers = {"Authorization": f"Bearer {bearer_token}"}
        response = requests.get(url, headers=headers).json()
        print(f"Twitter API Response: {response}")  # Log the response for debugging
        if response and 'trends' in response[0]:
            # Extract hashtags from the Twitter trends
            hashtags = [re.findall(r'#\w+', trend['name']) for trend in response[0]['trends']]
            return [hashtag for sublist in hashtags for hashtag in sublist]  # Flatten the list
        else:
            print("No Twitter trends found.")
            return []
    except Exception as e:
        print(f"Error fetching Twitter trends: {e}")
        return []

# Function to fetch Instagram Trends (Placeholder)
def fetch_instagram_trends(date):
    print(f"Fetching Instagram Trends (Placeholder) for {date}...")
    return ["#ExampleTrend1", "#ExampleTrend2", "#TrendingExample"]  # Placeholder trends

# Function to get global trending topics (hashtags)
def get_global_trending_hashtags(youtube_api_key, twitter_bearer_token, date):
    try:
        google_trends = fetch_google_trends(date)
        youtube_trends = fetch_youtube_trends(youtube_api_key, date)
        twitter_trends = fetch_twitter_trends(twitter_bearer_token, date)
        instagram_trends = fetch_instagram_trends(date)

        # Combine all hashtags from different sources
        all_hashtags = google_trends + youtube_trends + twitter_trends + instagram_trends

        # Filter and only keep the hashtags that appear more than once (significant hashtags)
        common_hashtags = Counter(all_hashtags).most_common()

        # Get top 10 hashtags
        top_10_hashtags = [hashtag for hashtag, count in common_hashtags[:10]]

        return top_10_hashtags
    except Exception as e:
        print(f"Error fetching global hashtags: {e}")
        return []

# Main function to execute
if __name__ == "__main__":
    # Ask for a date input
    date_input = input("Enter the date (YYYY-MM-DD): ")

    # Validate the date format
    try:
        datetime.datetime.strptime(date_input, '%Y-%m-%d')  # Check if the date is in the correct format
    except ValueError:
        print("Invalid date format. Please use YYYY-MM-DD.")
        exit()

    youtube_api_key = config("youtube_api_key")
    twitter_bearer_token = config("twitter_bearer_token")

    if not youtube_api_key or not twitter_bearer_token:
        print("Please set the YouTube API Key and Twitter Bearer Token as environment variables.")
    else:
        top_10_hashtags = get_global_trending_hashtags(youtube_api_key, twitter_bearer_token, date_input)

        if top_10_hashtags:
            print("\nTop 10 Trending Hashtags Globally:")
            for i, hashtag in enumerate(top_10_hashtags, 1):
                print(f"{i}. {hashtag}")
        else:
            print("No significant global hashtags found.")