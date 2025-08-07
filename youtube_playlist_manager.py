# Simple fix to use your EXISTING Google Sheet

# Add this configuration at the top of the file (around line 18)
# Replace SPREADSHEET_NAME with your actual Google Sheet ID

# Method 1: Use Google Sheet ID directly
SPREADSHEET_ID = "1WriUk6rNf7XDs0K_WM2sQjghciDhZx2-ICUliC_bDvI"  # Get this from your sheet URL

# Method 2: If you prefer to find by name (your existing sheet name)
SPREADSHEET_NAME = "Your Existing Sheet Name"  # Name of your existing Google Sheet

# Replace the entire get_or_create_spreadsheet method with this simple version:

def get_or_create_spreadsheet(self, spreadsheet_name):
    """Use existing spreadsheet only - never create new ones"""
    if not self.sheets:
        return None
    
    # Method 1: If you have the direct Sheet ID (recommended)
    if SPREADSHEET_ID and SPREADSHEET_ID != "1WriUk6rNf7XDs0K_WM2sQjghciDhZx2-ICUliC_bDvI":
        try:
            # Test if the sheet exists and is accessible
            sheet_metadata = self.sheets.spreadsheets().get(
                spreadsheetId=SPREADSHEET_ID
            ).execute()
            
            sheet_title = sheet_metadata.get('properties', {}).get('title', 'Unknown')
            print(f"✅ Using existing Google Sheet: '{sheet_title}'")
            print(f"🔗 Sheet URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
            return SPREADSHEET_ID
            
        except Exception as e:
            print(f"❌ Cannot access Google Sheet with ID: {SPREADSHEET_ID}")
            print(f"   Error: {e}")
            print(f"💡 Please check:")
            print(f"   • Sheet ID is correct")
            print(f"   • Sheet is shared with your Google account")
            print(f"   • Sheet exists and isn't deleted")
            return None
    
    # Method 2: Find by name (if you don't want to use direct ID)
    try:
        # Search for existing sheet by name (this requires Drive API scope)
        print(f"🔍 Searching for existing sheet named: '{spreadsheet_name}'")
        
        # Note: This is limited and may not find all sheets
        # Better to use the direct Sheet ID method above
        
        print(f"❌ Sheet name search not implemented")
        print(f"💡 Please use Method 1: Set SPREADSHEET_ID at the top of the file")
        print(f"   Get your Sheet ID from the URL:")
        print(f"   https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/edit")
        return None
        
    except Exception as e:
        print(f"❌ Error searching for existing sheet: {e}")
        return None

# Enhanced add_video_links_to_sheet method that ensures all videos are written:

def add_video_links_to_sheet(self, spreadsheet_id, videos, channel_map=None):
    """Add ALL video URLs to existing Google Sheet with verification"""
    if not self.sheets:
        return False
        
    try:
        # Prepare data
        header_row = [['Video URL', 'Video Title', 'Channel Name', 'Duration', 'Date Added']]
        video_data = []
        
        current_date = datetime.datetime.now(TIMEZONE).strftime('%Y-%m-%d')
        
        print(f"📊 Preparing {len(videos)} videos for Google Sheet...")
        
        for i, video in enumerate(videos, 1):
            video_url = f"https://www.youtube.com/watch?v={video['id']}"
            video_title = video.get('title', 'Unknown Title')
            
            # Get channel name
            if channel_map and video['id'] in channel_map:
                channel_name = channel_map[video['id']]
            else:
                channel_name = 'Unknown Channel'
            
            duration = video.get('duration_formatted', 'Unknown')
            
            video_data.append([video_url, video_title, channel_name, duration, current_date])
            
            if i % 10 == 0:  # Progress indicator
                print(f"   📝 Prepared {i}/{len(videos)} videos...")
        
        # Combine all data
        all_data = header_row + video_data
        total_rows = len(all_data)
        
        print(f"📊 Writing {total_rows} rows to Google Sheet (1 header + {len(videos)} videos)...")
        
        # Clear existing data
        try:
            clear_range = f'A:Z'  # Clear all columns
            self.sheets.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=clear_range
            ).execute()
            print(f"✅ Cleared existing data from sheet")
        except Exception as e:
            print(f"⚠️  Warning: Could not clear existing data: {e}")
        
        # Write all data at once
        try:
            range_name = f'A1:E{total_rows}'
            
            body = {
                'values': all_data,
                'majorDimension': 'ROWS'
            }
            
            result = self.sheets.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            updated_rows = result.get('updatedRows', 0)
            updated_cells = result.get('updatedCells', 0)
            
            print(f"📊 Google Sheet Results:")
            print(f"   ✅ Rows updated: {updated_rows}")
            print(f"   ✅ Cells updated: {updated_cells}")
            print(f"   ✅ Expected rows: {total_rows}")
            
            # Verify success
            if updated_rows == total_rows:
                print(f"🎉 SUCCESS: All {len(videos)} videos written to Google Sheet!")
                return True
            else:
                print(f"⚠️  PARTIAL: Only {updated_rows}/{total_rows} rows written")
                
                # Try to read back and count actual videos
                try:
                    read_result = self.sheets.spreadsheets().values().get(
                        spreadsheetId=spreadsheet_id,
                        range='A:A'
                    ).execute()
                    
                    actual_rows = len(read_result.get('values', []))
                    actual_videos = max(0, actual_rows - 1)  # Subtract header
                    
                    print(f"📊 Verification: {actual_videos} videos actually in sheet")
                    
                    if actual_videos == len(videos):
                        print(f"✅ Verification successful: All videos are present!")
                        return True
                    else:
                        print(f"❌ Missing videos: {len(videos) - actual_videos} videos not written")
                        return False
                        
                except Exception as verify_e:
                    print(f"⚠️  Could not verify sheet contents: {verify_e}")
                    return False
                
        except Exception as e:
            print(f"❌ Failed to write to Google Sheet: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Error preparing data for Google Sheet: {e}")
        return False

# Instructions for the user:

"""
SETUP INSTRUCTIONS:

1. Get your Google Sheet ID:
   • Go to your existing Google Sheet
   • Look at the URL: https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/edit
   • Copy the SHEET_ID part

2. Update the code:
   • Replace 'your_google_sheet_id_here' with your actual Sheet ID in SPREADSHEET_ID

3. Make sure your Google Sheet is accessible:
   • The sheet must be owned by or shared with your Google account
   • The account must have edit permissions

Example:
SPREADSHEET_ID = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

That's it! No new sheets will be created, only your existing sheet will be updated.
"""
