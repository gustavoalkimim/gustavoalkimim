import os
import sys
import random
import requests

# ── Configurações ───────────────────────────────────────────────────────────────

GITHUB_USERNAME = "gustavoalkimim"
OUTPUT_PATH     = "profile/game-of-life.svg"
GENERATIONS     = 80
FRAME_DURATION  = 0.16   # segundos por frame

COLS = 53
ROWS = 7

CELL_SIZE = 11
CELL_GAP  = 3

# Paleta de cores igual ao GitHub
COLOR_DEAD    = "#161b22"
COLOR_BORN    = "#26a641"
COLOR_ALIVE   = "#39d353"
COLOR_DYING   = "#0e4429"
COLOR_BG      = "#0d1117"
COLOR_BORDER  = "#30363d"
COLOR_TEXT    = "#8b949e"
COLOR_HEADER  = "#21262d"


# ── Buscar dados da API GraphQL do GitHub ───────────────────────────────────────

def fetch_contributions(username: str, token: str) -> list:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays {
                contributionCount
                weekday
              }
            }
          }
        }
      }
    }
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        "https://api.github.com/graphql",
        headers=headers,
        json={"query": query, "variables": {"login": username}},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"[ERRO] API retornou {resp.status_code}: {resp.text}")
        sys.exit(1)

    data = resp.json()
    if "errors" in data:
        print(f"[ERRO] GraphQL: {data['errors']}")
        sys.exit(1)

    weeks = (
        data["data"]["user"]
        ["contributionsCollection"]
        ["contributionCalendar"]
        ["weeks"]
    )

    # Grade [col][row]: 1 = teve commit, 0 = não teve
    grid = [[0] * ROWS for _ in range(COLS)]
    for col_idx, week in enumerate(weeks[:COLS]):
        for day in week["contributionDays"]:
            r = day["weekday"]  # 0=Dom … 6=Sab
            grid[col_idx][r] = 1 if day["contributionCount"] > 0 else 0

    return grid


def make_fallback_grid() -> list:
    """Grid aleatório usado quando não há token (testes locais)."""
    random.seed(42)
    return [[1 if random.random() < 0.35 else 0 for _ in range(ROWS)] for _ in range(COLS)]


# ── Game of Life ────────────────────────────────────────────────────────────────

def count_neighbors(grid: list, c: int, r: int) -> int:
    total = 0
    for dc in (-1, 0, 1):
        for dr in (-1, 0, 1):
            if dc == 0 and dr == 0:
                continue
            nc, nr = c + dc, r + dr
            if 0 <= nc < COLS and 0 <= nr < ROWS:
                total += grid[nc][nr]
    return total


def next_gen(grid: list) -> list:
    new = [[0] * ROWS for _ in range(COLS)]
    for c in range(COLS):
        for r in range(ROWS):
            n = count_neighbors(grid, c, r)
            if grid[c][r] == 1:
                new[c][r] = 1 if n in (2, 3) else 0
            else:
                new[c][r] = 1 if n == 3 else 0
    return new


def run_simulation(initial: list) -> list:
    """Retorna lista de frames. Reinicia do inicial se a população cair demais."""
    frames = [initial]
    current = initial
    for _ in range(GENERATIONS - 1):
        nxt = next_gen(current)
        alive = sum(nxt[c][r] for c in range(COLS) for r in range(ROWS))
        if alive < 8:
            # Reinicia: mistura inicial com alguns aleátórios para variar
            revive = [[0] * ROWS for _ in range(COLS)]
            for c in range(COLS):
                for r in range(ROWS):
                    revive[c][r] = initial[c][r] or (1 if random.random() < 0.05 else 0)
            nxt = revive
        frames.append(nxt)
        current = nxt
    return frames


# ── Gerador de SVG ──────────────────────────────────────────────────────────────

def cell_color(alive_now: int, alive_prev: int) -> str:
    if alive_now and not alive_prev:
        return COLOR_BORN    # nasceu agora
    if not alive_now and alive_prev:
        return COLOR_DYING   # acabou de morrer
    if alive_now:
        return COLOR_ALIVE   # viva
    return COLOR_DEAD        # morta


