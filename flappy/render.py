"""
IA de Flappy Bird em enxame: a engine em C (flappy/engine) treina a
população; este script guarda o histórico, grava o GIF com os 100 pássaros
voando juntos, desenha a evolução + o cérebro do campeão em SVG e atualiza
o README.

uso:
  python flappy/render.py train <gerações>
  python flappy/render.py render
"""
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
POP_PATH = ROOT / "data" / "population.txt"
HISTORY_PATH = ROOT / "data" / "history.json"
GIF_PATH = ROOT / "swarm.gif"
SVG_PATH = ROOT / "evolution.svg"
README_PATH = ROOT.parent / "README.md"
ENGINE = Path(os.environ.get("FLAPPY_ENGINE") or ROOT / "engine" / ("flappy.exe" if os.name == "nt" else "flappy"))

FRAME_TICKS = 1440       # o GIF mostra o começo do voo; o placar é do voo inteiro
TICKS_PER_FRAME = 6       # menos quadros = GIF mais leve (o cenário inteiro muda a cada quadro)
FRAME_MS = 70
FALL_FRAMES = 8          # quadros da animação de queda de quem morre
INPUTS = ["height", "velocity", "pipe dist.", "gap top", "gap bottom", "gap speed"]
HIDDEN = 6
MOVING_FROM, SPACING_FROM = 50, 150

WORLD_W, WORLD_H = 480, 360
PIPE_W = 52

# Paleta roxa — mesma do resto do perfil
COLOR_BG = "#0d1117"
COLOR_PANEL = "#161b22"
COLOR_GRID = "#21262d"
COLOR_BORDER = "#30363d"
COLOR_TEXT = "#c9d1d9"
COLOR_MUTED = "#8b949e"
COLOR_ACCENT = "#A685E2"
COLOR_GOLD = "#f6c177"
COLOR_LIGHT = "#e8e1ff"


# ------------------------------------------------------------------ engine

def engine(*args):
    out = subprocess.run([str(ENGINE), *map(str, args)], capture_output=True, text=True, check=True)
    return out.stdout


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_population():
    lines = POP_PATH.read_text(encoding="utf-8").splitlines()
    header = dict(l.split() for l in lines[1:4])
    genomes = [[float(x) for x in l.split()] for l in lines[4:] if l.strip()]
    return int(header["generation"]), genomes


def load_history():
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    return {"started_at": now(), "generations": []}


def train(generations):
    history = load_history()
    for line in engine("train", POP_PATH, generations).splitlines():
        stats = json.loads(line)
        stats["at"] = now()
        history["generations"].append(stats)
        print(line)
    HISTORY_PATH.write_text(json.dumps(history, indent=1) + "\n", encoding="utf-8")
    render()


# ------------------------------------------------------------------ GIF

# O jogo é desenhado em meia resolução (240x180 + chão) e ampliado 2x sem
# suavização: cada "pixel" vira um bloco 2x2, como em pixel art.
SCALE = 2
LOW_W, LOW_H = WORLD_W // SCALE, WORLD_H // SCALE
GROUND_H = 16                          # faixa de chão abaixo do mundo (em px baixos)
BIRD_LOW_X = 90 // SCALE

# Céu e cenário: azul de dia, mas o chão e os pássaros puxam pro roxo do perfil
SKY_BANDS = ["#3d8fe0", "#4a9be6", "#57a7eb", "#65b3ef", "#74bff3", "#84caf6", "#95d4f8", "#a7ddfa"]
CLOUD = ["#ffffff", "#e3f3fd", "#b8def6"]                       # luz, sombra, contorno
HILLS = ["#8fd9c9", "#6cc4b4"]
PIPE = {"outline": "#1d3510", "body": "#6cbf2e", "light": "#b4ec6c", "dark": "#468a1c"}
GROUND = {"top": "#6f5cc2", "stripe": "#A685E2", "dirt": "#302b63", "dot": "#24204d"}
BIRD = {
    "outline": "#2a1f4a", "eye": "#ffffff", "pupil": "#1b1530", "beak": "#ff9f1c",
    "body": "#f4f0ff", "wing": "#b9a6f0",            # enxame: branco-lilás
    "gold": "#ffc93c", "gold_wing": "#ff9f1c",       # campeão
    "crown": "#fff36b",
    "dead": "#9aa3b2", "dead_wing": "#6b7280",
}


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:          # Pillow antigo: fonte bitmap fixa
        return ImageFont.load_default()


