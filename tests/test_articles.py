import os
import unittest

os.environ.setdefault("X_AGENT_DEBUG_LOG", "/tmp/x-agent-test.log")

from x_agent import articles


class ArticleHelpersTest(unittest.TestCase):
    def test_markdown_blocks_are_parsed(self):
        blocks = articles.parse_article_markdown(
            "## Heading\n\nBody with **bold**.\n\n- one\n- two\n\n> quote"
        )
        self.assertEqual(
            [block.kind for block in blocks],
            ["heading", "body", "ul", "quote"],
        )
        self.assertEqual(blocks[1].text, "Body with bold.")
        self.assertEqual(blocks[2].text, ("one", "two"))

    def test_markdown_links_remain_readable_and_explicit(self):
        blocks = articles.parse_article_markdown(
            "Read [the advisory](https://example.com/advisory)."
        )
        self.assertEqual(
            blocks[0].text,
            "Read the advisory (https://example.com/advisory).",
        )

    def test_empty_article_is_rejected(self):
        with self.assertRaises(ValueError):
            articles.parse_article_markdown("  \n")

    def test_title_is_normalized(self):
        self.assertEqual(articles._validate_title("  A   title "), "A title")

    def test_public_article_url_pattern(self):
        self.assertIsNotNone(
            articles.ARTICLE_PUBLIC_RE.match(
                "https://x.com/pepetheshneine/article/123456"
            )
        )

    def test_draft_publication_rejects_noncanonical_url_before_browser(self):
        with self.assertRaisesRegex(ValueError, "canonical X Article edit URL"):
            articles.publish_article_draft("https://example.com/draft/123", "Title", "Body")

    def test_article_plaintext_preserves_visible_structure(self):
        blocks = articles.parse_article_markdown(
            "## Heading\n\nParagraph.\n\n- one\n- two"
        )
        self.assertEqual(
            articles._article_plaintext(blocks),
            "HEADING\n\nParagraph.\n\n• one\n• two",
        )

    def test_ordered_article_parts_follow_rendered_body(self):
        blocks = articles.parse_article_markdown("## First\n\nSecond")
        self.assertEqual(articles._ordered_article_parts(blocks), ["FIRST", "Second"])

    def test_large_article_text_is_split_without_reordering(self):
        text = "x" * 3_101
        chunks = articles._text_chunks(text, 1_500)
        self.assertEqual([len(chunk) for chunk in chunks], [1_500, 1_500, 101])
        self.assertEqual("".join(chunks), text)

    def test_order_assertion_rejects_missing_article_content(self):
        blocks = articles.parse_article_markdown("## First\n\nSecond")
        with self.assertRaisesRegex(RuntimeError, "missing or reorders"):
            articles._assert_article_order("FIRST", blocks, "test")


if __name__ == "__main__":
    unittest.main()
