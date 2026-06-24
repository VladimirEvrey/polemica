import os
from dotenv import load_dotenv
load_dotenv()

"""
Polemica Game — Full Data Scraper
==================================
Собирает ВСЕХ активных игроков и их связи через парсинг матчей.

Стратегия:
  1. Парсим матчи подряд от последнего назад (или вперёд)
  2. Из каждого матча вытаскиваем всех игроков → пополняем базу юзеров
  3. Строим граф связей: кто с кем играл и сколько раз

Запуск:
    pip install requests beautifulsoup4 tqdm
    python scraper.py

    # Только свои игры (быстро, ~минута):
    python scraper.py --mode my --user-id 1382

    # Все матчи за последние N (долго):
    python scraper.py --mode all --last 10000

Результат:
    players.db   — SQLite база (быстрый поиск)
    matches.json — матчи и составы
    connections.json — граф связей
    top_pairs.csv    — топ пар по совместным играм
"""

import argparse
import json
import os
import sqlite3
import time
import csv
from collections import defaultdict

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE_URL = "https://polemicagame.com"
DELAY    = float(os.getenv("DELAY", "0.25"))   # сек между запросами; увеличь до 0.5 при 429

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/html, */*",
})

# ─────────────────────────────────────────────
# БД
# ─────────────────────────────────────────────

def init_db(path="players.db"):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            user_id   INTEGER PRIMARY KEY,
            username  TEXT,
            mmr       INTEGER,
            total_games INTEGER,
            points    REAL,
            subscription INTEGER,
            prime_member INTEGER
        );
        CREATE TABLE IF NOT EXISTS matches (
            match_id  INTEGER PRIMARY KEY,
            parsed    INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS match_players (
            match_id  INTEGER,
            user_id   INTEGER,
            PRIMARY KEY (match_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS connections (
            uid1   INTEGER,
            uid2   INTEGER,
            cnt    INTEGER DEFAULT 1,
            PRIMARY KEY (uid1, uid2)
        );
    """)
    conn.commit()
    return conn


def upsert_player(conn, user_id, username):
    conn.execute(
        "INSERT OR IGNORE INTO players (user_id, username) VALUES (?,?)",
        (user_id, username)
    )


def save_match(conn, match_id, player_ids):
    conn.execute("INSERT OR IGNORE INTO matches (match_id, parsed) VALUES (?,1)", (match_id,))
    for uid in player_ids:
        conn.execute(
            "INSERT OR IGNORE INTO match_players (match_id, user_id) VALUES (?,?)",
            (match_id, uid)
        )
    # обновляем граф связей
    ids = list(set(player_ids))
    for i in range(len(ids)):
        for j in range(i+1, len(ids)):
            a, b = min(ids[i], ids[j]), max(ids[i], ids[j])
            conn.execute("""
                INSERT INTO connections (uid1, uid2, cnt) VALUES (?,?,1)
                ON CONFLICT(uid1,uid2) DO UPDATE SET cnt=cnt+1
            """, (a, b))
    conn.commit()


# ─────────────────────────────────────────────
# ПАРСИНГ МАТЧА
# ─────────────────────────────────────────────

def parse_match(match_id):
    """Возвращает список (user_id, username) из HTML страницы матча."""
    url = f"{BASE_URL}/match/{match_id}"
    try:
        r = session.get(url, timeout=10)
        if r.status_code == 404:
            return None          # матча нет
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    players = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/profile/" in href:
            try:
                uid = int(href.split("/profile/")[1].split("/")[0].split("?")[0])
                name = a.get_text(strip=True)
                if uid and name and uid not in players:
                    players[uid] = name
            except (ValueError, IndexError):
                continue
    return list(players.items())   # [(uid, name), ...]


# ─────────────────────────────────────────────
# РЕЖИМ 1: Все мои игры (быстро)
# ─────────────────────────────────────────────

def fetch_user_match_ids(user_id, max_pages=999):
    ids = []
    for page in range(1, max_pages+1):
        url = f"{BASE_URL}/profile/default/get-games?userId={user_id}&page={page}"
        try:
            r = session.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  Ошибка page={page}: {e}")
            break
        rows = data.get("rows", [])
        ids += [row["id"] for row in rows if row.get("type") == "match"]
        if len(rows) < 10:
            break
        time.sleep(DELAY)
    return ids


def mode_my_games(user_id, db_path="players.db"):
    conn = init_db(db_path)
    print(f"[1/2] Загружаем список игр юзера {user_id}...")
    match_ids = fetch_user_match_ids(user_id)
    print(f"    Найдено матчей: {len(match_ids)}")

    print("[2/2] Парсим составы матчей...")
    for mid in tqdm(match_ids):
        players = parse_match(mid)
        if players:
            for uid, name in players:
                upsert_player(conn, uid, name)
            save_match(conn, mid, [uid for uid, _ in players])
        time.sleep(DELAY)

    print_my_partners(user_id, conn)
    export_csv(conn, "top_pairs.csv")
    conn.close()


def print_my_partners(user_id, conn, top_n=30):
    rows = conn.execute("""
        SELECT p.username, c.cnt
        FROM connections c
        JOIN players p ON p.user_id = CASE WHEN c.uid1=? THEN c.uid2 ELSE c.uid1 END
        WHERE c.uid1=? OR c.uid2=?
        ORDER BY c.cnt DESC
        LIMIT ?
    """, (user_id, user_id, user_id, top_n)).fetchall()

    print(f"\nТоп партнёров для user_id={user_id}:")
    for i, (name, cnt) in enumerate(rows, 1):
        print(f"  {i:3}. {name:35} — {cnt} игр вместе")


# ─────────────────────────────────────────────
# РЕЖИМ 2: Все матчи подряд (полный сбор)
# ─────────────────────────────────────────────

def mode_all_matches(last_match_id=591399, count=10000, db_path="players.db"):
    conn = init_db(db_path)

    # уже спарсенные
    done = {row[0] for row in conn.execute("SELECT match_id FROM matches WHERE parsed=1")}
    print(f"Уже в базе: {len(done)} матчей")

    start = last_match_id
    end   = max(1, last_match_id - count)
    ids   = [i for i in range(start, end, -1) if i not in done]

    print(f"Парсим {len(ids)} матчей (от {start} до {end})...")
    errors = 0
    for mid in tqdm(ids):
        players = parse_match(mid)
        if players is None:
            # 404 — матча нет, помечаем чтобы не повторять
            conn.execute("INSERT OR IGNORE INTO matches (match_id, parsed) VALUES (?,1)", (mid,))
            conn.commit()
        elif players:
            for uid, name in players:
                upsert_player(conn, uid, name)
            save_match(conn, mid, [uid for uid, _ in players])
            errors = 0
        else:
            errors += 1
            if errors > 10:
                print("  10 ошибок подряд — возможно rate limit. Пауза 30 сек...")
                time.sleep(30)
                errors = 0
        time.sleep(DELAY)

    total_players = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    total_matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    total_pairs   = conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
    print(f"\nИтого в базе:")
    print(f"  Игроков:  {total_players}")
    print(f"  Матчей:   {total_matches}")
    print(f"  Пар:      {total_pairs}")

    export_csv(conn, "top_pairs.csv")
    conn.close()


# ─────────────────────────────────────────────
# ЭКСПОРТ
# ─────────────────────────────────────────────

def export_csv(conn, path="top_pairs.csv", limit=5000):
    rows = conn.execute("""
        SELECT p1.username, c.uid1, p2.username, c.uid2, c.cnt
        FROM connections c
        JOIN players p1 ON p1.user_id = c.uid1
        JOIN players p2 ON p2.user_id = c.uid2
        ORDER BY c.cnt DESC
        LIMIT ?
    """, (limit,)).fetchall()

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["username_1", "user_id_1", "username_2", "user_id_2", "games_together"])
        w.writerows(rows)
    print(f"\nСохранено: {path} ({len(rows)} строк)")


def query_partners(user_id, db_path="players.db", top_n=30):
    """Отдельная команда: показать партнёров из готовой БД."""
    conn = sqlite3.connect(db_path)
    print_my_partners(user_id, conn, top_n)
    conn.close()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Polemica scraper")
    parser.add_argument("--mode", choices=["my", "all", "query"], default="my",
                        help="my=мои игры, all=все матчи подряд, query=запрос из готовой БД")
    parser.add_argument("--user-id", type=int, default=1382,
                        help="ID юзера (для --mode my/query)")
    parser.add_argument("--last",    type=int, default=591399,
                        help="Последний известный match_id (для --mode all)")
    parser.add_argument("--count",   type=int, default=10000,
                        help="Сколько матчей парсить (для --mode all)")
    parser.add_argument("--db",      type=str, default="players.db",
                        help="Путь к SQLite базе")
    args = parser.parse_args()

    if args.mode == "my":
        mode_my_games(args.user_id, args.db)
    elif args.mode == "all":
        mode_all_matches(args.last, args.count, args.db)
    elif args.mode == "query":
        query_partners(args.user_id, args.db)
