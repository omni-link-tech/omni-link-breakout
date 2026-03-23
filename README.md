# OmniLink Breakout Demo

A Pygame Breakout game controlled by a local AI engine, orchestrated through
the OmniLink platform via **tool calling**.  The AI agent never sees the game —
it simply calls the `make_move` tool, which runs a local controller that
predicts the ball trajectory and moves the paddle in real time.

This keeps API credit usage to a minimum (one call to kick off the game).

This demo showcases four core OmniLink features:

| Feature | How it is used |
|---|---|
| **Tool Calling** | Agent calls `make_move` — the platform forwards execution to the local AI controller |
| **Commands** | Agent outputs `Command: stop_game` to end the game early |
| **Short-Term Memory** | Game state (score, lives, level) is saved periodically so the agent can answer questions |
| **Chat API** | The agent can be asked about the game state at any time from the OmniLink UI |

---

## Benchmark Results

| Metric | Value |
|---|---|
| **Final Score** | 80 |
| **Level** | 1 |
| **Lives Used** | 5/5 |
| **Play Time** | 34s |
| **Bricks Destroyed** | 8/112 |
| **API Calls** | 1 kick-off + 1 review |
| **AI Strategy** | Ball trajectory prediction with brick-aware aiming |

The Breakout agent demonstrates the ball prediction and paddle aiming algorithms.
The ball speed increases rapidly with time (+5 px/sec per second), making
sustained play challenging at higher speeds.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.9 or later |
| OmniKey | Sign up at https://www.omnilink-agents.com |

Python packages:

```
pip install pygame requests
```

The OmniLink Python client (`omnilink-lib`) must be available on your
`PYTHONPATH`.  The script auto-adds `../../omnilink-lib/src` to `sys.path`,
so the default repo layout works out of the box.

---

## Quick Start

You need **two terminals**.

### 1. Start the game server (Terminal 1)

```bash
python server_wrapper.py
```

This launches:
- The **Pygame window** (640x720) — the Breakout game itself
- An **HTTP API** on **http://localhost:5002** for state polling and action sending

Press **SPACE** in the Pygame window to start playing.

### 2. Run the AI agent (Terminal 2)

```bash
cd breakout_link
python -u play_breakout.py
```

The `-u` flag disables output buffering so you see events printed in real time.

The script will wait until you press SPACE in the Pygame window to start.

### 3. Watch and interact

- **Pygame window** — Watch the AI control the paddle in real time.
- **OmniLink UI** — Log in at https://www.omnilink-agents.com, find the
  `breakout-agent` profile, and chat with it.  Ask things like *"What's the
  score?"* or *"How many lives are left?"* — the agent has the current
  game state in memory.
- **Stop the game** — Type *"stop the game"* in the OmniLink UI.  The agent
  will output `Command: stop_game`, which the script detects and ends the
  session.

---

## Configuration

All settings are at the top of `breakout_link/play_breakout.py`:

```python
BASE_URL      = "https://www.omnilink-agents.com"  # OmniLink platform URL
OMNI_KEY      = "olink_..."                         # Your OmniKey
AGENT_NAME    = "breakout-agent"                    # Agent profile name
ENGINE        = "g2-engine"                         # AI engine (see below)
POLL_INTERVAL = 0.06       # Seconds between game state polls (~16 ticks/sec)
MEMORY_EVERY  = 10         # Save state to memory every N seconds
ASK_EVERY     = 30         # Agent reviews the game every N seconds
```

### Available Engines

| Engine | Model |
|---|---|
| `g1-engine` | Gemini |
| `g2-engine` | GPT-5 |
| `g3-engine` | Grok |
| `g4-engine` | Claude |

### Free Plan Limits

- **1 agent profile** — the script creates/updates a `breakout-agent` profile.
- **Monthly credit cap** — the tool-calling architecture minimises API usage:
  1 call to kick off + 1 review call every 30 seconds of gameplay.

---

## How It Works

### Architecture

```
+---------------------+       +--------------------+       +------------------+
|   OmniLink Cloud    |       |  server_wrapper.py |       |   Pygame Window  |
|   Chat + Memory +   |       |  localhost:5002     |       |   640x720        |
|   Tool Calling      |       |  HTTP API + Game    |       |   Breakout game  |
+---------------------+       +--------------------+       +------------------+
        ^                            ^       |
        |  REST API                  |       | Pygame renders
        v                           |  HTTP  | directly
+---------------------+             |       |
|  play_breakout.py    |-------------+       |
|  + breakout_engine.py|  GET /data (poll state)
|  + breakout_api.py   |  POST /callback (send actions)
|  + OmniLinkClient    |
+---------------------+
```

### Control Loop

Unlike chess or Go (turn-based), Breakout runs as a **continuous control loop**:

