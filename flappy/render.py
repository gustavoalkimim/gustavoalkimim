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

FRAME_TICKS = 1600       # o GIF mostra o começo do voo; o placar é do voo inteiro
TICKS_PER_FRAME = 4
FALL_FRAMES = 8          # quadros da animação de queda de quem morre
INPUTS = ["height", "velocity", "pipe dist.", "gap top", "gap bottom", "gap speed"]
HIDDEN = 6
MOVING_FROM, SPACING_FROM = 50, 150

WORLD_W, WORLD_H = 480, 360
PIPE_W = 52

# Paleta roxa — mesma do resto do perfil
COLOR_BG = "#0d1117"
COLOR_SKY = "#11151f"
COLOR_PANEL = "#161b22"
COLOR_GRID = "#21262d"
COLOR_BORDER = "#30363d"
COLOR_TEXT = "#c9d1d9"
COLOR_MUTED = "#8b949e"
COLOR_ACCENT = "#A685E2"
COLOR_GOLD = "#f6c177"
COLOR_LIGHT = "#e8e1ff"
COLOR_PIPE = "#302b63"
COLOR_PIPE_LIP = "#6f5cc2"
COLOR_BIRD = "#b9a6f0"
COLOR_DEAD = "#5b6270"


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

def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:          # Pillow antigo: fonte bitmap fixa
        return ImageFont.load_default()