def generate_svg(frames: list) -> str:
    prev_frames = [frames[0]] + frames[:-1]

    total_dur = round(GENERATIONS * FRAME_DURATION, 2)
    pad       = 10
    header_h  = 32
    legend_h  = 28

    inner_w = COLS * (CELL_SIZE + CELL_GAP) + CELL_GAP
    inner_h = ROWS * (CELL_SIZE + CELL_GAP) + CELL_GAP
    svg_w   = inner_w + pad * 2
    svg_h   = inner_h + pad * 2 + header_h + legend_h

    lines = []

    # ── Cabeçalho SVG ──
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{svg_w}" height="{svg_h}" '
        f'viewBox="0 0 {svg_w} {svg_h}">'
    )

    # Fundo
    lines.append(
        f'<rect width="{svg_w}" height="{svg_h}" rx="10" '
        f'fill="{COLOR_BG}" stroke="{COLOR_BORDER}" stroke-width="1"/>'
    )

    # Barra de cabeçalho
    lines.append(
        f'<rect x="0" y="0" width="{svg_w}" height="{header_h}" rx="10" '
        f'fill="{COLOR_HEADER}"/>'
    )
    lines.append(
        f'<rect x="0" y="{header_h - 10}" width="{svg_w}" height="10" '
        f'fill="{COLOR_HEADER}"/>'
    )
    lines.append(
        f'<line x1="0" y1="{header_h}" x2="{svg_w}" y2="{header_h}" '
        f'stroke="{COLOR_BORDER}" stroke-width="1"/>'
    )

    # Bolinhas de "janela" estilo macOS
    for i, color in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        lines.append(
            f'<circle cx="{16 + i * 20}" cy="{header_h // 2}" r="6" fill="{color}"/>'
        )

    # Título no cabeçalho
    lines.append(
        f'<text x="{svg_w // 2}" y="{header_h // 2 + 5}" '
        f'text-anchor="middle" font-family="monospace" font-size="12" '
        f'fill="{COLOR_TEXT}">Conway\'s Game of Life · lucascoelho74</text>'
    )

    # ── Células ──
    cell_y_offset = header_h + pad

    for c in range(COLS):
        for r in range(ROWS):
            x = pad + c * (CELL_SIZE + CELL_GAP) + CELL_GAP
            y = cell_y_offset + r * (CELL_SIZE + CELL_GAP) + CELL_GAP

            # Cor de cada frame
            colors = [
                cell_color(frames[i][c][r], prev_frames[i][c][r])
                for i in range(GENERATIONS)
            ]

            # Comprime runs consecutivos iguais para deixar o SVG menor
            values    = []
            key_times = []
            for i, color in enumerate(colors):
                t = round(i / GENERATIONS, 5)
                if not values or color != values[-1]:
                    values.append(color)
                    key_times.append(t)

            # SMIL precisa que values e keyTimes terminem igual
            values.append(values[0])
            key_times.append(1.0)

            vals_str  = ";".join(values)
            times_str = ";".join(str(t) for t in key_times)

            lines.append(
                f'<rect x="{x}" y="{y}" width="{CELL_SIZE}" height="{CELL_SIZE}" rx="2" '
                f'fill="{colors[0]}">'
                f'<animate attributeName="fill" '
                f'values="{vals_str}" keyTimes="{times_str}" '
                f'dur="{total_dur}s" repeatCount="indefinite" calcMode="discrete"/>'
                f'</rect>'
            )

    # ── Legenda ──
    legend_y = header_h + pad + inner_h + pad + CELL_GAP + 8
    legend_items = [
        (COLOR_ALIVE,  "viva"),
        (COLOR_BORN,   "nasceu"),
        (COLOR_DYING,  "morreu"),
        (COLOR_DEAD,   "inativa"),
    ]
    item_w = svg_w // len(legend_items)
    for i, (color, label) in enumerate(legend_items):
        lx = i * item_w + item_w // 2
        lines.append(
            f'<rect x="{lx - 30}" y="{legend_y}" '
            f'width="10" height="10" rx="2" fill="{color}"/>'
        )
        lines.append(
            f'<text x="{lx - 16}" y="{legend_y + 9}" '
            f'font-family="monospace" font-size="10" fill="{COLOR_TEXT}">{label}</text>'
        )

    # Indicador pulsante de "live"
    gen_x = svg_w - pad - 4
    gen_y = legend_y + 9
    lines.append(
        f'<circle cx="{gen_x - 52}" cy="{gen_y - 4}" r="4" fill="#3fb950">'
        f'<animate attributeName="opacity" values="1;0.2;1" keyTimes="0;0.5;1" '
        f'dur="2s" repeatCount="indefinite"/>'
        f'</circle>'
    )
    lines.append(
        f'<text x="{gen_x - 44}" y="{gen_y}" '
        f'font-family="monospace" font-size="10" fill="#3fb950" font-weight="bold">'
        f'live</text>'
    )

    lines.append('</svg>')
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    token = os.environ.get("GH_TOKEN", "")

    if token:
        print(f"Buscando contribuições de @{GITHUB_USERNAME} via API...")
        initial_grid = fetch_contributions(GITHUB_USERNAME, token)
        alive = sum(initial_grid[c][r] for c in range(COLS) for r in range(ROWS))
        print(f"Grid carregado: {alive} dias com commit de {COLS * ROWS} possíveis")
    else:
        print("GH_TOKEN não encontrado — usando grid de teste aleatório")
        initial_grid = make_fallback_grid()

    print(f"Simulando {GENERATIONS} gerações...")
    frames = run_simulation(initial_grid)

    print("Gerando SVG...")
    svg = generate_svg(frames)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(svg)

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"SVG salvo em '{OUTPUT_PATH}' ({size_kb:.1f} KB)")
    print("Pronto!")
