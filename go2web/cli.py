import argparse
from urllib.parse import urlparse, urljoin
import socket
import ssl
import requests
import hashlib
from bs4 import BeautifulSoup
import json
import os
from dotenv import load_dotenv
import webbrowser
import time
from datetime import datetime
import shutil


load_dotenv()

MAX_REDIRECTS = 5
CACHE_EXPIRY = 3600
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")

def get_cache_file(url):
    # Use MD5 hash of the URL as the cache file name
    hashed = hashlib.md5(url.encode()).hexdigest()
    return f"cache/{hashed}.cache"

def save_cache(url, content, is_chunked=False):
    os.makedirs("cache", exist_ok=True)
    cache_file = get_cache_file(url)
    timestamp = str(time.time())
    metadata = f"chunked={int(is_chunked)}\n".encode()
    with open(cache_file, "wb") as f:
        # write timestamp as bytes, followed by content
        f.write(timestamp.encode() + b"\n" + metadata + content)
    print(f"\033[92mNew cache saved\033[0m")


def load_cache(url):
    cache_file = get_cache_file(url)
    if os.path.exists(cache_file):
        # open file in binary read mode
        with open(cache_file, "rb") as f:
            #first line is timestamp and rest is content
            lines = f.readlines()
            # if cache file is empty, return None
            if len(lines) < 3:
                return None, False
            # convert timestamp to float
            timestamp = float(lines[0].decode().strip())
            is_chunked_line = lines[1].decode().strip()
            is_chunked = is_chunked_line == "chunked=1"
            cached_data = b"".join(lines[2:])

            if (time.time() - timestamp) < CACHE_EXPIRY:
                cache_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                print(f"\033[92mUsing cached content (saved on {cache_time})\033[0m")
                return cached_data.decode(errors="ignore"), is_chunked
            else:
                print(f"\033[93mCache expired for {url}. Fetching fresh data.\033[0m")
                try:
                    # add a delay before removing the cache file
                    time.sleep(0.5)
                    os.remove(cache_file)
                except PermissionError:
                    try:
                        # force remove the cache file as if it is a folder
                        shutil.rmtree(cache_file, ignore_errors=True)
                        print("\033[91mCache automatically removed.\033[0m")
                    except Exception as e:
                        print(f"\033[91m Could not delete cache file: {e}\033[0m")

    return None, False


def clear_html_tags(html):
        # use the built in parser
        soup = BeautifulSoup(html, "html.parser")
        #soup now represents the html tree

        for script_or_style in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
            script_or_style.decompose()
            # remove the script and style tags

        content_blocks = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"])
        text = "\n".join(block.get_text(separator=" ").strip() for block in content_blocks if block.get_text().strip())
        return text

def parse_headers(headers):
    # Split headers into three parts separated by 2 newlines
    header_section, _, body = headers.partition("\r\n\r\n")
    headers = {}
    lines = header_section.split("\r\n")
    status_line = lines[0]

    #HTTP/1.1 200 OK
    status_code = int(status_line.split(" ")[1]) if len(status_line.split(" ")) > 1 else 200

    for line in lines[1:]: #skip the status line
        if ": " in line: #eg Content-Type: text/html
            key, value = line.split(": ", 1)
            headers[key.lower()] = value

    return status_code, headers, body


def decode_chunked_response(body):
    decoded_body = b"" #decoded body as bytes
    pos = 0

    #loop through the chunks
    while pos < len(body):
        chunk_size_end = body.find(b"\r\n", pos) #search for the position of the first \r\n
        if chunk_size_end == -1:
            break

        try:
            #first the size is displayed, followed by \r\n
            chunk_size_hex = body[pos:chunk_size_end].decode('ascii').strip()
            chunk_size = int(chunk_size_hex, 16)
        except (ValueError, UnicodeDecodeError):
            break
        #if chunk size is 0, it is the last chunk
        if chunk_size == 0:
            break

        pos = chunk_size_end + 2 #skip the \r\n

        chunk_data = body[pos:pos + chunk_size] #get the chunk data
        decoded_body += chunk_data #append the chunk data to the decoded body

        pos = pos + chunk_size + 2 #skip the chunk data and \r\n

    return decoded_body


