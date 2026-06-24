import os
from dotenv import load_dotenv
load_dotenv()

"""
Polemica Dashboard Generator
=============================
Читает players.db (SQLite) и генерирует stats.html — красивый дашборд.

Запуск:
    python dashboard.py
    python dashboard.py --db players.db --user-id 1382 --out stats.html
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────
# ЧТЕНИЕ ДАННЫХ ИЗ БД
# ─────────────────────────────────────────────

def load_data(db_path, user_id=None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Общая статистика
    total_players = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    total_matches = conn.execute("SELECT COUNT(*) FROM matches WHERE parsed=1").fetchone()[0]
    total_pairs   = conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0]

    # Топ игроков по количеству матчей в базе
    top_players = conn.execute("""
        SELECT p.user_id, p.username, COUNT(mp.match_id) as match_count
        FROM players p
        JOIN match_players mp ON mp.user_id = p.user_id
        GROUP BY p.user_id
        ORDER BY match_count DESC
        LIMIT 20
    """).fetchall()

    # Топ пар
    top_pairs = conn.execute("""
        SELECT p1.username AS username1, c.uid1, p2.username AS username2, c.uid2, c.cnt
        FROM connections c
        JOIN players p1 ON p1.user_id = c.uid1
        JOIN players p2 ON p2.user_id = c.uid2
        ORDER BY c.cnt DESC
        LIMIT 30
    """).fetchall()

    # Партнёры конкретного юзера
    my_partners = []
    my_username = f"user_{user_id}"
    if user_id:
        row = conn.execute("SELECT username FROM players WHERE user_id=?", (user_id,)).fetchone()
        if row:
            my_username = row[0]
        my_partners = conn.execute("""
            SELECT p.username, p.user_id,
                   CASE WHEN c.uid1=? THEN c.uid2 ELSE c.uid1 END as partner_id,
                   c.cnt
            FROM connections c
            JOIN players p ON p.user_id = CASE WHEN c.uid1=? THEN c.uid2 ELSE c.uid1 END
            WHERE c.uid1=? OR c.uid2=?
            ORDER BY c.cnt DESC
            LIMIT 30
        """, (user_id, user_id, user_id, user_id)).fetchall()

    # Матчи с наибольшим числом известных игроков
    top_matches = conn.execute("""
        SELECT match_id, COUNT(user_id) as player_count
        FROM match_players
        GROUP BY match_id
        ORDER BY player_count DESC
        LIMIT 10
    """).fetchall()

    conn.close()
    return {
        "total_players": total_players,
        "total_matches": total_matches,
        "total_pairs": total_pairs,
        "top_players": [dict(r) for r in top_players],
        "top_pairs": [dict(r) for r in top_pairs],
        "my_partners": [dict(r) for r in my_partners],
        "my_username": my_username,
        "user_id": user_id,
        "top_matches": [dict(r) for r in top_matches],
    }


# ─────────────────────────────────────────────
# ГЕНЕРАЦИЯ HTML
# ─────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polemica — Статистика</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;700&display=swap');

  :root {
    --bg:        #0e0e11;
    --surface:   #17171c;
    --border:    #2a2a34;
    --accent:    #c84b4b;
    --accent2:   #e87c3e;
    --text:      #e8e6e1;
    --muted:     #6b6878;
    --green:     #4caf7d;
    --gold:      #d4a843;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    line-height: 1.6;
    min-height: 100vh;
  }

  /* ── шапка ── */
  header {
    border-bottom: 1px solid var(--border);
    padding: 28px 40px 24px;
    display: flex;
    align-items: baseline;
    gap: 20px;
  }
  header h1 {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 26px;
    font-weight: 700;
    letter-spacing: -0.5px;
    color: var(--text);
  }
  header h1 span { color: var(--accent); }
  .header-sub {
    font-size: 13px;
    color: var(--muted);
  }

  /* ── grid layout ── */
  .layout {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 1px;
    background: var(--border);
    border-top: 1px solid var(--border);
  }
  .layout > * { background: var(--bg); }

  /* ── метрики верхние ── */
  .metrics {
    grid-column: 1 / -1;
    display: flex;
    gap: 1px;
    background: var(--border);
  }
  .metric {
    flex: 1;
    background: var(--bg);
    padding: 28px 32px;
  }
  .metric-val {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 42px;
    font-weight: 700;
    letter-spacing: -1.5px;
    line-height: 1;
    color: var(--text);
  }
  .metric-val.accent  { color: var(--accent); }
  .metric-val.accent2 { color: var(--accent2); }
  .metric-val.green   { color: var(--green); }
  .metric-label {
    font-size: 12px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 6px;
  }

  /* ── секция ── */
  .section {
    padding: 28px 32px;
  }
  .section-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 13px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted);
    margin-bottom: 20px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }

  /* ── таблица ── */
  table { width: 100%; border-collapse: collapse; }
  th {
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-align: left;
    padding: 0 0 10px;
  }
  td {
    padding: 9px 0;
    border-top: 1px solid var(--border);
    font-size: 13px;
    vertical-align: middle;
  }
  td.num {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 15px;
    font-weight: 500;
    color: var(--accent);
    text-align: right;
    padding-left: 12px;
    white-space: nowrap;
  }
  td.rank {
    font-size: 11px;
    color: var(--muted);
    width: 28px;
  }
  td.rank.gold   { color: var(--gold); font-weight: 600; }
  td.rank.silver { color: #9ba3af; font-weight: 600; }
  td.rank.bronze { color: #cd7f32; font-weight: 600; }
  .name-link {
    color: var(--text);
    text-decoration: none;
    transition: color 0.15s;
  }
  .name-link:hover { color: var(--accent); }

  /* ── бар ── */
  .bar-wrap {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 4px;
  }
  .bar-track {
    flex: 1;
    height: 3px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    transition: width 0.6s ease;
  }
  .bar-fill.green { background: var(--green); }

  /* ── пара ── */
  .pair {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 9px 0;
    border-top: 1px solid var(--border);
  }
  .pair:first-child { border-top: none; }
  .pair-names {
    flex: 1;
    font-size: 13px;
    color: var(--text);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .pair-sep {
    color: var(--muted);
    font-size: 11px;
    margin: 0 2px;
  }
  .pair-cnt {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 14px;
    font-weight: 500;
    color: var(--accent2);
    flex-shrink: 0;
  }

  /* ── мои партнёры хайлайт ── */
  .my-section {
    grid-column: 1 / -1;
    background: #13111a;
    border-top: 2px solid var(--accent);
  }
  .my-section .section-title { color: var(--accent); }

  /* ── футер ── */
  footer {
    border-top: 1px solid var(--border);
    padding: 16px 40px;
    font-size: 12px;
    color: var(--muted);
    display: flex;
    justify-content: space-between;
  }

  @media (max-width: 900px) {
    .layout { grid-template-columns: 1fr; }
    .metrics { flex-direction: column; }
    header { padding: 20px; }
    .section { padding: 20px; }
  }
</style>
</head>
<body>

<header>
  <h1>Polemica <span>Stats</span></h1>
  <span class="header-sub">PLAYER_LABEL</span>
</header>

<div class="layout">

  <!-- метрики -->
  <div class="metrics">
    <div class="metric">
      <div class="metric-val accent">TOTAL_PLAYERS</div>
      <div class="metric-label">Игроков в базе</div>
    </div>
    <div class="metric">
      <div class="metric-val accent2">TOTAL_MATCHES</div>
      <div class="metric-label">Матчей обработано</div>
    </div>
    <div class="metric">
      <div class="metric-val green">TOTAL_PAIRS</div>
      <div class="metric-label">Уникальных пар</div>
    </div>
  </div>

  MY_SECTION

  <!-- топ активных игроков -->
  <div class="section">
    <div class="section-title">Топ активных игроков</div>
    <table>
      <thead><tr><th>#</th><th>Игрок</th><th style="text-align:right">Матчей</th></tr></thead>
      <tbody>TOP_PLAYERS_ROWS</tbody>
    </table>
  </div>

  <!-- топ пар -->
  <div class="section" style="grid-column: span 2;">
    <div class="section-title">Чаще всего играли вместе</div>
    TOP_PAIRS_ROWS
  </div>

</div>

<footer>
  <span>Polemica Game Stats</span>
  <span>polemicagame.com</span>
</footer>

</body>
</html>
"""

