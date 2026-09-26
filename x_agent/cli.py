import argparse
import json
import sys

from .posts import create_post, create_thread, reply_to_post, status


def _stdin_text() -> str:
    return sys.stdin.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Private X publishing agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    post = sub.add_parser("post", help="Read final approved text from stdin and publish it")
    post.add_argument("--publish", action="store_true", required=True)
    thread = sub.add_parser("thread", help="Read a JSON string array from stdin and publish it")
    thread.add_argument("--publish", action="store_true", required=True)
    reply = sub.add_parser("reply", help="Read final approved text from stdin and publish it as a reply")
    reply.add_argument("post_url")
    reply.add_argument("--publish", action="store_true", required=True)
    args = parser.parse_args()
    if args.command == "status":
        result = status()
    elif args.command == "post":
        result = create_post(_stdin_text())
    elif args.command == "thread":
        result = create_thread(json.loads(_stdin_text()))
    else:
        result = reply_to_post(args.post_url, _stdin_text())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