def outlined(sprite, color):
    """Contorno de 1 px em volta do que não é transparente (cara de pixel art)."""
    from PIL import ImageFilter
    alpha = sprite.getchannel("A").point(lambda a: 255 if a else 0)
    grown = alpha.filter(ImageFilter.MaxFilter(3))
    edge = Image.new("RGBA", sprite.size, color)
    edge.putalpha(Image.eval(grown, lambda a: a).point(lambda a: a))
    out = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
    out.alpha_composite(edge)
    out.alpha_composite(sprite)
    return out


def bird_sprite(body, wing, wing_up, crown=False, dead=False):
    """Pássaro gordinho olhando pra direita, 16x14 px baixos."""
    img = Image.new("RGBA", (16, 14), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    top = 3
    d.ellipse([2, top, 12, top + 9], fill=body)
    if wing_up:
        d.ellipse([1, top + 1, 7, top + 5], fill=wing)
    else:
        d.ellipse([1, top + 4, 7, top + 8], fill=wing)
    d.rectangle([11, top + 4, 14, top + 6], fill=BIRD["beak"] if not dead else BIRD["dead_wing"])
    d.rectangle([8, top + 1, 10, top + 3], fill=BIRD["eye"])
    if dead:   # olho de "x"
        d.point([(8, top + 1), (10, top + 3), (10, top + 1), (8, top + 3)], fill=BIRD["pupil"])
    else:
        d.rectangle([10, top + 2, 10, top + 3], fill=BIRD["pupil"])
    if crown:
        d.rectangle([5, top - 1, 9, top], fill=BIRD["crown"])
        d.point([(5, top - 2), (7, top - 2), (9, top - 2)], fill=BIRD["crown"])
    sprite = outlined(img, BIRD["outline"])
    return sprite.transpose(Image.Transpose.FLIP_TOP_BOTTOM) if dead else sprite


def cloud_sprite(w, h, seed):
    """Nuvem feita de bolhas sobrepostas, com sombra embaixo."""
    import random
    rnd = random.Random(seed)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(6):
        r = rnd.randint(h // 3, h // 2)
        cx = rnd.randint(r, w - r)
        d.ellipse([cx - r, h - 2 * r - 1, cx + r, h - 1], fill=CLOUD[1])
    for _ in range(6):
        r = rnd.randint(h // 3, h // 2 - 1)
        cx = rnd.randint(r, w - r)
        d.ellipse([cx - r, h - 2 * r - 3, cx + r, h - 3], fill=CLOUD[0])
    return outlined(img, CLOUD[2])


def make_gif(generation, replay, record):
    W, H = 700, 440
    vx, vy = 20, 20                                  # canto da tela do jogo (px reais)
    px = vx + WORLD_W + 24                           # painel da direita
    title_font, big_font, label_font, tiny_font = font(15), font(28), font(12), font(11)
    score_font = font(40)
    frames, durations = [], []

    sprites = {
        ("swarm", up): bird_sprite(BIRD["body"], BIRD["wing"], up) for up in (False, True)
    }
    sprites.update({("champ", up): bird_sprite(BIRD["gold"], BIRD["gold_wing"], up, crown=True)
                    for up in (False, True)})
    dead_sprite = bird_sprite(BIRD["dead"], BIRD["dead_wing"], False, dead=True)
    clouds = [(cloud_sprite(44, 16, s), s * 97 % 260, 8 + s * 13 % 50) for s in range(1, 6)]

    total = replay["birds"]
    alive_hist = []
    falling = {}                                     # pássaro -> [y, vy, quadros restantes]
    prev, prev_y = {}, {}
    champion_fell = None

    def scenery(low, tick):
        d = ImageDraw.Draw(low)
        band = LOW_H / len(SKY_BANDS)
        for i, c in enumerate(SKY_BANDS):
            d.rectangle([0, int(i * band), LOW_W, int((i + 1) * band)], fill=c)
        for sprite, x0, y0 in clouds:                # nuvens: parallax lento
            x = (x0 - tick * 0.25) % (LOW_W + 60) - 50
            low.alpha_composite(sprite, (int(x), int(y0)))
        for k in range(-1, LOW_W // 40 + 2):          # morrinhos parados: mexer tudo pesa no GIF
            cx = k * 40 + 20
            d.ellipse([cx - 22, LOW_H - 14, cx + 22, LOW_H + 20], fill=HILLS[k % 2])

    def pipes(low, frame):
        d = ImageDraw.Draw(low)
        for x, top, bottom in frame["p"]:
            x0 = int(x / SCALE)
            w = PIPE_W // SCALE
            t, b = int(top / SCALE), int(bottom / SCALE)
            for y0, y1, lip_y in ((0, t, t - 6), (b, LOW_H, b)):
                d.rectangle([x0, y0, x0 + w - 1, y1], fill=PIPE["outline"])
                d.rectangle([x0 + 1, y0, x0 + w - 2, y1], fill=PIPE["body"])
                d.rectangle([x0 + 3, y0, x0 + 5, y1], fill=PIPE["light"])
                d.rectangle([x0 + w - 5, y0, x0 + w - 3, y1], fill=PIPE["dark"])
                # boca do cano, um pouco mais larga
                d.rectangle([x0 - 2, lip_y, x0 + w + 1, lip_y + 6], fill=PIPE["outline"])
                d.rectangle([x0 - 1, lip_y + 1, x0 + w, lip_y + 5], fill=PIPE["body"])
                d.rectangle([x0 + 1, lip_y + 1, x0 + 3, lip_y + 5], fill=PIPE["light"])
                d.rectangle([x0 + w - 4, lip_y + 1, x0 + w - 2, lip_y + 5], fill=PIPE["dark"])

    def ground(low, tick):
        d = ImageDraw.Draw(low)
        y = LOW_H
        d.rectangle([0, y, LOW_W, y + GROUND_H], fill=GROUND["dirt"])
        d.rectangle([0, y, LOW_W, y + 3], fill=GROUND["top"])
        off = -(tick * 1.5) % 8                      # listras andam com o mundo
        for k in range(-1, LOW_W // 8 + 2):
            sx = int(k * 8 + off)
            d.polygon([(sx, y + 3), (sx + 4, y + 3), (sx + 2, y + 6), (sx - 2, y + 6)], fill=GROUND["stripe"])
        for k in range(0, LOW_W, 11):
            d.point(((k + int(off) * 3) % LOW_W, y + 10 + k % 4), fill=GROUND["dot"])

    def put_bird(low, sprite, y):
        low.alpha_composite(sprite, (BIRD_LOW_X - 8, int(y / SCALE) - 8))

    def panel(d, frame, alive, champion_alive):
        d.text((px, 20), f"GEN {generation}", font=title_font, fill=COLOR_ACCENT)
        d.text((px, 50), f"{alive}", font=big_font, fill=COLOR_LIGHT)
        d.text((px + d.textlength(f"{alive}", font=big_font) + 4, 62), f"/ {total}", font=label_font, fill=COLOR_MUTED)
        d.text((px, 84), "alive", font=label_font, fill=COLOR_MUTED)
        status = "flying" if champion_alive else f"fell at pipe {champion_fell}"
        d.ellipse([px, 124, px + 10, 134], fill=BIRD["gold"])
        d.text((px + 16, 121), "champion", font=label_font, fill=COLOR_TEXT)
        d.text((px + 16, 137), status, font=tiny_font, fill=BIRD["gold"] if champion_alive else COLOR_MUTED)
        d.text((px, 168), f"record: {record} pipes", font=tiny_font, fill=COLOR_MUTED)

        sx, sy, sw, sh = px, 210, 150, 70               # quantos seguem vivos
        d.rectangle([sx, sy, sx + sw, sy + sh], outline=COLOR_GRID)
        if len(alive_hist) > 1:
            n = max(len(alive_hist) - 1, 1)
            pts = [(sx + sw * i / n, sy + sh - sh * a / total) for i, a in enumerate(alive_hist)]
            d.line(pts, fill=COLOR_ACCENT, width=2)
        d.text((sx, sy + sh + 6), "survivors over time", font=tiny_font, fill=COLOR_MUTED)

    def render_frame(frame, duration, overlay=None):
        low = Image.new("RGBA", (LOW_W, LOW_H + GROUND_H))
        scenery(low, frame["t"])
        pipes(low, frame)
        ground(low, frame["t"])

        for b, (y, v, left) in list(falling.items()):
            put_bird(low, dead_sprite, y)
            v += 2.4
            y = min(y + v, WORLD_H + 10)
            falling[b] = [y, v, left - 1]
            if left <= 1:
                del falling[b]

        alive = {i: y for i, y in frame["b"]}
        for i, y in alive.items():
            if i != 0:   # asa pra cima quando está subindo
                put_bird(low, sprites[("swarm", y < prev_y.get(i, y))], y)
        if 0 in alive:
            put_bird(low, sprites[("champ", alive[0] < prev_y.get(0, alive[0]))], alive[0])

        img = Image.new("RGB", (W, H), COLOR_BG)
        img.paste(low.convert("RGB").resize((LOW_W * SCALE, (LOW_H + GROUND_H) * SCALE), Image.Resampling.NEAREST),
                  (vx, vy))
        d = ImageDraw.Draw(img)
        score = str(frame["n"])
        tw = d.textlength(score, font=score_font)
        d.text((vx + (WORLD_W - tw) / 2, vy + 14), score, font=score_font, fill="#ffffff",
               stroke_width=3, stroke_fill=BIRD["outline"])

        panel(d, frame, len(alive), 0 in alive)
        d.text((vx, H - 18), "100 neural nets from scratch in C · evolved by a genetic algorithm",
               font=tiny_font, fill=COLOR_MUTED)
        if overlay:
            box = [vx + 60, 150, vx + WORLD_W - 60, 256]
            d.rectangle([box[0] + 4, box[1] + 4, box[2] + 4, box[3] + 4], fill=BIRD["outline"])  # sombra
            d.rectangle(box, fill="#ffffff", outline=BIRD["outline"], width=3)
            for i, (text, f, color) in enumerate(overlay):
                tw = d.textlength(text, font=f)
                d.text((vx + (WORLD_W - tw) / 2, 166 + i * 28), text, font=f, fill=color)
        frames.append(img)
        durations.append(duration)

    for frame in replay["frames"]:
        alive = {i: y for i, y in frame["b"]}
        for i, y in prev.items():
            if i not in alive:
                falling[i] = [y, -4.0, FALL_FRAMES]
                if i == 0:
                    champion_fell = frame["n"] + 1
        alive_hist.append(len(alive))
        prev_y = prev
        render_frame(frame, FRAME_MS)
        prev = alive

    last = replay["frames"][-1]
    still = {**last, "b": [[i, y] for i, y in prev.items()]}
    while falling:                                   # termina a queda dos últimos
        render_frame(still, FRAME_MS)

    dark, accent = BIRD["outline"], "#6f5cc2"
    if replay["frames"][-1]["b"] and replay["ticks"] > FRAME_TICKS:
        overlay = [
            ("...and they kept flying. Full run:", label_font, accent),
            (f"best bird: {replay['best_pipes']} pipes · champion: {replay['champion_pipes']}", title_font, dark),
            ("reached the 500-pipe cap!" if replay["finished"]
             else f"the last one fell at pipe {replay['pipes'] + 1}", label_font, accent),
        ]
    else:
        overlay = [
            ("Everyone fell.", label_font, accent),
            (f"best bird: {replay['best_pipes']} pipes", title_font, dark),
            ("next generation trains on Monday", label_font, accent),
        ]
    render_frame(still, 3500, overlay)

    # paleta fixa: todas as cores do cenário + rampas pro antialiasing do texto
    colors = [COLOR_BG, COLOR_PANEL, COLOR_GRID, COLOR_BORDER, COLOR_TEXT, COLOR_MUTED, COLOR_ACCENT,
              COLOR_LIGHT, "#ffffff", *SKY_BANDS, *CLOUD, *HILLS, *PIPE.values(), *GROUND.values(),
              *BIRD.values(), accent]
    flat = [c for h in dict.fromkeys(colors) for c in hex_rgb(h)]
    ramps = [(COLOR_BG, t) for t in (COLOR_TEXT, COLOR_MUTED, COLOR_ACCENT, COLOR_LIGHT, BIRD["gold"])]
    ramps += [("#ffffff", dark), ("#ffffff", accent), (dark, SKY_BANDS[0]), (dark, SKY_BANDS[2])]
    for base, target in ramps:
        a, b = hex_rgb(base), hex_rgb(target)
        for t in (0.33, 0.66):
            flat += [round(a[i] + (b[i] - a[i]) * t) for i in range(3)]
    palette = Image.new("P", (1, 1))
    palette.putpalette(flat + [0] * (768 - len(flat)))

    quantized = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    quantized[0].save(GIF_PATH, save_all=True, append_images=quantized[1:], duration=durations,
                      loop=0, optimize=True, disposal=1)


# ------------------------------------------------------------------ SVG

def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(history, genome):
    W, H = 860, 330
    gens = history["generations"]
    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    a("<style>"
      ".t{font-family:'Fira Code','Segoe UI',monospace;fill:" + COLOR_TEXT + "}"
      ".m{fill:" + COLOR_MUTED + "}"
      ".draw{stroke-dasharray:1;stroke-dashoffset:1;animation:draw 2.2s ease-out .3s forwards}"
      "@keyframes draw{to{stroke-dashoffset:0}}"
      ".fade{opacity:0;animation:fade 1s ease-out 1.6s forwards}@keyframes fade{to{opacity:1}}"
      "@keyframes pulse{0%,100%{r:7}50%{r:9.5}}"
      ".n{animation:pulse 2.6s ease-in-out infinite}"
      "</style>")
    a(f'<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
      f'<stop offset="0" stop-color="{COLOR_ACCENT}" stop-opacity=".35"/>'
      f'<stop offset="1" stop-color="{COLOR_ACCENT}" stop-opacity="0"/></linearGradient></defs>')
    a(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{COLOR_BG}" stroke="{COLOR_BORDER}"/>')

    # gráfico: canos passados por geração
    cx0, cy0, cw, ch = 60, 56, 360, 220
    a(f'<text class="t" x="24" y="32" font-size="12" letter-spacing="2" style="fill:{COLOR_ACCENT}">'
      f'PIPES PASSED PER GENERATION</text>')
    top = min(500, max([g["best_pipes"] for g in gens] + [60]) * 1.15)
    last = max(len(gens) - 1, 1)

    def pt(i, v):
        return cx0 + cw * i / last, cy0 + ch - ch * v / top

    for frac in (0, 0.5, 1):
        y = cy0 + ch - ch * frac
        a(f'<line x1="{cx0}" y1="{y:.1f}" x2="{cx0 + cw}" y2="{y:.1f}" stroke="{COLOR_GRID}"/>')
        a(f'<text class="t m" x="{cx0 - 8}" y="{y + 4:.1f}" font-size="10" text-anchor="end">{top * frac:.0f}</text>')
    # onde o jogo fica mais difícil
    for level, label in ((MOVING_FROM, "pipes start moving"), (SPACING_FROM, "spacing varies")):
        if level < top:
            y = cy0 + ch - ch * level / top
            a(f'<line x1="{cx0}" y1="{y:.1f}" x2="{cx0 + cw}" y2="{y:.1f}" stroke="{COLOR_GOLD}" '
              f'stroke-opacity=".5" stroke-dasharray="4 4"/>')
            a(f'<text class="t" x="{cx0 + cw - 4}" y="{y - 5:.1f}" font-size="10" text-anchor="end" '
              f'style="fill:{COLOR_GOLD}" fill-opacity=".8">{label}</text>')
    a(f'<text class="t m" x="{cx0}" y="{cy0 + ch + 18}" font-size="10">gen 0</text>')
    a(f'<text class="t m" x="{cx0 + cw}" y="{cy0 + ch + 18}" font-size="10" text-anchor="end">'
      f'gen {gens[-1]["generation"] if gens else 0}</text>')

    if len(gens) >= 2:
        best = [pt(i, g["best_pipes"]) for i, g in enumerate(gens)]
        mean = [pt(i, g["mean_pipes"]) for i, g in enumerate(gens)]
        area = f"M{cx0},{cy0 + ch} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in best) + f" L{cx0 + cw},{cy0 + ch} Z"
        a(f'<path class="fade" d="{area}" fill="url(#area)"/>')
        a(f'<polyline class="draw" pathLength="1" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in mean)}" '
          f'fill="none" stroke="{COLOR_MUTED}" stroke-width="1.5"/>')
        a(f'<polyline class="draw" pathLength="1" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in best)}" '
          f'fill="none" stroke="{COLOR_ACCENT}" stroke-width="2.5" stroke-linejoin="round"/>')
        x, y = best[-1]
        a(f'<circle class="fade" cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{COLOR_ACCENT}"/>')
    elif gens:
        _, y = pt(0, gens[0]["best_pipes"])
        a(f'<circle cx="{cx0 + cw / 2}" cy="{y:.1f}" r="4" fill="{COLOR_ACCENT}"/>')
        a(f'<text class="t m" x="{cx0 + cw / 2}" y="{y - 12:.1f}" font-size="11" text-anchor="middle">'
          f'just hatched — come back next Monday</text>')
    a(f'<text class="t" x="{cx0}" y="{H - 16}" font-size="11"><tspan style="fill:{COLOR_ACCENT}">━ best bird</tspan>'
      f'<tspan class="m">   ━ swarm average</tspan></text>')

    # cérebro do campeão
    nx_in, nx_hid, nx_out = 590, 712, 818
    a(f'<text class="t" x="460" y="32" font-size="12" letter-spacing="2" style="fill:{COLOR_ACCENT}">'
      f"CHAMPION'S BRAIN · {len(genome)} WEIGHTS</text>")
    ys = [76 + i * 36 for i in range(len(INPUTS))]
    out_y = sum(ys) / len(ys)
    n_in = len(INPUTS) + 1
    w_in = [genome[j * n_in:(j + 1) * n_in] for j in range(HIDDEN)]
    w_out = genome[HIDDEN * n_in:HIDDEN * n_in + HIDDEN]
    biggest = max(abs(w) for w in genome) or 1

    def edge(x1, y1, x2, y2, w):
        k = abs(w) / biggest
        color = COLOR_ACCENT if w > 0 else COLOR_GOLD
        a(f'<line x1="{x1}" y1="{y1:.1f}" x2="{x2}" y2="{y2:.1f}" stroke="{color}" '
          f'stroke-width="{0.3 + 2.7 * k:.2f}" stroke-opacity="{0.15 + 0.7 * k:.2f}"/>')

    for j in range(HIDDEN):
        for i in range(len(INPUTS)):
            edge(nx_in, ys[i], nx_hid, ys[j], w_in[j][i])
        edge(nx_hid, ys[j], nx_out, out_y, w_out[j])
    for i, name in enumerate(INPUTS):
        a(f'<circle cx="{nx_in}" cy="{ys[i]}" r="6" fill="{COLOR_PANEL}" stroke="{COLOR_MUTED}"/>')
        a(f'<text class="t m" x="{nx_in - 14}" y="{ys[i] + 4}" font-size="11" text-anchor="end">{esc(name)}</text>')
    for j in range(HIDDEN):
        act = math.tanh(w_in[j][-1])
        a(f'<circle class="n" style="animation-delay:{j * 0.3:.1f}s" cx="{nx_hid}" cy="{ys[j]}" r="7" '
          f'fill="{COLOR_ACCENT if act > 0 else COLOR_GOLD}" fill-opacity="{0.35 + 0.5 * abs(act):.2f}" '
          f'stroke="{COLOR_ACCENT}"/>')
    a(f'<circle cx="{nx_out}" cy="{out_y:.1f}" r="10" fill="{COLOR_ACCENT}"/>')
    a(f'<text class="t m" x="{nx_out}" y="{out_y + 28:.1f}" font-size="11" text-anchor="middle">flap?</text>')
    a(f'<text class="t" x="460" y="{H - 16}" font-size="11"><tspan style="fill:{COLOR_ACCENT}">━ excites</tspan>'
      f'<tspan style="fill:{COLOR_GOLD}">   ━ inhibits</tspan></text>')
    a("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------------ README

def phase_name(pipes):
    if pipes >= 500:
        return "beat the game (500)"
    if pipes >= SPACING_FROM:
        return "variable spacing"
    if pipes >= MOVING_FROM:
        return "moving pipes"
    return "static pipes"


def render_readme(history, replay):
    gens = history["generations"]
    last = gens[-1]
    started = datetime.strptime(history["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    weeks = (datetime.now(timezone.utc) - started).days // 7
    record = max(gens, key=lambda g: g["best_pipes"])

    body = "\n".join([
        "| Generation | Training for | Best bird | Swarm average | Record | Hardest phase reached |",
        "| :---: | :---: | :---: | :---: | :---: | :---: |",
        f"| **{last['generation']}** | {weeks} week{'s' if weeks != 1 else ''} | {last['best_pipes']:.0f} pipes "
        f"| {last['mean_pipes']:.1f} pipes | {record['best_pipes']:.0f} (gen {record['generation']}) "
        f"| {phase_name(record['best_pipes'])} |",
        "",
        "<sub>Each bird sees 6 numbers (height, velocity, next gap) → 6 hidden neurons → flap or not, 60 times a "
        "second. All 100 birds fly the same 3 worlds per generation; the gap narrows, the speed rises, pipes start "
        f"moving at pipe {MOVING_FROM} and spacing varies from pipe {SPACING_FROM} — [source](./flappy/engine) · "
        "[how it works](./flappy/README.md)</sub>",
    ])
    readme = README_PATH.read_text(encoding="utf-8")
    new = re.sub(r"(<!--START_SECTION:flappy-->).*?(<!--END_SECTION:flappy-->)",
                 lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", readme, flags=re.S)
    README_PATH.write_text(new, encoding="utf-8")


def render():
    history = load_history()
    generation, genomes = load_population()
    replay = json.loads(engine("replay", POP_PATH, 5000 + generation, FRAME_TICKS, TICKS_PER_FRAME))
    record = max(int(round(g["best_pipes"])) for g in history["generations"])

    make_gif(generation, replay, record)
    SVG_PATH.write_text(render_svg(history, genomes[0]), encoding="utf-8")
    render_readme(history, replay)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "train":
        train(int(sys.argv[2]))
    elif len(sys.argv) == 2 and sys.argv[1] == "render":
        render()
    else:
        print(__doc__)
        sys.exit(1)
