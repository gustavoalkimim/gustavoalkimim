"""
Xadrez comunitário do perfil: visitantes jogam de brancas abrindo issues
"chess|move|e2e4"; a engine em C (chess/engine) joga de pretas.

Este script é só a "cola": lê as issues, chama a engine, guarda o estado em
chess/data/state.json, desenha chess/board.svg e reescreve a seção do README.

uso:
  python chess/play.py process <issues.json> <respostas.json>
  python chess/play.py render
"""
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

REPO = "gustavoalkimim/gustavoalkimim"
THINK_MS = 3000

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "state.json"
SVG_PATH = ROOT / "board.svg"
README_PATH = ROOT.parent / "README.md"
ENGINE = Path(os.environ.get("CHESS_ENGINE") or ROOT / "engine" / ("chess.exe" if os.name == "nt" else "chess"))

MOVE_RE = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$")

# Paleta roxa — mesma do Game of Life e do header
COLOR_BG = "#0d1117"
COLOR_BORDER = "#30363d"
COLOR_LIGHT = "#cabdf5"
COLOR_DARK = "#6f5cc2"
COLOR_ACCENT = "#A685E2"
COLOR_TEXT = "#c9d1d9"
COLOR_MUTED = "#8b949e"
COLOR_LAST_USER = "#5eead4"
COLOR_LAST_ENGINE = "#f6c177"

