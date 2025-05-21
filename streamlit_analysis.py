import pandas as pd
from datetime import datetime
import sys
import json
from pathlib import Path
import sqlite3
import streamlit as st
import plotly.graph_objs as go
from datetime import date
import player_rating_progression_scrape

DB_PATH = 'matches.db'

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

@st.cache_data
def load_and_filter(player, start_date, end_date):
    conn = sqlite3.connect('matches.db')
    df = pd.read_sql_query(
        """
        SELECT * FROM matches
        WHERE (player1 = :p OR player2 = :p)
          AND match_date BETWEEN :s AND :e
        """,
        conn,
        params={"p": player, "s": start_date.strftime("%Y-%m-%d"), "e": end_date.strftime("%Y-%m-%d")},
        parse_dates=["match_date"]
    )
    conn.close()
    return enrich_dataframe(df, player)


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
    # conversion rate
    won1 = df[df["set1_floris"] > df["set1_opp"]]
    stats["converted"] = won1["won"].sum()
    stats["conversion_rate"] = (
        stats["converted"] / len(won1)
        if len(won1) > 0 else 0.0
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


# — Streamlit App —
st.set_page_config(layout="wide")
st.title("🎾 Dynamic Player Report")

# 1) Single form for all inputs
with st.form("report_form"):
    col1, col2, col3 = st.columns([2,2,2])
    with col1:
        player   = st.text_input("Player name", "Floris Bokx")
        knltb_id = st.text_input("KNLTB Player ID (only if new)", "")
    with col2:
        start = st.date_input("Start date", date(2018,1,1))
        end   = st.date_input("End date", date.today())
    with col3:
        submitted = st.form_submit_button("Generate Report")

if not submitted:
    st.info("Fill out the form and click Generate Report.")
    st.stop()

# 2) On submit: ensure dates valid
if start > end:
    st.error("Start date must be before end date.")
    st.stop()

# 3) Check if we’ve scraped before
conn = sqlite3.connect('matches.db')
cur  = conn.cursor()
cur.execute("SELECT 1 FROM current_ratings WHERE name = ?", (player,))
has_current = cur.fetchone() is not None
conn.close()

# 4) If never scraped, require ID and run scraper
if not has_current:
    if not knltb_id.strip():
        st.error(f"No data for {player}. Please enter their KNLTB ID to scrape.")
        st.stop()
    with st.spinner("Scraping historical data..."):
        player_rating_progression_scrape.main(knltb_id)
    st.success("Scraping complete!")

# 5) Load filtered data (may be empty if no matches in range)
df = load_and_filter(player, start, end)
if df.empty:
    st.warning(f"No matches for {player} between {start} and {end}.")

# 6) Compute stats & format text
stats = compute_statistics(df)

# 7) Layout results in two columns
col_left, col_right = st.columns([1, 2], gap="large")

with col_left:
    st.subheader("Key Metrics")

    # unpack stats
    w, l       = stats['won'], stats['lost']
    win_pct    = w/(w+l) if w+l>0 else 0
    w3, l3     = stats['won_3'], stats['lost_3']
    set3_pct   = w3/(w3+l3) if w3+l3>0 else 0
    tbw, tbl   = stats['tb_won'], stats['tb_lost']
    tb_pct     = tbw/(tbw+tbl) if tbw+tbl>0 else 0
    comeback_p = stats['comeback_rate']
    conv_rate  = stats['conversion_rate']

    # first 6 metrics in a 2×3 grid
    metrics = [
        ("🏆 Win Rate",        f"{win_pct:.1%}",              f"{w}/{l}"),
        ("🎾 3-Set W/L %",     f"{set3_pct:.1%}",             f"{w3}/{l3}"),
        ("⏱️ Longest Winstreak", stats['longest_streak'],      None),
        ("🎯 Tiebreak Win%",    f"{tb_pct:.1%}",               f"{tbw}/{tbl}"),
        ("🔄 Won after losing 1st set", f"{comeback_p:.1%}",      f"{stats['comebacks']}"),
        ("✅ Won after winning 1st set", f"{conv_rate:.1%}",       f"{stats['converted']}")
    ]

    # chunk into rows of 2
    for row in [metrics[i:i+2] for i in range(0, 6, 2)]:
        c1, c2 = st.columns(2)
        for col, (label, value, delta) in zip((c1, c2), row):
            if delta:
                col.metric(label, value, delta=delta)
            else:
                col.metric(label, value)

    # All other metrics in a styled HTML block
    html = """
    <style>
      .stats-block p {{ margin:0.3em 0; }}
      .stats-block span.num {{ font-weight:bold; }}
    </style>
    <div class="stats-block">
      <p>📈 <strong>Set-Win %:</strong> <span class="num">{setwin:.1%}</span></p>
      <p>🎲 <strong>Game-Win %:</strong> <span class="num">{gamewin:.1%}</span></p>
      <p>⚔️ <strong>Against better rated:</strong> <span class="num">{upset:.1%}</span></p>
      <p>⭐ <strong>Against worse rated:</strong> <span class="num">{fav:.1%}</span></p>
      <p>🔢 <strong>(7-5) Sets W/L:</strong> <span class="num">{csw}/{csl} ({cs_pct:.1%})</span></p>
      <p>🍩 <strong>Bagels W/L:</strong> <span class="num">{bag_w}/{bag_l} ({bag_pct:.1%})</span></p>
      <p>🥖 <strong>Breadsticks W/L:</strong> <span class="num">{br_w}/{br_l} ({br_pct:.1%})</span></p>
      <p>🥇 <strong>Best beaten:</strong> <span class="num">{bb_op} ({bb_rt:.2f})</span></p>
      <p>👎 <strong>Worst lost to:</strong> <span class="num">{wl_op} ({wl_rt:.2f})</span></p>
      <p>📉 <strong>Avg rating beaten:</strong> <span class="num">{avg_b:.2f}</span></p>
      <p>📈 <strong>Avg rating lost to:</strong> <span class="num">{avg_l:.2f}</span></p>
      <p>🔢 <strong>Set1 Win %:</strong> <span class="num">{s1:.1%}</span> 
         | <strong>Set2:</strong> <span class="num">{s2:.1%}</span> 
         | <strong>Set3:</strong> <span class="num">{s3:.1%}</span></p>
      <p>⚡ <strong>Biggest upset win:</strong> <span class="num">vs {up_op}, {up_diff:.2f} difference</span></p>
      <p>⚡ <strong>Worst upset loss:</strong> <span class="num">vs {bl_op}, {bl_diff:.2f} difference</span></p>
    </div>
    """.format(
        total=len(df),
        setwin=stats['set_win_pct'],
        gamewin=stats['game_win_pct'],
        upset=stats['upset_win_pct'],
        fav=stats['favoured_win_pct'],
        csw=stats['close_set_won'], csl=stats['close_set_lost'],
        cs_pct=stats['close_set_won'] / (stats['close_set_won'] + stats['close_set_lost']) if (
                    stats['close_set_won'] + stats['close_set_lost']) else 0,
        bag_w=stats['bagels_won'], bag_l=stats['bagels_lost'],
        bag_pct=stats['bagels_won'] / (stats['bagels_won'] + stats['bagels_lost']) if (
                    stats['bagels_won'] + stats['bagels_lost']) else 0,
        br_w=stats['bread_won'], br_l=stats['bread_lost'],
        br_pct=stats['bread_won'] / (stats['bread_won'] + stats['bread_lost']) if (
                    stats['bread_won'] + stats['bread_lost']) else 0,
        bb_op=stats['best_beaten']['opponent'], bb_rt=stats['best_beaten']['rating'],
        wl_op=stats['worst_lost_to']['opponent'], wl_rt=stats['worst_lost_to']['rating'],
        avg_b=stats['avg_rating_beaten'], avg_l=stats['avg_rating_lostto'],
        s1=stats['set1_win_pct'], s2=stats['set2_win_pct'], s3=stats['set3_win_pct'],
        up_op=stats['biggest_upset_win']['opponent'], up_diff=stats['biggest_upset_win']['rating_diff'],
        bl_op=stats['biggest_bad_beat_loss']['opponent'], bl_diff=stats['biggest_bad_beat_loss']['rating_diff']
    )

    st.markdown(html, unsafe_allow_html=True)

with col_right:
    st.subheader("Rating Over Time")
    # prepare time-series
    hist = df[['match_date','floris_rating']].rename(
        columns={'match_date':'date','floris_rating':'rating'}
    )
    conn = sqlite3.connect('matches.db')
    cr   = pd.read_sql_query(
        "SELECT date, rating FROM current_ratings WHERE name = ?",
        conn, params=(player,), parse_dates=["date"]
    )
    conn.close()
    cr.columns = ['date','rating']
    all_data = pd.concat([hist, cr], ignore_index=True).sort_values('date')

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=all_data['date'], y=all_data['rating'],
        mode='lines+markers', line_shape='spline',
        marker=dict(size=6), name='Rating'
    ))
    best_idx = all_data['rating'].idxmin()
    fig.add_trace(go.Scatter(
        x=[all_data.loc[best_idx,'date']],
        y=[all_data.loc[best_idx,'rating']],
        mode='markers+text',
        text=[f"{all_data.loc[best_idx,'rating']:.2f}"],
        textposition='bottom center',
        marker=dict(size=12, color='red'),
        showlegend=False
    ))
    fig.update_layout(
        height=700,
        margin=dict(l=60, r=40, t=60, b=60),
        xaxis=dict(
            type='date', tickformat='%Y-%m-%d',
            dtick='M6', tickangle=-45
        ),
        yaxis=dict(title='Rating', autorange=True),
        plot_bgcolor='#fafafa', paper_bgcolor='#ffffff'
    )
    st.plotly_chart(fig, use_container_width=True)