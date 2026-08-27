"""Shim for backwards compatibility - delegates to app.seed"""
from app.seed import main

__all__ = ["main"]

if __name__ == "__main__":
    main()