```
1. Kick off            One API call: agent calls Tool: make_move
                       This confirms the agent is connected. The local
                       AI controller then takes over.

2. Poll state          breakout_api.get_state() fetches the game state
                       via GET /data: ball position, paddle position,
                       velocity, bricks, score, lives, level.

3. Predict & act       breakout_engine.decide_action():
                       - Predicts where the ball will intercept the
                         paddle row, accounting for wall bounces
                       - Returns LEFT, RIGHT, or STOP to align the
                         paddle with the predicted landing point
                       - Uses a 5px deadzone to prevent jitter

4. Send action         breakout_api.send_action() POSTs the action
                       to the game server, which queues it for the
                       next Pygame frame.

5. Check for UI stop   Every MEMORY_EVERY seconds, reads the agent's
                       memory via get_memory(). If the user typed "stop"
                       in the OmniLink UI, the agent's response contains
                       "Command: stop_game" — the script exits.

6. Save to memory      set_memory() writes score, lives, level, and
                       ball/paddle positions so the agent can answer
                       questions from the UI.

7. Agent review        Every ASK_EVERY seconds, the script asks the
   (periodic)          agent to review. The agent either:
                       - Calls Tool: make_move → game continues
                       - Outputs Command: stop_game → game ends

8. Sleep & repeat      Waits POLL_INTERVAL seconds (~60ms), back to 2.
```

### Stopping the Game

There are three ways the session can end:

| Method | How |
|---|---|
| **Game Over** | All 5 lives lost — the Pygame window shows GAMEOVER |
| **Agent review** | Every 30s the agent evaluates the game state and can output `Command: stop_game` |
| **User via OmniLink UI** | Type "stop the game" in the chat — the script detects it on the next memory check |

### Ball Prediction Algorithm

The AI engine predicts where the ball will land at the paddle row:

1. If the ball is moving **upward** (dy <= 0), track current ball X
2. If moving **downward**, calculate time to reach paddle Y
3. Project X position: `ball_x + ball_dx * t`
4. Handle **wall bounces** by reflecting the projected X within `[0, width]`
5. Move paddle to align its centre with the predicted landing point

### OmniLink Tool Calling

```python
system_instruction = {
    "mainTask": "You are a Breakout game coordinator...",
    "availableTools": "make_move",
    "availableToolDetails": [
        {
            "name": "make_move",
            "description": "Runs the Breakout AI to move the paddle.",
        },
    ],
    "availableCommands": "stop_game",
    "allowToolUse": True,
}
```

The model responds in this format:

```
Command: none
Response: I'll keep playing.
Tool: make_move
```

---

## Key Files

| File | Description |
|---|---|
| `breakout_link/play_breakout.py` | Main script — OmniLink integration, control loop, memory sync |
| `breakout_link/breakout_engine.py` | AI controller — ball prediction, paddle movement decisions |
| `breakout_link/breakout_api.py` | HTTP client for polling state and sending actions |
| `breakout.py` | Pygame game engine — physics, rendering, collision |
| `server_wrapper.py` | HTTP + MQTT bridge wrapping the Pygame game |

---

## Game Mechanics

| Parameter | Value |
|---|---|
| Window size | 640 x 720 pixels |
| Paddle | 60 x 10 px, speed 450 px/sec |
| Ball | 10 x 10 px, initial speed 250 px/sec |
| Bricks | 8 rows x 14 columns (42 x 15 px each) |
| Lives | 5 |
| Scoring | +10 per brick, +2 ball speed per brick |
| Difficulty | Ball speed increases with time (+5 px/sec per second of play) |

---

## OmniLink Python Client — Quick Reference

```python
from omnilink.client import OmniLinkClient

client = OmniLinkClient(
    omni_key="olink_...",
    base_url="https://www.omnilink-agents.com",
)

# Chat with tool calling
result = client.chat(
    "Play Breakout. Call the make_move tool.",
    agent_name="breakout-agent",
    engine="g2-engine",
    system_instruction={...},
    temperature=0.0,
)

# Save game state to memory
client.set_memory("breakout-agent", [
    {"role": "user",  "parts": [{"text": "Current game state..."}]},
    {"role": "model", "parts": [{"text": "Score: 120, Lives: 4..."}]},
])

# Read memory (e.g. to check for a stop flag)
memory = client.get_memory("breakout-agent")
```

---

## Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `429: Monthly usage limit exceeded` | OmniKey credits exhausted | Wait for monthly reset or upgrade plan |
| `403: PROFILE_LIMIT_REACHED` | Free plan allows only 1 profile | Reuse an existing profile name |
| `Connection refused` on port 5002 | Game server not running | Start `python server_wrapper.py` first |
| Paddle doesn't move | Game not started | Press SPACE in the Pygame window |
| No output from `play_breakout.py` | Buffered stdout | Use `python -u` (unbuffered) |
| Stop from UI doesn't work | Checked between memory intervals | Try again — checked every 10 seconds |
| `ModuleNotFoundError: omnilink` | Python can't find the library | Ensure `omnilink-lib/src` is on your `PYTHONPATH` |
| `ModuleNotFoundError: pygame` | Pygame not installed | Run `pip install pygame` |
