import sys, re, threading, time, json
import pygame
from http.server import HTTPServer, BaseHTTPRequestHandler
import paho.mqtt.client as mqtt

from breakout import Breakout

# ── Configuration ──────────────────────────────────────────────────────────────
HTTP_PORT     = 5002
MQTT_BROKER   = "localhost"
MQTT_PORT     = 1883
CMD_TOPIC     = "olink/commands"
CTX_TOPIC     = "olink/context"
PUBLISH_EVERY = 5

# ── Shared state ───────────────────────────────────────────────────────────────
_GAME: Breakout = None
_VERSION      = 0

# ──────────────────────────────────────────────────────────────────────────────
# State builder
# ──────────────────────────────────────────────────────────────────────────────
def _build_state(game: Breakout) -> dict:
    return {
        "type":         "state",
        "paddle_x":     game.paddle.x,
        "paddle_w":     game.paddle.width,
        "ball_x":       game.ball.x,
        "ball_y":       game.ball.y,
        "ball_dx":      game.ball_dx,
        "ball_dy":      game.ball_dy,
        "bricks":       [{"x": b["rect"].x, "y": b["rect"].y, "w": b["rect"].width, "h": b["rect"].height} for b in game.bricks],
        "score":        game.score1,
        "level":        game.level,
        "lives":        game.lives,
        "play_time":    game.play_time,
        "game_state":   game.state,   # TITLE | PLAY | PAUSE | GAMEOVER | VICTORY
        "width":        640,
        "height":       720,
    }

# ──────────────────────────────────────────────────────────────────────────────
# Pause / resume parser
# ──────────────────────────────────────────────────────────────────────────────
def _parse_cmd(raw: str):
    raw = raw.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            for key in ("command", "action", "cmd"):
                if key in data:
                    return str(data[key])
        if isinstance(data, str):
            return data
    except json.JSONDecodeError:
        pass
    m = re.search(r'["\']?(?:command|action|cmd)["\']?\s*:\s*["\']?(\w+)["\']?', raw, re.I)
    if m:
        return m.group(1)
    if raw.lower() in ("pause", "resume", "pause_game", "resume_game"):
        return raw
    return None

def _apply_cmd(cmd: str):
    game = _GAME
    if game is None:
        return
    cmd_l = cmd.strip().lower().strip("\"'")
    if cmd_l in ("pause", "pause_game"):
        if game.state == "PLAY":
            game.toggle_pause()
            print(f"[MQTT] ⏸  PAUSED  (cmd='{cmd}')")
    elif cmd_l in ("resume", "resume_game"):
        if game.state == "PAUSE":
            game.toggle_pause()
            print(f"[MQTT] ▶  RESUMED  (cmd='{cmd}')")
    else:
        print(f"[MQTT] Unknown command: '{cmd}'")

# ──────────────────────────────────────────────────────────────────────────────
# MQTT
# ──────────────────────────────────────────────────────────────────────────────
def _on_connect(client, userdata, flags, rc, props=None):
    if rc == 0:
        print(f"[MQTT] Connected to {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(CMD_TOPIC)
        print(f"[MQTT] Subscribed to '{CMD_TOPIC}'")
    else:
        print(f"[MQTT] Connection failed rc={rc}")

def _on_message(client, userdata, msg):
    raw = msg.payload.decode("utf-8", errors="replace")
    print(f"[MQTT] ← '{msg.topic}': {raw}")
    cmd = _parse_cmd(raw)
    if cmd:
        _apply_cmd(cmd)

def _publisher_loop(client):
    last = time.time()
    while True:
        time.sleep(1)
        if time.time() - last >= PUBLISH_EVERY and _GAME is not None:
            last = time.time()
            g = _GAME
            payload = {
                "topic":     "breakout_summary",
                "score":     g.score1,
                "level":     g.level,
                "lives":     g.lives,
                "state":     g.state,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            client.publish(CTX_TOPIC, json.dumps(payload))
            print(f"[MQTT] → '{CTX_TOPIC}': score={g.score1} level={g.level} lives={g.lives}")

def start_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = _on_connect
    client.on_message = _on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"[MQTT] WARNING: Cannot connect – {e}")
        return
    threading.Thread(target=_publisher_loop, args=(client,), daemon=True, name="mqtt-pub").start()

# ──────────────────────────────────────────────────────────────────────────────
# HTTP API
# ──────────────────────────────────────────────────────────────────────────────
class BreakoutAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        global _VERSION
        if self.path != "/data":
            self.send_error(404); return
        if _GAME is None:
            self.send_error(503, "Game not ready"); return

        _VERSION += 1
        game = _GAME
        payload = {
            "command": "ACTIVATE" if game.state == "PLAY" else "IDLE",
            "payload": json.dumps(_build_state(game)),
            "version": _VERSION,
        }
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._cors(); self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/callback":
            self.send_error(404); return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            data   = json.loads(body)
            action = data.get("action")
            actions = data.get("actions")
            
            if isinstance(actions, list) and len(actions) > 0 and _GAME:
                for act in actions:
                    act_str = str(act).upper()
                    if act_str in ("LEFT", "RIGHT", "STOP"):
                        _GAME.pending_actions.append(act_str)
            elif action and isinstance(action, str) and _GAME:
                act_str = action.upper()
                if act_str in ("LEFT", "RIGHT", "STOP"):
                    _GAME.pending_actions.append(act_str)
        except Exception as e:
            print(f"[HTTP] /callback parse error: {e}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._cors(); self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

def run_http():
    server = HTTPServer(("", HTTP_PORT), BreakoutAPIHandler)
    print(f"[HTTP] API on port {HTTP_PORT}")
    server.serve_forever()

# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=run_http,   daemon=True, name="http").start()
    start_mqtt()

    print("[Game] Initialising Breakout…")
    game = Breakout()
    _GAME = game

    print("[Game] Ready – waiting for agent commands on port", HTTP_PORT)
    try:
        game.run()
    except SystemExit:
        pass
    except Exception as exc:
        print(f"[Game] Crash: {exc}")
    finally:
        print("[Game] Exiting.")
        pygame.quit()
        sys.exit(0)
