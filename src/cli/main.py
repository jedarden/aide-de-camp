"""
ADC CLI main entry point.

Provides the command-line interface for aide-de-camp.
"""

import argparse
import asyncio
import sys
from typing import Optional

import httpx

from .config import get_config
from . import commands

# Shared version reader (src/_version.py). The CLI is normally launched via
# ./adc, which puts src/ on sys.path so _version is importable as a top-level
# module; the fallback covers being imported as src.cli.main (e.g. from the
# repo root, where src is a package and the helper lives at src._version).
try:
    from _version import read_version
except ImportError:
    from .._version import read_version


class CLIError(Exception):
    """Base exception for CLI errors."""

    pass


class ConnectionError(CLIError):
    """Raised when connection to server fails."""

    pass


def create_parser() -> argparse.ArgumentParser:
    """Create the main CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="adc",
        description="ADC (aide-de-camp) - Universal personal interface",
        epilog="For more information, see https://github.com/jedarden/aide-de-camp",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {read_version()}",
    )

    parser.add_argument(
        "--server",
        metavar="URL",
        help="Server URL (default: from config or http://localhost:8000)",
    )

    parser.add_argument(
        "--session",
        metavar="ID",
        help="Session ID (default: from config or creates new session)",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="Commands",
        description="Available commands",
        required=True,
    )

    # dispatch command
    dispatch_parser = subparsers.add_parser(
        "dispatch",
        help="Dispatch an utterance to the intent router",
        description="Send an utterance to the router and stream results via SSE",
    )
    dispatch_parser.add_argument(
        "utterance",
        help="The utterance to dispatch",
    )
    dispatch_parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Return immediately without streaming results",
    )

    # ask command
    ask_parser = subparsers.add_parser(
        "ask",
        help="Ask a question (query a specific topic)",
        description="Query a specific topic with a question",
    )
    ask_parser.add_argument(
        "question",
        help="The question to ask",
    )
    ask_parser.add_argument(
        "--topic",
        metavar="ID",
        help="Topic ID to query (default: active topic)",
    )

    # status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show active session status",
        description="Display the current session status and summary",
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Output status as JSON",
    )

    # topics command
    topics_parser = subparsers.add_parser(
        "topics",
        help="List active topics",
        description="Show all active topics for the current session",
    )
    topics_parser.add_argument(
        "--json",
        action="store_true",
        help="Output topics as JSON",
    )

    # exceptions command
    exceptions_parser = subparsers.add_parser(
        "exceptions",
        help="Show exception queue",
        description="Display the current exception queue and monitoring status",
    )
    exceptions_parser.add_argument(
        "--json",
        action="store_true",
        help="Output exceptions as JSON",
    )

    # config command
    config_parser = subparsers.add_parser(
        "config",
        help="Manage CLI configuration",
        description="View or update CLI configuration",
    )
    config_parser.add_argument(
        "--set-server",
        metavar="URL",
        help="Set the server URL",
    )
    config_parser.add_argument(
        "--set-session",
        metavar="ID",
        help="Set the session ID",
    )
    config_parser.add_argument(
        "--show",
        action="store_true",
        help="Show current configuration",
    )

    return parser


async def run_command(args: argparse.Namespace) -> int:
    """
    Run the specified command.

    Returns exit code (0 for success, non-zero for error).
    """
    config = get_config()

    # Override config with CLI arguments
    server_url = args.server or config.get_server_url()
    session_id = args.session or config.get_session_id()

    try:
        if args.command == "dispatch":
            return await commands.dispatch(
                utterance=args.utterance,
                server_url=server_url,
                session_id=session_id,
                stream=not args.no_stream,
                config=config,
            )

        elif args.command == "ask":
            return await commands.ask(
                question=args.question,
                topic_id=args.topic,
                server_url=server_url,
                session_id=session_id,
                config=config,
            )

        elif args.command == "status":
            return await commands.status(
                server_url=server_url,
                session_id=session_id,
                as_json=args.json,
            )

        elif args.command == "topics":
            return await commands.topics(
                server_url=server_url,
                session_id=session_id,
                as_json=args.json,
            )

        elif args.command == "exceptions":
            return await commands.exceptions(
                server_url=server_url,
                as_json=args.json,
            )

        elif args.command == "config":
            return commands.config_cmd(
                set_server=args.set_server,
                set_session=args.set_session,
                show=args.show,
            )

        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            return 1

    except httpx.ConnectError as e:
        print(f"Failed to connect to server at {server_url}: {e}", file=sys.stderr)
        print("Hint: Use 'adc --set-server <url>' to configure the server URL", file=sys.stderr)
        return 1
    except httpx.HTTPStatusError as e:
        print(f"HTTP error {e.response.status_code}: {e.response.text}", file=sys.stderr)
        return 1
    except ConnectionError as e:
        print(f"Connection error: {e}", file=sys.stderr)
        return 1
    except CLIError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if asyncio.run(run_command(args)) == 0:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
