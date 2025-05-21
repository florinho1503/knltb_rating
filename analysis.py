import pandas as pd
from datetime import datetime
import sys
import json
from pathlib import Path
import sqlite3

DB_PATH = 'matches.db'

def load_matches(db_path: str, player: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT * FROM matches WHERE player1 = :player OR player2 = :player",
        conn, params={"player": player}, parse_dates=["match_date"]
    )
    conn.close()
    return df

def enrich_dataframe(df: pd.DataFrame, player: str) -> pd.DataFrame:
    df = df.copy()
    df["is_p1"] = df["player1"] == player
    # Floris’s rating
    df["floris_rating"] = df.apply(lambda r: r["rating1"] if r["is_p1"] else r["rating2"], axis=1)
    # Opponent name & rating
    df["opp_name"]   = df.apply(lambda r: r["player2"] if r["is_p1"] else r["player1"], axis=1)
    df["opp_rating"] = df.apply(lambda r: r["rating2"] if r["is_p1"] else r["rating1"], axis=1)
    # Per-set scores
    for i in (1,2,3):
        df[f"set{i}_floris"] = df.apply(
            lambda r: r[f"set{i}_p1"] if r["is_p1"] else r[f"set{i}_p2"], axis=1
        )
        df[f"set{i}_opp"] = df.apply(
            lambda r: r[f"set{i}_p2"] if r["is_p1"] else r[f"set{i}_p1"], axis=1
        )
    # Win flag
    df["won"] = df["winner"] == player
    # 3-set flag
    df["is_3set"] = df["set3_floris"].notna()
    return df

