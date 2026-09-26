"""Compatibility entry point for the private X agent.

Use stdin, for example:
    printf '%s' 'Approved text' | python3 post.py post --publish
"""

from x_agent.cli import main


if __name__ == "__main__":
    main()
