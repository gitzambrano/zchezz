"""Read UCI ``info ... score`` values and convert them to a known point of view.

Standard UCI engines (Stockfish and others) report ``score cp`` and
``score mate`` from the side to move.

Zchezz engines (every profile, including the frozen baselines) do not:
  * ``score cp`` is White-relative;
  * ``score mate N`` is always printed as a positive N, so its sign carries no
    information. The side that mates is the side favoured by the last
    ``score cp`` of the same search line.

Callers select the convention once per engine with :func:`pov_from_id_name`
(from the UCI ``id name`` line), or force it with ``"white"`` / ``"stm"``.
Then they feed every ``info`` line of one search to a :class:`SearchScores`
instance and read White-relative values from it.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

WHITE = "white"   # score is White-relative (Zchezz)
STM = "stm"       # score is side-to-move relative (UCI standard)
AUTO = "auto"
POVS = (AUTO, WHITE, STM)

DEFAULT_MATE_CP = 19000

_SCORE_RE = re.compile(r"\bscore (cp|mate) (-?\d+)")
_MPV_RE = re.compile(r"\bmultipv (\d+)")


def pov_from_id_name(id_name: Optional[str]) -> str:
    """Return the score convention of an engine from its ``id name`` value."""
    if id_name and id_name.strip().lower().startswith("zchezz"):
        return WHITE
    return STM


def resolve_pov(requested: str, id_name: Optional[str]) -> str:
    """Apply an explicit override; ``auto`` uses :func:`pov_from_id_name`."""
    if requested not in POVS:
        raise ValueError(f"score point of view must be one of {POVS}, got {requested!r}")
    return pov_from_id_name(id_name) if requested == AUTO else requested


def parse_score(line: str) -> Optional[Tuple[str, int]]:
    """Return ``("cp"|"mate", value)`` from an ``info`` line, or ``None``."""
    m = _SCORE_RE.search(line)
    return (m.group(1), int(m.group(2))) if m else None


def parse_multipv(line: str) -> int:
    m = _MPV_RE.search(line)
    return int(m.group(1)) if m else 1


def to_stm(white_cp: Optional[int], white_to_move: bool) -> Optional[int]:
    """Convert a White-relative score to the side to move."""
    if white_cp is None:
        return None
    return white_cp if white_to_move else -white_cp


class SearchScores:
    """White-relative scores of one ``go`` search, kept per MultiPV line."""

    def __init__(self, pov: str, white_to_move: bool, mate_cp: int = DEFAULT_MATE_CP):
        if pov not in (WHITE, STM):
            raise ValueError(f"resolved point of view must be {WHITE!r} or {STM!r}, got {pov!r}")
        self.pov = pov
        self.white_to_move = white_to_move
        self.mate_cp = mate_cp
        self._last_cp: Dict[int, int] = {}

    def feed(self, line: str) -> Optional[int]:
        """Return the White-relative score in ``line``.

        Returns ``None`` when the line has no score, or when the line is a
        Zchezz mate score and no earlier cp score gives its sign.
        """
        parsed = parse_score(line)
        if parsed is None:
            return None
        kind, value = parsed
        mpv = parse_multipv(line)
        if kind == "cp":
            white = value if (self.pov == WHITE or self.white_to_move) else -value
            self._last_cp[mpv] = white
            return white
        if self.pov == STM:
            stm_sign = 1 if value > 0 else -1
            return self.mate_cp * (stm_sign if self.white_to_move else -stm_sign)
        last = self._last_cp.get(mpv, self._last_cp.get(1))
        if last is None or last == 0:
            return None
        return self.mate_cp if last > 0 else -self.mate_cp
