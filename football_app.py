import itertools
import random
from datetime import date
from html import escape

import pandas as pd
import streamlit as st
from supabase import create_client


DEFAULT_PLAYERS = """Charlie
Alasdair
Joseph
Dom
Mo
Harry
Louis
James R
Ellis
Kieran
Jon
Oliver
Dan M
Danny"""

DEFAULT_TEAM_SIZE = 7


def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


supabase = init_connection()


@st.cache_data(show_spinner=False)
def load_history() -> pd.DataFrame:
    response = (
        supabase
        .table("football_data")
        .select("*")
        .order("id", desc=True)
        .execute()
    )

    data = response.data or []

    if not data:
        return pd.DataFrame(
            columns=["Date", "Player", "Result"]
        )

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
    return [
        player.strip()
        for player in player_text.splitlines()
        if player.strip()
    ]


def build_result_editor() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["Player", "Result"]
    )


def compute_weighted_scores(
    players: list[str],
    history: pd.DataFrame,
) -> dict[str, float]:
    raw_scores = {}

    for player in players:
        player_results = (
            history.loc[
                history["Player"] == player,
                "Result",
            ]
            .astype(str)
            .str.upper()
        )

        wins = int((player_results == "W").sum())
        losses = int((player_results == "L").sum())
        total_games = wins + losses

        if total_games == 0:
            raw_scores[player] = None
        else:
            weight_const = max(
                1.0,
                float(len(players)),
            )

            win_rate = wins / total_games

            raw_scores[player] = (
                wins + weight_const * win_rate
            ) / (
                total_games + weight_const
            )

    known_scores = [
        score
        for score in raw_scores.values()
        if score is not None
    ]

    average_score = (
        sum(known_scores) / len(known_scores)
        if known_scores
        else 0.0
    )

    return {
        player: (
            score
            if score is not None
            else average_score
        )
        for player, score in raw_scores.items()
    }


