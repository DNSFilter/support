"""Wrapper that runs build_guide.py with the correct asset paths."""
import pathlib, sys

# Brand assets ship with DNSFilter's internal build-guide skill (not in
# this repository). Set DNSFCLI_BRAND_ASSETS to its assets/ directory.
import os
if "DNSFCLI_BRAND_ASSETS" not in os.environ:
    sys.exit("Set DNSFCLI_BRAND_ASSETS to the build-guide skill assets directory.")
ASSETS = pathlib.Path(os.environ["DNSFCLI_BRAND_ASSETS"])
FONTS = ASSETS / "fonts"
LOGOS = ASSETS / "logos"
OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "docs"
OUT_DIR.mkdir(exist_ok=True)

src = (pathlib.Path(__file__).resolve().parent / "build_guide.py").read_text()
src = src.replace(
    "ASSETS = Path(__file__).resolve().parent",
    f'ASSETS = pathlib.Path(r"{ASSETS}")\nimport pathlib as pathlib',
)
src = src.replace('OUT_DIR = Path(".")', f'OUT_DIR = pathlib.Path(r"{OUT_DIR}")')
src = src.replace("if __name__ == \"__main__\":", "if True:")
# Preserve newlines inside prompt blocks so multi-line shell commands render
# one per line in the PDF (same patch build_command_reference.py applies).
src = src.replace(
    ".prompt-body {{ font-family: 'Inter','Arial',sans-serif;",
    ".prompt-body {{ white-space: pre-wrap; font-family: 'Inter','Arial',sans-serif;",
)

exec(compile(src, "build_guide.py", "exec"), {
    "__file__": str(ASSETS / "build_guide.py"),
    "__name__": "__main__",
    "pathlib": pathlib,
})
