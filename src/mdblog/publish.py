"""mdblog.publish: moves notes from a vault into a Hugo content directory."""

import shutil
from pathlib import Path


def copy_notes(vault: Path, content_dir: Path) -> list[Path]:
    """Copies each `*.md` file under `vault` to its relative path under `content_dir`.

    Returns the destination paths sorted. Overwrites existing destinations and
    creates missing parent directories. Raises `FileNotFoundError` when `vault`
    is not an existing directory.
    """
    if not vault.is_dir():
        raise FileNotFoundError(f"vault directory not found: {vault}")
    destinations: list[Path] = []
    for note in sorted(path for path in vault.rglob("*.md") if path.is_file()):
        destination = content_dir / note.relative_to(vault)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(note, destination)
        destinations.append(destination)
    return sorted(destinations)