def summarize_players(history: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Player",
        "Games",
        "Wins",
        "Losses",
        "Score",
    ]

    if history.empty:
        return pd.DataFrame(columns=columns)

    players = sorted(
        history["Player"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    scores = compute_weighted_scores(
        players,
        history,
    )

    rows = []

    for player in players:
        player_results = (
            history.loc[
                history["Player"] == player,
                "Result",
            ]
            .astype(str)
            .str.upper()
        )

        wins = int((player_results == "W").sum())
        losses = int((player_results == "L").sum())
        games = wins + losses

        rows.append(
            {
                "Player": player,
                "Games": games,
                "Wins": wins,
                "Losses": losses,
                "Score": scores.get(
                    player,
                    0.0,
                ),
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values(
            "Score",
            ascending=False,
        )
        .reset_index(drop=True)
    )


def generate_balanced_teams(
    players: list[str],
    team_size: int,
    history: pd.DataFrame,
):
    scores = compute_weighted_scores(
        players,
        history,
    )

    all_teams = list(
        itertools.combinations(
            players,
            team_size,
        )
    )

    match_ratings = []

    for team_a in all_teams:
        team_b = [
            player
            for player in players
            if player not in team_a
        ]

        team_a_score = sum(
            scores[player]
            for player in team_a
        )

        team_b_score = sum(
            scores[player]
            for player in team_b
        )

        match_rating = abs(
            team_a_score - team_b_score
        )

        match_ratings.append(
            {
                "match_rating": match_rating,
                "team_a": team_a,
                "team_b": tuple(team_b),
            }
        )

    best_rating = min(
        option["match_rating"]
        for option in match_ratings
    )

    best_options = [
        option
        for option in match_ratings
        if option["match_rating"] == best_rating
    ]

    chosen = random.choice(best_options)

    return chosen, scores


def team_card(title: str, team: list[str]) -> None:
    players_html = "<br>".join(
        escape(player)
        for player in team
    )

    st.markdown(
        f"""
        <div style="
            border: 1px solid rgba(128, 128, 128, 0.35);
            border-radius: 14px;
            padding: 22px 24px;
            text-align: center;
        ">
            <div style="
                font-size: 1.15rem;
                font-weight: 700;
                margin-bottom: 12px;
            ">
                {escape(title)}
            </div>

            <div style="
                font-size: 1.02rem;
                line-height: 1.7;
            ">
                {players_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def highlight_new_rows(df: pd.DataFrame) -> pd.DataFrame:
    styles = pd.DataFrame(
        "",
        index=df.index,
        columns=df.columns,
    )

    if "Games" in df.columns:
        styles.loc[
            df["Games"] == 0,
            :
        ] = "background-color: #FFF7CC"

    return styles


st.set_page_config(
    page_title="Football Team Generator",
    page_icon="⚽",
    layout="wide",
)

st.title("⚽ Football Team Generator")

history = load_history()

history_dates = pd.to_datetime(
    history["Date"],
    errors="coerce",
)

available_years = sorted(
    history_dates.dropna()
    .dt.year
    .astype(int)
    .unique()
    .tolist(),
    reverse=True,
)

overall_summary = summarize_players(history)


with st.sidebar:
    st.header("🛠️ Setup")

    if "team_size" not in st.session_state:
        st.session_state.team_size = DEFAULT_TEAM_SIZE

    with st.form("team_setup_form"):
        player_text = st.text_area(
            "Players — one per line",
            value=DEFAULT_PLAYERS,
            height=260,
        )

        players = parse_players(player_text)

        max_team_size = (
            max(2, len(players))
            if players
            else 2
        )

        if st.session_state.team_size > max_team_size:
            st.session_state.team_size = max_team_size

        team_size = st.number_input(
            "Team size",
            min_value=2,
            max_value=max_team_size,
            step=1,
            key="team_size",
        )

        generate_clicked = st.form_submit_button(
            "Generate teams"
        )

    st.subheader("📝 Last week results")

    result_date = st.date_input(
        "Date",
        value=date.today(),
    )

    with st.form(
        "results_form",
        clear_on_submit=False,
    ):
        result_editor = st.data_editor(
            build_result_editor(),
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Player": st.column_config.TextColumn(
                    "Player",
                    required=True,
                ),
                "Result": st.column_config.SelectboxColumn(
                    "Result",
                    options=["W", "L"],
                    required=True,
                ),
            },
            key="results_editor_form",
        )

        submitted = st.form_submit_button(
            "Save results"
        )

        if submitted:
            cleaned = result_editor.copy()

            cleaned = cleaned.dropna(
                how="all"
            )

            cleaned = cleaned[
                cleaned["Player"]
                .astype(str)
                .str.strip()
                != ""
            ].copy()

            if cleaned.empty:
                st.warning(
                    "Enter at least one player/result row before saving."
                )
            else:
                cleaned = cleaned[
                    ["Player", "Result"]
                ].copy()

                cleaned["Player"] = (
                    cleaned["Player"]
                    .astype(str)
                    .str.strip()
                )

                cleaned["Result"] = (
                    cleaned["Result"]
                    .astype(str)
                    .str.upper()
                )

                cleaned = cleaned[
                    cleaned["Result"].isin(["W", "L"])
                ]

                if cleaned.empty:
                    st.warning(
                        "No valid W/L rows to save."
                    )
                else:
                    cleaned["Date"] = (
                        result_date.isoformat()
                    )

                    save_results(cleaned)
                    load_history.clear()

                    st.success(
                        f"Saved {len(cleaned)} results "
                        f"for {result_date.isoformat()}."
                    )

                    st.rerun()


st.subheader("📚 History")

st.dataframe(
    history,
    use_container_width=True,
    height=260,
)

st.divider()


summary_col1, summary_col2 = st.columns(2)


with summary_col1:
    title_col, dropdown_col = st.columns(
        [1.2, 0.8]
    )

    with title_col:
        st.subheader("📅 Players by year")

    with dropdown_col:
        if available_years:
            current_year = date.today().year

            if current_year in available_years:
                default_year_index = (
                    available_years.index(current_year)
                )
            else:
                default_year_index = 0

            selected_year = st.selectbox(
                "Year",
                options=available_years,
                index=default_year_index,
            )
        else:
            selected_year = None

    if selected_year is not None:
        selected_year_history = history[
            history_dates.dt.year == selected_year
        ].copy()

        yearly_summary = summarize_players(
            selected_year_history
        )

        st.dataframe(
            yearly_summary,
            use_container_width=True,
            height=300,
        )
    else:
        st.info(
            "No dated results are available yet."
        )


with summary_col2:
    st.subheader("🌍 Overall players")

    st.dataframe(
        overall_summary,
        use_container_width=True,
        height=300,
    )


st.divider()


if not players:
    st.info(
        "Enter the players for this week, "
        "then generate the teams."
    )

elif len(players) < team_size:
    st.warning(
        "The team size cannot be larger "
        "than the number of players."
    )

else:
    if generate_clicked:
        selected_option, scores = (
            generate_balanced_teams(
                players,
                team_size,
                history,
            )
        )

        rankings_col, spacer_col, teams_col = st.columns(
            [1, 0.15, 1.05]
        )

        with rankings_col:
            st.subheader("🏅 Player rankings")

            ranking_df = summarize_players(
                history[
                    history["Player"].isin(players)
                ]
            )

            styled_ranking = ranking_df.style.apply(
                highlight_new_rows,
                axis=None,
            )

            st.dataframe(
                styled_ranking,
                use_container_width=True,
                height=360,
            )

        with teams_col:
            st.subheader("Chosen teams")

            team_a_col, team_b_col = st.columns(
                2,
                gap="small",
            )

            with team_a_col:
                team_card(
                    "Team A",
                    list(selected_option["team_a"]),
                )

            with team_b_col:
                team_card(
                    "Team B",
                    list(selected_option["team_b"]),
                )
