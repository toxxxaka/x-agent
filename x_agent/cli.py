import argparse
import json
import sys

from .articles import create_article, publish_article_draft
from .debug import logger
from .posts import create_post, create_thread, list_communities, reply_to_post, status


def _stdin_text() -> str:
    return sys.stdin.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Private X publishing agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("communities", help="List available X Communities without publishing")
    post = sub.add_parser("post", help="Read final approved text from stdin and publish it")
    post.add_argument("--publish", action="store_true", required=True)
    post.add_argument("--community", help="Exact X Community name; omitted means Everyone")
    post.add_argument("--image", help="Absolute local image path; upload is verified before publishing")
    thread = sub.add_parser("thread", help="Read a JSON string array from stdin and publish it")
    thread.add_argument("--publish", action="store_true", required=True)
    thread.add_argument("--community", help="Exact X Community name for the root; omitted means Everyone")
    thread.add_argument("--image", help="Absolute local image path for the root; upload is verified before publishing")
    reply = sub.add_parser("reply", help="Read final approved text from stdin and publish it as a reply")
    reply.add_argument("post_url")
    reply.add_argument("--publish", action="store_true", required=True)
    article = sub.add_parser(
        "article",
        help="Read Article Markdown from stdin and create it in X Articles",
    )
    article.add_argument("--title", required=True)
    article.add_argument("--cover", required=True, help="Absolute JPG, PNG, or WEBP path")
    article.add_argument(
        "--publish",
        action="store_true",
        help="Publish to Everyone; omitted saves a verified draft",
    )
    article_publish = sub.add_parser(
        "article-publish",
        help="Publish a previously verified X Article draft to Everyone",
    )
    article_publish.add_argument("draft_url", help="Canonical X Article edit URL")
    article_publish.add_argument("--title", required=True)
    article_publish.add_argument("--publish", action="store_true", required=True)
    args = parser.parse_args()
    if args.command == "status":
        result = status()
    elif args.command == "communities":
        result = list_communities()
    elif args.command == "post":
        result = create_post(_stdin_text(), community=args.community, image_path=args.image)
    elif args.command == "thread":
        result = create_thread(json.loads(_stdin_text()), community=args.community, image_path=args.image)
    elif args.command == "reply":
        result = reply_to_post(args.post_url, _stdin_text())
    elif args.command == "article":
        result = create_article(
            args.title,
            _stdin_text(),
            args.cover,
            publish=args.publish,
        )
    else:
        result = publish_article_draft(args.draft_url, args.title, _stdin_text())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("CLI failed")
        raise
