import os
import time
from typing import Set, Dict, List


class FillerManager:
    """
    Manages dynamic loading and refreshing of filler word lists
    from text files in a specified directory.
    
    Files named with "command" are treated as commands.
    Others are treated as fillers.
    """

    def __init__(self, directory: str):
        self.directory = directory
        self.last_loaded_time = 0
        self.fillers: Set[str] = set()
        self.commands: Set[str] = set()
        self._file_cache: Dict[str, float] = {}  # Caches file modification times

        if not os.path.isdir(directory):
            raise FileNotFoundError(f"Filler directory not found: {directory}")

        self.reload_if_changed()  # Initial load

    # -----------------------------------------
    # File Helpers
    # -----------------------------------------

    def _load_words_from_file(self, path: str) -> Set[str]:
        """Loads a set of words from a single text file."""
        if not os.path.exists(path):
            return set()

        try:
            with open(path, "r", encoding="utf-8") as f:
                return {
                    line.strip().lower()
                    for line in f
                    if line.strip()
                }
        except Exception as e:
            print(f"Error reading filler file {path}: {e}")
            return set()

    def _has_file_changes(self) -> bool:
        """
        Returns True if any .txt file in the directory has been
        modified, added, or removed since the last check.
        """
        files_updated = False
        current_files = set()

        for fname in os.listdir(self.directory):
            if not fname.endswith(".txt"):
                continue

            path = os.path.join(self.directory, fname)
            current_files.add(path)
            
            try:
                mtime = os.path.getmtime(path)
            except FileNotFoundError:
                continue

            if path not in self._file_cache or mtime > self._file_cache[path]:
                self._file_cache[path] = mtime
                files_updated = True

        # Check for deleted files
        if set(self._file_cache.keys()) != current_files:
            self._file_cache = {
                p: t for p, t in self._file_cache.items() if p in current_files
            }
            files_updated = True

        return files_updated

    # -----------------------------------------
    # Main Reload Logic
    # -----------------------------------------

    def reload_if_changed(self):
        """
        Reloads all filler and command files if any
        file modification is detected.
        """
        if not self._has_file_changes() and self.last_loaded_time > 0:
            return  # No update needed

        print("[FillerManager] Detected changes, reloading word lists...")
        new_fillers = set()
        new_commands = set()

        for fname in os.listdir(self.directory):
            if not fname.endswith(".txt"):
                continue

            path = os.path.join(self.directory, fname)
            words = self._load_words_from_file(path)

            if "command" in fname.lower():
                new_commands.update(words)
            else:
                new_fillers.update(words)

        self.fillers = new_fillers
        self.commands = new_commands
        self.last_loaded_time = time.time()

        print(
            f"[FillerManager] Reloaded. Fillers: {len(self.fillers)}, Commands: {len(self.commands)}"
        )

    # -----------------------------------------
    # Query Helpers
    # -----------------------------------------

    def is_filler(self, word: str) -> bool:
        """Check if a word is a known filler."""
        return word.lower().strip() in self.fillers

    def is_command(self, word: str) -> bool:
        """Check if a word is a known command."""
        return word.lower().strip() in self.commands