def compute_statistics(df: pd.DataFrame) -> dict:
    stats = {}
    n = len(df)

    # 1) Matches won/lost
    stats["won"] = df["won"].sum()
    stats["lost"] = n - stats["won"]

    # 2) Won/lost in 3 sets
    stats["won_3"]  = df[df["won"]  & df["is_3set"]].shape[0]
    stats["lost_3"] = df[~df["won"] & df["is_3set"]].shape[0]

    # 3) Longest win-streak (unchanged)
    def longest_streak(series):
        max_s = cur = 0
        for x in series:
            cur = cur+1 if x else 0
            max_s = max(max_s, cur)
        return max_s
    stats["longest_streak"] = longest_streak(df.sort_values("match_date")["won"])

    # 4) Tiebreaks won/lost (unchanged)
    tbw = tbl = 0
    for i in (1,2,3):
        sf, so = df[f"set{i}_floris"], df[f"set{i}_opp"]
        tb = ((sf==7)&(so==6))|((sf==6)&(so==7))
        tbw += int(((sf>so)& tb).sum())
        tbl += int(((so>sf)& tb).sum())
    stats["tb_won"], stats["tb_lost"] = tbw, tbl

    # 5) Comeback rate (down 0–1 → win)
    dropped1 = df[df["set1_floris"] < df["set1_opp"]]
    stats["comebacks"] = dropped1["won"].sum()
    stats["comeback_rate"] = (
        stats["comebacks"] / len(dropped1)
        if len(dropped1)>0 else 0.0
    )

    # A) Set-win percentage
    total_sets = 0
    sets_won   = 0
    for i in (1,2,3):
        sf = df[f"set{i}_floris"]
        so = df[f"set{i}_opp"]
        played = sf.notna() & so.notna()
        total_sets += int(played.sum())
        sets_won   += int(((sf>so)& played).sum())
    stats["set_win_pct"] = sets_won / total_sets if total_sets else 0.0

    # B) Games-won percentage
    gf = go = 0
    for i in (1,2,3):
        sf = df[f"set{i}_floris"].fillna(0)
        so = df[f"set{i}_opp"].fillna(0)
        gf += sf.sum()
        go += so.sum()
    stats["game_win_pct"] = gf / (gf+go) if (gf+go)>0 else 0.0

    # C) Performance vs higher-rated opponents
    upsets = df[df["opp_rating"] < df["floris_rating"]]
    favours = df[df["opp_rating"] >= df["floris_rating"]]
    stats["upset_win_pct"] = (
        upsets["won"].sum() / len(upsets)
        if len(upsets)>0 else None
    )
    stats["favoured_win_pct"] = (
        favours["won"].sum() / len(favours)
        if len(favours)>0 else None
    )

    # D) Straight-sets vs 3-sets ratio (of wins)
    wins = df[df["won"]]
    straight = wins[~wins["is_3set"]].shape[0]
    three    = wins[wins["is_3set"]].shape[0]
    stats["straight_vs_3_ratio"] = (straight, three)

    # E) Close-set outcomes (7-5 / 5-7)
    csw = csl = 0
    for i in (1,2,3):
        sf, so = df[f"set{i}_floris"], df[f"set{i}_opp"]
        mask75 = (sf==7)&(so==5)
        mask57 = (sf==5)&(so==7)
        csw += int(mask75.sum())
        csl += int(mask57.sum())
    stats["close_set_won"], stats["close_set_lost"] = csw, csl

    # F) Bagels (6-0) & Breadsticks (6-1)
    bagels_won = bread_won = bagels_lost = bread_lost = 0
    for i in (1,2,3):
        sf, so = df[f"set{i}_floris"], df[f"set{i}_opp"]
        played = sf.notna() & so.notna()
        bagels_won  += int(((sf==6)&(so==0)& played).sum())
        bread_won   += int(((sf==6)&(so==1)& played).sum())
        bagels_lost += int(((so==6)&(sf==0)& played).sum())
        bread_lost  += int(((so==6)&(sf==1)& played).sum())
    stats["bagels_won"]  = bagels_won
    stats["bread_won"]   = bread_won
    stats["bagels_lost"] = bagels_lost
    stats["bread_lost"]  = bread_lost

    # G) Best/Worst & averages (unchanged from before)
    beaten = df[df["won"]]
    lostto = df[~df["won"]]

    if not beaten.empty:
        bb_row = beaten.loc[beaten["opp_rating"].idxmin()]
        stats["best_beaten"] = {
            "opponent": bb_row["opp_name"],
            "rating": bb_row["opp_rating"]
        }
        stats["avg_rating_beaten"] = beaten["opp_rating"].mean()

    if not lostto.empty:
        wl_row = lostto.loc[lostto["opp_rating"].idxmax()]
        stats["worst_lost_to"] = {
            "opponent": wl_row["opp_name"],
            "rating": wl_row["opp_rating"]
        }
        stats["avg_rating_lostto"] = lostto["opp_rating"].mean()

    for i in (1, 2, 3):
        sf = df[f"set{i}_floris"]
        so = df[f"set{i}_opp"]
        played = sf.notna() & so.notna()
        wins = ((sf > so) & played).sum()
        total = played.sum()
        stats[f"set{i}_win_pct"] = wins / total if total else None

        # Biggest upset win
    wins_df = df[df["won"]].copy()  # <-- copy() here
    wins_df["rating_diff"] = wins_df["floris_rating"] - wins_df["opp_rating"]
    upsets = wins_df[wins_df["rating_diff"] > 0]
    if not upsets.empty:
        uw = upsets.loc[upsets["rating_diff"].idxmax()]
        stats["biggest_upset_win"] = {
            "opponent": uw["opp_name"],
            "rating_diff": uw["rating_diff"]
        }
    else:
        stats["biggest_upset_win"] = None

    # Biggest bad-beat loss
    losses_df = df[~df["won"]].copy()  # <-- and copy() here
    losses_df["rating_diff"] = losses_df["opp_rating"] - losses_df["floris_rating"]
    bad_beats = losses_df[losses_df["rating_diff"] > 0]
    if not bad_beats.empty:
        bb = bad_beats.loc[bad_beats["rating_diff"].idxmax()]
        stats["biggest_bad_beat_loss"] = {
            "opponent": bb["opp_name"],
            "rating_diff": bb["rating_diff"]
        }
    else:
        stats["biggest_bad_beat_loss"] = None


    return stats


