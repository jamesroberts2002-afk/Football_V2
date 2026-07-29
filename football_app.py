import itertools
import random
from datetime import date

import pandas as pd
import streamlit as st
from supabase import create_client

DEFAULT_PLAYERS = [
    "Charlie", "Alasdair", "Joseph", "Dom", "Mo", "Harry", "Louis",
    "James R", "Ellis", "Kieran", "Jon", "Oliver", "Dan M", "Danny",
]
DEFAULT_TEAM_SIZE = 7


def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


supabase = init_connection()


@st.cache_data(show_spinner=False)
def load_history():
    response = supabase.table("football_data").select("*").order("id", desc=True).execute()
    data = response.data or []

    if not data:
        return pd.DataFrame(columns=["Date", "Player", "Result"])

    df = pd.DataFrame(data)

    if "Date" not in df.columns:
        df["Date"] = ""
    if "Player" not in df.columns:
        df["Player"] = ""
    if "Result" not in df.columns:
        df["Result"] = ""

    return df[["Date", "Player", "Result"]].copy()


def save_results(results_df: pd.DataFrame) -> None:
    records = results_df.to_dict("records")
    if records:
        supabase.table("football_data").insert(records).execute()


def parse_players(player_text: str) -> list[str]:
    return [p.strip() for p in player_text.split(",") if p.strip()]


def build_result_editor() -> pd.DataFrame:
    return pd.DataFrame(columns=["Player", "Result"])


def compute_weighted_scores(players: list[str], history: pd.DataFrame) -> dict[str, float]:
    raw_scores = {}

    for player in players:
        player_results = history.loc[history["Player"] == player, "Result"].astype(str).str.upper()
        wins = int((player_results == "W").sum())
        losses = int((player_results == "L").sum())
        total = wins + losses

        if total == 0:
            raw_scores[player] = None
        else:
            weight_const = max(1.0, float(len(players)))
            win_rate = wins / total
            raw_scores[player] = (wins + weight_const * win_rate) / (total + weight_const)

    known_scores = [v for v in raw_scores.values() if v is not None]
    average_score = sum(known_scores) / len(known_scores) if known_scores else 0.0

    return {
        player: (score if score is not None else average_score)
        for player, score in raw_scores.items()
    }


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
    return chosen, scores


def team_card(title: str, team: list[str]):
    players_html = "<br>".join(team)
    st.markdown(
        f"""
        <div style="
            border: 1px solid #D9D9D9;
            border-radius: 14px;
            padding: 16px 18px;
            background: #FAFAFA;
            min-height: 180px;
        ">
            <div style="font-size: 1.15rem; font-weight: 700; margin-bottom: 10px;">{title}</div>
            <div style="font-size: 1.02rem; line-height: 1.7;">{players_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="Football Team Generator", page_icon="⚽", layout="wide")
st.title("⚽ Football Team Generator")

history = load_history()

with st.sidebar:
    st.header("🛠️ Setup")

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

    st.subheader("📝 Last week results")
    result_date = st.date_input("Date", value=date.today())

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
                cleaned["Date"] = result_date.isoformat()
                save_results(cleaned)
                load_history.clear()
                st.session_state.results_editor_df = build_result_editor()
                st.success(f"Saved {len(cleaned)} results for {result_date.isoformat()}.")
                st.rerun()

st.subheader("📚 History")
st.dataframe(history, use_container_width=True, height=260)

st.divider()

if players and len(players) < team_size:
    st.warning("The team size cannot be larger than the number of players.")
elif not players:
    st.info("Enter the players for this week, save results, then generate the teams.")
else:
    st.subheader("Generate teams")

    if st.button("Generate teams"):
        selected_option, scores = generate_balanced_teams(players, team_size, history)

        rankings_col, spacer_col, teams_col = st.columns([1, 0.15, 1.05])

        with rankings_col:
            st.subheader("🏅 Player rankings")
            ranking_df = pd.DataFrame(
                {"Player": list(scores.keys()), "Score": list(scores.values())}
            ).sort_values("Score", ascending=False)
            st.dataframe(ranking_df, use_container_width=True, height=360)

        with teams_col:
            st.subheader("Chosen teams")

            team_a_col, team_b_col = st.columns(2, gap="small")
            with team_a_col:
                team_card("Team A", list(selected_option["team_a"]))
            with team_b_col:
                team_card("Team B", list(selected_option["team_b"]))
