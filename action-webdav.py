import os
import sys
from dateutil import parser
from webdav3.client import Client
from importlib import reload
import logging
import io

sys.path.append('notion-query')
import notion

from settings import page_filters, block_filters, date_property, webdav_outdir, name_property, webdav_logname

# initialize logging
log_stream = io.StringIO()
logging.basicConfig(stream=log_stream, level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger()

# Initialize Notion Query
q = notion.Query()
q.set_token(os.getenv('NOTION_TOKEN'))  # Use environment variable for Notion token

database_id = os.getenv('DATABASE_ID')  # Set database ID as an environment variable
outdir = './data'

# Step 1: Configure WebDAV client with check disabled and environment variables

options = {
    'webdav_hostname': os.getenv('WEBDAV_HOSTNAME'),
    'webdav_login': os.getenv('WEBDAV_LOGIN'),
    'webdav_password': os.getenv('WEBDAV_PASSWORD'),
    'disable_check': True
}

client = Client(options)

# Step 2: Define helper functions

def list_webdav_directory(remote_path):
    try:
        return client.list(remote_path, get_info=True)
    except Exception as e:
        log.info(f"Failed to list directory: {e}")
        return []

def upload_file_to_webdav(local_path, remote_path):
    try:
        client.upload_sync(remote_path=remote_path, local_path=local_path)
        log.info(f"Uploaded {local_path} to {remote_path}")
        return True
    except Exception as e:
        log.info(f"Failed to upload {local_path} to {remote_path}: {e}")
        return False

def download_file_from_webdav(remote_path, local_path):
    try:
        client.download_sync(remote_path=remote_path, local_path=local_path)
        log.info(f"Downloaded {remote_path} to {local_path}")
        return True
    except Exception as e:
        log.info(f"Failed to download {remote_path} to {local_path}: {e}")
        return False

def delete_file_from_webdav(remote_path):
    try:
        client.clean(remote_path)
        log.info(f"Deleted {remote_path}")
        return True
    except Exception as e:
        log.info(f"Failed to delete {remote_path}: {e}")
        return False

def append_log_to_webdav():
    remote_log_path = os.path.join(webdav_outdir, webdav_logname)
    local_log_path = os.path.join('/tmp', webdav_logname)

    # Step 1: Attempt to download the existing log file from WebDAV
    success = download_file_from_webdav(remote_log_path, local_log_path)
    if success:
        with open(local_log_path, 'r') as f:
            existing_log = f.read()
    if not success: 
        log.info(f'Log file not found on WebDAV; creating a new log file.')
        existing_log = ''  # Start with an empty log if download fails

    # Step 2: Read new log entries and combine with the existing log
    new_log_entries = log_stream.getvalue()
    combined_log = existing_log + new_log_entries

    # Step 3: Write combined log to the local file
    with open(local_log_path, 'w') as f:
        f.write(combined_log)

    # Step 4: Upload the updated log file back to WebDAV
    upload_file_to_webdav(local_log_path, remote_log_path)

    # Clean up the temporary local file
    os.remove(local_log_path)

# Step 3: Fetch Notion image information

pages = q.get_pages(database_id=database_id, filters=page_filters)

file_urls = []
file_names = []
file_times = []
for page_header in pages:
    page_title = notion.get_page_title(page_header, name_property=name_property)
    page_id = notion.get_page_id(page_header)
    page_date = page_header['properties'][date_property]['date']['start'].replace('-', '_')
    blocks = q.get_blocks(page_id=page_id, filters=block_filters)
    n_image = len(blocks)

    pagefile_urls = notion.get_image_urls(blocks)
    pagefile_extensions = notion.get_url_extensions(pagefile_urls)
    pagefile_names = [f'{page_date}_{page_title}_{i+1:02d}.{pagefile_extensions[i]}' 
                      for i in range(n_image)]
    pagefile_times = notion.get_block_times(blocks)
    
    file_urls += pagefile_urls
    file_names += pagefile_names
    file_times += pagefile_times

# Step 4: Sync images with WebDAV
remote_files_info = list_webdav_directory(webdav_outdir)
# filter non-image file 
remote_files_info = [file_info for file_info in remote_files_info
                     if isinstance(file_info['content_type'], str)
                     and 'image' not in file_info['content_type']]
remote_file_names = [file_info['name'] for file_info in remote_files_info]
remote_file_times = [parser.parse(file_info['modified']) for file_info in remote_files_info]
remote_file_times_dict = dict(zip(remote_file_names, remote_file_times))

# (a) Upload new or modified files
count_uploaded = 0
count_skipped = 0
for file_name, file_url, file_time in zip(file_names, file_urls, file_times):
    remote_path = os.path.join(webdav_outdir, file_name)
    needs_update = file_name not in remote_file_names or file_time > remote_file_times_dict.get(file_name)
    if needs_update:
        if file_name in remote_file_names:
            client.clean(remote_path)  # Remove outdated file on WebDAV
        local_path = os.path.join("/tmp", file_name)  # Temporary local storage
        notion.download_files([file_name], [file_url], "/tmp")
        success = upload_file_to_webdav(local_path, remote_path)
        if success: count_uploaded += 1
        os.remove(local_path)  # Clean up temporary file after upload
    else: 
        log.info(f"{remote_path} already exists, skipped")
        count_skipped += 1

# (b) Delete files in WebDAV that are not in Notion
count_deleted = 0
for remote_file_name in remote_file_names:
    if remote_file_name not in file_names:
        remote_path = os.path.join(webdav_outdir, remote_file_name)
        success = delete_file_from_webdav(remote_path)
        if success: count_deleted += 1

# finalize job
print(f'Skipped {count_skipped} files; uploaded {count_uploaded} files; deleted {count_deleted} files. Log appended to {webdav_logname}.')
append_log_to_webdav()


# TODO: create log and change output to files count