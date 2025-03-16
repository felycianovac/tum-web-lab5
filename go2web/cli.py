import argparse
from urllib.parse import urlparse, urljoin
import socket
import ssl
import os
import hashlib
from bs4 import BeautifulSoup
import json

MAX_REDIRECTS = 5

def get_cache_file(url):
    hashed = hashlib.md5(url.encode()).hexdigest()
    return f"cache/{hashed}.cache"

def save_cache(url, content):
    os.makedirs("cache", exist_ok=True)
    cache_file = get_cache_file(url)
    with open(cache_file, "wb") as f:
        f.write(content)


def load_cache(url):
    cache_file = get_cache_file(url)
    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            return f.read()
    return None

def clear_html_tags(html):
        soup = BeautifulSoup(html, "html.parser")

        for script_or_style in soup(["script", "style", "noscript"]):
            script_or_style.decompose()

        text = soup.get_text(separator="\n")
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        return text

def parse_headers(headers):
    header_section, _, body = headers.partition("\r\n\r\n")
    headers = {}
    lines = header_section.split("\r\n")
    status_line = lines[0]

    status_code = int(status_line.split(" ")[1]) if len(status_line.split(" ")) > 1 else 200

    for line in lines[1:]:
        if ": " in line:
            key, value = line.split(": ", 1)
            headers[key.lower()] = value

    return status_code, headers, body


def make_http_request(url, redirect_count=0, initial_url=None):
    if initial_url is None:
        initial_url = url

    if redirect_count > MAX_REDIRECTS:
        print(f"\033[91m Too many redirects for {initial_url} \033[0m")
        return None


    cached_content = load_cache(url)
    if cached_content:
        print("Using cached content")
        return cached_content.decode(errors="ignore")

    parsed_url = urlparse(url)
    if not parsed_url.netloc:
        print(f"\033[Invalid URL\033[0m")
        return None

    host = parsed_url.netloc
    path = parsed_url.path if parsed_url.path else "/"

    use_ssl = parsed_url.scheme == "https"
    port = 443 if use_ssl else 80

    request_headers = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "User-Agent: go2web/1.0\r\n"
        "Accept: application/json, text/html\r\n"
        "Connection: close\r\n"
        "\r\n"
    )

    try:
        sock = socket.create_connection((host, port))
        if use_ssl:
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)

        sock.sendall(request_headers.encode())

        response = b""
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response += data
        sock.close()

        response_str = response.decode(errors="ignore")

        status_code, headers, body = parse_headers(response_str)

        if status_code in [301, 302, 307, 308] and  "location" in headers:
            new_url = urljoin(url, headers["location"])
            print(f"\033[93m Redirecting to {new_url} \033[0m")
            return make_http_request(new_url, redirect_count + 1, initial_url)

        save_cache(url, response)

        return response_str

    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def fetch_url(url):
    response = make_http_request(url)
    if response is None:
        return

    if response:
        status_code, headers, body = parse_headers(response)
        content_type = headers.get("content-type", "")

        if "application/json" in content_type:
            try:
                json_data = json.loads(body)
                print(json.dumps(json_data, indent=4))
            except json.JSONDecodeError:
                print(f"\033[91m Failed to parse JSON response. \033[0m")

        elif "text/html" in content_type:
            print(clear_html_tags(body))
        else:
            print(f"\033[91m Failed to parse response. \033[0m")
    else:
        print(f"\033[91m Failed to fetch URL content. \033[0m")


def main():
    parser = argparse.ArgumentParser(description="CLI tool to fetch content from the web")
    parser.add_argument("-u", "--url", help="Fetch content from a URL")
    parser.add_argument("-s", "--search", help="Search the web for a query")

    args = parser.parse_args()

    if args.url:
        fetch_url(args.url)
    elif args.search:
        print(f"Searching for: {args.search}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