GLYPHS = {"k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}
WHITE_GLYPHS = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙"}
PIECE_NAMES = {"K": "King", "Q": "Queen", "R": "Rook", "B": "Bishop", "N": "Knight", "P": "Pawn"}

STATUS_TEXT = {
    "checkmate": "Checkmate",
    "stalemate": "Stalemate",
    "fifty_move": "Draw by the 50-move rule",
    "threefold": "Draw by threefold repetition",
    "insufficient_material": "Draw by insufficient material",
}


# ------------------------------------------------------------------ engine

def engine(*args):
    out = subprocess.run([str(ENGINE), *args], capture_output=True, text=True, timeout=60)
    data = json.loads(out.stdout)
    if "error" in data:
        raise ValueError(data["error"])
    return data


def engine_state(moves):
    return engine("state", *moves)


def engine_think(moves):
    return engine("think", str(THINK_MS), *moves)


# ------------------------------------------------------------------ estado

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_game(number):
    return {"number": number, "moves": [], "players": [], "log": [], "engine": None, "started_at": now()}


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {
        "game": new_game(1),
        "record": {"engine_wins": 0, "draws": 0, "engine_losses": 0},
        "leaderboard": {},
        "history": [],
    }


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def finish_game(state, st):
    """Fecha a partida: placar geral, vitórias dos jogadores e histórico."""
    game = state["game"]
    if st["status"] == "checkmate":
        result = "1-0" if st["turn"] == "black" else "0-1"
    else:
        result = "1/2-1/2"

    record = state["record"]
    if result == "1-0":
        record["engine_losses"] += 1
        for login in game["players"]:
            state["leaderboard"].setdefault(login, {"moves": 0, "wins": 0})["wins"] += 1
    elif result == "0-1":
        record["engine_wins"] += 1
    else:
        record["draws"] += 1

    game["result"] = result
    game["reason"] = st["status"]
    game["ended_at"] = now()
    state["history"].insert(0, {
        "number": game["number"], "result": result, "reason": st["status"],
        "plies": len(game["moves"]), "players": len(game["players"]), "ended_at": game["ended_at"],
    })
    del state["history"][10:]


# ------------------------------------------------------------------ issues

def issue_url(title):
    body = "Just click **Create** — a GitHub Action plays your move and my engine answers. Don't edit the title!"
    return f"https://github.com/{REPO}/issues/new?title={quote(title, safe='')}&body={quote(body, safe='')}"


def format_eval(info):
    """Avaliação do ponto de vista das brancas (a engine pensa como pretas)."""
    if not info:
        return "0.00"
    if info["mate_in"]:
        return f"M{abs(info['mate_in'])}" if info["mate_in"] < 0 else f"-M{info['mate_in']}"
    return f"{-info['score'] / 100:+.2f}"


def format_count(n):
    for div, suffix in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
        if n >= div:
            return f"{n / div:.1f}{suffix}"
    return str(n)


def handle_move(state, uci, login, issue):
    game = state["game"]
    profile = f"https://github.com/{REPO.split('/')[0]}"

    if not MOVE_RE.match(uci):
        return f"🤔 `{uci}` doesn't look like a move. Use the links on [the profile]({profile})."

    st = engine_state(game["moves"])
    if st["status"] != "ongoing":
        return (f"🏁 This game is already over ({STATUS_TEXT[st['status']]}). "
                f"[Start a new one]({issue_url('chess|new')})!")

    legal = {m["uci"]: m["san"] for m in st["legal"]}
    if uci not in legal:
        return (f"❌ `{uci}` isn't legal in the current position — someone probably moved before you. "
                f"Check the board on [the profile]({profile}) and pick another move.")

    san = legal[uci]
    game["moves"].append(uci)
    if login not in game["players"]:
        game["players"].append(login)
    entry = state["leaderboard"].setdefault(login, {"moves": 0, "wins": 0})
    entry["moves"] += 1

    move_number = (len(game["moves"]) + 1) // 2
    log = {"n": move_number, "white": san, "black": None, "user": login, "issue": issue, "at": now()}
    game["log"].append(log)

    st = engine_state(game["moves"])
    if st["status"] != "ongoing":
        finish_game(state, st)
        if st["status"] == "checkmate":
            return f"🏆 **{san}** — CHECKMATE! You beat my engine, @{login}. Legendary. 👑"
        return f"🤝 **{san}** — {STATUS_TEXT[st['status']]}. Good game, @{login}!"

    info = engine_think(game["moves"])
    info["ply"] = len(game["moves"])
    game["moves"].append(info["best"])
    game["engine"] = info
    log["black"] = info["san"]

    reply = (f"✅ You played **{san}**. My engine answered **{info['san']}** "
             f"(depth {info['depth']}, {format_count(info['nodes'])} positions in "
             f"{info['time_ms'] / 1000:.1f}s, eval {format_eval(info)}).")

    st = engine_state(game["moves"])
    if st["status"] != "ongoing":
        finish_game(state, st)
        if st["status"] == "checkmate":
            reply += "\n\n💀 That's checkmate — the engine wins this one."
        else:
            reply += f"\n\n🤝 {STATUS_TEXT[st['status']]}."
        reply += f" [Start a new game]({issue_url('chess|new')})."
    return reply + f"\n\nThe board on [the profile]({profile}) updates in a few seconds. Thanks for playing, @{login}!"


def handle_new(state, login):
    game = state["game"]
    if "result" not in game and game["moves"]:
        return "⏳ The current game isn't over yet — make a move instead!"
    if "result" in game:
        state["game"] = new_game(game["number"] + 1)
    return f"♟️ Game #{state['game']['number']} started by @{login}. You're White — make the first move!"


def process(issues_path, replies_path):
    state = load_state()
    issues = json.loads(Path(issues_path).read_text(encoding="utf-8"))
    replies = []

    # mais antigas primeiro: se duas issues propõem lances pra mesma posição,
    # a segunda é avisada que a posição mudou
    for issue in sorted(issues, key=lambda i: i["number"]):
        parts = issue["title"].strip().split("|")
        login = issue["author"]["login"]
        if parts[0].strip().lower() != "chess":
            continue
        action = parts[1].strip().lower() if len(parts) > 1 else ""
        try:
            if action == "move" and len(parts) > 2:
                body = handle_move(state, parts[2].strip().lower(), login, issue["number"])
            elif action == "new":
                body = handle_new(state, login)
            else:
                body = "🤔 Unknown command. Use the move links on the profile."
        except (ValueError, subprocess.SubprocessError, json.JSONDecodeError) as err:
            body = f"⚠️ Something went wrong processing this move: `{err}`"
        replies.append({"number": issue["number"], "body": body})
        print(f"#{issue['number']} @{login}: {issue['title']}")

    save_state(state)
    render(state)
    Path(replies_path).write_text(json.dumps(replies, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ SVG

def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def parse_board(fen):
    rows = fen.split()[0].split("/")
    board = {}
    for r, row in enumerate(rows):
        f = 0
        for ch in row:
            if ch.isdigit():
                f += int(ch)
            else:
                board[(f, 7 - r)] = ch
                f += 1
    return board


def sq_xy(sq, x0, y0, size):
    f, r = ord(sq[0]) - 97, int(sq[1]) - 1
    return x0 + f * size, y0 + (7 - r) * size


def render_svg(state, st):
    game = state["game"]
    size, x0, y0 = 50, 34, 24
    width, height = 860, 456
    board = parse_board(st["fen"])
    moves = game["moves"]
    out = []
    a = out.append

    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    a("<style>"
      ".p{font-family:'Segoe UI Symbol','Noto Sans Symbols 2','DejaVu Sans','Apple Symbols',serif;"
      "font-size:42px;text-anchor:middle;dominant-baseline:central}"
      ".w{fill:#fff;stroke:#1b1530;stroke-width:1.3px;paint-order:stroke}"
      ".b{fill:#1b1530;stroke:#efeaff;stroke-width:1px;paint-order:stroke}"
      ".t{font-family:'Fira Code','Segoe UI',monospace;fill:" + COLOR_TEXT + "}"
      ".m{fill:" + COLOR_MUTED + "}.c{font-size:11px;fill:" + COLOR_MUTED + ";font-family:'Fira Code',monospace}"
      "@keyframes pulse{0%,100%{opacity:.25}50%{opacity:.6}}"
      ".pulse{animation:pulse 2.4s ease-in-out infinite}"
      "</style>")
    a('<defs><radialGradient id="chk"><stop offset="0%" stop-color="#ff4d6d" stop-opacity=".95"/>'
      '<stop offset="100%" stop-color="#ff4d6d" stop-opacity="0"/></radialGradient>'
      f'<linearGradient id="bar" x1="0" x2="1"><stop offset="0" stop-color="{COLOR_ACCENT}"/>'
      '<stop offset="1" stop-color="#e8e1ff"/></linearGradient></defs>')
    a(f'<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="12" fill="{COLOR_BG}" stroke="{COLOR_BORDER}"/>')

    # casas
    for r in range(8):
        for f in range(8):
            color = COLOR_LIGHT if (f + r) % 2 else COLOR_DARK
            a(f'<rect x="{x0 + f * size}" y="{y0 + (7 - r) * size}" width="{size}" height="{size}" fill="{color}"/>')

    # destaques dos dois últimos lances (comunidade em roxo, engine em dourado)
    last_engine = moves[-1] if moves and len(moves) % 2 == 0 else None
    last_user = moves[-2] if last_engine and len(moves) >= 2 else (moves[-1] if moves else None)
    for mv, color in ((last_user, COLOR_LAST_USER), (last_engine, COLOR_LAST_ENGINE)):
        if not mv:
            continue
        for sq in (mv[:2], mv[2:4]):
            x, y = sq_xy(sq, x0, y0, size)
            a(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" fill="{color}" opacity=".45"/>')
    if last_engine:
        x, y = sq_xy(last_engine[2:4], x0, y0, size)
        a(f'<rect class="pulse" x="{x + 2}" y="{y + 2}" width="{size - 4}" height="{size - 4}" fill="none" '
          f'stroke="{COLOR_LAST_ENGINE}" stroke-width="3" rx="4"/>')

    if st["check"]:
        king = "K" if st["turn"] == "white" else "k"
        for (f, r), pc in board.items():
            if pc == king:
                a(f'<circle cx="{x0 + f * size + size / 2}" cy="{y0 + (7 - r) * size + size / 2}" '
                  f'r="{size * .55}" fill="url(#chk)"/>')

    # peças; a última peça da engine desliza da origem até o destino
    for (f, r), pc in sorted(board.items()):
        cx, cy = x0 + f * size + size / 2, y0 + (7 - r) * size + size / 2 + 2
        cls = "w" if pc.isupper() else "b"
        glyph = GLYPHS[pc.lower()] + "︎"
        sq = f"{chr(97 + f)}{r + 1}"
        if last_engine and sq == last_engine[2:4]:
            fx, fy = sq_xy(last_engine[:2], x0, y0, size)
            tx, ty = sq_xy(sq, x0, y0, size)
            dx, dy = fx - tx, fy - ty
            a(f'<g transform="translate({dx} {dy})"><animateTransform attributeName="transform" type="translate" '
              f'from="{dx} {dy}" to="0 0" begin="0.6s" dur="0.7s" fill="freeze" calcMode="spline" '
              f'keyTimes="0;1" keySplines=".4 0 .2 1"/>'
              f'<text class="p {cls}" x="{cx}" y="{cy}">{glyph}</text></g>')
        else:
            a(f'<text class="p {cls}" x="{cx}" y="{cy}">{glyph}</text>')

    for i in range(8):
        a(f'<text class="c" x="{x0 + i * size + size / 2}" y="{y0 + 8 * size + 16}" text-anchor="middle">{chr(97 + i)}</text>')
        a(f'<text class="c" x="{x0 - 14}" y="{y0 + (7 - i) * size + size / 2 + 4}" text-anchor="middle">{i + 1}</text>')

    # painel lateral
    px = x0 + 8 * size + 36
    info = game.get("engine")
    a(f'<text class="t" x="{px}" y="{y0 + 14}" font-size="12" letter-spacing="3" fill="{COLOR_ACCENT}" '
      f'style="fill:{COLOR_ACCENT}">COMMUNITY  vs  ENGINE</text>')

    if st["status"] == "ongoing":
        headline = "Your move, White" if st["turn"] == "white" else "Engine is thinking…"
        if st["check"]:
            headline += " (check!)"
    elif st["status"] == "checkmate":
        headline = "Checkmate — the community wins!" if st["turn"] == "black" else "Checkmate — engine wins"
    else:
        headline = STATUS_TEXT[st["status"]]
    move_no = len(moves) // 2 + 1
    a(f'<text class="t" x="{px}" y="{y0 + 48}" font-size="22" font-weight="bold">{esc(headline)}</text>')
    a(f'<text class="t m" x="{px}" y="{y0 + 72}" font-size="13">Game #{game["number"]} · move {move_no} · '
      f'{len(game["players"])} player{"s" if len(game["players"]) != 1 else ""}</text>')

    # barra de avaliação (branco à esquerda), anima do centro até o valor
    bar_w, by = 340, y0 + 96
    if info and info["mate_in"]:
        frac = 1.0 if info["mate_in"] < 0 else 0.0
    else:
        cp = -info["score"] if info else 0
        frac = 1 / (1 + math.exp(-cp / 250))
    target = max(4, min(bar_w - 4, bar_w * frac))
    a(f'<rect x="{px}" y="{by}" width="{bar_w}" height="14" rx="7" fill="#21262d"/>')
    a(f'<rect x="{px}" y="{by}" width="{target:.1f}" height="14" rx="7" fill="url(#bar)">'
      f'<animate attributeName="width" from="{bar_w / 2}" to="{target:.1f}" dur="1.2s" begin="0.3s" '
      f'fill="freeze" calcMode="spline" keyTimes="0;1" keySplines=".4 0 .2 1"/></rect>')
    a(f'<text class="t m" x="{px}" y="{by + 32}" font-size="12">eval {esc(format_eval(info))} (White\'s view)</text>')

    # números da última busca
    sy = by + 66
    stats = [
        ("depth", str(info["depth"]) if info else "–"),
        ("positions", format_count(info["nodes"]) if info else "–"),
        ("speed", f'{format_count(info["nps"])}/s' if info else "–"),
        ("time", f'{info["time_ms"] / 1000:.1f}s' if info else "–"),
    ]
    for i, (label, value) in enumerate(stats):
        sx = px + i * 88
        a(f'<text class="t" x="{sx}" y="{sy}" font-size="20" font-weight="bold" style="fill:#e8e1ff">{value}</text>')
        a(f'<text class="t m" x="{sx}" y="{sy + 18}" font-size="11">{label}</text>')

    if info and info.get("pv_san"):
        line = " ".join(info["pv_san"][:7])
        a(f'<text class="t m" x="{px}" y="{sy + 50}" font-size="12">engine expects: '
          f'<tspan style="fill:{COLOR_TEXT}">{esc(line)}</tspan></text>')

    # últimas jogadas
    ly = sy + 86
    a(f'<text class="t" x="{px}" y="{ly}" font-size="12" letter-spacing="2" style="fill:{COLOR_ACCENT}">LAST MOVES</text>')
    recent = game["log"][-5:]
    if not recent:
        a(f'<text class="t m" x="{px}" y="{ly + 24}" font-size="13">No moves yet — be the first!</text>')
    for i, entry in enumerate(reversed(recent)):
        yy = ly + 24 + i * 22
        black = entry["black"] or "…"
        a(f'<text class="t" x="{px}" y="{yy}" font-size="13">'
          f'<tspan class="m">{entry["n"]}.</tspan> {esc(entry["white"])} '
          f'<tspan style="fill:{COLOR_LAST_ENGINE}">{esc(black)}</tspan>'
          f'<tspan class="m"> · @{esc(entry["user"])}</tspan></text>')

    rec = state["record"]
    a(f'<text class="t m" x="{px}" y="{height - 22}" font-size="11">engine record: {rec["engine_wins"]}W '
      f'{rec["draws"]}D {rec["engine_losses"]}L · written from scratch in C</text>')
    a("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------------ README

HOW_TO_PLAY = [
    "<details>",
    "<summary><b>❓ How to play (step by step)</b></summary>",
    "",
    "1. **Pick a move** in the table below and click it. `e2→e4` moves the piece on **e2** to **e4**.",
    "2. GitHub opens a **New issue** page with everything already filled in. Don't change anything — "
    "just click **Create**. (You need to be logged in to GitHub.)",
    "3. **Wait about a minute.** A GitHub Action checks your move, my engine thinks for ~3 seconds and plays Black.",
    "4. The bot **replies on your issue** with the engine's move and closes it. Refresh this page to see "
    "the new position — the board image can take a few minutes to update because GitHub caches it.",
    "",
    "Everyone plays the same game together. If two people move at the same time, the first issue wins and "
    "the second one is told the position changed. Hover a move to see it in chess notation.",
    "",
    "</details>",
]


def move_label(m):
    """Lance legível pra quem não conhece notação: origem → destino."""
    san, uci = m["san"], m["uci"]
    if san.startswith("O-O-O"):
        label = "castle long"
    elif san.startswith("O-O"):
        label = "castle short"
    else:
        label = f"{uci[:2]}{'×' if 'x' in san else '→'}{uci[2:4]}"
        if len(uci) == 5:
            label += "=" + uci[4].upper()
    if san.endswith(("+", "#")):
        label += san[-1]
    return label


def render_readme(state, st):
    game = state["game"]
    lines = []

    if st["status"] == "ongoing":
        lines += [
            "**It's your move — you play White.** Pick a move below: each one reads **from → to** "
            "(`e2→e4` moves the piece on e2 to e4, `×` is a capture). Columns are **a–h** left to right, "
            "rows **1–8** from the bottom.",
            "",
            *HOW_TO_PLAY,
            "",
        ]
        groups = {}
        for m in sorted(st["legal"], key=lambda m: m["uci"]):
            san = m["san"]
            kind = "K" if san.startswith("O-O") else (san[0] if san[0] in "KQRBN" else "P")
            groups.setdefault(kind, []).append(m)
        lines.append("| Piece | Moves |")
        lines.append("| :--- | :--- |")
        for kind in "KQRBNP":
            if kind not in groups:
                continue
            # o título do link mostra a notação de xadrez (SAN) ao passar o mouse
            links = " ".join(f"[`{move_label(m)}`]({issue_url('chess|move|' + m['uci'])} \"{m['san']}\")"
                             for m in groups[kind])
            lines.append(f"| {WHITE_GLYPHS[kind]} {PIECE_NAMES[kind]} | {links} |")
    else:
        lines.append(f"**Game #{game['number']} is over — {STATUS_TEXT[st['status']]} "
                     f"({game.get('result', '')}).** [▶️ Start a new game]({issue_url('chess|new')})")

    if st["history_san"]:
        pgn = []
        for i, san in enumerate(st["history_san"]):
            pgn.append(f"{i // 2 + 1}. {san}" if i % 2 == 0 else san)
        lines += ["", "<details><summary>📜 Moves of this game</summary>", "", "```", " ".join(pgn), "```", "", "</details>"]

    top = sorted(state["leaderboard"].items(), key=lambda kv: (-kv[1]["wins"], -kv[1]["moves"], kv[0]))[:5]
    if top:
        lines += ["", "**🏆 Top players**", "", "| Player | Moves | Wins vs. engine |", "| :--- | ---: | ---: |"]
        for login, s in top:
            lines.append(f"| [@{login}](https://github.com/{login}) | {s['moves']} | {s['wins']} |")

    lines += ["", "<sub>Engine: 0x88 board, PVS alpha-beta with transposition table, null-move pruning, LMR and "
              "quiescence search — [source](./chess/engine) · [how it works](./chess/README.md)</sub>"]

    body = "\n".join(lines)
    readme = README_PATH.read_text(encoding="utf-8")
    new = re.sub(r"(<!--START_SECTION:chess-->).*?(<!--END_SECTION:chess-->)",
                 lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", readme, flags=re.S)
    README_PATH.write_text(new, encoding="utf-8")


def render(state=None):
    state = state or load_state()
    st = engine_state(state["game"]["moves"])
    SVG_PATH.write_text(render_svg(state, st), encoding="utf-8")
    render_readme(state, st)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "process":
        process(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 2 and sys.argv[1] == "render":
        render()
    else:
        print(__doc__)
        sys.exit(1)
