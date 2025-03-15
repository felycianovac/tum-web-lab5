import argparse
from urllib.parse import urlparse
import socket
import ssl

def make_http_request(url):
    parsed_url = urlparse(url)
    if not parsed_url.netloc:
        print("Invalid URL")
        return None

    host = parsed_url.netloc
    path = parsed_url.path if parsed_url.path else "/"

    use_ssl = parsed_url.scheme == "https"
    port = 443 if use_ssl else 80

    request_headers = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "User-Agent: go2web/1.0\r\n"
        "Connection: close\r\n"
        "\r\n"
    )

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

    return response.decode(errors="ignore")


def main():
    parser = argparse.ArgumentParser(description="CLI tool to fetch content from the web")
    parser.add_argument("-u", "--url", help="Fetch content from a URL")
    parser.add_argument("-s", "--search", help="Search the web for a query")

    args = parser.parse_args()

    if args.url:
        print(make_http_request(args.url))
    elif args.search:
        print(f"Searching for: {args.search}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
