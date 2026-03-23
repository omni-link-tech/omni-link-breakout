"""Play Breakout using OmniLink tool calling.

The AI agent calls the ``make_move`` tool, which acts as a local
Breakout AI controller.  The model never sees the game — it simply
triggers the tool.  The tool reads the game state, predicts the ball
trajectory, and moves the paddle accordingly.

This keeps API credit usage to a minimum (one call to kick off).

Usage
-----
    python -u play_breakout.py
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

# ── Path setup ─────────────────────────────────────────────────────────
_HERE = str(pathlib.Path(__file__).resolve().parent)
LIB_PATH = str(pathlib.Path(__file__).resolve().parents[3] / "omnilink-lib" / "src")
if _HERE in sys.path:
    sys.path.remove(_HERE)
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from omnilink.tool_runner import ToolRunner

if _HERE not in sys.path:
    sys.path.append(_HERE)

from breakout_api import get_state, send_action
from breakout_engine import decide_action, state_summary


class BreakoutRunner(ToolRunner):
    agent_name = "breakout-agent"
    display_name = "Breakout"
    tool_description = "Move paddle."

    def __init__(self) -> None:
        self._last_score = 0
        self._last_lives = -1
        self._last_level = -1

    def get_state(self) -> dict[str, Any]:
        return get_state()

    def execute_action(self, state: dict[str, Any]) -> None:
        if state.get("game_state") == "PLAY":
            send_action(decide_action(state))

    def state_summary(self, state: dict[str, Any]) -> str:
        return state_summary(state)

    def is_game_over(self, state: dict[str, Any]) -> bool:
        return state.get("game_state") == "GAMEOVER"

    def game_over_message(self, state: dict[str, Any]) -> str:
        return f"GAME OVER — Final score: {state.get('score', 0)}, Level: {state.get('level', 1)}"

    def on_start(self) -> None:
        try:
            send_action("RESUME")
            print("  Game resumed.")
        except Exception:
            pass

    def log_events(self, state: dict[str, Any]) -> None:
        score = state.get("score", 0)
        lives = state.get("lives", 0)
        level = state.get("level", 1)

        if score != self._last_score:
            print(f"  Score: {score}  (+{score - self._last_score})")
            self._last_score = score
        if lives != self._last_lives:
            if self._last_lives > 0 and lives < self._last_lives:
                print(f"  ** Life lost! Lives: {lives}")
            self._last_lives = lives
        if level != self._last_level:
            print(f"  Level: {level}")
            self._last_level = level


if __name__ == "__main__":
    BreakoutRunner().run()
