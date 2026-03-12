# OmniLink Breakout Project

This directory contains a full Pygame implementation of Atari Breakout augmented with the OmniLink interaction architecture. The project is designed to provide both standard playable gameplay as well as external AI environment integration through HTTP REST endpoints and MQTT events.

## Features Added & Game Mechanics
- **Core Breakout Rules**: Ball bounces off walls, paddle, and destroys colored bricks.
- **Lives System**: The game provides 5 lives. 
- **Time-based Difficulty**: As the game progresses (measured in active playtime seconds), the ball's velocity will incrementally increase, making it harder to track.
- **Macro-Action API**: Capable of accepting left/right translation directives from AI tools instantly.

## Architecture & Components

The core architecture matches the OmniLink Tetris project:

- **`breakout.py` (The Game Engine)**: A Pygame environment exposing the Breakout model.
- **`server_wrapper.py` (Backend REST / MQTT Bridge)**: The server connecting the game to the AI endpoints.
  - **`GET /data` (Port 5002)**: Emits current JSON state of the board, ball, bricks, and status.
  - **`POST /callback` (Port 5002)**: Returns an array of game actions (`LEFT`, `RIGHT`, `STOP`) directly into the engine's action queue.
  - **MQTT (`olink/commands`)**: Enables toggling pause states in real-time.
  - **MQTT (`olink/context`)**: Publishes summary telemetry data of the active game (score and level tracking).
- **`agent.ts`**: The intelligent predictive agent written in Node TypeScript. It polls `/data`, predicts where the ball will intercept the paddle's Y-plane by calculating bounces, and acts immediately.

## How to Run

1. **Launch the Server & Game Environment**:
   Starting the HTTP Server and Pygame Client together:
   ```bash
   python server_wrapper.py
   ```
   At this point, the game screen will appear in an idle/waiting state to accept agent requests, or you can interact manually by pressing Space and moving with Arrow Keys.

2. **Launch the Agent**:
   Transpile and fire up the Node isolated agent.
   ```bash
   npx ts-node agent.ts
   ```
   The agent will immediately link up and start steering the paddle autonomously to catch the ball.
