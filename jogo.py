import pygame
import sys
import json
import os
from random import randint, uniform, choice
from dataclasses import dataclass

pygame.init()

# ── Constantes ────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 800, 619
FPS            = 60
HIGHSCORE_FILE = "highscore.json"

# Geometria da estrada
HORIZON_Y  = 210          # linha do horizonte
VP_X       = SCREEN_W // 2
ROAD_W_BOT = 540          # largura da estrada no fundo (px)
Z_NEAR     = 1.2          # profundidade do jogador
Z_FAR      = 250.0        # profundidade de spawn (horizonte)
STRIP_LEN  = 2.0          # unidades de mundo por faixa de cor
SCROLL_SPD = 0.09         # velocidade de scroll por unit de speed

# Faixas
NUM_LANES    = 5
LANE_OFF     = [-0.74, -0.37, 0.0, 0.37, 0.74]  # offsets como fração do half-road

# Cores
SKY_TOP  = ( 90, 170, 230)
SKY_BOT  = (230, 190, 120)
GRASS_A  = (180, 120,  40)
GRASS_B  = (150,  90,  25)
ROAD_A   = ( 90,  88,  85)
ROAD_B   = (112, 110, 107)
RMB_A    = (195,  40,  40)
RMB_B    = (220, 220, 220)
MARK_C   = (220, 220, 220)
WHITE    = (255, 255, 255)
BLACK    = (  0,   0,   0)
YELLOW   = (255, 215,  45)
RED      = (215,  50,  50)
GREEN    = ( 50, 205,  75)
ORANGE   = (255, 145,   0)
GRAY     = (165, 165, 165)
FUEL_HI  = ( 50, 220,  80)
FUEL_LO  = (220,  60,  60)

def lerp(a, b, t):
    return a + (b - a) * t

# ── Projeção perspectiva ──────────────────────────────────────────────────────
def project(z, lane_offset):
    """z: distância no mundo (Z_NEAR=jogador, Z_FAR=horizonte).
       lane_offset: -1.0 a +1.0 da metade da estrada.
       Retorna (screen_x, screen_y, scale) ou None se atrás da câmera."""
    if z <= 0:
        return None
    pz   = Z_NEAR / z
    sy   = int(HORIZON_Y + (SCREEN_H - HORIZON_Y) * pz)
    road = ROAD_W_BOT * pz / 2
    sx   = int(VP_X + lane_offset * road)
    return sx, sy, pz

# ── Assets ────────────────────────────────────────────────────────────────────
def load_img(path, size=None):
    img = pygame.image.load(path).convert_alpha()
    return pygame.transform.smoothscale(img, size) if size else img

def load_highscore():
    if os.path.exists(HIGHSCORE_FILE):
        try:
            with open(HIGHSCORE_FILE) as f:
                return json.load(f).get("highscore", 0)
        except Exception:
            pass
    return 0

def save_highscore(score):
    with open(HIGHSCORE_FILE, "w") as f:
        json.dump({"highscore": score}, f)

# ── Partículas ────────────────────────────────────────────────────────────────
@dataclass
class Particle:
    x: float; y: float; vx: float; vy: float
    life: int; max_life: int; color: tuple; size: float

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.3
        self.life -= 1
        return self.life > 0

    def draw(self, surf):
        r = max(1, int(self.size * self.life / self.max_life))
        a = int(255 * self.life / self.max_life)
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, a), (r, r), r)
        surf.blit(s, (int(self.x) - r, int(self.y) - r))

def explode(particles, x, y):
    colors = [(255, 100, 30), (255, 210, 50), (255, 60, 60), (200, 200, 200)]
    for _ in range(32):
        spd = uniform(2, 7)
        life = randint(16, 36)
        particles.append(Particle(
            x, y, uniform(-spd, spd), uniform(-spd, 0.5),
            life, life, choice(colors), uniform(2.5, 6)
        ))

