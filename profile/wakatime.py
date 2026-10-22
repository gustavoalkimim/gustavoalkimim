"""
Card "This week in code": busca as estatísticas dos últimos 7 dias no
WakaTime e desenha profile/wakatime.svg no estilo do resto do perfil.

uso:
  WAKATIME_API_KEY=... python profile/wakatime.py
  python profile/wakatime.py --sample exemplo.json   # testa o desenho sem a API
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://wakatime.com/api/v1/users/current/stats/last_7_days"
OUTPUT_PATH = Path(__file__).resolve().parent / "wakatime.svg"
MAX_LANGUAGES = 6

# Paleta roxa — mesma do Game of Life, do xadrez e do Tetris
COLOR_BG = "#0d1117"
COLOR_BORDER = "#30363d"
COLOR_TRACK = "#21262d"
COLOR_TEXT = "#c9d1d9"
COLOR_MUTED = "#8b949e"
COLOR_ACCENT = "#A685E2"
COLOR_LIGHT = "#e8e1ff"


def fetch_stats(api_key):
    token = base64.b64encode(api_key.encode()).decode()
    req = urllib.request.Request(API_URL, headers={"Authorization": f"Basic {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            # 202 = o WakaTime ainda está calculando; tenta na próxima execução
            if resp.status == 202:
                return None
            return json.load(resp)["data"]
    except urllib.error.HTTPError as err:
        print(f"[ERRO] WakaTime respondeu {err.code}: {err.read()[:200]!r}")
        sys.exit(1)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(data):
    W, H = 860, 250
    languages = [l for l in data.get("languages", []) if l.get("total_seconds", 0) > 0][:MAX_LANGUAGES]
    total = data.get("human_readable_total") or "0 mins"
    daily = data.get("human_readable_daily_average") or "0 mins"
    best = data.get("best_day") or {}
    editors = [e["name"] for e in data.get("editors", [])[:2]]

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    a("<style>"
      ".t{font-family:'Fira Code','Segoe UI',monospace;fill:" + COLOR_TEXT + "}"
      ".m{fill:" + COLOR_MUTED + "}"
      ".bar{transform-origin:left;transform:scaleX(0);animation:grow 1.1s cubic-bezier(.4,0,.2,1) forwards}"
      "@keyframes grow{to{transform:scaleX(1)}}"
      "</style>")
    a(f'<defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="{COLOR_ACCENT}"/>'
      f'<stop offset="1" stop-color="{COLOR_LIGHT}"/></linearGradient></defs>')
    a(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{COLOR_BG}" stroke="{COLOR_BORDER}"/>')

    # coluna da esquerda: totais
    a(f'<text class="t" x="28" y="36" font-size="12" letter-spacing="2" style="fill:{COLOR_ACCENT}">'
      f'THIS WEEK IN CODE</text>')
    blocks = [(total, "coded in the last 7 days"), (daily, "daily average")]
    if best.get("text"):
        blocks.append((best["text"], f"best day · {best.get('date', '')}"))
    for i, (value, label) in enumerate(blocks):
        y = 78 + i * 56
        a(f'<text class="t" x="28" y="{y}" font-size="20" font-weight="bold" style="fill:{COLOR_LIGHT}">{esc(value)}</text>')
        a(f'<text class="t m" x="28" y="{y + 18}" font-size="11">{esc(label)}</text>')

    # coluna da direita: linguagens
    lx, bar_x, bar_w = 330, 450, 300
    a(f'<text class="t" x="{lx}" y="36" font-size="12" letter-spacing="2" style="fill:{COLOR_ACCENT}">LANGUAGES</text>')
    if not languages:
        a(f'<text class="t m" x="{lx}" y="80" font-size="13">No coding activity tracked this week yet.</text>')
    top = max((l["percent"] for l in languages), default=1) or 1
    for i, lang in enumerate(languages):
        y = 66 + i * 28
        width = max(4, bar_w * lang["percent"] / top)
        a(f'<text class="t" x="{lx}" y="{y + 10}" font-size="13">{esc(lang["name"])}</text>')
        a(f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="12" rx="6" fill="{COLOR_TRACK}"/>')
        a(f'<rect class="bar" style="animation-delay:{0.2 + i * 0.12:.2f}s" x="{bar_x}" y="{y}" '
          f'width="{width:.1f}" height="12" rx="6" fill="url(#g)"/>')
        a(f'<text class="t m" x="{bar_x + bar_w + 12}" y="{y + 10}" font-size="11">'
          f'{esc(lang.get("text", ""))} · {lang["percent"]:.0f}%</text>')

    footer = "tracked with WakaTime"
    if editors:
        footer += " · " + " & ".join(editors)
    a(f'<text class="t m" x="28" y="{H - 18}" font-size="11">{esc(footer)}</text>')
    a("</svg>")
    return "\n".join(out)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--sample":
        data = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["data"]
    else:
        api_key = os.environ.get("WAKATIME_API_KEY")
        if not api_key:
            print("[ERRO] defina WAKATIME_API_KEY")
            sys.exit(1)
        data = fetch_stats(api_key)
        if data is None:
            print("WakaTime ainda está calculando as estatísticas — nada a fazer agora.")
            return
    OUTPUT_PATH.write_text(render_svg(data), encoding="utf-8")
    print(f"SVG salvo em {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