def generate_rating_plot_html(player_name, output_path="rating_plot.html"):
    """
        Generates an HTML report showing rating progression (from matches + current ratings)
        and a formatted stats grid. Pulls data from 'matches' and 'current_ratings' tables.

        player_name : the player to report on
        stats       : the <br>-joined stats string from analyze()
        output_path : where to write the .html file
    """
    stats = analyze(player_name)

    rows = []
    for line in stats.split("<br>"):
        if ":" in line:
            key, val = line.split(":", 1)
            rows.append(f"<div class='stat-key'>{key.strip()}:</div>")
            rows.append(f"<div class='stat-value'>{val.strip()}</div>")
    rows_html = "\n        ".join(rows)


    # --- 1) Load all historical ratings from matches table ---
    conn = sqlite3.connect('matches.db')
    cursor = conn.cursor()
    cursor.execute("""
            SELECT 
              match_date,
              CASE 
                WHEN player1 = ? THEN rating1 
                ELSE rating2 
              END AS rating
            FROM matches
            WHERE player1 = ? OR player2 = ?
        """, (player_name, player_name, player_name))
    match_rows = cursor.fetchall()

    # --- 2) Load current ratings ---
    cursor.execute("""
            SELECT date, rating
            FROM current_ratings
            WHERE name = ?
        """, (player_name,))
    current_rows = cursor.fetchall()
    conn.close()

    # --- 3) Combine & normalize into list of dicts ---
    data = []
    for date_val, rating in match_rows:
        if date_val is None:
            continue
        # match_date is stored as TEXT 'YYYY-MM-DD'
        iso = date_val if isinstance(date_val, str) else date_val.strftime("%Y-%m-%d")
        data.append({'date': iso, 'rating': float(rating)})

    for date_val, rating in current_rows:
        # current_ratings.date stored as TEXT 'YYYY-MM-DD'
        iso = date_val if isinstance(date_val, str) else date_val.strftime("%Y-%m-%d")
        data.append({'date': iso, 'rating': float(rating)})

    # sort chronologically
    data.sort(key=lambda x: x['date'])

    # --- 4) Prepare JS data arrays ---
    dates_js = json.dumps([entry['date'] for entry in data])
    ratings_js = json.dumps([entry['rating'] for entry in data])
    player_js = json.dumps(player_name)


    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; background: #f4f4f9; margin:0; }}
    .container {{ max-width:960px; margin:40px auto; background:#fff; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1); padding:20px; }}
    h3 {{ text-align:center; color:#333; margin-bottom:0.5em; }}
    #stats-raw {{ display: grid; grid-template-columns: auto 1fr; gap: 8px 16px; background: #fafafa; border: 1px solid #ddd; border-radius: 6px; padding: 16px; font-family: 'Courier New', monospace; font-size: 14px; line-height: 1.5; margin-bottom: 2em; }}
    #stats-raw .stat-key {{ font-weight: bold; color: #333; text-align: right; padding-right: 8px; }}
    #stats-raw .stat-value {{ color: #555; }}
    #chart {{ width:100%; height:500px; }}
  </style>
</head>
<body>
  <div class="container">
    <h3>{player_name}: Rating & Match Statistics (singles)</h3>
    <div id="stats-raw">
      {rows_html}
    </div>
    <div id="chart"></div>
  </div>
  <script>
    const dates   = {dates_js};
    const ratings = {ratings_js};
    const player  = {player_js};

    const trace = {{ 
      x: dates, y: ratings, 
      mode: 'lines+markers', 
      type: 'scatter', 
      marker: {{ size: 8, color: '#0074D9' }}, 
      line: {{ shape: 'spline', smoothing: 0.5, color: '#0074D9' }}, 
      hovertemplate: '%{{x}}<br>Rating: %{{y}}<extra></extra>' 
    }};
    
    const bestValue = Math.min(...ratings);
    const bestIdx   = ratings.indexOf(bestValue);
    const traceBest = {{ 
      x: [dates[bestIdx]], y: [bestValue], 
      mode: 'markers+text', 
      type: 'scatter', 
      marker: {{ size: 12, color: '#FF4136' }}, 
      text: [bestValue], 
      textposition: 'bottom center', 
      hovertemplate: 'Best: %{{y}} on %{{x}}<extra></extra>' 
    }};

    const layout = {{
  margin: {{ l:60, r:40, t:60, b:60 }},
  xaxis: {{
    type: 'date',
    tickformat: '%Y-%m-%d',
    tickangle: -45,
    dtick: 'M6'        // one tick every 6 months
  }},
  yaxis: {{
    title:'Rating (singles)',
    range:[Math.min(...ratings)-0.2, Math.max(...ratings)+0.2]
  }},
  plot_bgcolor:'#fafafa',
  paper_bgcolor:'#ffffff',
  hovermode:'closest'
}};


    Plotly.newPlot('chart', [trace, traceBest], layout, {{ responsive: true }});
  </script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Wrote interactive chart to {output_path}")


def analyze(PLAYER):
    df    = load_matches(DB_PATH, PLAYER)
    df    = enrich_dataframe(df, PLAYER)
    stats = compute_statistics(df)

    lines = []
    lines.append(f"=== Statistics for {PLAYER} ===")
    lines.append(f"Matches played:   {len(df)}")
    # 1) Overall W/L %
    w, l = stats['won'], stats['lost']
    pct = w / (w + l) if (w + l) > 0 else 0
    lines.append(f" • Won/Lost:       {w}/{l} ({pct:.1%})")

    # 2) 3-set W/L %
    w3, l3 = stats['won_3'], stats['lost_3']
    pct3 = w3 / (w3 + l3) if (w3 + l3) > 0 else 0
    lines.append(f" • 3-set W/L:      {w3}/{l3} ({pct3:.1%})")

    lines.append(f" • Longest streak: {stats['longest_streak']}")
    # 3) Tiebreaks W/L %
    tbw, tbl = stats['tb_won'], stats['tb_lost']
    pct_tb = tbw / (tbw + tbl) if (tbw + tbl) > 0 else 0
    lines.append(f" • Tiebreak W/L:   {tbw}/{tbl} ({pct_tb:.1%})")

    lines.append(f" • Comebacks:      {stats['comebacks']} ({stats['comeback_rate']:.1%})")
    lines.append("")

    lines.append(f"Set-win %:        {stats['set_win_pct']:.1%}")
    lines.append(f"Game-win %:       {stats['game_win_pct']:.1%}")
    if stats['upset_win_pct'] is not None:
        lines.append(f"Upset win %:      {stats['upset_win_pct']:.1%}")
    else:
        lines.append("Upset win %:      N/A")
    if stats['favoured_win_pct'] is not None:
        lines.append(f"Favoured win %:   {stats['favoured_win_pct']:.1%}")
    else:
        lines.append("Favoured win %:   N/A")

    # 4) Close sets W/L %
    csw, csl = stats['close_set_won'], stats['close_set_lost']
    pct_cs = csw / (csw + csl) if (csw + csl) > 0 else 0
    lines.append(f"Close sets (7-5/5-7) W/L: {csw}/{csl} ({pct_cs:.1%})")

    # 5) Bagels W/L %
    bwon, bloss = stats['bagels_won'], stats['bagels_lost']
    pct_bag = bwon / (bwon + bloss) if (bwon + bloss) > 0 else 0
    lines.append(f"Bagels W/L (6-0):       {bwon}/{bloss} ({pct_bag:.1%})")

    # 6) Breadsticks W/L %
    brw, brl = stats['bread_won'], stats['bread_lost']
    pct_br = brw / (brw + brl) if (brw + brl) > 0 else 0
    lines.append(f"Breadsticks W/L (6-1):   {brw}/{brl} ({pct_br:.1%})")

    lines.append("")
    bb = stats["best_beaten"]
    if bb:
        lines.append(
            f"Best beaten:      {bb['opponent']} "
            f"(rating {bb['rating']:.2f})"
        )
    else:
        lines.append("Best beaten:      None")
    wl = stats["worst_lost_to"]
    if wl:
        lines.append(
            f"Worst lost to:    {wl['opponent']} "
            f"(rating {wl['rating']:.2f})"
        )
    else:
        lines.append("Worst lost to:    None")
    lines.append(f"Avg rating beaten:{stats.get('avg_rating_beaten', 0):.2f}")
    lines.append(f"Avg rating lost to:{stats.get('avg_rating_lostto', 0):.2f}")

    for i in (1, 2, 3):
        pct = stats.get(f"set{i}_win_pct")
        if pct is not None:
            lines.append(f"Set {i} win %:       {pct:.1%}")
        else:
            lines.append(f"Set {i} win %:       N/A")

    bw = stats["biggest_upset_win"]
    if bw:
        lines.append(f"Biggest upset win: vs {bw['opponent']}, {bw['rating_diff']:.2f} difference")
    else:
        lines.append("Biggest upset win:     None")

    bl = stats["biggest_bad_beat_loss"]
    if bl:
        lines.append(f"Worst upset loss: vs {bl['opponent']}, {bl['rating_diff']:.2f} difference")
    else:
        lines.append("Biggest bad-beat loss: None")

    # join with <br> so we can inject into HTML
    stats = "<br>".join(lines)

    for line in stats.split("<br>"):
        print(line)

    return stats



if __name__ == "__main__":
    PLAYER = input('choose player: ')
    # PLAYER = 'Rutger Wijnsema'
    generate_rating_plot_html(PLAYER, output_path=f"analyses/{PLAYER}.html")
