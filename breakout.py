import pygame
import time
import math
import random

# Config
WIDTH, HEIGHT = 640, 720
FPS = 60

# Colors (Atari Breakout approximation)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
CYAN  = (0, 255, 255)
RED = (200, 72, 72)
ORANGE = (198, 108, 58)
GREEN = (180, 122, 48) # Atari breakout uses brownish/gold for green
YELLOW = (162, 162, 42)

# Mechanics
PADDLE_WIDTH = 90
PADDLE_HEIGHT = 10
BALL_SIZE = 10
BRICK_ROWS = 8
BRICK_COLS = 14
BRICK_WIDTH = 42
BRICK_HEIGHT = 15
BRICK_PAD = 3
BRICK_OFFSET_Y = 120
BRICK_OFFSET_X = (WIDTH - (BRICK_COLS * BRICK_WIDTH)) // 2

# Row colors mapping for Atari Breakout 8 rows: Red, Red, Orange, Orange, Green, Green, Yellow, Yellow
ROW_COLORS = [
    RED, RED,
    ORANGE, ORANGE,
    GREEN, GREEN,
    YELLOW, YELLOW
]

class Breakout:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("OmniLink Breakout")
        self.clock = pygame.time.Clock()
        try:
            self.font_large = pygame.font.Font(pygame.font.match_font('courier', bold=True), 60)
            self.font_small = pygame.font.Font(pygame.font.match_font('courier', bold=True), 30)
        except:
            self.font_large = pygame.font.SysFont("monospace", 60, bold=True)
            self.font_small = pygame.font.SysFont("monospace", 30, bold=True)
            
        self.reset_game()
        self.state = "PAUSE"  # Wait for controller to resume
        self.start_ticks = pygame.time.get_ticks()
        
        # Async interactions — last action wins (no queue latency)
        self.current_action = None
        self.ball_trail = []

    def build_bricks(self):
        self.bricks = []
        for row in range(BRICK_ROWS):
            color = ROW_COLORS[row]
            for col in range(BRICK_COLS):
                bx = BRICK_OFFSET_X + col * BRICK_WIDTH
                by = BRICK_OFFSET_Y + row * BRICK_HEIGHT
                self.bricks.append({"rect": pygame.Rect(bx, by, BRICK_WIDTH - BRICK_PAD, BRICK_HEIGHT - BRICK_PAD), "color": color})

    def reset_game(self):
        self.score1 = 0
        self.score2 = 0
        self.lives = 5
        self.level = 1
        self.play_time = 0.0
        self.start_ticks = pygame.time.get_ticks()
        self.paddle_v = 1400 # px/sec
        
        self.reset_level()
        
    def reset_level(self):
        self.build_bricks()
        self.reset_ball()
        
    def reset_ball(self):
        self.paddle = pygame.Rect(WIDTH//2 - PADDLE_WIDTH//2, HEIGHT - 50, PADDLE_WIDTH, PADDLE_HEIGHT)
        self.ball = pygame.Rect(WIDTH//2 - BALL_SIZE//2, HEIGHT//2, BALL_SIZE, BALL_SIZE)
        
        speed = min(250 + (self.play_time * 5), 500) # increase speed over time, capped
        angle = random.uniform(math.pi*0.25, math.pi*0.75) if random.random() < 0.5 else random.uniform(math.pi*1.25, math.pi*1.75)
        self.ball_dx = speed * math.cos(angle)
        self.ball_dy = abs(speed * math.sin(angle)) # make it go down initially
        
    def toggle_pause(self):
        if self.state == "PLAY":
            self.state = "PAUSE"
        elif self.state == "PAUSE":
            self.state = "PLAY"
            self.start_ticks = pygame.time.get_ticks() - int(self.play_time * 1000)

    def step(self, dt):
        if self.state != "PLAY":
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    exit()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        if self.state in ("TITLE", "GAMEOVER"):
                            self.reset_game()
                            self.state = "PLAY"
                            self.start_ticks = pygame.time.get_ticks()
                        else:
                            self.toggle_pause()
            return
            
        self.play_time = (pygame.time.get_ticks() - self.start_ticks) / 1000.0

        # Handle events and queue
        keys = pygame.key.get_pressed()
        action = None
        
        if self.current_action:
            action = self.current_action
            # STOP clears the action; LEFT/RIGHT persist until overwritten.
            if action == "STOP":
                self.current_action = None
            
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    self.toggle_pause()
                    return

        # Paddle Mvmt
        if keys[pygame.K_LEFT] or action == "LEFT":
            self.paddle.x -= self.paddle_v * dt
        if keys[pygame.K_RIGHT] or action == "RIGHT":
            self.paddle.x += self.paddle_v * dt
            
        # Constrain Paddle
        if self.paddle.left < 0: self.paddle.left = 0
        if self.paddle.right > WIDTH: self.paddle.right = WIDTH

        # Record ball trail
        self.ball_trail.append((self.ball.centerx, self.ball.centery))
        if len(self.ball_trail) > 10:
            self.ball_trail.pop(0)

        # Ball Mvmt
        self.ball.x += self.ball_dx * dt
        self.ball.y += self.ball_dy * dt

        # Wall Collisions
        if self.ball.left <= 0:
            self.ball.left = 0
            self.ball_dx *= -1
        elif self.ball.right >= WIDTH:
            self.ball.right = WIDTH
            self.ball_dx *= -1
            
        if self.ball.top <= 0:
            self.ball.top = 0
            self.ball_dy *= -1
            
        # Floor (Death)
        if self.ball.bottom >= HEIGHT:
            self.lives -= 1
            self.current_action = None  # clear stale direction
            if self.lives <= 0:
                self.state = "GAMEOVER"
            else:
                self.reset_ball()
            return

        # Paddle Collision
        if self.ball.colliderect(self.paddle) and self.ball_dy > 0:
            self.ball.bottom = self.paddle.top
            # Angle modification based on hit position
            offset = (self.ball.centerx - self.paddle.centerx) / (PADDLE_WIDTH / 2)
            # Prevent near-vertical bounce: enforce a strong minimum offset
            if abs(offset) < 0.4:
                offset = 0.4 if random.random() < 0.5 else -0.4
            angle = math.pi/2 - offset * math.pi/3  # between pi/6 and 5pi/6
            speed = math.hypot(self.ball_dx, self.ball_dy)
            self.ball_dx = speed * math.cos(angle)
            self.ball_dy = -abs(speed * math.sin(angle))
            
        # Brick Collision
        hit_index = self.ball.collidelist([b["rect"] for b in self.bricks])
        if hit_index != -1:
            brick = self.bricks.pop(hit_index)
            # Find collision normal
            overlap_left = self.ball.right - brick["rect"].left
            overlap_right = brick["rect"].right - self.ball.left
            overlap_top = self.ball.bottom - brick["rect"].top
            overlap_bottom = brick["rect"].bottom - self.ball.top
            
            min_overlap = min(overlap_left, overlap_right, overlap_top, overlap_bottom)
            
            if min_overlap == overlap_left or min_overlap == overlap_right:
                self.ball_dx *= -1
            else:
                self.ball_dy *= -1
                
            self.score1 += 10
            
            # Speed scaling (capped so paddle can always keep up)
            speed = math.hypot(self.ball_dx, self.ball_dy)
            speed = min(speed + 2, 500)
            # Enforce minimum horizontal speed to prevent vertical traps
            min_dx = speed * 0.15
            if abs(self.ball_dx) < min_dx:
                sign = 1 if self.ball_dx >= 0 else -1
                if sign == 0:
                    sign = 1 if random.random() < 0.5 else -1
                self.ball_dx = sign * min_dx
            angle = math.atan2(self.ball_dy, self.ball_dx)
            self.ball_dx = speed * math.cos(angle)
            self.ball_dy = speed * math.sin(angle)

        if len(self.bricks) == 0:
            self.level += 1
            self.reset_level()

    def draw(self):
        self.screen.fill((5, 5, 15))

        # Subtle horizontal lines for depth
        for y in range(0, HEIGHT, 6):
            pygame.draw.line(self.screen, (8, 8, 22), (0, y), (WIDTH, y))

        # UI Top Headers with labels
        lives_label = self.font_small.render("LIVES", True, (100, 100, 120))
        self.screen.blit(lives_label, (30, 20))
        lives_val = self.font_large.render(str(self.lives), True, WHITE)
        self.screen.blit(lives_val, (30, 48))

        score_label = self.font_small.render("SCORE", True, (100, 100, 120))
        self.screen.blit(score_label, (WIDTH // 2 - score_label.get_width() // 2, 20))
        score_val = self.font_large.render(f"{self.score1:04d}", True, WHITE)
        self.screen.blit(score_val, (WIDTH // 2 - score_val.get_width() // 2, 48))

        level_label = self.font_small.render("LEVEL", True, (100, 100, 120))
        self.screen.blit(level_label, (WIDTH - 120, 20))
        level_val = self.font_large.render(str(self.level), True, WHITE)
        self.screen.blit(level_val, (WIDTH - 120, 48))

        # Bricks with 3D highlight effect
        for b in self.bricks:
            r = b["rect"]
            color = b["color"]
            # Main brick body
            pygame.draw.rect(self.screen, color, r, border_radius=2)
            # Top/left highlight
            hi = tuple(min(255, c + 50) for c in color)
            pygame.draw.line(self.screen, hi, (r.left + 1, r.top + 1), (r.right - 2, r.top + 1))
            pygame.draw.line(self.screen, hi, (r.left + 1, r.top + 1), (r.left + 1, r.bottom - 2))
            # Bottom/right shadow
            sh = tuple(max(0, c - 60) for c in color)
            pygame.draw.line(self.screen, sh, (r.left + 1, r.bottom - 1), (r.right - 1, r.bottom - 1))
            pygame.draw.line(self.screen, sh, (r.right - 1, r.top + 1), (r.right - 1, r.bottom - 1))

        # Ball trail
        for i, (tx, ty) in enumerate(self.ball_trail):
            alpha = int(50 * (i + 1) / max(len(self.ball_trail), 1))
            size = max(1, int(BALL_SIZE * 0.3 * (i + 1) / max(len(self.ball_trail), 1)))
            trail_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(trail_surf, (200, 220, 255, alpha), (size, size), size)
            self.screen.blit(trail_surf, (int(tx) - size, int(ty) - size))

        # Ball glow
        glow_r = BALL_SIZE * 2
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (150, 200, 255, 25), (glow_r, glow_r), glow_r)
        self.screen.blit(glow_surf, (int(self.ball.centerx) - glow_r, int(self.ball.centery) - glow_r))

        # Ball (circle instead of square)
        pygame.draw.circle(self.screen, (200, 230, 255), (int(self.ball.centerx), int(self.ball.centery)), BALL_SIZE // 2 + 1)
        pygame.draw.circle(self.screen, WHITE, (int(self.ball.centerx), int(self.ball.centery)), BALL_SIZE // 2)

        # Paddle with highlight
        pygame.draw.rect(self.screen, CYAN, self.paddle, border_radius=4)
        hi_rect = pygame.Rect(self.paddle.x + 2, self.paddle.y + 1, self.paddle.width - 4, self.paddle.height // 2)
        hi_color = tuple(min(255, c + 50) for c in CYAN)
        pygame.draw.rect(self.screen, hi_color, hi_rect, border_radius=3)

        if self.state == "TITLE":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            t = self.font_large.render("BREAKOUT", True, CYAN)
            self.screen.blit(t, (WIDTH//2 - t.get_width()//2, HEIGHT//2 - 40))
            t2 = self.font_small.render("PRESS SPACE TO START", True, WHITE)
            self.screen.blit(t2, (WIDTH//2 - t2.get_width()//2, HEIGHT//2 + 40))
        elif self.state == "GAMEOVER":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            t = self.font_large.render("GAME OVER", True, RED)
            self.screen.blit(t, (WIDTH//2 - t.get_width()//2, HEIGHT//2 - 40))
            t2 = self.font_small.render(f"SCORE: {self.score1}", True, WHITE)
            self.screen.blit(t2, (WIDTH//2 - t2.get_width()//2, HEIGHT//2 + 30))
            t3 = self.font_small.render("PRESS SPACE TO RESTART", True, (160, 160, 160))
            self.screen.blit(t3, (WIDTH//2 - t3.get_width()//2, HEIGHT//2 + 70))
        elif self.state == "PAUSE":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            t = self.font_large.render("PAUSED", True, YELLOW)
            self.screen.blit(t, (WIDTH//2 - t.get_width()//2, HEIGHT//2))

        pygame.display.flip()

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.step(dt)
            self.draw()

if __name__ == "__main__":
    b = Breakout()
    b.run()
