#!/usr/bin/env python3
"""Thin wrapper for direct script invocation: python dnsfcli.py [args]"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dnsfcli.cli import app_entry

if __name__ == "__main__":
    app_entry()
