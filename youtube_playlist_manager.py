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
    'https://www.googleapis.com/auth/drive'
]

# Set your timezone here
TIMEZONE = pytz.timezone('Asia/Hong_Kong')  # Hong Kong timezone (UTC+8)

# Google Drive folder configuration
FOLDER_NAME = "Podkits"  # Name of your Google Drive folder

class UltraEfficientYouTubeManager:
    def __init__(self):
        self.youtube = None
        self.sheets = None
        self.drive = None
        self.quota_used = 0
        self.authenticate()
    
    def log_quota(self, operation, cost):
        """Track quota usage with exact costs"""
        self.quota_used += cost
        print(f"🔢 Quota: {self.quota_used}/10,000 (+{cost} for {operation})")
    
    def authenticate(self):
        """Authenticate with Google APIs using OAuth2 (no service account needed!)"""
        creds = None
        
        # Check environment
        if os.environ.get('GITHUB_ACTIONS'):
            print("🤖 GitHub Actions detected - using OAuth credentials")
        else:
            print("💻 Local environment detected - using OAuth credentials")
        
        # For GitHub Actions: Check if both credentials.json and token.json exist
        if os.environ.get('GITHUB_ACTIONS'):
            if not os.path.exists('credentials.json'):
                print("❌ ERROR: credentials.json not found in GitHub Actions!")
                print("📋 Setup: Add your OAuth credentials.json as GitHub secret 'GOOGLE_CREDENTIALS_JSON'")
                raise Exception("Missing credentials.json in GitHub Actions")
            
            if not os.path.exists('token.json'):
                print("❌ ERROR: token.json not found in GitHub Actions!")
                print("📋 Setup: Add your token.json as GitHub secret 'GOOGLE_TOKEN_JSON'")
                print("💡 Generate token.json by running script locally first")
                raise Exception("Missing token.json in GitHub Actions")
        
        # For local: Check if credentials.json exists
        if not os.environ.get('GITHUB_ACTIONS') and not os.path.exists('credentials.json'):
            print("❌ ERROR: credentials.json not found!")
            print("📋 Setup Instructions:")
            print("1. Go to https://console.cloud.google.com/")
            print("2. APIs & Services → Credentials")
            print("3. Create OAuth 2.0 Client ID (Desktop application)")
            print("4. Download and save as 'credentials.json'")
            raise Exception("Missing credentials.json file")
        
        # Load existing token if available
        if os.path.exists('token.json'):
            try:
                creds = Credentials.from_authorized_user_file('token.json', SCOPES)
                print("🔑 Loaded existing OAuth token")
            except Exception as e:
                print(f"⚠️  Token file corrupted: {e}")
                if not os.environ.get('GITHUB_ACTIONS'):  # Only delete locally
                    print("🔄 Removing corrupted token, will re-authenticate...")
                    os.remove('token.json')
                creds = None
        
        # Handle token refresh or new authentication
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    print("🔄 Refreshing expired OAuth token...")
                    creds.refresh(Request())
                    print("✅ Token refreshed successfully")
                except Exception as e:
                    print(f"❌ Token refresh failed: {e}")
                    if os.environ.get('GITHUB_ACTIONS'):
                        print("💡 Token expired in GitHub Actions - regenerate token.json locally")
                        raise Exception("Token refresh failed in GitHub Actions")
                    else:
                        print("🔄 Starting fresh authentication...")
                        if os.path.exists('token.json'):
                            os.remove('token.json')
                        creds = None
            
            # If refresh failed or no valid creds, start OAuth flow
            if not creds:
                if os.environ.get('GITHUB_ACTIONS'):
                    print("❌ OAuth flow not possible in GitHub Actions (no browser)")
                    print("💡 Generate token.json locally first, then add as GitHub secret")
                    raise Exception("Cannot run OAuth flow in GitHub Actions")
                
                try:
                    print("🚀 Starting OAuth authentication flow...")
                    print("📱 A browser window will open for authentication")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        'credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                    print("✅ OAuth authentication completed")
                except Exception as e:
                    print(f"❌ OAuth flow failed: {e}")
                    raise Exception(f"Authentication failed: {e}")
            
            # Save the new/refreshed credentials (only locally)
            if not os.environ.get('GITHUB_ACTIONS'):
                try:
                    with open('token.json', 'w') as token:
                        token.write(creds.to_json())
                    print("💾 Saved OAuth token to token.json")
                    print("💡 For GitHub Actions: Add token.json content as secret 'GOOGLE_TOKEN_JSON'")
                except Exception as e:
                    print(f"⚠️  Warning: Could not save token: {e}")
        
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
            self.sheets = None
        
        try:
            self.drive = build('drive', 'v3', credentials=creds)
            print("✅ Successfully authenticated with Google Drive API")
            
        except Exception as e:
            print(f"⚠️  Warning: Google Drive API failed: {e}")
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
            
            # Combine header and links
            all_data = header_row + video_links
            
            # Write to sheet
            range_name = 'Video Links!A1'
            body = {'values': all_data}
            
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
        """Get yesterday's date range in Hong Kong timezone"""
        hk_now = datetime.datetime.now(TIMEZONE)
        hk_yesterday_start = hk_now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=1)
        hk_yesterday_end = hk_yesterday_start + datetime.timedelta(hours=23, minutes=59, seconds=59)
        
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
    
    def get_subscriptions_batch(self, batch_size=50):
        """ULTRA-EFFICIENT: Get all subscriptions in minimum API calls"""
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
            
            if self.quota_used > 9000:
                print(f"⚠️  Stopping to preserve quota")
                break
        
        print(f"📺 Retrieved {len(all_channels)} channels using only {len(all_channels)//50 + 1} API calls")
        return all_channels
    
    def batch_get_channel_uploads(self, channel_ids):
        """ULTRA EFFICIENT: Get upload playlists for up to 50 channels in ONE call"""
        if not channel_ids:
            return {}
        
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
        """ULTRA-MEGA EFFICIENT: Get videos from yesterday only"""
        yesterday_start, yesterday_end = self.get_yesterday_dates()
        
        all_video_ids = []
        video_to_channel_map = {}
        
        print(f"🔍 DAILY SCAN: Searching {len(uploads_data)} upload playlists...")
        
        hk_yesterday_start = yesterday_start.astimezone(TIMEZONE)
        hk_yesterday_end = yesterday_end.astimezone(TIMEZONE)
        
        print(f"📅 Yesterday (HK time): {hk_yesterday_start.strftime('%A, %B %d, %Y')}")
        print(f"📅 Time range (HK): {hk_yesterday_start.strftime('%Y-%m-%d %H:%M:%S')} to {hk_yesterday_end.strftime('%Y-%m-%d %H:%M:%S')}")
        
        processed_count = 0
        videos_yesterday = 0
        
        for channel_id, data in uploads_data.items():
            uploads_playlist = data['uploads_playlist']
            channel_title = data['title']
            
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
                        published_date = datetime.datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                        
                        if yesterday_start <= published_date <= yesterday_end:
                            video_id = item['snippet']['resourceId']['videoId']
                            all_video_ids.append(video_id)
                            video_to_channel_map[video_id] = channel_title
                            channel_video_count += 1
                            videos_yesterday += 1
                        elif published_date < yesterday_start:
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
    
    def batch_add_videos_to_playlist(self, playlist_id, videos, channel_map):
        """Add videos to playlist with quota awareness"""
        added_count = 0
        
        print(f"➕ Adding {len(videos)} videos to playlist...")
        
        for video in videos:
            if self.quota_used + 50 > 10000:
                print(f"⚠️  Quota limit reached. Added {added_count}/{len(videos)} videos.")
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
    
    def run_daily_manager(self):
        """ULTRA-EFFICIENT main function using OAuth (no service account!)"""
        yesterday_start, yesterday_end = self.get_yesterday_dates()
        hk_yesterday = yesterday_start.astimezone(TIMEZONE)
        
        print("🚀 ULTRA-EFFICIENT YOUTUBE DAILY MANAGER (OAuth Version)")
        print("=" * 70)
        print(f"📅 Target date: {hk_yesterday.strftime('%A, %B %d, %Y')} (Hong Kong time)")
        print(f"🎬 Videos longer than 10 minutes only")
        print(f"🔢 Daily quota: 10,000 units")
        print(f"🔑 Using OAuth credentials (no service account needed!)")
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
        
        # STEP 2: Get all subscriptions (ultra-efficient)
        print(f"\n🔍 STEP 2: Getting subscribed channels...")
        channels = self.get_subscriptions_batch()
        
        if not channels:
            print("❌ No subscribed channels found")
            return
        
        # STEP 3: Batch get upload playlists (mega-efficient)
        print(f"\n🔍 STEP 3: Getting upload playlists for {len(channels)} channels...")
        channel_ids = [ch['id'] for ch in channels]
        uploads_data = self.batch_get_channel_uploads(channel_ids)
        
        # STEP 4: Get videos from yesterday ONLY
        print(f"\n🔍 STEP 4: Scanning uploads from yesterday...")
        video_ids, channel_map = self.batch_get_recent_videos_daily(uploads_data)
        
        if not video_ids:
            print("ℹ️  No videos found from yesterday")
            
            # Still create Google Sheet even if no new videos
            if self.sheets:
                print(f"\n📊 STEP 5: Creating daily Google Sheet...")
                spreadsheet_id = self.create_daily_spreadsheet()
                if spreadsheet_id:
                    self.add_video_links_to_sheet(spreadsheet_id, [])
                    print(f"✅ Created daily Google Sheet with header only")
            return
        
        # STEP 5: Batch get video details (10+ minutes only)
        print(f"\n🔍 STEP 5: Filtering for videos longer than 10 minutes...")
        long_videos = self.batch_get_video_details(video_ids)
        
        if not long_videos:
            print("ℹ️  No videos longer than 10 minutes found from yesterday")
            
            # Still create Google Sheet even if no long videos
            if self.sheets:
                print(f"\n📊 STEP 6: Creating daily Google Sheet...")
                spreadsheet_id = self.create_daily_spreadsheet()
                if spreadsheet_id:
                    self.add_video_links_to_sheet(spreadsheet_id, [])
                    print(f"✅ Created daily Google Sheet with header only")
            return
        
        # STEP 6: Add new videos to playlist
        print(f"\n➕ STEP 6: Adding yesterday's videos to 'Yesterday' playlist...")
        added_count = self.batch_add_videos_to_playlist(yesterday_playlist_id, long_videos, channel_map)
        
        # STEP 7: Create daily Google Sheet
        print(f"\n📊 STEP 7: Creating daily Google Sheet with video links...")
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
            print(f"⚠️  Google Sheets API not available")
        
        # Results
        print("\n" + "=" * 70)
        print(f"🎉 ULTRA-EFFICIENT DAILY RESULTS:")
        print(f"   📅 Yesterday: {hk_yesterday.strftime('%A, %B %d, %Y')} (Hong Kong time)")
        print(f"   📺 Channels scanned: {len(channels)}")
        print(f"   🎬 Videos from yesterday: {len(video_ids)}")
        print(f"   ⏱️  Long videos (10+ min): {len(long_videos)}")
        print(f"   ✅ Videos added to playlist: {added_count}")
        print(f"   🔢 Total quota used: {self.quota_used}/10,000 units")
        print(f"   ⚡ Efficiency: {len(video_ids)/max(self.quota_used, 1):.2f} videos per quota unit")
        
        if yesterday_playlist_id:
            print(f"   🔗 Yesterday Playlist: https://www.youtube.com/playlist?list={yesterday_playlist_id}")
        
        if spreadsheet_id:
            print(f"   📊 Daily Google Sheet: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
            print(f"   📁 Sheet saved in '{FOLDER_NAME}' folder")
        
        print("=" * 70)

def main():
    """Main function - OAuth version (no service account needed!)"""
    print("🎬 ULTRA-EFFICIENT YouTube Daily Manager (OAuth Version)")
    print("🚀 Creates daily Google Sheets + Maintains Yesterday playlist")
    print("📁 Saves sheets in 'Podkits' folder with date in filename")
    print("🔑 Uses OAuth credentials - no service account needed!")
    print("⚡ Optimized for minimal API quota usage")
    print("-" * 70)
    
    try:
        manager = UltraEfficientYouTubeManager()
        manager.run_daily_manager()
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print(f"\n🔧 TROUBLESHOOTING:")
        print(f"1. Make sure you have OAuth credentials.json file")
        print(f"2. Check that all APIs are enabled in Google Cloud Console")
        print(f"3. Verify 'Podkits' folder exists in your Google Drive")
        print(f"4. For GitHub Actions: Add both credentials.json AND token.json as secrets")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