def rank_class(i):
    if i == 0: return "gold"
    if i == 1: return "silver"
    if i == 2: return "bronze"
    return ""

def fmt(n):
    return f"{n:,}".replace(",", " ")

def generate_html(data, out_path="stats.html"):
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    html = HTML_TEMPLATE

    # метрики
    html = html.replace("TOTAL_PLAYERS", fmt(data["total_players"]))
    html = html.replace("TOTAL_MATCHES", fmt(data["total_matches"]))
    html = html.replace("TOTAL_PAIRS",   fmt(data["total_pairs"]))

    # заголовок
    if data["user_id"]:
        label = f"Профиль: {data['my_username']} (ID {data['user_id']}) · Обновлено: {now}"
    else:
        label = f"Общая статистика · Обновлено: {now}"
    html = html.replace("PLAYER_LABEL", label)

    # мои партнёры
    if data["my_partners"]:
        max_cnt = data["my_partners"][0]["cnt"] if data["my_partners"] else 1
        rows = ""
        for i, p in enumerate(data["my_partners"]):
            pct = p["cnt"] / max_cnt * 100
            rc  = rank_class(i)
            rows += f"""
            <div class="pair">
              <span class="rank {rc}" style="width:24px;flex-shrink:0">{i+1}</span>
              <div style="flex:1;min-width:0">
                <a class="name-link" href="https://polemicagame.com/profile/{p['user_id']}" target="_blank">{p['username']}</a>
                <div class="bar-wrap">
                  <div class="bar-track"><div class="bar-fill green" style="width:{pct:.1f}%"></div></div>
                </div>
              </div>
              <span class="pair-cnt">{p['cnt']}</span>
            </div>"""
        my_block = f"""
  <div class="section my-section">
    <div class="section-title">Чаще всего играл вместе с — {data['my_username']}</div>
    {rows}
  </div>"""
    else:
        my_block = ""
    html = html.replace("MY_SECTION", my_block)

    # топ игроков
    max_m = data["top_players"][0]["match_count"] if data["top_players"] else 1
    rows = ""
    for i, p in enumerate(data["top_players"]):
        pct = p["match_count"] / max_m * 100
        rc  = rank_class(i)
        rows += f"""
        <tr>
          <td class="rank {rc}">{i+1}</td>
          <td>
            <a class="name-link" href="https://polemicagame.com/profile/{p['user_id']}" target="_blank">{p['username']}</a>
            <div class="bar-wrap">
              <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>
            </div>
          </td>
          <td class="num">{p['match_count']}</td>
        </tr>"""
    html = html.replace("TOP_PLAYERS_ROWS", rows)

    # топ пар
    max_c = data["top_pairs"][0]["cnt"] if data["top_pairs"] else 1
    pairs = ""
    for i, p in enumerate(data["top_pairs"]):
        pct = p["cnt"] / max_c * 100
        pairs += f"""
        <div class="pair">
          <span style="font-size:11px;color:var(--muted);width:24px;flex-shrink:0">{i+1}</span>
          <div style="flex:1;min-width:0">
            <span class="pair-names">
              <a class="name-link" href="https://polemicagame.com/profile/{p['uid1']}" target="_blank">{p['username1']}</a>
              <span class="pair-sep">×</span>
              <a class="name-link" href="https://polemicagame.com/profile/{p['uid2']}" target="_blank">{p['username2']}</a>
            </span>
            <div class="bar-wrap">
              <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>
            </div>
          </div>
          <span class="pair-cnt">{p['cnt']}</span>
        </div>"""
    html = html.replace("TOP_PAIRS_ROWS", pairs)

    Path(out_path).write_text(html, encoding="utf-8")
    print(f"Дашборд сохранён: {out_path}")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Генератор HTML-дашборда Polemica")
    parser.add_argument("--db",      default="players.db", help="Путь к SQLite базе")
    parser.add_argument("--user-id", type=int, default=None, help="ID юзера для секции 'Мои партнёры'")
    parser.add_argument("--out",     default="stats.html", help="Путь к выходному HTML")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Ошибка: файл {args.db} не найден.")
        print("Сначала запусти polemica_scraper.py для сбора данных.")
        sys.exit(1)

    data = load_data(args.db, args.user_id)
    generate_html(data, args.out)
