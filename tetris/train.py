"""
IA de Tetris que aprende em público: a engine em C (tetris/engine) treina a
população; este script guarda o histórico, grava o GIF do campeão jogando,
desenha o gráfico de evolução + o "cérebro" em SVG e atualiza o README.

uso:
  python tetris/train.py train <gerações>
  python tetris/train.py render
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
GIF_PATH = ROOT / "replay.gif"
SVG_PATH = ROOT / "brain.svg"
README_PATH = ROOT.parent / "README.md"
ENGINE = Path(os.environ.get("TETRIS_ENGINE") or ROOT / "engine" / ("tetris.exe" if os.name == "nt" else "tetris"))

GIF_PIECES = 150                 # o GIF mostra o começo; o placar final é da partida inteira
FULL_GAME_PIECES = 1000
MINI_INDICES = [10, 30, 60, 90]  # filhos da população nova, pra comparar com o campeão
FEATURES = ["lines", "holes", "height", "bumpiness", "max height", "wells", "row trans.", "col trans."]
HIDDEN = 8

# Paleta roxa — mesma do resto do perfil
COLOR_BG = "#0d1117"
COLOR_PANEL = "#161b22"
COLOR_GRID = "#21262d"
COLOR_BORDER = "#30363d"
COLOR_TEXT = "#c9d1d9"
COLOR_MUTED = "#8b949e"
COLOR_ACCENT = "#A685E2"
COLOR_GOLD = "#f6c177"
PIECE_COLORS = {
    "I": "#7dd3fc", "O": "#fde68a", "T": "#c4b5fd", "S": "#86efac",
    "Z": "#fca5a5", "J": "#93c5fd", "L": "#fdba74",
}


# ------------------------------------------------------------------ engine

def engine(*args):
    out = subprocess.run([str(ENGINE), *map(str, args)], capture_output=True, text=True, check=True)
    return out.stdout


def load_population():
    lines = POP_PATH.read_text(encoding="utf-8").splitlines()
    header = dict(l.split() for l in lines[1:4])
    genomes = [[float(x) for x in l.split()] for l in lines[4:] if l.strip()]
    return int(header["generation"]), genomes


def load_history():
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    return {"started_at": now(), "generations": []}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def train(generations):
    history = load_history()
    out = engine("train", POP_PATH, generations)
    for line in out.splitlines():
        stats = json.loads(line)
        stats["at"] = now()
        history["generations"].append(stats)
        print(line)
    HISTORY_PATH.write_text(json.dumps(history, indent=1) + "\n", encoding="utf-8")
    render()


def replay(index, seed, pieces):
    return json.loads(engine("replay", POP_PATH, index, seed, pieces))


# ------------------------------------------------------------------ GIF

def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:          # Pillow antigo: fonte bitmap fixa
        return ImageFont.load_default()


class Board:
    """Reaplica os lances exportados pela engine pra desenhar quadro a quadro."""

    def __init__(self, game):
        self.moves = game["moves"][:GIF_PIECES]
        self.topped_out = game["over"] and len(game["moves"]) <= GIF_PIECES
        self.cells = {}
        self.i = 0
        self.score = self.lines = self.tetrises = 0

    @property
    def done(self):
        return self.i >= len(self.moves)

    @property
    def dead(self):
        return self.done and self.topped_out

    def step(self):
        move = self.moves[self.i]
        for x, y in move["cells"]:
            self.cells[(x, y)] = move["p"]
        cleared = sorted(move["cleared"])
        if cleared:
            kept = {}
            for (x, y), p in self.cells.items():
                if y in cleared:
                    continue
                kept[(x, y - sum(1 for c in cleared if c < y))] = p
            self.cells = kept
        n = len(cleared)
        self.score += [0, 100, 300, 500, 800][n]
        self.lines += n
        self.tetrises += n == 4
        self.i += 1
        return move


def draw_board(d, cells, x0, y0, cell, falling=None, flash_rows=(), dead=False):
    w, h = 10 * cell, 20 * cell
    d.rectangle([x0 - 2, y0 - 2, x0 + w + 1, y0 + h + 1], fill=COLOR_PANEL, outline=COLOR_BORDER)
    if cell >= 12:
        for gx in range(1, 10):
            d.line([x0 + gx * cell, y0, x0 + gx * cell, y0 + h - 1], fill=COLOR_GRID)
        for gy in range(1, 20):
            d.line([x0, y0 + gy * cell, x0 + w - 1, y0 + gy * cell], fill=COLOR_GRID)

    def block(x, y, color):
        if y >= 20:
            return
        px, py = x0 + x * cell, y0 + (19 - y) * cell
        d.rectangle([px + 1, py + 1, px + cell - 1, py + cell - 1], fill=color)

    for (x, y), p in cells.items():
        color = "#ffffff" if y in flash_rows else (COLOR_MUTED if dead else PIECE_COLORS[p])
        block(x, y, color)
    if falling:
        p, pts = falling
        for x, y in pts:
            block(x, y, PIECE_COLORS[p])


def make_gif(generation, champion, minis, full):
    W, H = 640, 400
    big, small = 16, 7
    bx, by = 28, 56
    title_font, big_font, label_font, tiny_font = font(15), font(26), font(12), font(11)

    main = Board(champion)
    boards = [Board(m) for m in minis]
    frames, durations = [], []

    def frame(falling=None, flash=(), duration=60, overlay=None):
        img = Image.new("RGB", (W, H), COLOR_BG)
        d = ImageDraw.Draw(img)
        d.text((bx, 20), f"GEN {generation}  ·  CHAMPION", font=title_font, fill=COLOR_ACCENT)
        draw_board(d, main.cells, bx, by, big, falling, flash)

        px = 222
        stats = [("score", f"{main.score:,}"), ("lines", str(main.lines)),
                 ("tetrises", str(main.tetrises)), ("pieces", str(main.i))]
        for i, (label, value) in enumerate(stats):
            y = by + 8 + i * 70
            d.text((px, y), value, font=big_font, fill="#e8e1ff")
            d.text((px, y + 32), label, font=label_font, fill=COLOR_MUTED)

        d.text((424, 20), "POPULATION", font=title_font, fill=COLOR_ACCENT)
        for k, b in enumerate(boards):
            mx, my = 424 + (k % 2) * 96, by + 10 + (k // 2) * 166
            draw_board(d, b.cells, mx, my, small, dead=b.dead)
            status = "game over" if b.dead else f"{b.lines} lines"
            d.text((mx, my + 144), f"#{MINI_INDICES[k]} · {status}", font=tiny_font, fill=COLOR_MUTED)

        d.text((bx, H - 22), "neural net from scratch in C · evolved by a genetic algorithm",
               font=tiny_font, fill=COLOR_MUTED)
        if overlay:
            d.rectangle([110, 150, 530, 250], fill=COLOR_PANEL, outline=COLOR_ACCENT, width=2)
            for i, (text, f, color) in enumerate(overlay):
                tw = d.textlength(text, font=f)
                d.text(((W - tw) / 2, 166 + i * 30), text, font=f, fill=color)
        frames.append(img)
        durations.append(duration)

    while not main.done:
        move = main.moves[main.i]
        top = max(y for _, y in move["cells"])
        lift = max(0, 19 - top)
        mid = lift // 2
        frame(falling=(move["p"], [(x, y + lift) for x, y in move["cells"]]), duration=40)
        frame(falling=(move["p"], [(x, y + mid) for x, y in move["cells"]]), duration=40)

        if move["cleared"]:
            for x, y in move["cells"]:
                main.cells[(x, y)] = move["p"]
            frame(flash=set(move["cleared"]), duration=110)
            main.cells = {k: v for k, v in main.cells.items() if k not in {tuple(c) for c in move["cells"]}}
        main.step()
        for b in boards:
            if not b.done:
                b.step()
    frame(duration=600)

    frame(duration=3500, overlay=[
        (f"Full game · up to {FULL_GAME_PIECES:,} pieces", label_font, COLOR_MUTED),
        (f"{full['score']:,} pts · {full['lines']} lines · {full['tetrises']} tetrises", title_font, "#e8e1ff"),
        ("survived to the end" if not full["over"] else f"topped out after {full['pieces']} pieces",
         label_font, COLOR_GOLD if full["over"] else COLOR_ACCENT),
    ])

    palette = Image.new("P", (1, 1))
    colors = [COLOR_BG, COLOR_PANEL, COLOR_GRID, COLOR_BORDER, COLOR_TEXT, COLOR_MUTED, COLOR_ACCENT,
              COLOR_GOLD, "#e8e1ff", "#ffffff", *PIECE_COLORS.values()]
    flat = [c for h in colors for c in hex_rgb(h)]
    # rampas entre fundo e textos pra suavizar o antialiasing das fontes
    for target in (COLOR_TEXT, COLOR_MUTED, COLOR_ACCENT, "#e8e1ff", COLOR_GOLD):
        a, b = hex_rgb(COLOR_BG), hex_rgb(target)
        for t in (0.25, 0.5, 0.75):
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

    # gráfico de fitness
    cx0, cy0, cw, ch = 60, 56, 360, 220
    a(f'<text class="t" x="24" y="32" font-size="12" letter-spacing="2" style="fill:{COLOR_ACCENT}">'
      f'FITNESS PER GENERATION</text>')
    top = max([g["best"] for g in gens] + [1]) * 1.1
    last = max(len(gens) - 1, 1)

    def pt(i, v):
        return cx0 + cw * i / last, cy0 + ch - ch * v / top

    for frac in (0, 0.5, 1):
        y = cy0 + ch - ch * frac
        a(f'<line x1="{cx0}" y1="{y:.1f}" x2="{cx0 + cw}" y2="{y:.1f}" stroke="{COLOR_GRID}"/>')
        a(f'<text class="t m" x="{cx0 - 8}" y="{y + 4:.1f}" font-size="10" text-anchor="end">'
          f'{top * frac / 1000:.0f}k</text>')
    a(f'<text class="t m" x="{cx0}" y="{cy0 + ch + 18}" font-size="10">gen 0</text>')
    a(f'<text class="t m" x="{cx0 + cw}" y="{cy0 + ch + 18}" font-size="10" text-anchor="end">'
      f'gen {gens[-1]["generation"] if gens else 0}</text>')

    if len(gens) >= 2:
        best = [pt(i, g["best"]) for i, g in enumerate(gens)]
        mean = [pt(i, g["mean"]) for i, g in enumerate(gens)]
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in best)
        area = f"M{cx0},{cy0 + ch} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in best) + f" L{cx0 + cw},{cy0 + ch} Z"
        a(f'<path class="fade" d="{area}" fill="url(#area)"/>')
        a(f'<polyline class="draw" pathLength="1" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in mean)}" '
          f'fill="none" stroke="{COLOR_MUTED}" stroke-width="1.5" stroke-dasharray="1"/>')
        a(f'<polyline class="draw" pathLength="1" points="{line}" fill="none" stroke="{COLOR_ACCENT}" '
          f'stroke-width="2.5" stroke-linejoin="round"/>')
        x, y = best[-1]
        a(f'<circle class="fade" cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{COLOR_ACCENT}"/>')
    elif gens:
        x, y = pt(0, gens[0]["best"])
        a(f'<circle cx="{cx0 + cw / 2}" cy="{y:.1f}" r="4" fill="{COLOR_ACCENT}"/>')
        a(f'<text class="t m" x="{cx0 + cw / 2}" y="{y - 12:.1f}" font-size="11" text-anchor="middle">'
          f'just born — come back next Monday</text>')
    a(f'<text class="t" x="{cx0}" y="{H - 16}" font-size="11"><tspan style="fill:{COLOR_ACCENT}">━ best</tspan>'
      f'<tspan class="m">   ━ population mean</tspan></text>')

    # cérebro do campeão
    nx_in, nx_hid, nx_out = 590, 712, 818
    a(f'<text class="t" x="460" y="32" font-size="12" letter-spacing="2" style="fill:{COLOR_ACCENT}">'
      f"CHAMPION'S BRAIN · {len(genome)} WEIGHTS</text>")
    ys = [64 + i * 30 for i in range(8)]
    out_y = sum(ys) / len(ys)
    n_in = len(FEATURES) + 1
    w_in = [genome[j * n_in:(j + 1) * n_in] for j in range(HIDDEN)]
    w_out = genome[HIDDEN * n_in:HIDDEN * n_in + HIDDEN]
    biggest = max(abs(w) for w in genome) or 1

    def edge(x1, y1, x2, y2, w):
        k = abs(w) / biggest
        color = COLOR_ACCENT if w > 0 else COLOR_GOLD
        a(f'<line x1="{x1}" y1="{y1:.1f}" x2="{x2}" y2="{y2:.1f}" stroke="{color}" '
          f'stroke-width="{0.3 + 2.7 * k:.2f}" stroke-opacity="{0.15 + 0.7 * k:.2f}"/>')

    for j in range(HIDDEN):
        for i in range(len(FEATURES)):
            edge(nx_in, ys[i], nx_hid, ys[j], w_in[j][i])
        edge(nx_hid, ys[j], nx_out, out_y, w_out[j])
    for i, name in enumerate(FEATURES):
        a(f'<circle cx="{nx_in}" cy="{ys[i]}" r="6" fill="{COLOR_PANEL}" stroke="{COLOR_MUTED}"/>')
        a(f'<text class="t m" x="{nx_in - 14}" y="{ys[i] + 4}" font-size="11" text-anchor="end">{esc(name)}</text>')
    for j in range(HIDDEN):
        act = math.tanh(w_in[j][-1])
        a(f'<circle class="n" style="animation-delay:{j * 0.3:.1f}s" cx="{nx_hid}" cy="{ys[j]}" r="7" '
          f'fill="{COLOR_ACCENT if act > 0 else COLOR_GOLD}" fill-opacity="{0.35 + 0.5 * abs(act):.2f}" '
          f'stroke="{COLOR_ACCENT}"/>')
    a(f'<circle cx="{nx_out}" cy="{out_y:.1f}" r="10" fill="{COLOR_ACCENT}"/>')
    a(f'<text class="t m" x="{nx_out}" y="{out_y + 28:.1f}" font-size="11" text-anchor="middle">move</text>')
    a(f'<text class="t m" x="{nx_out}" y="{out_y + 42:.1f}" font-size="11" text-anchor="middle">score</text>')
    a(f'<text class="t" x="460" y="{H - 16}" font-size="11"><tspan style="fill:{COLOR_ACCENT}">━ excites</tspan>'
      f'<tspan style="fill:{COLOR_GOLD}">   ━ inhibits</tspan></text>')
    a("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------------ README

def render_readme(history, full):
    gens = history["generations"]
    last = gens[-1]
    started = datetime.strptime(history["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    weeks = (datetime.now(timezone.utc) - started).days // 7
    record = max(gens, key=lambda g: g["best"])

    body = "\n".join([
        "| Generation | Training for | Best fitness | Record | Champion (showcase game) |",
        "| :---: | :---: | :---: | :---: | :---: |",
        f"| **{last['generation']}** | {weeks} week{'s' if weeks != 1 else ''} | {last['best']:,.0f} "
        f"| {record['best']:,.0f} (gen {record['generation']}) "
        f"| {full['lines']} lines · {full['tetrises']} tetrises |",
        "",
        "<sub>8 board features → 8 hidden neurons → 1 move score. 100 networks per generation, "
        "each plays 3 games of up to 1,000 pieces; the best 5 survive and the rest are bred by "
        "tournament selection, crossover and mutation — [source](./tetris/engine) · "
        "[how it works](./tetris/README.md)</sub>",
    ])
    readme = README_PATH.read_text(encoding="utf-8")
    new = re.sub(r"(<!--START_SECTION:tetris-->).*?(<!--END_SECTION:tetris-->)",
                 lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", readme, flags=re.S)
    README_PATH.write_text(new, encoding="utf-8")


def render():
    history = load_history()
    generation, genomes = load_population()
    shown = generation - 1                 # o campeão salvo é o da última geração avaliada
    seed = 1000 + generation               # partida de vitrine muda a cada treino

    full = replay(0, seed, FULL_GAME_PIECES)
    champion = replay(0, seed, GIF_PIECES)
    minis = [replay(i, seed, GIF_PIECES) for i in MINI_INDICES if i < len(genomes)]

    make_gif(shown, champion, minis, full)
    SVG_PATH.write_text(render_svg(history, genomes[0]), encoding="utf-8")
    render_readme(history, full)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "train":
        train(int(sys.argv[2]))
    elif len(sys.argv) == 2 and sys.argv[1] == "render":
        render()
    else:
        print(__doc__)
        sys.exit(1)