# ── Carro inimigo ─────────────────────────────────────────────────────────────
class EnemyCar:
    W, H = 55, 90

    def __init__(self, images):
        self.images = images
        self.image  = choice(images)
        self.lane   = randint(0, NUM_LANES - 1)
        self.t      = uniform(0.05, 0.65)   # 0=horizonte, 1=jogador
        self.speed  = uniform(0.0015, 0.003) # t-units/frame (~7-12s para cruzar)

    def respawn(self, speed_mult):
        self.image = choice(self.images)
        self.lane  = randint(0, NUM_LANES - 1)
        self.t     = 0.0
        self.speed = uniform(0.002, 0.005) * speed_mult

    def update(self, speed_mult):
        self.t += self.speed * speed_mult
        return self.t

    @property
    def offset(self):
        return LANE_OFF[self.lane]

    def draw(self, surf):
        t = self.t
        if t <= 0.01 or t >= 1.1:
            return
        rh = ROAD_W_BOT * t / 2
        sx = int(VP_X + self.offset * rh)
        sy = int(HORIZON_Y + (SCREEN_H - HORIZON_Y) * t)
        w  = max(3, int(self.W * t))
        h  = max(4, int(self.H * t))
        img = pygame.transform.scale(self.image, (w, h))
        surf.blit(img, (sx - w // 2, sy - h))

# ── Lata de combustível ───────────────────────────────────────────────────────
class FuelCan:
    W, H = 26, 36

    def __init__(self, speed_mult):
        self.lane  = randint(0, NUM_LANES - 1)
        self.t     = 0.0
        self.speed = uniform(0.004, 0.007) * speed_mult

    def update(self, speed_mult):
        self.t += self.speed * speed_mult
        return self.t

    @property
    def offset(self):
        return LANE_OFF[self.lane]

    def draw(self, surf):
        t = self.t
        if t <= 0.01 or t >= 1.1:
            return
        rh = ROAD_W_BOT * t / 2
        sx = int(VP_X + self.offset * rh)
        sy = int(HORIZON_Y + (SCREEN_H - HORIZON_Y) * t)
        w  = max(3, int(self.W * t))
        h  = max(4, int(self.H * t))
        pygame.draw.rect(surf, (250, 200, 30), (sx - w // 2, sy - h, w, h))
        pygame.draw.rect(surf, (200, 50,  40), (sx - w // 4, sy - h, max(1, w // 2), max(1, h // 4)))
        if w > 5:
            pygame.draw.rect(surf, BLACK, (sx - w // 2, sy - h, w, h), 1)

# ── Jogador ───────────────────────────────────────────────────────────────────
class Player:
    W, H      = 55, 90
    MAX_LIVES  = 3
    INV_FRAMES = 90
    MAX_FUEL   = 100.0
    FUEL_DRAIN = 0.022
    KEY_DELAY  = 16

    def __init__(self, image):
        self.image   = image
        self.lane    = 2
        self.lane_f  = 2.0
        self.lives   = self.MAX_LIVES
        self.inv     = 0
        self.fuel    = self.MAX_FUEL
        self.kdelay  = 0

    @property
    def screen_pos(self):
        li = max(0, min(NUM_LANES - 1, int(self.lane_f)))
        hi = min(NUM_LANES - 1, li + 1)
        fr = self.lane_f - int(self.lane_f)
        off = lerp(LANE_OFF[li], LANE_OFF[hi], fr)
        return project(Z_NEAR, off)

    def handle_input(self, keys):
        if self.kdelay > 0:
            return
        if keys[pygame.K_LEFT] and self.lane > 0:
            self.lane -= 1
            self.kdelay = self.KEY_DELAY
        elif keys[pygame.K_RIGHT] and self.lane < NUM_LANES - 1:
            self.lane += 1
            self.kdelay = self.KEY_DELAY

    def update(self):
        self.lane_f += (self.lane - self.lane_f) * 0.2
        if self.inv > 0:
            self.inv -= 1
        if self.kdelay > 0:
            self.kdelay -= 1
        self.fuel = max(0.0, self.fuel - self.FUEL_DRAIN)

    def hit(self):
        if self.inv > 0:
            return False
        self.lives -= 1
        self.inv = self.INV_FRAMES
        return True

    def add_fuel(self, amount=35.0):
        self.fuel = min(self.MAX_FUEL, self.fuel + amount)

    def draw(self, surf):
        if self.inv > 0 and (self.inv // 6) % 2 == 0:
            return
        p = self.screen_pos
        if not p:
            return
        sx, sy, _ = p
        surf.blit(self.image, (sx - self.W // 2, sy - self.H))

# ── Gradiente de céu (pré-calculado) ─────────────────────────────────────────
def make_sky():
    s = pygame.Surface((SCREEN_W, HORIZON_Y))
    for y in range(HORIZON_Y):
        t = y / max(1, HORIZON_Y - 1)
        r = int(lerp(SKY_TOP[0], SKY_BOT[0], t))
        g = int(lerp(SKY_TOP[1], SKY_BOT[1], t))
        b = int(lerp(SKY_TOP[2], SKY_BOT[2], t))
        pygame.draw.line(s, (r, g, b), (0, y), (SCREEN_W, y))
    return s

# ── Renderiza estrada com perspectiva ─────────────────────────────────────────
DIVIDERS = [-0.555, -0.185, 0.185, 0.555]  # offsets dos divisores de faixa

def draw_road(surf, sky_surf, scroll):
    surf.blit(sky_surf, (0, 0))
    for y in range(HORIZON_Y + 1, SCREEN_H):
        pz = (y - HORIZON_Y) / (SCREEN_H - HORIZON_Y)
        if pz <= 0:
            continue
        z        = Z_NEAR / pz
        seg      = int(z / STRIP_LEN + scroll) % 2
        rh       = int(ROAD_W_BOT * pz / 2)   # half-width desta linha
        rumble   = max(1, int(rh * 0.055))
        rl, rr   = VP_X - rh, VP_X + rh

        # Grama lateral
        gc = GRASS_A if seg == 0 else GRASS_B
        pygame.draw.line(surf, gc, (0,  y), (rl, y))
        pygame.draw.line(surf, gc, (rr, y), (SCREEN_W, y))

        # Borda (rumble strip)
        rc = RMB_A if seg == 0 else RMB_B
        pygame.draw.line(surf, rc, (rl, y), (min(rl + rumble, rr), y))
        pygame.draw.line(surf, rc, (max(rr - rumble, rl), y), (rr, y))

        # Asfalto
        pygame.draw.line(surf, ROAD_A if seg == 0 else ROAD_B,
                         (rl + rumble, y), (rr - rumble, y))

        # Marcações de faixa (tracejadas — só no seg 0)
        if seg == 0:
            for div in DIVIDERS:
                mx = int(VP_X + div * rh * 2)
                if rl + rumble < mx < rr - rumble:
                    pygame.draw.line(surf, MARK_C, (mx, y), (mx + 1, y))

# ── Texto com sombra ──────────────────────────────────────────────────────────
def draw_text(surf, text, font, color, x, y, center=False):
    s = font.render(text, True, BLACK)
    m = font.render(text, True, color)
    r = m.get_rect()
    if center:
        r.center = (x, y)
    else:
        r.topleft = (x, y)
    surf.blit(s, r.move(2, 2))
    surf.blit(m, r)

def make_heart(size=26):
    s  = pygame.Surface((size, size), pygame.SRCALPHA)
    rv = size // 4
    cx = size // 2
    pygame.draw.circle(s, (220, 50, 60), (cx - rv, rv + 1), rv)
    pygame.draw.circle(s, (220, 50, 60), (cx + rv, rv + 1), rv)
    pygame.draw.polygon(s, (220, 50, 60), [(1, rv + 4), (cx, size - 2), (size - 1, rv + 4)])
    return s

# ── Jogo ──────────────────────────────────────────────────────────────────────
class Game:
    MENU = "menu"; PLAYING = "playing"; PAUSED = "paused"; GAME_OVER = "over"

    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Fuga no Horizonte")
        self.clock  = pygame.time.Clock()
        self._load_assets()
        self.highscore = load_highscore()
        self.state     = self.MENU
        self._init_game()

    def _load_assets(self):
        self.player_img = load_img("carro1.png", (55, 90))
        enemy_files     = [f"carro{i}.png" for i in range(2, 10)] + ["jipe.png", "jipe1.png"]
        self.enemy_imgs = [load_img(f, (55, 90)) for f in enemy_files]
        self.sky_surf   = make_sky()
        self.heart_img  = make_heart(28)
        self.overlay    = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.font_xl = pygame.font.SysFont("Arial Black", 54, bold=True)
        self.font_lg = pygame.font.SysFont("Arial Black", 34, bold=True)
        self.font_md = pygame.font.SysFont("Arial Black", 22, bold=True)
        self.font_sm = pygame.font.SysFont("Arial",       17)

        # Inimigos demo para animar o menu
        self.menu_enemies = [EnemyCar(self.enemy_imgs) for _ in range(5)]
        for me in self.menu_enemies:
            me.t     = uniform(0.05, 0.9)
            me.speed = uniform(0.004, 0.009)

        # Brilho do sol no horizonte (pré-calculado)
        self.sun_surf = pygame.Surface((200, 120), pygame.SRCALPHA)
        for _r in range(58, 0, -1):
            _a = int(100 * (1 - _r / 58))
            pygame.draw.circle(self.sun_surf, (255, 220, 80, _a), (100, 95), _r + 22)
        pygame.draw.circle(self.sun_surf, (255, 248, 160), (100, 95), 22)

        # Overlay degradê do menu (pré-calculado)
        self.menu_overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        for _row in range(SCREEN_H):
            _a = int(70 + 150 * _row / SCREEN_H)
            pygame.draw.line(
                self.menu_overlay, (0, 0, 0, _a),
                (0, _row), (SCREEN_W, _row)
            )

    def _init_game(self):
        self.player    = Player(self.player_img)
        self.enemies   = [EnemyCar(self.enemy_imgs) for _ in range(6)]
        self.fuel_cans = []
        self.particles = []
        self.ticks     = 0
        self.score     = 0
        self.speed     = 1.0
        self.scroll    = 0.0
        self.shake     = 0
        self.fuel_cd   = randint(450, 650)

    # ── Loop ──────────────────────────────────────────────────────────────────
    def run(self):
        while True:
            self.clock.tick(FPS)
            self._events()
            dispatch = {
                self.MENU:      self._menu,
                self.PLAYING:   self._playing,
                self.PAUSED:    self._paused,
                self.GAME_OVER: self._game_over,
            }
            dispatch[self.state]()
            pygame.display.flip()

    # ── Eventos ───────────────────────────────────────────────────────────────
    def _events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if ev.type != pygame.KEYDOWN:
                continue
            k = ev.key
            if self.state == self.MENU and k in (pygame.K_RETURN, pygame.K_SPACE):
                self._init_game(); self.state = self.PLAYING
            elif self.state == self.PLAYING and k == pygame.K_ESCAPE:
                self.state = self.PAUSED
            elif self.state == self.PAUSED:
                if k == pygame.K_ESCAPE: self.state = self.PLAYING
                if k == pygame.K_q:      self.state = self.MENU
            elif self.state == self.GAME_OVER:
                if k in (pygame.K_RETURN, pygame.K_SPACE):
                    self._init_game(); self.state = self.PLAYING
                if k == pygame.K_q:
                    self.state = self.MENU

    # ── Menu ──────────────────────────────────────────────────────────────────
    def _menu(self):
        self.scroll += SCROLL_SPD * 3.5

        # Atualiza inimigos demo
        for me in self.menu_enemies:
            me.t += me.speed
            if me.t > 1.15:
                me.t     = 0.0
                me.lane  = randint(0, NUM_LANES - 1)
                me.image = choice(self.enemy_imgs)

        # Estrada pseudo-3D rolando
        draw_road(self.screen, self.sky_surf, self.scroll)

        # Brilho do sol no horizonte
        self.screen.blit(self.sun_surf, (SCREEN_W // 2 - 100, HORIZON_Y - 95))

        # Carros demo (mais distantes primeiro)
        for me in sorted(self.menu_enemies, key=lambda o: o.t):
            me.draw(self.screen)

        # Carro do jogador na base
        self.screen.blit(self.player_img, (SCREEN_W // 2 - 27, SCREEN_H - 95))

        # Overlay degradê
        self.screen.blit(self.menu_overlay, (0, 0))

        # Título com cor pulsante
        t_ms  = pygame.time.get_ticks()
        pulse = abs((t_ms % 1800) / 900.0 - 1.0)
        tc    = (255, int(180 + 75 * pulse), int(60 * pulse))
        draw_text(self.screen, "FUGA NO HORIZONTE", self.font_xl, tc,
                  SCREEN_W // 2, 115, center=True)

        # Painel de informações
        pw, ph = 480, 200
        panel  = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 130))
        pygame.draw.rect(panel, (255, 200, 50, 120), (0, 0, pw, ph), 2,
                         border_radius=10)
        self.screen.blit(panel, (SCREEN_W // 2 - pw // 2, 195))

        draw_text(self.screen, "Desvie do trafego!",
                  self.font_md, WHITE,  SCREEN_W // 2, 215, center=True)
        draw_text(self.screen, f"Recorde: {self.highscore}s",
                  self.font_md, ORANGE, SCREEN_W // 2, 257, center=True)
        draw_text(self.screen, "Setas <- -> : trocar faixa  |  ESC: pausar",
                  self.font_sm, GRAY,   SCREEN_W // 2, 320, center=True)
        draw_text(self.screen, "Latas amarelas: combustivel extra",
                  self.font_sm, YELLOW, SCREEN_W // 2, 348, center=True)

        if (t_ms // 500) % 2 == 0:
            draw_text(self.screen, "ENTER ou ESPACO para jogar",
                      self.font_lg, GREEN, SCREEN_W // 2, 435, center=True)

    # ── Jogando ───────────────────────────────────────────────────────────────
    def _playing(self):
        keys = pygame.key.get_pressed()
        self.player.handle_input(keys)
        self.player.update()

        self.ticks  += 1
        self.score   = self.ticks // FPS
        self.speed   = min(1.0 + (self.score // 12) * 0.1, 3.2)
        self.scroll += SCROLL_SPD * self.speed

        if self.player.fuel <= 0:
            self._end_game(); return

        ox, oy = (randint(-6, 6), randint(-6, 6)) if self.shake > 0 else (0, 0)
        if self.shake > 0:
            self.shake -= 1

        # Inimigos
        for e in self.enemies:
            e.update(self.speed)
            if e.t > 1.12:
                e.respawn(self.speed)
                continue
            if 0.82 < e.t < 1.08 and e.lane == self.player.lane:
                if self.player.hit():
                    p = self.player.screen_pos
                    if p:
                        explode(self.particles, p[0], p[1] - 45)
                    self.shake = 20
                    if self.player.lives <= 0:
                        self._end_game(); return

        # Latas de combustível
        self.fuel_cd -= 1
        if self.fuel_cd <= 0:
            self.fuel_cans.append(FuelCan(self.speed))
            self.fuel_cd = randint(400, 700)

        kept = []
        for can in self.fuel_cans:
            can.update(self.speed)
            if can.t > 1.12:
                continue
            if 0.82 < can.t < 1.08 and can.lane == self.player.lane:
                self.player.add_fuel()
                continue
            kept.append(can)
        self.fuel_cans = kept

        self.particles = [p for p in self.particles if p.update()]

        # Desenho
        draw_road(self.screen, self.sky_surf, self.scroll)
        if ox or oy:
            self.screen.scroll(ox, oy)

        all_objs = sorted(self.enemies + self.fuel_cans, key=lambda o: o.t)
        for obj in all_objs:
            obj.draw(self.screen)

        self.player.draw(self.screen)

        for p in self.particles:
            p.draw(self.screen)

        self._hud()

    def _end_game(self):
        if self.score > self.highscore:
            self.highscore = self.score
            save_highscore(self.score)
        self.state = self.GAME_OVER

    # ── HUD ───────────────────────────────────────────────────────────────────
    def _hud(self):
        bar = pygame.Surface((SCREEN_W, 50), pygame.SRCALPHA)
        bar.fill((0, 0, 0, 155))
        self.screen.blit(bar, (0, 0))

        draw_text(self.screen, f"Tempo: {self.score}s",       self.font_md, WHITE,  12, 14)
        draw_text(self.screen, f"Recorde: {self.highscore}s", self.font_md, YELLOW, 180, 14)

        # Barra de combustível
        fx, fy, fw, fh = SCREEN_W - 175, 13, 135, 24
        pygame.draw.rect(self.screen, (45, 45, 45), (fx, fy, fw, fh), border_radius=5)
        fill = int(fw * self.player.fuel / Player.MAX_FUEL)
        fc = FUEL_HI if self.player.fuel > 30 else FUEL_LO
        if fill > 0:
            pygame.draw.rect(self.screen, fc, (fx, fy, fill, fh), border_radius=5)
        pygame.draw.rect(self.screen, GRAY, (fx, fy, fw, fh), 1, border_radius=5)
        draw_text(self.screen, "FUEL", self.font_sm, WHITE, fx + fw // 2, fy + 12, center=True)

        # Vidas
        for i in range(self.player.lives):
            self.screen.blit(self.heart_img, (SCREEN_W // 2 - 44 + i * 34, 11))

        # Velocidade
        vel = int((self.speed - 1.0) / 0.1) + 1
        cor = GREEN if vel <= 4 else YELLOW if vel <= 8 else RED
        draw_text(self.screen, f"Vel: {vel}", self.font_md, cor, 12, SCREEN_H - 34)

    # ── Pausado ───────────────────────────────────────────────────────────────
    def _paused(self):
        draw_road(self.screen, self.sky_surf, self.scroll)
        for e in sorted(self.enemies, key=lambda o: o.t):
            e.draw(self.screen)
        self.player.draw(self.screen)
        self._hud()
        self.overlay.fill((0, 0, 0, 175))
        self.screen.blit(self.overlay, (0, 0))
        draw_text(self.screen, "PAUSADO",         self.font_xl, YELLOW, SCREEN_W // 2, 220, center=True)
        draw_text(self.screen, "ESC - Continuar", self.font_md, WHITE,  SCREEN_W // 2, 330, center=True)
        draw_text(self.screen, "Q   - Menu",      self.font_md, GRAY,   SCREEN_W // 2, 378, center=True)

    # ── Game Over ─────────────────────────────────────────────────────────────
    def _game_over(self):
        self.scroll += SCROLL_SPD
        draw_road(self.screen, self.sky_surf, self.scroll)
        self.overlay.fill((0, 0, 0, 185))
        self.screen.blit(self.overlay, (0, 0))
        draw_text(self.screen, "GAME OVER",             self.font_xl, RED,    SCREEN_W // 2, 155, center=True)
        draw_text(self.screen, f"Tempo: {self.score}s", self.font_lg, WHITE,  SCREEN_W // 2, 258, center=True)
        if self.score >= self.highscore and self.score > 0:
            draw_text(self.screen, "NOVO RECORDE!",               self.font_md, YELLOW, SCREEN_W // 2, 318, center=True)
        else:
            draw_text(self.screen, f"Recorde: {self.highscore}s", self.font_md, ORANGE, SCREEN_W // 2, 318, center=True)
        draw_text(self.screen, "ENTER - Jogar novamente", self.font_md, GREEN, SCREEN_W // 2, 410, center=True)
        draw_text(self.screen, "Q     - Menu principal",  self.font_md, GRAY,  SCREEN_W // 2, 458, center=True)

if __name__ == "__main__":
    Game().run()
