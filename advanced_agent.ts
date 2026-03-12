/**
 * OmniLink Breakout Advanced Agent
 * ─────────────────────────────────────────────────────────────
 * Target : Browser / OmniLink Tool environment (ESM / isolated Worker)
 *
 * Architecture:
 *   GET  http://localhost:5002/data      ← paddle x, ball x/y, velocity
 *   POST http://localhost:5002/callback  → action: LEFT|RIGHT|STOP
 *   MQTT ws://localhost:9001  olink/commands  ← pause/resume
 */

// ── Logging flags ─────────────────────────────────────────────────────────────
const ADV_LOG_DECISION = false;
const ADV_LOG_ACTION = false;
const ADV_LOG_EVENTS = true;
const ADV_LOG_ERRORS = true;
const ADV_LOG_MQTT = true;

// ── Config ────────────────────────────────────────────────────────────────────
const ADV_API_URL = "http://localhost:5002";
const ADV_POLL_DELAY_MS = 16; // Perfectly matched to 60fps update loop (16.6ms)
const ADV_MQTT_WS_URL = "ws://localhost:9001";
const ADV_CMD_TOPIC = "olink/commands";

interface AdvBrick {
    x: number; y: number; w: number; h: number;
}

interface AdvGameState {
    type: "state";
    paddle_x: number;
    paddle_w: number;
    ball_x: number;
    ball_y: number;
    ball_dx: number;
    ball_dy: number;
    bricks: AdvBrick[];
    score: number;
    level: number;
    lives: number;
    play_time: number;
    game_state: string; // TITLE | PLAY | PAUSE | GAMEOVER | VICTORY
    width: number;
    height: number;
}

interface AdvPyState {
    command: "IDLE" | "ACTIVATE";
    payload: string;
    version: number;
}

interface AdvAgentAction {
    action: "LEFT" | "RIGHT" | "STOP";
    version: number;
    timestamp: string;
}

// ── State variables ───────────────────────────────────────────────────────────
let advLastVersion = -1;
let advLastScore = -1;
let advLastLevel = -1;
let advLastLives = -1;
let advLastState = "";

