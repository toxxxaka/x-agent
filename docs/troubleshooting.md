# Troubleshooting

| Symptom | Meaning | Safe next step |
| --- | --- | --- |
| `another X publishing action is already running` | Host lock is held. | Wait for the active operation; do not kill a browser blindly. |
| `session is not authenticated` | Cookie session expired or was invalidated. | Export a fresh session from a browser you control. |
| Community not found uniquely | X did not expose one exact selectable match. | Run `list_x_communities()` and use its displayed name. |
| Image upload cannot be verified | X did not prove attachment success. | Inspect sanitized image log entries and do not post text-only as a fallback. |
| Article preview missing content | Draft.js/UI did not retain the full body. | Keep it a draft, correct the editor flow, and verify the preview before publishing. |

When reporting a problem, include the operation stage and sanitized status code—not cookies, bearer tokens, full diagnostic logs, or private post content.
