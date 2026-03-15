"""Allow running data-bridge as a module: python3 -m data-bridge → python3 -m main inside the directory."""

from main import main
import asyncio

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[BRIDGE] Interrupted — goodbye")
