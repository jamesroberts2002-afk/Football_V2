from pathlib import Path
import itertools
import random

import numpy as np
import pandas as pd
import streamlit as st
from supabase import create_client, Client 

DEFAULT_PLAYERS = [
    "Charlie",
    "Alasdair",
    "Joseph",
    "Dom",
    "Mo",
    "Harry",
    "Louis",
    "James R",
    "Ellis",
    "Kieran",
    "Jon",
    "Oliver",
    "Dan M",
    "Danny",
]
DEFAULT_TEAM_SIZE = 7

# Initialize connection.
# Uses st.cache_resource to only run once.
def init_connection():
    url = st.secrets.connections.supabase["SUPABASE_URL"]
    key = st.secrets.connections.supabase["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# Perform query.
@st.cache_data(show_spinner=False)
def run_query():
    return supabase.table("football_data").select("*").execute()

rows = run_query()

player_list = []
result_list = []
index_list = []
for row in rows.data:
    index_list.append(row["index"])
    player_list.append(row["Player"])
    result_list.append(row["Result"])

football_data = pd.DataFrame({
    "index": index_list,
    "Player": player_list,
    "Result": result_list,
}).set_index("index")


def save_history(history: pd.DataFrame) -> None:
    dict_list = []
    for index, row in history.reset_index().iterrows():
        temp_dict = {
            "index": row["index"],
            "Player": row["Player"],
            "Result": row["Result"]
        }
        dict_list.append(temp_dict)
    response = (
        supabase.table("football_data")
        .upsert(dict_list)
        .execute()
    )


def parse_players(player_text: str) -> list[str]:
    return [player.strip() for player in player_text.split(",") if player.strip()]


def build_result_editor() -> pd.DataFrame:
    return pd.DataFrame(columns=["Player", "Result"])


def compute_weighted_scores(players: list[str], history: pd.DataFrame) -> dict[str, float]:
    wins = {}
    losses = {}
    for player in players:
        player_results = history.loc[history["Player"] == player, "Result"].astype(str).str.upper()
        wins[player] = int((player_results == "W").sum())
        losses[player] = int((player_results == "L").sum())

    totals = {player: wins[player] + losses[player] for player in players}
    weight_const = float(np.mean(list(totals.values()))) if totals else 1.0

    scores = {}
    for player in players:
        total_games = totals[player]
        win_rate = wins[player] / total_games if total_games else 0.0
        scores[player] = (
            wins[player] + weight_const * win_rate
        ) / (losses[player] + wins[player] + weight_const)

    return scores


def generate_balanced_teams(players: list[str], team_size: int, history: pd.DataFrame):
    scores = compute_weighted_scores(players, history)
    all_teams = list(itertools.combinations(players, team_size))

    match_ratings = []
    for team in all_teams:
        team_a_rank = sum(scores[player] for player in team)
        team_b = [player for player in players if player not in team]
        team_b_rank = sum(scores[player] for player in team_b)
        match_ratings.append(
            {
                "match_rating": abs(team_a_rank - team_b_rank),
                "team_a": team,
                "team_b": tuple(team_b),
            }
        )

    best_rating = min(option["match_rating"] for option in match_ratings)
    best_options = [option for option in match_ratings if option["match_rating"] == best_rating]
    chosen = random.choice(best_options)
    return chosen, best_options, scores


st.set_page_config(page_title="Football Team Generator", page_icon="⚽")
st.title("Football Team Generator")

history = football_data

with st.sidebar:
    st.header("Setup")
    player_text = st.text_area(
        "Players (comma separated)",
        value=", ".join(DEFAULT_PLAYERS),
        height=140,
    )
    players = parse_players(player_text)
    max_team_size = max(2, len(players)) if players else 2
    team_size = st.number_input(
        "Team size",
        min_value=2,
        max_value=max_team_size,
        value=min(DEFAULT_TEAM_SIZE, max_team_size),
        step=1,
    )

    st.subheader("Last week results")
    if "results_editor_df" not in st.session_state:
        st.session_state.results_editor_df = build_result_editor()

    result_editor = st.data_editor(
        st.session_state.results_editor_df,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Player": st.column_config.TextColumn("Player", required=True),
            "Result": st.column_config.SelectboxColumn(
                "Result",
                options=["W", "L"],
                required=True,
            ),
        },
        key="results_editor",
    )
    st.session_state.results_editor_df = result_editor

    if st.button("Save results"):
        cleaned_results = result_editor.copy()
        cleaned_results = cleaned_results.dropna(how="all")
        cleaned_results = cleaned_results[
            cleaned_results["Player"].astype(str).str.strip() != ""
        ]
        if cleaned_results.empty:
            st.warning("Enter at least one player/result row before saving.")
        else:
            cleaned_results = cleaned_results[["Player", "Result"]].copy()
            cleaned_results["Result"] = cleaned_results["Result"].astype(str).str.upper()
            cleaned_results = cleaned_results[cleaned_results["Result"].isin(["W", "L"])]
            if not cleaned_results.empty:
                history = pd.concat([history, cleaned_results], ignore_index=True)
                save_history(history)
                st.success("Results saved to football.csv")
                st.session_state.results_editor_df = build_result_editor()

st.subheader("History")
st.dataframe(history, use_container_width=True)

if players:
    if len(players) < team_size:
        st.warning("The team size cannot be larger than the number of players.")
    else:
        selected_option, all_options, scores = generate_balanced_teams(players, team_size, history)
        team_a = selected_option["team_a"]
        team_b = selected_option["team_b"]

        st.subheader("Balanced teams")
        st.write("Selected balanced split")
        st.write(f"Team A: {list(team_a)}")
        st.write(f"Team B: {list(team_b)}")

        st.subheader("All equally balanced options")
        if len(all_options) == 1:
            st.write("Only one equally balanced split was found.")
        else:
            for index, option in enumerate(all_options, start=1):
                st.write(f"{index}. Team A: {list(option['team_a'])} | Team B: {list(option['team_b'])}")

        st.caption("Player rankings")
        ranking_df = pd.DataFrame(
            {
                "Player": list(scores.keys()),
                "Score": list(scores.values()),
            }
        ).sort_values("Score", ascending=False)
        st.dataframe(ranking_df, use_container_width=True)
else:
    st.info("Add at least one player name to generate teams.")