def make_http_request(url, redirect_count=0, initial_url=None):
    isChunked = False
    if initial_url is None:
        initial_url = url

    if redirect_count > MAX_REDIRECTS:
        print(f"\033[91m Too many redirects for {initial_url} \033[0m")
        return None, isChunked

    cached_content, temp = load_cache(url)
    isChunked = temp
    if cached_content:
        return cached_content, isChunked

    parsed_url = urlparse(url)
    if not parsed_url.netloc:
        print(f"\033[91m Invalid URL \033[0m")
        return None, isChunked

    host = parsed_url.netloc #parse the host
    path = parsed_url.path if parsed_url.path else "/" #parse the path

    use_ssl = parsed_url.scheme == "https" #check if the scheme is https
    port = 443 if use_ssl else 80 #set the port

    request_headers = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "User-Agent: go2web/1.0\r\n"
        "Accept: application/json, text/html\r\n"
        "Connection: close\r\n"
        "\r\n"
    )

    try:
        #create a socket connection
        sock = socket.create_connection((host, port))
        if use_ssl:
            #wrap the socket with SSL
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)
        #send the request headers
        sock.sendall(request_headers.encode())

        response = b""
        while True:
            data = sock.recv(4096) #receive data in chunks of 4096 bytes
            if not data:
                break
            response += data #append the data to the response
        sock.close()

        header_end = response.find(b"\r\n\r\n") #find the end of the headers
        if header_end == -1:
            print(f"\033[91m Invalid response format \033[0m")
            return None, isChunked

        headers_raw = response[:header_end] #get the headers
        body = response[header_end + 4:] #skip the \r\n\r\n

        headers = {}
        header_lines = headers_raw.split(b"\r\n")
        status_line = header_lines[0].decode(errors="ignore")
        status_code = int(status_line.split(" ")[1]) if len(status_line.split(" ")) > 1 else 200

        for line in header_lines[1:]:
            if b": " in line:
                key, value = line.split(b": ", 1)
                headers[key.lower()] = value

        # Check if the response is chunked and decode it
        if headers.get(b"transfer-encoding", b"").lower() == b"chunked":
            isChunked = True
            body = decode_chunked_response(body)
            decoded_headers = "\r\n".join(line.decode(errors="ignore") for line in header_lines)
            decoded_headers = decoded_headers.replace("Transfer-Encoding: chunked", "")  # Remove chunked header

            response = (decoded_headers + "\r\n\r\n").encode() + body

        if status_code in [301, 302, 307, 308] and b"location" in headers:
            new_url = urljoin(url, headers[b"location"].decode()) #handle redirects
            print(f"\033[93m Redirecting to {new_url} \033[0m")
            return make_http_request(new_url, redirect_count + 1, initial_url)

        save_cache(url, response, isChunked)

        return response.decode(errors="ignore"), isChunked

    except Exception as e:
        print(f"\033[91m Error fetching {url}: {e} \033[0m")
        return None, isChunked

def fetch_url(url):
    response, is_chunked = make_http_request(url)
    if response is None:
        return

    if response:
        try:
            header_end = response.find("\r\n\r\n")
            if header_end == -1:
                print(f"\033[91m Invalid response format \033[0m")
                return

            headers_text = response[:header_end] #get the headers
            body = response[header_end + 4:] #skip the \r\n\r\n

            headers = {}
            #
            for line in headers_text.split("\r\n")[1:]:
                if ": " in line:
                    key, value = line.split(": ", 1)
                    headers[key.lower()] = value

            content_type = headers.get("content-type", "").lower()

            if "application/json" in content_type:
                if "/stream/" in url:
                    for line in body.split("\n"):
                        line = line.strip()
                        if line and not line.startswith(("{", "}")):
                            continue
                        if line:
                            try:
                                json_obj = json.loads(line)
                                print(json.dumps(json_obj, indent=2))
                            except json.JSONDecodeError:
                                pass
                else:
                    try:
                        json_obj = json.loads(body)
                        print(json.dumps(json_obj, indent=2))
                    except json.JSONDecodeError:
                        print(f"\033[91m Failed to parse JSON response. \033[0m")
                        print(body[:500])

            elif "text/html" in content_type:
                print(clear_html_tags(body))

            else:
                print(f"\033[91m Content type: {content_type} \033[0m")
                print(body[:1000])

        except Exception as e:
            print(f"\033[91m Error processing response: {e} \033[0m")
    else:
        print(f"\033[91m Failed to fetch URL content. \033[0m")

def search_web(query):
    if not GOOGLE_API_KEY or not SEARCH_ENGINE_ID:
        print("\033[91m Missing API key or Search Engine ID. Set them in the .env file.\033[0m")
        return

    search_url = ( #create the search URL
        f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_API_KEY}&cx={SEARCH_ENGINE_ID}"
    )
    try:
        response = requests.get(search_url)
        response.raise_for_status()
        data = response.json()
        print("\033[92m🔍 Top 10 Search Results:\033[0m")

        search_results = {}

        for i, item in enumerate(data.get("items", [])[:10], start=1):
            title = item.get("title", "No Title")
            link = item.get("link", "No Link")
            snippet = item.get("snippet", "No Description")

            print(f"\033[94m{i}. {title}\033[0m")
            print(f"   📎 {link}")
            print(f"   📝 {snippet}\n")

            search_results[str(i)] = link

        choice = input("\n\033[93mEnter the number of the link to open (or press Enter to skip): \033[0m").strip()

        if choice in search_results:
            print(f"\n\033[92mOpening {search_results[choice]} in browser...\033[0m")
            webbrowser.open(search_results[choice])
        elif choice == "":
            print("\033[93mNo selection made. Exiting...\033[0m")
        else:
            print("\033[91mNo valid selection made.\033[0m")

    except requests.exceptions.RequestException as e:
        print(f"\033[91m[ERROR] Failed to fetch search results: {e}\033[0m")


def clear_cache():
    try:
        shutil.rmtree("cache")
        print("\033[92mCache cleared.\033[0m")
    except Exception as e:
        print(f"\033[91mFailed to clear cache: {e}\033[0m")

def main():
    parser = argparse.ArgumentParser(description="CLI tool to fetch content from the web", add_help=False)
    parser.add_argument("-u", "--url", help="Fetch content from a URL")
    parser.add_argument("-s", "--search", nargs="+",  help="Search the web for a query")
    parser.add_argument("-c", "--clear-cache", action="store_true", help="Clear cached content")
    parser.add_argument("-h", "--help", action="store_true", help="Show this help message")

    args = parser.parse_args()

    if args.help:
        parser.print_help()
        return

    if args.url:
        fetch_url(args.url)
    elif args.search:
        search_web(args.search)
    elif args.clear_cache:
        clear_cache()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
