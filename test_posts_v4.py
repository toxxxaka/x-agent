import os
import sys
import unittest

os.environ.setdefault("X_AGENT_DEBUG_LOG", "/tmp/x-agent-test.log")
sys.path.insert(0, "/home/ai/x-agent-build")

from x_agent import posts_v4 as posts


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class PostHelpersTest(unittest.TestCase):
    def test_user_rest_id_before_tweet_is_not_selected(self):
        payload = {
            "data": {
                "viewer": {
                    "rest_id": "111",
                    "__typename": "User",
                    "legacy": {"screen_name": "pepetheshneine"},
                },
                "create_tweet": {
                    "tweet_results": {
                        "result": {
                            "rest_id": "222",
                            "__typename": "Tweet",
                            "legacy": {"full_text": "test"},
                        }
                    }
                },
            }
        }
        self.assertEqual(posts._find_tweet_result(payload), {"id": "222"})

    def test_visibility_wrapper_is_unwrapped(self):
        payload = {
            "result": {
                "__typename": "TweetWithVisibilityResults",
                "tweet": {"__typename": "Tweet", "rest_id": "333"},
            }
        }
        self.assertEqual(posts._find_tweet_result(payload), {"id": "333"})

    def test_user_only_payload_has_no_tweet(self):
        payload = {
            "result": {
                "rest_id": "444",
                "__typename": "User",
                "legacy": {"screen_name": "someone"},
                "core": {},
            }
        }
        self.assertIsNone(posts._find_tweet_result(payload))

    def test_extract_url_uses_configured_username(self):
        response = FakeResponse(
            {"result": {"rest_id": "555", "__typename": "Tweet"}}
        )
        self.assertEqual(
            posts.extract_created_post_url(response),
            f"https://x.com/{posts.X_USERNAME}/status/555",
        )

    def test_status_url_with_share_query_is_normalized(self):
        url, status_id = posts._canonical_status_url(
            "https://x.com/pepetheshneine/status/123?s=46"
        )
        self.assertEqual(url, "https://x.com/pepetheshneine/status/123")
        self.assertEqual(status_id, "123")


if __name__ == "__main__":
    unittest.main()
