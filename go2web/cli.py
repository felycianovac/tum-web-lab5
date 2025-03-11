import argparse
from urllib.parse import urlparse

def main():
    parser = argparse.ArgumentParser(description="CLI tool to fetch content from the web")
    parser.add_argument("-u", "--url", help="Fetch content from a URL")
    parser.add_argument("-s", "--search", help="Search the web for a query")

    args = parser.parse_args()

    if args.url:
        parsed_url = urlparse(args.url)
        if not parsed_url.netloc:
            print("Invalid URL")
        else:
            #TODO: Add functionality to fetch content from the web
            pass
    elif args.search:
        print(f"Searching for: {args.search}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
