import os
import sys
from dateutil import parser
from webdav3.client import Client
from importlib import reload

sys.path.append('notion-query')
import notion

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
    """List files in the remote WebDAV directory."""
    try:
        return client.list(remote_path, get_info=True)[1:]
    except Exception as e:
        print(f"Failed to list directory: {e}")
        return []

def upload_file_to_webdav(local_path, remote_path):
    """Upload file to WebDAV."""
    try:
        client.upload_sync(remote_path=remote_path, local_path=local_path)
        print(f"Uploaded {local_path} to {remote_path}")
    except Exception as e:
        print(f"Failed to upload {local_path} to {remote_path}: {e}")

def download_file_from_webdav(remote_path, local_path):
    """Download file from WebDAV."""
    try:
        client.download_sync(remote_path=remote_path, local_path=local_path)
        print(f"Downloaded {remote_path} to {local_path}")
    except Exception as e:
        print(f"Failed to download {remote_path} to {local_path}: {e}")

# Step 3: Fetch Notion image information
page_filters = {
    '状态': '完成',
    '类型': '电绘',
}
block_filters = {
    'type': 'image'
}

pages = q.get_pages(database_id=database_id, filters=page_filters)

file_urls = []
file_names = []
file_times = []
for page_header in pages:
    page_title = notion.get_page_title(page_header)
    page_id = notion.get_page_id(page_header)
    page_date = page_header['properties']['更新日期']['date']['start'].replace('-', '_')
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
webdav_outdir = "/SWAP/cmsn/"
remote_files_info = list_webdav_directory(webdav_outdir)
remote_file_names = [file_info['name'] for file_info in remote_files_info]
remote_file_times = [parser.parse(file_info['modified']) for file_info in remote_files_info]
remote_file_times_dict = dict(zip(remote_file_names, remote_file_times))

# (a) Upload new or modified files
for file_name, file_url, file_time in zip(file_names, file_urls, file_times):
    remote_path = os.path.join(webdav_outdir, file_name)
    needs_update = file_name not in remote_file_names or file_time > remote_file_times_dict.get(file_name)
    if needs_update:
        if file_name in remote_file_names:
            client.clean(remote_path)  # Remove outdated file on WebDAV
        local_path = os.path.join("/tmp", file_name)  # Temporary local storage
        notion.download_files([file_name], [file_url], "/tmp")
        upload_file_to_webdav(local_path, remote_path)
        os.remove(local_path)  # Clean up temporary file after upload
    else: 
        print(f"{remote_path} already exists, skipped")

# (b) Delete files in WebDAV that are not in Notion
for remote_file_name in remote_file_names:
    if remote_file_name not in file_names:
        remote_path = os.path.join(webdav_outdir, remote_file_name)
        try:
            client.clean(remote_path)
            print(f"Deleted {remote_path}")
        except Exception as e:
            print(f"Failed to delete {remote_path}: {e}")
