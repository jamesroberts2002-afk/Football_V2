import itertools
import random

import pandas as pd
import streamlit as st
from supabase import create_client

DEFAULT_PLAYERS = [
]
DEFAULT_TEAM_SIZE = 6


def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


supabase = init_connection()


@st.cache_data(show_spinner=False)
def load_history():
    response = supabase.table("football_data").select("*").execute()
    data = response.data or []
    if not data:
        return pd.DataFrame(columns=["Player", "Result"])

    df = pd.DataFrame(data)

    if "Player" not in df.columns:
        df["Player"] = ""
    if "Result" not in df.columns:
        df["Result"] = ""

    return df[["Player", "Result"]].copy()


def save_results(results_df: pd.DataFrame) -> None:
    records = results_df.to_dict("records")
    if records:
        supabase.table("football_data").insert(records).execute()


def parse_players(player_text: str) -> list[str]:
    return [p.strip() for p in player_text.split(",") if p.strip()]


def build_result_editor() -> pd.DataFrame:
    return pd.DataFrame(columns=["Player", "Result"])


def compute_weighted_scores(players: list[str], history: pd.DataFrame) -> dict[str, float]:
    scores = {}

    for player in players:
        player_results = history.loc[history["Player"] == player, "Result"].astype(str).str.upper()
        wins = int((player_results == "W").sum())
        losses = int((player_results == "L").sum())
        total = wins + losses

        if total == 0:
            scores[player] = 0.0
        else:
            weight_const = max(1.0, float(len(players)))
            win_rate = wins / total
            scores[player] = (wins + weight_const * win_rate) / (total + weight_const)

    return scores


def generate_balanced_teams(players: list[str], team_size: int, history: pd.DataFrame):
    scores = compute_weighted_scores(players, history)
    all_teams = list(itertools.combinations(players, team_size))

    match_ratings = []
    for team_a in all_teams:
        team_b = [p for p in players if p not in team_a]
        rating = abs(sum(scores[p] for p in team_a) - sum(scores[p] for p in team_b))
        match_ratings.append(
            {
                "match_rating": rating,
                "team_a": team_a,
                "team_b": tuple(team_b),
            }
        )

    best_rating = min(x["match_rating"] for x in match_ratings)
    best_options = [x for x in match_ratings if x["match_rating"] == best_rating]
    chosen = random.choice(best_options)
    return chosen, best_options, scores


st.set_page_config(page_title="Football Team Generator", page_icon="⚽")
st.title("Football Team Generator")

history = load_history()

st.subheader("Debug: loaded history")
st.write(f"Rows loaded: {len(history)}")
st.dataframe(history.head(20), use_container_width=True)

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
        cleaned = result_editor.copy()
        cleaned = cleaned.dropna(how="all")
        cleaned = cleaned[cleaned["Player"].astype(str).str.strip() != ""].copy()

        if cleaned.empty:
            st.warning("Enter at least one player/result row before saving.")
        else:
            cleaned = cleaned[["Player", "Result"]].copy()
            cleaned["Player"] = cleaned["Player"].astype(str).str.strip()
            cleaned["Result"] = cleaned["Result"].astype(str).str.upper()
            cleaned = cleaned[cleaned["Result"].isin(["W", "L"])]

            if cleaned.empty:
                st.warning("No valid W/L rows to save.")
            else:
                save_results(cleaned)
                load_history.clear()
                st.session_state.results_editor_df = build_result_editor()
                st.success("Results saved.")
                st.rerun()

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
            for i, option in enumerate(all_options, start=1):
                st.write(f"{i}. Team A: {list(option['team_a'])} | Team B: {list(option['team_b'])}")

        st.caption("Player rankings")
        ranking_df = pd.DataFrame(
            {"Player": list(scores.keys()), "Score": list(scores.values())}
        ).sort_values("Score", ascending=False)
        st.dataframe(ranking_df, use_container_width=True)
else:
    st.info("Add at least one player name to generate teams.")
