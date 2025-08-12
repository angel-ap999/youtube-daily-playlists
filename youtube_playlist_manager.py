import os
import datetime
import json
import time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import re
import pytz

# Scopes needed for YouTube API and Google Sheets API
SCOPES = [
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'  # Added for folder access
]

# Set your timezone here
TIMEZONE = pytz.timezone('Asia/Hong_Kong')  # Hong Kong timezone (UTC+8)

# Google Drive folder configuration
FOLDER_NAME = "Podkits"  # Name of your Google Drive folder

class UltraEfficientYouTubeManager:
    def __init__(self):
        self.youtube = None
        self.sheets = None
        self.drive = None  # Added for Google Drive
        self.quota_used = 0
        self.authenticate()
    
    def log_quota(self, operation, cost):
        """Track quota usage with exact costs"""
        self.quota_used += cost
        print(f"🔢 Quota: {self.quota_used}/10,000 (+{cost} for {operation})")
    
    def authenticate(self):
        """Authenticate with YouTube API using OAuth2 with improved error handling"""
        creds = None
        
        # Check environment
        if os.environ.get('GITHUB_ACTIONS'):
            print("🤖 GitHub Actions detected")
        else:
            print("💻 Local environment detected")
        
        # Check if credentials.json exists
        if not os.path.exists('credentials.json'):
            print("❌ ERROR: credentials.json not found!")
            if os.environ.get('GITHUB_ACTIONS'):
                print("📋 GitHub Actions Setup:")
                print("1. Add your credentials.json content as GitHub secret 'GOOGLE_CREDENTIALS_JSON'")
                print("2. Update workflow to create credentials.json:")
                print("   - name: Create credentials file")
                print("     run: echo '${{ secrets.GOOGLE_CREDENTIALS_JSON }}' > credentials.json")
            else:
                print("📋 Local Setup Instructions:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a new project or select existing one")
                print("3. Enable YouTube Data API v3, Google Sheets API, and Google Drive API")
                print("4. Create OAuth 2.0 credentials")
                print("5. Download and save as 'credentials.json'")
            raise Exception("Missing credentials.json file")
        
        # Check if it's a service account or OAuth credentials
        try:
            with open('credentials.json', 'r') as f:
                cred_data = json.load(f)
            
            if 'type' in cred_data and cred_data['type'] == 'service_account':
                print("🔑 Using service account authentication")
                from google.oauth2 import service_account
                creds = service_account.Credentials.from_service_account_file(
                    'credentials.json', scopes=SCOPES)
                print("✅ Service account authentication successful")
            else:
                print("🔑 Using OAuth authentication")
                # Load existing token if available
                if os.path.exists('token.json'):
                    try:
                        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
                        print("🔑 Loaded existing token")
                    except Exception as e:
                        print(f"⚠️  Token file corrupted: {e}")
                        print("🔄 Removing corrupted token, will re-authenticate...")
                        os.remove('token.json')
                        creds = None
                
                # Handle token refresh or new authentication
                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        try:
                            print("🔄 Refreshing expired token...")
                            creds.refresh(Request())
                            print("✅ Token refreshed successfully")
                        except Exception as e:
                            print(f"❌ Token refresh failed: {e}")
                            print("🔄 Starting fresh authentication...")
                            # Remove the bad token and start fresh
                            if os.path.exists('token.json'):
                                os.remove('token.json')
                            creds = None
                    
                    # If refresh failed or no valid creds, start OAuth flow
                    if not creds:
                        if os.environ.get('GITHUB_ACTIONS'):
                            print("❌ OAuth flow not possible in GitHub Actions")
                            print("💡 Use a service account for GitHub Actions:")
                            print("1. Create service account at https://console.cloud.google.com/")
                            print("2. Download service account JSON")
                            print("3. Replace GitHub secret content with service account JSON")
                            raise Exception("OAuth requires browser - use service account for GitHub Actions")
                        
                        try:
                            print("🚀 Starting OAuth authentication flow...")
                            flow = InstalledAppFlow.from_client_secrets_file(
                                'credentials.json', SCOPES)
                            creds = flow.run_local_server(port=0)
                            print("✅ OAuth authentication completed")
                        except Exception as e:
                            print(f"❌ OAuth flow failed: {e}")
                            raise Exception(f"Authentication failed: {e}")
                    
                    # Save the new/refreshed credentials
                    if not os.environ.get('GITHUB_ACTIONS'):  # Don't save in GitHub Actions
                        try:
                            with open('token.json', 'w') as token:
                                token.write(creds.to_json())
                            print("💾 Saved new authentication token")
                        except Exception as e:
                            print(f"⚠️  Warning: Could not save token: {e}")
        
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            raise
        
        # Build the API clients
        try:
            self.youtube = build('youtube', 'v3', credentials=creds)
            print("✅ Successfully authenticated with YouTube API")
            
            # Test the connection
            test_request = self.youtube.channels().list(part='snippet', mine=True)
            test_response = test_request.execute()
            user_channel = test_response.get('items', [{}])[0].get('snippet', {}).get('title', 'Unknown')
            print(f"👤 Authenticated as: {user_channel}")
            
        except Exception as e:
            print(f"❌ Failed to build YouTube API client: {e}")
            raise Exception(f"API client creation failed: {e}")
        
        try:
            self.sheets = build('sheets', 'v4', credentials=creds)
            print("✅ Successfully authenticated with Google Sheets API")
            
        except Exception as e:
            print(f"⚠️  Warning: Google Sheets API failed: {e}")
            print("📝 Video logging to spreadsheet will be skipped")
            self.sheets = None
        
        try:
            self.drive = build('drive', 'v3', credentials=creds)
            print("✅ Successfully authenticated with Google Drive API")
            
        except Exception as e:
            print(f"⚠️  Warning: Google Drive API failed: {e}")
            print("📝 Folder organization will be skipped")
            self.drive = None
    
    def find_folder_id(self, folder_name):
        """Find the folder ID by name"""
        if not self.drive:
            return None
            
        try:
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
            results = self.drive.files().list(q=query, fields="files(id, name)").execute()
            folders = results.get('files', [])
            
            if folders:
                folder_id = folders[0]['id']
                print(f"📁 Found '{folder_name}' folder: {folder_id}")
                return folder_id
            else:
                print(f"⚠️  Folder '{folder_name}' not found - sheet will be created in root")
                return None
                
        except Exception as e:
            print(f"❌ Error finding folder: {e}")
            return None
    
    def create_daily_spreadsheet(self):
        """Create a new Google Sheet with today's date in the Podkits folder"""
        if not self.sheets:
            return None
        
        # Get today's date in Hong Kong timezone
        hk_now = datetime.datetime.now(TIMEZONE)
        date_str = hk_now.strftime('%Y-%m-%d')
        spreadsheet_name = f"New video links - {date_str}"
        
        # Find the Podkits folder
        folder_id = self.find_folder_id(FOLDER_NAME)
        
        try:
            # Create the spreadsheet
            spreadsheet = {
                'properties': {
                    'title': spreadsheet_name
                },
                'sheets': [{
                    'properties': {
                        'title': 'Video Links',
                        'gridProperties': {
                            'rowCount': 500,
                            'columnCount': 1
                        }
                    }
                }]
            }
            
            spreadsheet = self.sheets.spreadsheets().create(
                body=spreadsheet,
                fields='spreadsheetId'
            ).execute()
            
            spreadsheet_id = spreadsheet.get('spreadsheetId')
            print(f"📊 Created new Google Sheet: '{spreadsheet_name}'")
            
            # Move to Podkits folder if found
            if folder_id and self.drive:
                try:
                    # Move the file to the folder
                    self.drive.files().update(
                        fileId=spreadsheet_id,
                        addParents=folder_id,
                        removeParents='root',
                        fields='id, parents'
                    ).execute()
                    print(f"📁 Moved sheet to '{FOLDER_NAME}' folder")
                except Exception as e:
                    print(f"⚠️  Could not move to folder: {e}")
            
            print(f"🔗 Sheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
            return spreadsheet_id
            
        except Exception as e:
            print(f"❌ Error creating Google Sheet: {e}")
            return None
    
    def add_video_links_to_sheet(self, spreadsheet_id, videos):
        """Add video URLs to Google Sheet with header"""
        if not self.sheets:
            return False
            
        try:
            # Prepare header
            header_row = [['Video Links']]
            video_links = []
            
            # Add video links (if any)
            for video in videos:
                video_url = f"https://www.youtube.com/watch?v={video['id']}"
                video_links.append([video_url])
            
            # Combine header and links (header always included, even if no videos)
            all_data = header_row + video_links
            
            # Write header + video links starting from A1
            range_name = 'Video Links!A1'
            
            body = {
                'values': all_data
            }
            
            result = self.sheets.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            if len(videos) > 0:
                print(f"📊 Added {len(videos)} video links to Google Sheet")
            else:
                print(f"📊 Created Google Sheet with header (no videos found)")
            
            return True
            
        except Exception as e:
            print(f"❌ Error updating Google Sheet: {e}")
            return False
    
    def get_yesterday_dates(self):
        """
        Get the date range for yesterday (00:00 to 23:59:59) in Hong Kong timezone
        Returns timezone-aware datetime objects in UTC for API compatibility
        """
        # Get current time in Hong Kong timezone
        hk_now = datetime.datetime.now(TIMEZONE)
        
        # Yesterday in Hong Kong timezone (00:00:00)
        hk_yesterday_start = hk_now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=1)
        
        # Yesterday's end in Hong Kong timezone (23:59:59)
        hk_yesterday_end = hk_yesterday_start + datetime.timedelta(hours=23, minutes=59, seconds=59)
        
        # Convert to UTC for API compatibility (YouTube API uses UTC)
        yesterday_start_utc = hk_yesterday_start.astimezone(pytz.UTC)
        yesterday_end_utc = hk_yesterday_end.astimezone(pytz.UTC)
        
        return yesterday_start_utc, yesterday_end_utc
    
    def find_playlist_by_name(self, playlist_name):
        """Find a playlist by exact name match"""
        try:
            request = self.youtube.playlists().list(
                part='snippet',
                mine=True,
                maxResults=50
            )
            response = request.execute()
            self.log_quota("playlists.list", 1)
            
            for playlist in response['items']:
                if playlist['snippet']['title'] == playlist_name:
                    return playlist['id']
            
            return None
            
        except Exception as e:
            print(f"❌ Error searching for playlist: {e}")
            return None
    
    def get_playlist_videos(self, playlist_id):
        """Get all videos currently in the playlist"""
        try:
            all_videos = []
            next_page_token = None
            
            while True:
                request = self.youtube.playlistItems().list(
                    part='snippet',
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                response = request.execute()
                self.log_quota("playlistItems.list", 1)
                
                for item in response['items']:
                    all_videos.append({
                        'playlist_item_id': item['id'],
                        'video_id': item['snippet']['resourceId']['videoId'],
                        'title': item['snippet']['title'],
                        'published': item['snippet']['publishedAt']
                    })
                
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
            
            return all_videos
            
        except Exception as e:
            print(f"❌ Error getting playlist videos: {e}")
            return []
    
    def remove_old_videos_from_playlist(self, playlist_id, yesterday_start):
        """Remove videos older than yesterday from the playlist"""
        print(f"🗑️  Checking for old videos to remove from playlist...")
        
        # Get current videos in playlist
        current_videos = self.get_playlist_videos(playlist_id)
        
        if not current_videos:
            print(f"ℹ️  Playlist is empty, nothing to remove")
            return 0
        
        print(f"📋 Found {len(current_videos)} videos currently in playlist")
        
        # Get actual video publish dates (not playlist addition dates)
        video_ids = [v['video_id'] for v in current_videos]
        actual_publish_dates = {}
        
        # Batch get video details to get real publish dates
        video_batches = [video_ids[i:i+50] for i in range(0, len(video_ids), 50)]
        
        for batch in video_batches:
            try:
                request = self.youtube.videos().list(
                    part='snippet',
                    id=','.join(batch)
                )
                response = request.execute()
                self.log_quota("videos.list (batch)", 1)
                
                for video in response['items']:
                    video_id = video['id']
                    published_at = video['snippet']['publishedAt']
                    actual_publish_dates[video_id] = published_at
                    
            except Exception as e:
                print(f"❌ Error getting video publish dates: {e}")
                continue
        
        # Check which videos are older than yesterday (using ACTUAL publish dates)
        videos_to_remove = []
        
        for video in current_videos:
            try:
                video_id = video['video_id']
                if video_id in actual_publish_dates:
                    published_at = actual_publish_dates[video_id]
                    published_date = datetime.datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    
                    # If video was originally published before yesterday, mark for removal
                    if published_date < yesterday_start:
                        videos_to_remove.append(video)
                        
                        # Convert to HK time for display
                        hk_published = published_date.astimezone(TIMEZONE)
                        hk_yesterday = yesterday_start.astimezone(TIMEZONE)
                        print(f"   🗑️  Will remove: {video['title']} (published {hk_published.strftime('%Y-%m-%d')} < yesterday {hk_yesterday.strftime('%Y-%m-%d')})")
                    
            except Exception as e:
                print(f"⚠️  Date parsing error for {video['title']}: {e}")
                continue
        
        # Remove old videos
        removed_count = 0
        if videos_to_remove:
            print(f"🗑️  Removing {len(videos_to_remove)} old videos from playlist...")
            
            for video in videos_to_remove:
                # Check quota before each removal
                if self.quota_used + 50 > 10000:
                    print(f"⚠️  Quota limit approaching, stopped removing old videos")
                    break
                
                try:
                    request = self.youtube.playlistItems().delete(
                        id=video['playlist_item_id']
                    )
                    request.execute()
                    self.log_quota("playlistItems.delete", 50)
                    
                    removed_count += 1
                    print(f"   ✅ [{removed_count}] Removed: {video['title']}")
                    
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"   ❌ Failed to remove: {video['title']} - {str(e)}")
        else:
            print(f"ℹ️  No old videos to remove - all current videos were originally published yesterday or later")
        
        return removed_count
    
    def get_subscriptions_batch(self, batch_size=50):
        """Ultra-efficient: Get all subscriptions in minimum API calls"""
        print("📋 Fetching ALL subscribed channels in batches...")
        
        all_channels = []
        next_page_token = None
        
        while True:
            request = self.youtube.subscriptions().list(
                part='snippet',
                mine=True,
                maxResults=batch_size,
                pageToken=next_page_token
            )
            response = request.execute()
            self.log_quota("subscriptions.list", 1)
            
            for item in response['items']:
                all_channels.append({
                    'id': item['snippet']['resourceId']['channelId'],
                    'title': item['snippet']['title']
                })
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
            
            # Stop if approaching quota limit
            if self.quota_used > 9000:
                print(f"⚠️  Stopping subscription fetch to preserve quota")
                break
        
        print(f"📺 Retrieved {len(all_channels)} channels using only {len(all_channels)//50 + 1} API calls")
        return all_channels
    
    def batch_get_channel_uploads(self, channel_ids):
        """ULTRA EFFICIENT: Get upload playlists for up to 50 channels in ONE call"""
        if not channel_ids:
            return {}
        
        # YouTube API allows up to 50 IDs per request
        channel_batches = [channel_ids[i:i+50] for i in range(0, len(channel_ids), 50)]
        uploads_map = {}
        
        for batch in channel_batches:
            try:
                request = self.youtube.channels().list(
                    part='contentDetails,snippet',
                    id=','.join(batch)
                )
                response = request.execute()
                self.log_quota("channels.list (batch)", 1)
                
                for channel in response['items']:
                    channel_id = channel['id']
                    uploads_playlist = channel['contentDetails']['relatedPlaylists']['uploads']
                    channel_title = channel['snippet']['title']
                    uploads_map[channel_id] = {
                        'uploads_playlist': uploads_playlist,
                        'title': channel_title
                    }
                    
            except Exception as e:
                print(f"❌ Error in batch channel request: {str(e)}")
                continue
        
        print(f"🚀 Got upload playlists for {len(uploads_map)} channels using only {len(channel_batches)} API calls!")
        return uploads_map
    
    def batch_get_recent_videos_daily(self, uploads_data):
        """
        ULTRA-MEGA EFFICIENT: Get videos from yesterday only
        Targets the previous calendar date (00:00 to 23:59:59)
        """
        # Get yesterday's date range
        yesterday_start, yesterday_end = self.get_yesterday_dates()
        
        all_video_ids = []
        video_to_channel_map = {}
        
        print(f"🔍 DAILY SCAN: Searching {len(uploads_data)} upload playlists...")
        
        # Display dates in Hong Kong timezone for user clarity
        hk_yesterday_start = yesterday_start.astimezone(TIMEZONE)
        hk_yesterday_end = yesterday_end.astimezone(TIMEZONE)
        
        print(f"📅 Yesterday (HK time): {hk_yesterday_start.strftime('%A, %B %d, %Y')}")
        print(f"📅 Time range (HK): {hk_yesterday_start.strftime('%Y-%m-%d %H:%M:%S')} to {hk_yesterday_end.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 Time range (UTC): {yesterday_start.strftime('%Y-%m-%d %H:%M:%S')} to {yesterday_end.strftime('%Y-%m-%d %H:%M:%S')}")
        
        processed_count = 0
        videos_yesterday = 0
        
        for channel_id, data in uploads_data.items():
            uploads_playlist = data['uploads_playlist']
            channel_title = data['title']
            
            # Check quota before each request
            if self.quota_used > 9500:
                print(f"⚠️  Quota limit approaching, stopping early")
                break
            
            try:
                request = self.youtube.playlistItems().list(
                    part='snippet',
                    playlistId=uploads_playlist,
                    maxResults=50
                )
                response = request.execute()
                self.log_quota("playlistItems.list", 1)
                
                channel_video_count = 0
                for item in response['items']:
                    try:
                        published_at = item['snippet']['publishedAt']
                        
                        # Parse YouTube's ISO format to timezone-aware datetime
                        published_date = datetime.datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                        
                        # Check if video was published yesterday
                        if yesterday_start <= published_date <= yesterday_end:
                            video_id = item['snippet']['resourceId']['videoId']
                            all_video_ids.append(video_id)
                            video_to_channel_map[video_id] = channel_title
                            channel_video_count += 1
                            videos_yesterday += 1
                        elif published_date < yesterday_start:
                            # Videos are sorted by date (newest first), so we can stop early
                            # if we hit videos older than yesterday
                            break
                    
                    except Exception as e:
                        print(f"   ⚠️  Date parsing error for video in {channel_title}: {e}")
                        continue
                
                processed_count += 1
                if channel_video_count > 0:
                    print(f"   📹 [{processed_count}/{len(uploads_data)}] {channel_title}: {channel_video_count} video(s) yesterday")
                elif processed_count % 25 == 0:
                    print(f"   ⏳ Processed {processed_count}/{len(uploads_data)} channels... ({videos_yesterday} videos found)")
                
                time.sleep(0.02)
                
            except Exception as e:
                print(f"❌ Error for {channel_title}: {str(e)}")
                continue
        
        print(f"📊 Yesterday's summary:")
        print(f"   📺 Channels processed: {processed_count}")
        print(f"   🎬 Videos from yesterday: {len(all_video_ids)}")
        print(f"   ⚡ Efficiency: {len(all_video_ids)/max(processed_count, 1):.1f} videos per channel")
        
        return all_video_ids, video_to_channel_map
    
    def batch_get_video_details(self, video_ids):
        """MEGA EFFICIENT: Get details for videos longer than 10 minutes only"""
        if not video_ids:
            return []
        
        # Batch video details requests (up to 50 videos per call)
        video_batches = [video_ids[i:i+50] for i in range(0, len(video_ids), 50)]
        all_video_details = []
        
        print(f"🔍 Getting details for {len(video_ids)} videos in {len(video_batches)} batch(es)...")
        
        for batch_num, batch in enumerate(video_batches, 1):
            if self.quota_used > 9500:
                print(f"⚠️  Quota limit approaching, stopping video details fetch")
                break
                
            try:
                request = self.youtube.videos().list(
                    part='snippet,contentDetails',
                    id=','.join(batch)
                )
                response = request.execute()
                self.log_quota("videos.list (batch)", 1)
                
                batch_long_videos = 0
                for video in response['items']:
                    duration_seconds = self.parse_duration(video['contentDetails']['duration'])
                    
                    # Filter for videos > 10 minutes (600 seconds)
                    if duration_seconds > 600:
                        all_video_details.append({
                            'id': video['id'],
                            'title': video['snippet']['title'],
                            'duration_seconds': duration_seconds,
                            'duration_formatted': str(datetime.timedelta(seconds=int(duration_seconds))),
                            'published': video['snippet']['publishedAt']
                        })
                        batch_long_videos += 1
                
                print(f"   📊 Batch {batch_num}/{len(video_batches)}: {batch_long_videos}/{len(batch)} videos are 10+ minutes")
                        
            except Exception as e:
                print(f"❌ Error in batch video request: {str(e)}")
                continue
        
        # Sort by duration (longest first) for better user experience
        all_video_details.sort(key=lambda x: x['duration_seconds'], reverse=True)
        
        print(f"🎯 Found {len(all_video_details)} long videos (10+ min) using only {len(video_batches)} API calls!")
        return all_video_details
    
    def parse_duration(self, duration_str):
        """Parse YouTube ISO 8601 duration format (PT1H2M3S)"""
        if not duration_str:
            return 0
            
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
        if not match:
            return 0
        
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        
        return hours * 3600 + minutes * 60 + seconds
    
    def create_playlist(self, title, description=""):
        """Create playlist (costs 50 units)"""
        try:
            request = self.youtube.playlists().insert(
                part='snippet,status',
                body={
                    'snippet': {
                        'title': title,
                        'description': description
                    },
                    'status': {
                        'privacyStatus': 'private'
                    }
                }
            )
            response = request.execute()
            self.log_quota("playlists.insert", 50)
            
            playlist_id = response['id']
            print(f"✅ Created playlist: '{title}'")
            return playlist_id
            
        except Exception as e:
            print(f"❌ Error creating playlist: {str(e)}")
            return None
    
    def batch_add_videos_to_playlist(self, playlist_id, videos, channel_map):
        """Add videos to playlist with quota awareness"""
        added_count = 0
        
        print(f"➕ Adding {len(videos)} videos to playlist...")
        
        for video in videos:
            # Each playlist insert costs 50 units
            if self.quota_used + 50 > 10000:
                print(f"⚠️  Quota limit reached. Added {added_count}/{len(videos)} videos.")
                print("💡 Run script again tomorrow to add remaining videos.")
                break
            
            try:
                request = self.youtube.playlistItems().insert(
                    part='snippet',
                    body={
                        'snippet': {
                            'playlistId': playlist_id,
                            'resourceId': {
                                'kind': 'youtube#video',
                                'videoId': video['id']
                            }
                        }
                    }
                )
                request.execute()
                self.log_quota("playlistItems.insert", 50)
                
                channel_name = channel_map.get(video['id'], 'Unknown')
                added_count += 1
                print(f"   ✅ [{added_count}] {video['title']} ({video['duration_formatted']}) - {channel_name}")
                
                time.sleep(0.1)
                
            except Exception as e:
                print(f"   ❌ Failed: {video['title']} - {str(e)}")
        
        return added_count
    
    def save_progress(self, data, filename='daily_playlist_progress.json'):
        """Save progress to resume later if needed"""
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_progress(self, filename='daily_playlist_progress.json'):
        """Load progress from previous run"""
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
    
    def run_daily_videos_manager(self, max_channels=None, max_videos=None):
        """
        Maintain single 'Yesterday' playlist by removing old videos and adding new ones
        Ultra-efficient API usage with daily filtering for videos 10+ minutes
        Creates new Google Sheet daily with date in filename
        """
        # Get date ranges
        yesterday_start, yesterday_end = self.get_yesterday_dates()
        
        # Convert to Hong Kong timezone for display and naming
        hk_yesterday = yesterday_start.astimezone(TIMEZONE)
        
        print("🚀 DAILY YouTube Video Manager - Simple Daily Sheets")
        print("=" * 70)
        print(f"📅 TARGET DATE: {hk_yesterday.strftime('%A, %B %d, %Y')} (Hong Kong time)")
        print(f"🎬 Videos longer than 10 minutes only")
        print(f"🔢 Daily quota: 10,000 units")
        print(f"🎯 Goal: Maintain 'Yesterday' playlist + Create daily Google Sheet")
        print(f"📁 New sheets will be created in '{FOLDER_NAME}' folder")
        
        # Check if running in GitHub Actions
        if os.environ.get('GITHUB_ACTIONS'):
            print(f"🤖 Running in GitHub Actions environment")
        else:
            print(f"💻 Running in local environment")
        
        print("-" * 70)
        
        # STEP 1: Find or create the "Yesterday" playlist
        print(f"\n🔍 STEP 1: Finding or creating 'Yesterday' playlist...")
        yesterday_playlist_id = self.find_playlist_by_name("Yesterday")
        
        if yesterday_playlist_id:
            print(f"✅ Found existing 'Yesterday' playlist")
        else:
            print(f"📝 Creating new 'Yesterday' playlist...")
            description = f"Daily playlist containing videos longer than 10 minutes from yesterday. Auto-updated daily."
            yesterday_playlist_id = self.create_playlist("Yesterday", description)
            
            if not yesterday_playlist_id:
                print("❌ Failed to create playlist")
                return
        
        # STEP 2: Remove old videos (older than yesterday) from playlist
        print(f"\n🗑️  STEP 2: Removing old videos from playlist...")
        removed_count = self.remove_old_videos_from_playlist(yesterday_playlist_id, yesterday_start)
        
        if removed_count > 0:
            print(f"✅ Removed {removed_count} old videos from playlist")
        
        # STEP 3: Get all subscriptions (ultra-efficient)
        print(f"\n🔍 STEP 3: Getting subscribed channels...")
        channels = self.get_subscriptions_batch()
        
        if not channels:
            print("❌ No subscribed channels found")
            return
        
        # Apply channel limit for quota control
        if max_channels and len(channels) > max_channels:
            channels = channels[:max_channels]
            print(f"🔧 Limited to first {max_channels} channels for quota efficiency")
        
        # STEP 4: Batch get upload playlists (mega-efficient)
        print(f"\n🔍 STEP 4: Getting upload playlists for {len(channels)} channels...")
        channel_ids = [ch['id'] for ch in channels]
        uploads_data = self.batch_get_channel_uploads(channel_ids)
        
        # STEP 5: Get videos from yesterday ONLY
        print(f"\n🔍 STEP 5: Scanning uploads from yesterday...")
        video_ids, channel_map = self.batch_get_recent_videos_daily(uploads_data)
        
        if not video_ids:
            print("ℹ️  No videos found from yesterday")
            print("💡 This could mean:")
            print("   • No channels uploaded yesterday")
            print("   • Videos were uploaded as premieres/scheduled")
            print("   • Try running again later if premieres are starting today")
            
            # Still create Google Sheet even if no new videos
            if self.sheets:
                print(f"\n📊 STEP 6: Creating daily Google Sheet...")
                spreadsheet_id = self.create_daily_spreadsheet()
                if spreadsheet_id:
                    self.add_video_links_to_sheet(spreadsheet_id, [])
                    print(f"✅ Created daily Google Sheet with header only")
            return
        
        # STEP 6: Batch get video details (10+ minutes only)
        print(f"\n🔍 STEP 6: Filtering for videos longer than 10 minutes...")
        long_videos = self.batch_get_video_details(video_ids)
        
        if not long_videos:
            print("ℹ️  No videos longer than 10 minutes found from yesterday")
            print("💡 All videos from yesterday were shorter than 10 minutes")
            
            # Still create Google Sheet even if no long videos
            if self.sheets:
                print(f"\n📊 STEP 7: Creating daily Google Sheet...")
                spreadsheet_id = self.create_daily_spreadsheet()
                if spreadsheet_id:
                    self.add_video_links_to_sheet(spreadsheet_id, [])
                    print(f"✅ Created daily Google Sheet with header only")
            return
        
        # STEP 7: Add new videos to playlist
        print(f"\n➕ STEP 7: Adding yesterday's videos to 'Yesterday' playlist...")
        
        # Apply video limit for quota control
        videos_to_add = long_videos
        if max_videos and len(long_videos) > max_videos:
            videos_to_add = long_videos[:max_videos]
            print(f"🔧 Limited to first {max_videos} videos for quota efficiency")
        
        added_count = self.batch_add_videos_to_playlist(yesterday_playlist_id, videos_to_add, channel_map)
        
        # STEP 8: Create daily Google Sheet
        print(f"\n📊 STEP 8: Creating daily Google Sheet with video links...")
        spreadsheet_id = None
        
        if self.sheets:
            try:
                spreadsheet_id = self.create_daily_spreadsheet()
                
                if spreadsheet_id:
                    sheet_success = self.add_video_links_to_sheet(spreadsheet_id, long_videos)
                    
                    if sheet_success:
                        print(f"✅ Successfully created daily Google Sheet with {len(long_videos)} video links")
                    else:
                        print(f"⚠️  Failed to add links to Google Sheet")
                else:
                    print(f"⚠️  Failed to create daily Google Sheet")
                    
            except Exception as e:
                print(f"⚠️  Google Sheets integration failed: {e}")
        else:
            print(f"⚠️  Google Sheets API not available, skipping spreadsheet creation")
        
        # Results
        print("\n" + "=" * 70)
        print(f"🎉 DAILY RESULTS:")
        print(f"   📅 Yesterday: {hk_yesterday.strftime('%A, %B %d, %Y')} (Hong Kong time)")
        print(f"   📺 Channels scanned: {len(channels)}")
        print(f"   🎬 Videos from yesterday: {len(video_ids)}")
        print(f"   ⏱️  Long videos (10+ min): {len(long_videos)}")
        print(f"   🗑️  Old videos removed: {removed_count}")
        print(f"   ✅ New videos added: {added_count}")
        print(f"   🔢 Total quota used: {self.quota_used}/10,000 units")
        print(f"   🔗 Yesterday Playlist: https://www.youtube.com/playlist?list={yesterday_playlist_id}")
        
        if spreadsheet_id:
            print(f"   📊 Daily Google Sheet: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
            print(f"   📁 Sheet saved in '{FOLDER_NAME}' folder")
        else:
            print(f"   📊 Daily Google Sheet: Not created (see warnings above)")
        
        # Show video length distribution
        if long_videos:
            medium_videos = len([v for v in long_videos if 600 <= v['duration_seconds'] < 900])
            long_videos_15plus = len([v for v in long_videos if v['duration_seconds'] >= 900])
            
            print(f"\n📊 VIDEO LENGTH DISTRIBUTION (10+ minutes only):")
            print(f"   🟡 Medium (10-15 min): {medium_videos}")
            print(f"   🔴 Long (15+ min): {long_videos_15plus}")
        
        # Show top 5 videos by duration
        if long_videos:
            print(f"\n🏆 TOP 5 VIDEOS BY DURATION:")
            for i, video in enumerate(long_videos[:5], 1):
                channel_name = channel_map.get(video['id'], 'Unknown')
                print(f"   {i}. {video['duration_formatted']} - {video['title']} ({channel_name})")
        
        # Efficiency stats
        if len(channels) > 0:
            efficiency = self.quota_used / len(channels)
            print(f"\n⚡ EFFICIENCY STATS:")
            print(f"   📊 {efficiency:.1f} quota units per channel")
            print(f"   📈 {len(video_ids)/max(self.quota_used, 1):.1f} videos found per quota unit")
        
        # Save progress (simplified - no persistent config needed)
        progress_data = {
            'playlist_id': yesterday_playlist_id,
            'spreadsheet_id': spreadsheet_id,
            'target_date': hk_yesterday.strftime('%Y-%m-%d'),
            'target_date_hk': hk_yesterday.strftime('%A, %B %d, %Y'),
            'channels_processed': len(channels),
            'videos_found': len(video_ids),
            'long_videos_found': len(long_videos),
            'old_videos_removed': removed_count,
            'new_videos_added': added_count,
            'videos_available': len(long_videos),
            'sheets_integration': spreadsheet_id is not None,
            'quota_used': self.quota_used,
            'completed': added_count == len(videos_to_add),
            'timestamp': datetime.datetime.now().isoformat()
        }
        self.save_progress(progress_data)
        
        # Clean up progress file
        if added_count == len(videos_to_add):
            try:
                os.remove('daily_playlist_progress.json')
                print("✅ Process completed successfully, progress file cleaned up")
            except:
                pass

def main():
    """Main function for daily video management with simple daily Google Sheets"""
    print("🎬 YouTube Daily Manager - Simple Daily Sheets")
    print("🚀 Maintains 'Yesterday' playlist + Creates new Google Sheet daily")
    print("📁 New sheets saved in 'Podkits' folder with date in filename")
    print("-" * 70)
    
    try:
        manager = UltraEfficientYouTubeManager()
        
        print(f"💡 Key Features:")
        print(f"   • Includes videos longer than 10 minutes only")
        print(f"   • Maintains single 'Yesterday' playlist (removes old, adds new)")
        print(f"   • Creates NEW Google Sheet daily with format: 'New video links - YYYY-MM-DD'")
        print(f"   • Saves sheets in existing '{FOLDER_NAME}' folder")
        print(f"   • Ultra-efficient batch API calls")
        print(f"   • Smart quota tracking and preservation")
        print(f"   • GitHub Actions compatible")
        print(f"   • NO COMPLEX CONFIGURATION - Just works!")
        print("-" * 70)
        
        # Run the daily video management
        manager.run_daily_videos_manager()
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
