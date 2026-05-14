#!/usr/bin/env python3
from yalla_resources_tool.cli import main
from yalla_resources_tool.validation import validate
from yalla_resources_tool.emitters import generate
from yalla_resources_tool.io import sync_directory_contents, tree_snapshot
from yalla_resources_tool.checks import verify_generated_output

if __name__ == "__main__":
    import sys
    sys.exit(main())