// ── Prediction logic ──────────────────────────────────────────────────────────
function advPredictBallX(state: AdvGameState): number {
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

function advGetTargetBrickX(state: AdvGameState): number | null {
    if (!state.bricks || state.bricks.length === 0) return null;

    // Find the lowest brick (highest Y value)
    let lowestBrick = state.bricks[0];
    for (let i = 1; i < state.bricks.length; i++) {
        if (state.bricks[i].y > lowestBrick.y) {
            lowestBrick = state.bricks[i];
        }
    }

    // Return the center X of the lowest brick
    return lowestBrick.x + (lowestBrick.w / 2);
}

function advDecideAction(state: AdvGameState): "LEFT" | "RIGHT" | "STOP" {
    let targetX = advPredictBallX(state);
    const paddleCenter = state.paddle_x + (state.paddle_w / 2);

    // Apply Targeting Offset
    // Breakout paddle logic: The distance from paddle center alters the bounce angle.
    // We calculate the horizontal distance to the lowest brick and bias the target
    // so the ball strikes the edge of the paddle required to curve into it.
    const targetBrickX = advGetTargetBrickX(state);
    if (targetBrickX !== null) {
        const deltaX = targetBrickX - targetX;

        // Map deltaX to a proportional paddle offset (max offset slightly less than half paddle width to avoid edge misses)
        // A standard 60px paddle means max safe offset is ~20px
        const maxOffset = (state.paddle_w / 2) - 10;

        // Clamp the bias based on distance so it scales linearly up to the max offset
        const rawBias = (deltaX / state.width) * maxOffset * 4; // Multiplier accelerates the curve
        const finalBias = Math.max(-maxOffset, Math.min(maxOffset, rawBias));

        // Subtracted bias pushes the paddle relative to ball interception, generating desired ricochet
        targetX -= finalBias;
    } else {
        // Fallback to dead-center strictly if no bricks
        targetX += 5;
    }

    // Add a tiny deadzone buffer to avoid jittering
    const buffer = 2; // Tighter buffer for advanced agent

    if (paddleCenter < targetX - buffer) {
        return "RIGHT";
    } else if (paddleCenter > targetX + buffer) {
        return "LEFT";
    }
    return "STOP";
}

// ── Main Poll Loop ────────────────────────────────────────────────────────────
async function advAgentLoop(): Promise<void> {
    try {
        const res = await fetch(`${ADV_API_URL}/data`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const wrapper: AdvPyState = await res.json();

        if (wrapper.command === "ACTIVATE" && wrapper.version > advLastVersion) {
            advLastVersion = wrapper.version;
            const state: AdvGameState = JSON.parse(wrapper.payload);

            // Log state changes
            if (state.score !== advLastScore && advLastScore !== -1) {
                if (ADV_LOG_EVENTS) console.log(`[GAME] Score: ${state.score} (+${state.score - advLastScore})`);
            }
            advLastScore = state.score;

            if (state.level !== advLastLevel && advLastLevel !== -1) {
                if (ADV_LOG_EVENTS) console.log(`[GAME] Level Up: ${state.level}`);
            }
            advLastLevel = state.level;

            if (state.lives !== advLastLives && advLastLives !== -1) {
                if (ADV_LOG_EVENTS) console.log(`[GAME] Lives left: ${state.lives}`);
            }
            advLastLives = state.lives;

            if (state.game_state !== advLastState) {
                if (ADV_LOG_EVENTS) console.log(`[GAME] State: ${state.game_state}`);
                advLastState = state.game_state;
            }

            // Decide and send action if playing
            if (state.game_state === "PLAY") {
                const move = advDecideAction(state);

                const actionPayload: AdvAgentAction = {
                    action: move,
                    version: wrapper.version,
                    timestamp: new Date().toISOString()
                };

                await fetch(`${ADV_API_URL}/callback`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(actionPayload),
                });
            }
        } else if (wrapper.command === "IDLE") {
            // Optional idle loop to match the proxy expectations
        }
    } catch (err: unknown) {
        if (ADV_LOG_ERRORS) {
            const msg = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
            console.error(`[AGENT] Error: ${msg}`);
        }
    }
}

// ── MQTT pause/resume ─────────────────────────────────────────────────────────
const _gAdv = globalThis as Record<string, unknown>;

function advSendMqttCmd(cmd: "pause" | "resume"): void {
    const client = _gAdv["mqttClient"] as any;
    if (!client) { console.warn("[MQTT] Not connected."); return; }
    const payload = JSON.stringify({ command: cmd });
    client.publish(ADV_CMD_TOPIC, payload);
    if (ADV_LOG_MQTT) console.log(`[MQTT] → '${ADV_CMD_TOPIC}': ${payload}`);
}

_gAdv["pauseGame"] = () => advSendMqttCmd("pause");
_gAdv["resumeGame"] = () => advSendMqttCmd("resume");

async function advInitMqtt(): Promise<void> {
    try {
        const lib = _gAdv["mqtt"] as any;
        if (!lib) {
            console.warn("[MQTT] No global mqtt lib.");
            return;
        }
        const client = lib.connect(ADV_MQTT_WS_URL, { clientId: `advanced-breakout-agent-${Date.now()}` });
        client.on("connect", () => {
            if (ADV_LOG_MQTT) console.log(`[MQTT] ✅ Connected to ${ADV_MQTT_WS_URL}`);
            _gAdv["mqttClient"] = client;
        });
        client.on("error", (e: Error) => { if (ADV_LOG_ERRORS) console.error("[MQTT]", e.message); });
    } catch (err) {
        if (ADV_LOG_ERRORS) console.error("[MQTT] Init failed:", err);
    }
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
console.log("╔══════════════════════════════════════════════╗");
console.log("║  🚀  OmniLink Breakout Advanced Agent        ║");
console.log("╚══════════════════════════════════════════════╝");
console.log(`[CONFIG] API : ${ADV_API_URL}`);

advInitMqtt();

async function advRunLoop(): Promise<void> {
    await advAgentLoop();
    setTimeout(advRunLoop, ADV_POLL_DELAY_MS);
}

advRunLoop();

