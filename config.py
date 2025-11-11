import os
import json
from typing import List, Set

# ----------------------------------------
# Helpers
# ----------------------------------------

def _get_env_list(name: str, default: List[str]) -> List[str]:
    """
    Reads an environment variable that can be a:
    - JSON list:  ["uh","umm"]
    - Comma list: uh,umm,hmm
    """
    env_val = os.getenv(name)
    if not env_val:
        return default

    try:
        # Check if it looks like a JSON list
        if env_val.lstrip().startswith("["):
            return json.loads(env_val)
        
        # Otherwise, parse as comma-separated
        return list(map(str.strip, env_val.split(",")))
    except Exception:
        return default


def _load_words_from_file(path: str) -> Set[str]:
    """
    Loads a set of words from a text file, one word/phrase per line.
    """
    if not os.path.exists(path):
        return set()

    try:
        with open(path, "r", encoding="utf-8") as f:
            # Use a set comprehension for efficient loading
            return {line.strip().lower() for line in f if line.strip()}
    except Exception:
        return set()


def _load_all_from_directory(folder: str) -> Set[str]:
    """
    Loads all .txt files from the specified directory.
    """
    all_words = set()
    if not os.path.isdir(folder):
        return all_words

    for filename in os.listdir(folder):
        if filename.endswith(".txt"):
            filepath = os.path.join(folder, filename)
            all_words.update(_load_words_from_file(filepath))

    return all_words


# ----------------------------------------
# File-based filler loading
# ----------------------------------------

# Get the absolute path to the 'filler_words' directory
FILLER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "filler_words")
)

FILE_BASED_FILLERS = _load_all_from_directory(FILLER_DIR)


# ----------------------------------------
# Final IGNORED_FILLERS
# ----------------------------------------

DEFAULT_FILLERS_ENV = [
    "uh", "umm", "hmm", "haan", "okay", "hmm okay"
]

# Load fillers from environment, then merge with file-based fillers
env_fillers = {
    w.lower() for w in _get_env_list("IGNORED_FILLERS", DEFAULT_FILLERS_ENV)
}
IGNORED_FILLERS: Set[str] = env_fillers.union(FILE_BASED_FILLERS)


# ----------------------------------------
# Interrupt Commands
# ----------------------------------------

DEFAULT_INTERRUPTS_ENV = ["stop", "wait", "hold on", "pause"]

INTERRUPTION_TRIGGERS: Set[str] = {
    w.lower() for w in _get_env_list("INTERRUPT_COMMANDS", DEFAULT_INTERRUPTS_ENV)
}


# ----------------------------------------
# Thresholds
# ----------------------------------------

# Min confidence to accept an interruption while the agent is speaking
AGENT_SPEAKING_CONFIDENCE_THRESHOLD = float(
    os.getenv("MIN_CONFIDENCE_AGENT_SPEAKING", "0.35")
)

# Max number of tokens for a segment to be considered "short"
SHORT_SEGMENT_TOKEN_LIMIT = int(
    os.getenv("SHORT_SEGMENT_TOKENS", "5")
)