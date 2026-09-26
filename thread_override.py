

# Native composer avoids URL extraction between replies; this definition overrides
# the legacy sequential-reply implementation above.
def create_thread(posts: Iterable[str]) -> dict[str, Any]:
    """Publish a thread atomically through X's native multi-post composer."""
    from .native_thread import create_native_thread

    return create_native_thread([_validate_text(text) for text in posts])
