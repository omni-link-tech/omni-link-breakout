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
PADDLE_WIDTH = 60
PADDLE_HEIGHT = 10
BALL_SIZE = 10
BRICK_ROWS = 8
BRICK_COLS = 14
BRICK_WIDTH = 42
BRICK_HEIGHT = 15
BRICK_PAD = 3
BRICK_OFFSET_Y = 160
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
        self.is_fullscreen = False
        self.win_w, self.win_h = WIDTH, HEIGHT
        self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.RESIZABLE)
        self.game_surface = pygame.Surface((WIDTH, HEIGHT))
        pygame.display.set_caption("OmniLink Breakout")
        self.clock = pygame.time.Clock()
        try:
            self.font_large = pygame.font.Font(pygame.font.match_font('courier', bold=True), 60)
            self.font_small = pygame.font.Font(pygame.font.match_font('courier', bold=True), 30)
        except:
            self.font_large = pygame.font.SysFont("monospace", 60, bold=True)
            self.font_small = pygame.font.SysFont("monospace", 30, bold=True)
            
        self.reset_game()
        self.state = "TITLE"  # TITLE, PLAY, PAUSE, GAMEOVER
        
        # Async interactions
        self.pending_actions = []

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
        self.lives = 10
        self.level = 1
        self.play_time = 0.0
        self.start_ticks = pygame.time.get_ticks()
        self.paddle_v = 1000 # px/sec
        self.paddle_dir = "STOP"
        self.score_anim_timer = 0.0
        self.level_anim_timer = 0.0
        
        self.reset_level()
        
    def reset_level(self):
        self.build_bricks()
        self.reset_ball()
        
    def reset_ball(self):
        self.paddle = pygame.Rect(WIDTH//2 - PADDLE_WIDTH//2, HEIGHT - 50, PADDLE_WIDTH, PADDLE_HEIGHT)
        self.ball = pygame.Rect(WIDTH//2 - BALL_SIZE//2, HEIGHT//2, BALL_SIZE, BALL_SIZE)
        
        speed = 340 + ((self.level - 1) * 75) # Scale cleanly with levels
        angle = random.uniform(math.pi*0.25, math.pi*0.75) if random.random() < 0.5 else random.uniform(math.pi*1.25, math.pi*1.75)
        self.ball_dx = speed * math.cos(angle)
        self.ball_dy = abs(speed * math.sin(angle)) # make it go down initially
        
    def toggle_pause(self):
        if self.state == "PLAY":
            self.state = "PAUSE"
        elif self.state == "PAUSE":
            self.state = "PLAY"
            self.start_ticks = pygame.time.get_ticks() - int(self.play_time * 1000)

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            # We use current display info or just max the resolution, but FULLSCREEN usually adapts.
            # Using the actual monitor size for the surface
            info = pygame.display.Info()
            self.win_w, self.win_h = info.current_w, info.current_h
            self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.FULLSCREEN)
        else:
            self.win_w, self.win_h = WIDTH, HEIGHT
            self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.RESIZABLE)

    def step(self, dt):
        if self.state != "PLAY":
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    exit()
                elif event.type == pygame.VIDEORESIZE:
                    if not self.is_fullscreen:
                        self.win_w, self.win_h = event.w, event.h
                        self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.RESIZABLE)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_f:
                        self.toggle_fullscreen()
                    elif event.key == pygame.K_SPACE:
                        if self.state in ("TITLE", "GAMEOVER", "VICTORY"):
                            self.reset_game()
                            self.state = "PLAY"
                            self.start_ticks = pygame.time.get_ticks()
                        else:
                            self.toggle_pause()
            return
        self.play_time = (pygame.time.get_ticks() - self.start_ticks) / 1000.0

        if self.score_anim_timer > 0:
            self.score_anim_timer -= dt
        if self.level_anim_timer > 0:
            self.level_anim_timer -= dt

        # Handle events and queue
        keys = pygame.key.get_pressed()
        
        if self.pending_actions:
            # Shift from single-frame inputs to persistent velocity states
            self.paddle_dir = self.pending_actions[-1]
            self.pending_actions.clear()
            
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            elif event.type == pygame.VIDEORESIZE:
                if not self.is_fullscreen:
                    self.win_w, self.win_h = event.w, event.h
                    self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_f:
                    self.toggle_fullscreen()
                elif event.key == pygame.K_SPACE:
                    self.toggle_pause()
                    return

        # Paddle Mvmt
        if keys[pygame.K_LEFT] or self.paddle_dir == "LEFT":
            self.paddle.x -= self.paddle_v * dt
        if keys[pygame.K_RIGHT] or self.paddle_dir == "RIGHT":
            self.paddle.x += self.paddle_v * dt
            
        # Constrain Paddle
        if self.paddle.left < 0: self.paddle.left = 0
        if self.paddle.right > WIDTH: self.paddle.right = WIDTH

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
            self.score_anim_timer = 0.3

        if len(self.bricks) == 0:
            self.level += 1
            self.level_anim_timer = 0.5
            if self.level > 2:
                self.state = "VICTORY"
            else:
                self.reset_level()

    def draw(self):
        self.game_surface.fill(BLACK)
        
        # UI Animations
        score_offset_y = 0
        if self.score_anim_timer > 0:
            # Sin wave hop calculation
            progress = self.score_anim_timer / 0.3
            score_offset_y = -math.sin(progress * math.pi) * 15 # 15px bounce up

        level_offset_y = 0
        if self.level_anim_timer > 0:
            progress = self.level_anim_timer / 0.5
            level_offset_y = -math.sin(progress * math.pi) * 20 # 20px bounce up

        # UI Top Headers
        p1_txt = self.font_large.render(str(self.lives), True, WHITE)
        self.game_surface.blit(p1_txt, (50, 40))
        
        score1_txt = self.font_large.render(f"{self.score1:03d}", True, WHITE)
        self.game_surface.blit(score1_txt, (140, 40 + score_offset_y))
        
        p2_txt = self.font_large.render("LVL " + str(self.level), True, WHITE)
        self.game_surface.blit(p2_txt, (WIDTH - 250, 40 + level_offset_y))

        # Bricks
        for b in self.bricks:
            pygame.draw.rect(self.game_surface, b["color"], b["rect"])
            
        # Paddle and Ball
        pygame.draw.rect(self.game_surface, CYAN, self.paddle)
        pygame.draw.rect(self.game_surface, WHITE, self.ball)
        
        if self.state == "TITLE":
            t = self.font_small.render("PRESS SPACE TO START", True, WHITE)
            self.game_surface.blit(t, (WIDTH//2 - t.get_width()//2, HEIGHT//2 + 100))
            t_f = self.font_small.render("PRESS 'F' FOR FULLSCREEN", True, WHITE)
            self.game_surface.blit(t_f, (WIDTH//2 - t_f.get_width()//2, HEIGHT//2 + 140))
        elif self.state == "GAMEOVER":
            t = self.font_large.render("GAME OVER", True, RED)
            self.game_surface.blit(t, (WIDTH//2 - t.get_width()//2, HEIGHT//2))
            t2 = self.font_small.render("PRESS SPACE TO RESTART", True, WHITE)
            self.game_surface.blit(t2, (WIDTH//2 - t2.get_width()//2, HEIGHT//2 + 80))
        elif self.state == "VICTORY":
            t = self.font_large.render("YOU WIN", True, GREEN)
            self.game_surface.blit(t, (WIDTH//2 - t.get_width()//2, HEIGHT//2))
            t2 = self.font_small.render("PRESS SPACE TO RESTART", True, WHITE)
            self.game_surface.blit(t2, (WIDTH//2 - t2.get_width()//2, HEIGHT//2 + 80))
        elif self.state == "PAUSE":
            t = self.font_large.render("PAUSED", True, YELLOW)
            self.game_surface.blit(t, (WIDTH//2 - t.get_width()//2, HEIGHT//2))

        # Scale internal logical surface (WIDTH/HEIGHT) up/down to actual window constraints (win_w, win_h)
        scaled_surface = pygame.transform.scale(self.game_surface, (self.win_w, self.win_h))
        self.screen.blit(scaled_surface, (0, 0))

        pygame.display.flip()

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.step(dt)
            self.draw()

if __name__ == "__main__":
    b = Breakout()
    b.run()
