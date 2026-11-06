"""Command line entry point: `euro-info` or `python -m euroinfo`."""
from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="euro-info", description="European news, weather and research reader.")
    parser.add_argument("--version", action="version", version=f"Euro Info {__version__}")
    parser.add_argument("--widget-json", action="store_true",
                        help="print the latest stories and weather as JSON for the Plasma widget")
    parser.add_argument("--headlines", action="store_true", help="print weather, rates and the latest stories")
    parser.add_argument("--self-test", metavar="REPORT", help=argparse.SUPPRESS)
    parser.add_argument("--verbose", action="store_true", help="log debug details to the terminal")
    options, qt_arguments = parser.parse_known_args(argv)

    from . import logs
    logs.setup(options.verbose)
    if options.widget_json:
        from .core import widget
        return widget.main()
    if options.self_test:
        from .ui.application import self_test
        return self_test(options.self_test)
    if options.headlines:
        from .core import cli
        return cli.main()
    from .ui.application import run
    return run([sys.argv[0], *qt_arguments])


if __name__ == "__main__":
    raise SystemExit(main())
