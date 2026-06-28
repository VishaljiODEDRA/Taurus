from __future__ import annotations

import argparse

import uvicorn

from agent.web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only Taurus dashboard")
    parser.add_argument("--config", default="config/strategy.toml", help="Path to strategy TOML")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host; defaults to local-only")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--demo-data", action="store_true", help="Run with a synthetic public-safe demo ledger")
    args = parser.parse_args()

    app = create_app(config_path=args.config, demo_data=args.demo_data)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
