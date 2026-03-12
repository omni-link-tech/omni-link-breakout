/**
 * OmniLink Breakout Agent
 * ─────────────────────────────────────────────────────────────
 * Target : Browser / OmniLink Tool environment (ESM / isolated Worker)
 *
 * Architecture:
 *   GET  http://localhost:5002/data      ← paddle x, ball x/y, velocity
 *   POST http://localhost:5002/callback  → action: LEFT|RIGHT|STOP
 *   MQTT ws://localhost:9001  olink/commands  ← pause/resume
 */

// ── Logging flags ─────────────────────────────────────────────────────────────
const LOG_DECISION = false;
const LOG_ACTION = false;
const LOG_EVENTS = true;
const LOG_ERRORS = true;
const LOG_MQTT = true;

// ── Config ────────────────────────────────────────────────────────────────────
const API_URL = "http://localhost:5002";
const POLL_DELAY_MS = 50; // Slower reaction to make it miss occasionally
const MQTT_WS_URL = "ws://localhost:9001";
const CMD_TOPIC = "olink/commands";

interface Brick {
    x: number; y: number; w: number; h: number;
}

interface GameState {
    type: "state";
    paddle_x: number;
    paddle_w: number;
    ball_x: number;
    ball_y: number;
    ball_dx: number;
    ball_dy: number;
    bricks: Brick[];
    score: number;
    level: number;
    lives: number;
    play_time: number;
    game_state: string; // TITLE | PLAY | PAUSE | GAMEOVER | VICTORY
    width: number;
    height: number;
}

interface PyState {
    command: "IDLE" | "ACTIVATE";
    payload: string;
    version: number;
}

interface AgentAction {
    action: "LEFT" | "RIGHT" | "STOP";
    version: number;
    timestamp: string;
}

// ── State variables ───────────────────────────────────────────────────────────
let lastVersion = -1;
let lastScore = -1;
let lastLevel = -1;
let lastLives = -1;
let lastState = "";

// ── Prediction logic ──────────────────────────────────────────────────────────
function predictBallX(state: GameState): number {
    // If ball is moving up, just try to stay centered on it
    if (state.ball_dy < 0) {
        return state.ball_x;
    }

    // Ball is moving down. Calculate intercept with paddle height
    const paddle_y = state.height - 50;
    let b_x = state.ball_x;
    let b_y = state.ball_y;
    let dx = state.ball_dx;
    let dy = state.ball_dy;

    // Simulate bounces off walls until it reaches paddle_y
    let timeToIntercept = (paddle_y - b_y) / dy;
    let projected_x = b_x + dx * timeToIntercept;

    // Fold projected_x into bounds (bounces)
    const bounds = state.width;

    while (projected_x < 0 || projected_x > bounds) {
        if (projected_x < 0) {
            projected_x = -projected_x;
        } else if (projected_x > bounds) {
            projected_x = bounds - (projected_x - bounds);
        }
    }

    return projected_x;
}

function decideAction(state: GameState): "LEFT" | "RIGHT" | "STOP" {
    let targetX = predictBallX(state);

    // Introduce random noise to prediction
    const noise = (Math.random() - 0.5) * 30; // +/- 15px off
    targetX += noise;

    // Introduce random hesitation
    if (Math.random() < 0.05) {
        return "STOP";
    }

    const paddleCenter = state.paddle_x + (state.paddle_w / 2);

    // Add a slightly larger deadzone buffer to avoid jittering but allow more sloppiness
    const buffer = 15;

    if (paddleCenter < targetX - buffer) {
        return "RIGHT";
    } else if (paddleCenter > targetX + buffer) {
        return "LEFT";
    }
    return "STOP";
}

// ── Main Poll Loop ────────────────────────────────────────────────────────────
async function agentLoop(): Promise<void> {
    try {
        const res = await fetch(`${API_URL}/data`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const wrapper: PyState = await res.json();

        if (wrapper.command === "ACTIVATE" && wrapper.version > lastVersion) {
            lastVersion = wrapper.version;
            const state: GameState = JSON.parse(wrapper.payload);

            // Log state changes
            if (state.score !== lastScore && lastScore !== -1) {
                if (LOG_EVENTS) console.log(`[GAME] Score: ${state.score} (+${state.score - lastScore})`);
            }
            lastScore = state.score;

            if (state.level !== lastLevel && lastLevel !== -1) {
                if (LOG_EVENTS) console.log(`[GAME] Level Up: ${state.level}`);
            }
            lastLevel = state.level;

            if (state.lives !== lastLives && lastLives !== -1) {
                if (LOG_EVENTS) console.log(`[GAME] Lives left: ${state.lives}`);
            }
            lastLives = state.lives;

            if (state.game_state !== lastState) {
                if (LOG_EVENTS) console.log(`[GAME] State: ${state.game_state}`);
                lastState = state.game_state;
            }

            // Decide and send action if playing
            if (state.game_state === "PLAY") {
                const move = decideAction(state);

                const actionPayload: AgentAction = {
                    action: move,
                    version: wrapper.version,
                    timestamp: new Date().toISOString()
                };

                await fetch(`${API_URL}/callback`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(actionPayload),
                });
            }
        } else if (wrapper.command === "IDLE") {
            // Optional idle loop to match the proxy expectations
        }
    } catch (err: unknown) {
        if (LOG_ERRORS) {
            const msg = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
            console.error(`[AGENT] Error: ${msg}`);
        }
    }
}

// ── MQTT pause/resume ─────────────────────────────────────────────────────────
const _g = globalThis as Record<string, unknown>;

function sendMqttCmd(cmd: "pause" | "resume"): void {
    const client = _g["mqttClient"] as any;
    if (!client) { console.warn("[MQTT] Not connected."); return; }
    const payload = JSON.stringify({ command: cmd });
    client.publish(CMD_TOPIC, payload);
    if (LOG_MQTT) console.log(`[MQTT] → '${CMD_TOPIC}': ${payload}`);
}

_g["pauseGame"] = () => sendMqttCmd("pause");
_g["resumeGame"] = () => sendMqttCmd("resume");

async function initMqtt(): Promise<void> {
    try {
        const lib = _g["mqtt"] as any;
        if (!lib) {
            console.warn("[MQTT] No global mqtt lib.");
            return;
        }
        const client = lib.connect(MQTT_WS_URL, { clientId: `breakout-agent-${Date.now()}` });
        client.on("connect", () => {
            if (LOG_MQTT) console.log(`[MQTT] ✅ Connected to ${MQTT_WS_URL}`);
            _g["mqttClient"] = client;
        });
        client.on("error", (e: Error) => { if (LOG_ERRORS) console.error("[MQTT]", e.message); });
    } catch (err) {
        if (LOG_ERRORS) console.error("[MQTT] Init failed:", err);
    }
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
console.log("╔══════════════════════════════════════════════╗");
console.log("║  🧱  OmniLink Breakout Agent                 ║");
console.log("╚══════════════════════════════════════════════╝");
console.log(`[CONFIG] API : ${API_URL}`);

initMqtt();

async function runLoop(): Promise<void> {
    await agentLoop();
    setTimeout(runLoop, POLL_DELAY_MS);
}

runLoop();
