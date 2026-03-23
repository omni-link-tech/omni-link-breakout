"""Local Breakout AI engine — ball prediction and paddle control.

This module is the ``make_move`` tool: given the current game state it
simulates the ball trajectory (including brick and wall collisions) to
predict where the ball will intercept the paddle row and returns the
optimal paddle action (LEFT, RIGHT, or STOP).
"""

from __future__ import annotations

import math
from typing import Any

# Game constants (must match breakout.py).
PADDLE_Y = 670       # Approximate paddle top (HEIGHT - 50).
BALL_R = 5           # Half of BALL_SIZE (10).
WIDTH = 640
DEADZONE = 5         # Pixels of tolerance before moving the paddle.
MAX_SIM_STEPS = 800  # Safety cap on simulation iterations.
SIM_DT = 1.0 / 60   # Simulate at game frame rate.


# ── Ball trajectory simulation ───────────────────────────────────────

def _simulate_landing(state: dict[str, Any]) -> float:
    """Simulate the ball forward until it reaches PADDLE_Y.

    Handles wall bounces AND brick collisions so the prediction is
    accurate even when the ball ricochets off bricks on the way down.

    Returns the predicted X centre of the ball when it reaches the
    paddle row.
    """
    bx = state["ball_x"] + BALL_R
    by = state["ball_y"] + BALL_R
    dx = state["ball_dx"]
    dy = state["ball_dy"]
    w = state.get("width", WIDTH)

    # Build a simple list of brick rects for collision testing.
    bricks: list[tuple[float, float, float, float]] = []
    for b in state.get("bricks", []):
        bricks.append((b["x"], b["y"], b["w"], b["h"]))

    for _ in range(MAX_SIM_STEPS):
        # Already at or past paddle row heading down — done.
        if by >= PADDLE_Y and dy > 0:
            return bx

        # Step forward.
        bx += dx * SIM_DT
        by += dy * SIM_DT

        # Wall bounces.
        if bx - BALL_R <= 0:
            bx = BALL_R
            dx = abs(dx)
        elif bx + BALL_R >= w:
            bx = w - BALL_R
            dx = -abs(dx)

        if by - BALL_R <= 0:
            by = BALL_R
            dy = abs(dy)

        # Brick collisions — find first overlapping brick.
        hit = -1
        for i, (rx, ry, rw, rh) in enumerate(bricks):
            if (bx + BALL_R > rx and bx - BALL_R < rx + rw and
                    by + BALL_R > ry and by - BALL_R < ry + rh):
                hit = i
                break

        if hit >= 0:
            rx, ry, rw, rh = bricks.pop(hit)
            # Determine bounce axis from overlap.
            overlap_l = (bx + BALL_R) - rx
            overlap_r = (rx + rw) - (bx - BALL_R)
            overlap_t = (by + BALL_R) - ry
            overlap_b = (ry + rh) - (by - BALL_R)
            min_ov = min(overlap_l, overlap_r, overlap_t, overlap_b)
            if min_ov == overlap_l or min_ov == overlap_r:
                dx = -dx
            else:
                dy = -dy

    # Fallback: if simulation didn't converge, return current X.
    return bx


def predict_ball_x(state: dict[str, Any]) -> float:
    """Return the predicted X where the ball will meet the paddle row."""
    ball_dy = state["ball_dy"]

    if ball_dy <= 0:
        # Ball heading up — just track its current X.
        return state["ball_x"] + BALL_R

    return _simulate_landing(state)


# ── Action decision ──────────────────────────────────────────────────

def _pick_target_brick(state: dict[str, Any]) -> tuple[float, float] | None:
    """Pick the best brick to aim at. Returns (cx, cy) or None."""
    bricks = state.get("bricks", [])
    if not bricks:
        return None
    # Prefer the lowest brick (closest to paddle = easiest to aim at).
    best = max(bricks, key=lambda b: b["y"])
    return (best["x"] + best["w"] / 2, best["y"] + best["h"] / 2)


def _aim_paddle_center(landing_x: float, brick_cx: float, brick_cy: float,
                       paddle_w: float) -> float:
    """Calculate paddle center to deflect ball from landing_x toward brick.

    The game computes:
        offset = (ball_cx - paddle_center) / (paddle_w / 2)
        angle  = pi/2 - offset * pi/3

    After bounce the ball travels at ``angle`` from horizontal.  We
    reverse this to find the paddle center that sends the ball toward
    the target brick.
    """
    dx_to_brick = brick_cx - landing_x
    dy_to_brick = PADDLE_Y - brick_cy  # positive (brick is above)
    if dy_to_brick <= 0:
        return landing_x

    desired_angle = math.atan2(dy_to_brick, dx_to_brick)
    # Solve: desired_angle = pi/2 - offset * pi/3
    needed_offset = (math.pi / 2 - desired_angle) / (math.pi / 3)
    needed_offset = max(-0.9, min(0.9, needed_offset))

    # offset = (ball_cx - paddle_center) / (paddle_w / 2)
    # paddle_center = ball_cx - offset * (paddle_w / 2)
    paddle_cx = landing_x - needed_offset * (paddle_w / 2)

    # Clamp to playfield.
    paddle_cx = max(paddle_w / 2, min(WIDTH - paddle_w / 2, paddle_cx))
    return paddle_cx


def decide_action(state: dict[str, Any]) -> str:
    """Decide the paddle action based on the current game state.

    Returns ``'LEFT'``, ``'RIGHT'``, or ``'STOP'``.
    """
    landing_x = predict_ball_x(state)
    paddle_center = state["paddle_x"] + state["paddle_w"] / 2
    paddle_w = state["paddle_w"]
    ball_dy = state.get("ball_dy", 0)

    if ball_dy > 0:
        # Ball coming down — aim at a brick instead of just catching.
        brick = _pick_target_brick(state)
        if brick is not None:
            target_x = _aim_paddle_center(landing_x, brick[0], brick[1], paddle_w)
        else:
            target_x = landing_x
    else:
        # Ball going up — pre-position toward brick we want to hit next.
        brick = _pick_target_brick(state)
        if brick is not None:
            target_x = _aim_paddle_center(landing_x, brick[0], brick[1], paddle_w)
        else:
            target_x = landing_x

    if paddle_center < target_x - DEADZONE:
        return "RIGHT"
    elif paddle_center > target_x + DEADZONE:
        return "LEFT"
    else:
        return "STOP"


# ── State summary (for OmniLink memory) ─────────────────────────────

def state_summary(state: dict[str, Any]) -> str:
    """Build a concise text summary of the current game state."""
    bricks = state.get("bricks", [])
    total_bricks = len(bricks)
    lives = state.get("lives", 0)
    score = state.get("score", 0)
    level = state.get("level", 1)
    play_time = state.get("play_time", 0)
    game_state = state.get("game_state", "UNKNOWN")

    ball_x = state.get("ball_x", 0)
    ball_y = state.get("ball_y", 0)
    paddle_x = state.get("paddle_x", 0)
    paddle_w = state.get("paddle_w", 0)

    minutes = int(play_time) // 60
    seconds = int(play_time) % 60

    return (
        f"Game state: {game_state}\n"
        f"Score: {score} | Level: {level} | Lives: {lives}\n"
        f"Play time: {minutes}m {seconds}s\n"
        f"Bricks remaining: {total_bricks}\n"
        f"Ball position: ({ball_x:.0f}, {ball_y:.0f})\n"
        f"Paddle position: x={paddle_x:.0f}, width={paddle_w:.0f}"
    )
