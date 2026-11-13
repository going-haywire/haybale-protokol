"""Decide what publish.yml does. Standard library only; reads the checked-out project.

Writes ``enabled`` and ``matrix`` to $GITHUB_OUTPUT. Exits 1, with a message, when
publishing was requested but the run cannot be trusted to publish the right thing.
"""

import json
import os
import pathlib
import sys
import tomllib


def emit(enabled, matrix, standalone):
    line = (
        f"enabled={'true' if enabled else 'false'}\n"
        f"matrix={json.dumps(matrix)}\n"
        f"standalone={'true' if standalone else 'false'}\n"
    )
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a") as handle:
            handle.write(line)
    print(line, end="")


def fail(message):
    print(f"::error::{message}")
    sys.exit(1)


root = pathlib.Path(".")
config = tomllib.loads((root / "pyproject.toml").read_text())


def leaves_the_checkout(path):
    target = pathlib.Path(path)
    target = target if target.is_absolute() else root / target
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError:
        return True
    return False


# A root that links to something outside this checkout (a --dev project's haywire
# checkout) cannot be installed on a runner, so its tests cannot run there.
sources = config.get("tool", {}).get("uv", {}).get("sources", {})
standalone = not any(
    isinstance(source, dict) and "path" in source and leaves_the_checkout(source["path"])
    for source in sources.values()
)
distribute = config.get("tool", {}).get("haywire", {}).get("marketstall", {}).get("distribute", "git")

if distribute != "pypi":
    print(f"distribute = {distribute!r}: nothing to publish to PyPI.")
    emit(False, [], standalone)
    sys.exit(0)

if os.environ.get("GITHUB_REF_TYPE") != "tag":
    fail("Publishing runs on a version tag only. Retry with: gh workflow run publish.yml --ref vX.Y.Z")

libraries = []
for directory in sorted((root / "barn").glob("*")):
    manifest = directory / "pyproject.toml"
    if directory.is_symlink() or not manifest.is_file():
        continue
    project = tomllib.loads(manifest.read_text())["project"]
    libraries.append({"dist": project["name"], "version": project["version"], "path": directory.as_posix()})

if not libraries:
    fail("No library under barn/ to publish.")

tag = os.environ.get("GITHUB_REF_NAME", "")
wrong = [item for item in libraries if tag != f"v{item['version']}"]
if wrong:
    names = ", ".join(f"{item['dist']} {item['version']}" for item in wrong)
    fail(f"Tag {tag} does not match the committed version of: {names}. Nothing was uploaded.")

emit(True, libraries, standalone)