def make_gif(generation, replay, record):
    W, H = 700, 400
    vx, vy = 20, 20                      # canto da "tela" do jogo
    px = vx + WORLD_W + 24               # painel da direita
    title_font, big_font, label_font, tiny_font = font(15), font(28), font(12), font(11)
    frames, durations = [], []

    total = replay["birds"]
    alive_hist = []
    falling = {}                          # pássaro -> [y, vy, quadros restantes]
    prev = {}
    champion_fell = None

    def draw_world(d, frame):
        d.rectangle([vx, vy, vx + WORLD_W, vy + WORLD_H], fill=COLOR_SKY)
        for x, top, bottom in frame["p"]:
            x0, x1 = vx + x, vx + x + PIPE_W
            if x1 < vx or x0 > vx + WORLD_W:
                continue
            x0c, x1c = max(x0, vx), min(x1, vx + WORLD_W)
            d.rectangle([x0c, vy, x1c, vy + top], fill=COLOR_PIPE)
            d.rectangle([x0c, vy + bottom, x1c, vy + WORLD_H], fill=COLOR_PIPE)
            # "boca" do cano
            lx0, lx1 = max(x0 - 3, vx), min(x1 + 3, vx + WORLD_W)
            d.rectangle([lx0, vy + top - 8, lx1, vy + top], fill=COLOR_PIPE_LIP)
            d.rectangle([lx0, vy + bottom, lx1, vy + bottom + 8], fill=COLOR_PIPE_LIP)
        d.rectangle([vx, vy, vx + WORLD_W, vy + WORLD_H], outline=COLOR_BORDER)

    def bird(d, y, color, r, outline=None):
        cx, cy = vx + 90, vy + y
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=outline)
        d.ellipse([cx + r * .2, cy - r * .55, cx + r * .7, cy - r * .05], fill=COLOR_BG)   # olho

    def panel(d, frame, alive, champion_alive):
        d.text((px, 20), f"GEN {generation}", font=title_font, fill=COLOR_ACCENT)
        d.text((px, 50), f"{alive}", font=big_font, fill=COLOR_LIGHT)
        d.text((px + d.textlength(f"{alive}", font=big_font) + 4, 62), f"/ {total}", font=label_font, fill=COLOR_MUTED)
        d.text((px, 84), "alive", font=label_font, fill=COLOR_MUTED)
        d.text((px, 112), str(frame["n"]), font=big_font, fill=COLOR_LIGHT)
        d.text((px, 146), "pipes", font=label_font, fill=COLOR_MUTED)

        status = "flying" if champion_alive else f"fell at pipe {champion_fell}"
        d.ellipse([px, 178, px + 10, 188], fill=COLOR_GOLD)
        d.text((px + 16, 175), "champion", font=label_font, fill=COLOR_TEXT)
        d.text((px + 16, 191), status, font=tiny_font, fill=COLOR_GOLD if champion_alive else COLOR_MUTED)
        d.text((px, 222), f"record: {record} pipes", font=tiny_font, fill=COLOR_MUTED)

        # sparkline: quantos seguem vivos ao longo do voo
        sx, sy, sw, sh = px, 260, 150, 70
        d.rectangle([sx, sy, sx + sw, sy + sh], outline=COLOR_GRID)
        if len(alive_hist) > 1:
            n = max(len(alive_hist) - 1, 1)
            pts = [(sx + sw * i / n, sy + sh - sh * a / total) for i, a in enumerate(alive_hist)]
            d.line(pts, fill=COLOR_ACCENT, width=2)
        d.text((sx, sy + sh + 6), "survivors over time", font=tiny_font, fill=COLOR_MUTED)

    def render_frame(frame, duration, overlay=None):
        img = Image.new("RGB", (W, H), COLOR_BG)
        d = ImageDraw.Draw(img)
        draw_world(d, frame)

        for b, (y, v, left) in list(falling.items()):
            bird(d, y, COLOR_DEAD, 6)
            v += 2.4
            y = min(y + v, WORLD_H - 6)
            falling[b] = [y, v, left - 1]
            if left <= 1:
                del falling[b]

        alive = {i: y for i, y in frame["b"]}
        for i, y in alive.items():
            if i != 0:
                bird(d, y, COLOR_BIRD, 6)
        if 0 in alive:
            bird(d, alive[0], COLOR_GOLD, 9, outline=COLOR_BG)

        panel(d, frame, len(alive), 0 in alive)
        d.text((vx, H - 18), "100 neural nets from scratch in C · evolved by a genetic algorithm",
               font=tiny_font, fill=COLOR_MUTED)
        if overlay:
            d.rectangle([vx + 50, 140, vx + WORLD_W - 50, 240], fill=COLOR_PANEL, outline=COLOR_ACCENT, width=2)
            for i, (text, f, color) in enumerate(overlay):
                tw = d.textlength(text, font=f)
                d.text((vx + (WORLD_W - tw) / 2, 156 + i * 28), text, font=f, fill=color)
        frames.append(img)
        durations.append(duration)

    for frame in replay["frames"]:
        alive = {i: y for i, y in frame["b"]}
        for i, y in prev.items():
            if i not in alive:
                falling[i] = [y, 0.0, FALL_FRAMES]
                if i == 0:
                    champion_fell = frame["n"] + 1
        prev = alive
        alive_hist.append(len(alive))
        render_frame(frame, 50)

    last = replay["frames"][-1]
    while falling:                       # termina a queda dos últimos
        render_frame({**last, "b": [[i, y] for i, y in prev.items()]}, 50)

    if replay["frames"][-1]["b"] and replay["ticks"] > FRAME_TICKS:
        overlay = [
            ("...and they kept flying. Full run:", label_font, COLOR_MUTED),
            (f"best bird: {replay['best_pipes']} pipes · champion: {replay['champion_pipes']}",
             title_font, COLOR_LIGHT),
            ("reached the 500-pipe cap!" if replay["finished"]
             else f"the last one fell at pipe {replay['pipes'] + 1}", label_font, COLOR_ACCENT),
        ]
    else:
        overlay = [
            ("Everyone fell.", label_font, COLOR_MUTED),
            (f"best bird: {replay['best_pipes']} pipes", title_font, COLOR_LIGHT),
            ("next generation trains on Monday", label_font, COLOR_ACCENT),
        ]
    render_frame({**last, "b": [[i, y] for i, y in prev.items()]}, 3500, overlay)

    palette = Image.new("P", (1, 1))
    colors = [COLOR_BG, COLOR_SKY, COLOR_PANEL, COLOR_GRID, COLOR_BORDER, COLOR_TEXT, COLOR_MUTED, COLOR_ACCENT,
              COLOR_GOLD, COLOR_LIGHT, COLOR_PIPE, COLOR_PIPE_LIP, COLOR_BIRD, COLOR_DEAD]
    flat = [c for h in colors for c in hex_rgb(h)]
    # rampas pra suavizar o antialiasing do texto e das bordas dos pássaros
    for base in (COLOR_BG, COLOR_SKY, COLOR_PANEL):
        for target in (COLOR_TEXT, COLOR_MUTED, COLOR_ACCENT, COLOR_LIGHT, COLOR_GOLD, COLOR_BIRD):
            a, b = hex_rgb(base), hex_rgb(target)
            for t in (0.33, 0.66):
                flat += [round(a[i] + (b[i] - a[i]) * t) for i in range(3)]
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
