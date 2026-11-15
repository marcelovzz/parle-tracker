"""
espn_live.py
Módulo para consultar los endpoints públicos de ESPN (scoreboard y summary)
para NBA, NFL, MLB, NHL y Liga MX, y evaluar el estado de cobertura de cada selección.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import requests

logger = logging.getLogger(__name__)

ESPN_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"

SUPPORTED_SPORTS: Dict[str, str] = {
    "NBA": "basketball/nba",
    "NFL": "football/nfl",
    "MLB": "baseball/mlb",
    "NHL": "hockey/nhl",
    "Liga MX": "soccer/mex.1",
}

DEFAULT_LOGOS: Dict[str, str] = {
    "basketball/nba": "https://a.espncdn.com/i/teamlogos/leagues/500/nba.png",
    "football/nfl": "https://a.espncdn.com/i/teamlogos/leagues/500/nfl.png",
    "baseball/mlb": "https://a.espncdn.com/i/teamlogos/leagues/500/mlb.png",
    "hockey/nhl": "https://a.espncdn.com/i/teamlogos/leagues/500/nhl.png",
    "soccer/mex.1": "https://a.espncdn.com/i/leaguelogos/soccer/500/22.png",
}

REQUEST_TIMEOUT = 8


def get_cdn_logo(sport: str, team_abbr: str) -> str:
    """Devuelve URL de respaldo del CDN oficial de ESPN para un equipo."""
    abbr = (team_abbr or "").strip().lower()
    if not abbr:
        return DEFAULT_LOGOS.get(sport, DEFAULT_LOGOS["basketball/nba"])
    if sport == "basketball/nba":
        return f"https://a.espncdn.com/i/teamlogos/nba/500/{abbr}.png"
    if sport == "football/nfl":
        return f"https://a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png"
    if sport == "baseball/mlb":
        return f"https://a.espncdn.com/i/teamlogos/mlb/500/{abbr}.png"
    if sport == "hockey/nhl":
        return f"https://a.espncdn.com/i/teamlogos/nhl/500/{abbr}.png"
    return DEFAULT_LOGOS.get(sport, DEFAULT_LOGOS["basketball/nba"])


def fetch_scoreboard(sport: str) -> Dict[str, Any]:
    """Obtiene el JSON de scoreboard desde ESPN con manejo seguro de errores de red."""
    url = f"{ESPN_BASE_URL}/{sport}/scoreboard"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Error consultando scoreboard de %s: %s", sport, exc)
        return {"events": []}


def fetch_game_summary(sport: str, event_id: str) -> Dict[str, Any]:
    """Obtiene el JSON de summary (boxscore detallado) de un partido de ESPN."""
    url = f"{ESPN_BASE_URL}/{sport}/summary"
    try:
        resp = requests.get(url, params={"event": event_id}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Error consultando summary %s (%s): %s", event_id, sport, exc)
        return {}


def _find_event_for_team(
    events: List[Dict[str, Any]], team_abbr: str, opponent_abbr: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Busca el evento correspondiente al equipo (o rival) en la lista de eventos del día."""
    target = (team_abbr or "").strip().upper()
    opp = (opponent_abbr or "").strip().upper()

    for event in events:
        competitions = event.get("competitions", [])
        if not competitions:
            continue
        competitors = competitions[0].get("competitors", [])
        abbrs = {
            c.get("team", {}).get("abbreviation", "").upper(): c
            for c in competitors
        }
        names = {
            c.get("team", {}).get("shortDisplayName", "").upper(): c
            for c in competitors
        }
        if target in abbrs or target in names:
            return event
        if opp and (opp in abbrs or opp in names):
            return event
    return None


def extract_player_stat_from_summary(
    summary_data: Dict[str, Any],
    player_name: str,
    stat_type: Optional[str] = None,
) -> Tuple[Optional[float], str]:
    """
    Busca a un jugador en el boxscore del endpoint `summary` de ESPN y extrae
    el valor numérico de la estadística solicitada (puntos, rebotes, asistencias,
    yardas por pase, yardas por acarreo, yardas por recepción, hits, etc.).
    """
    if not summary_data or not player_name:
        return None, ""

    target_name = player_name.strip().lower()
    stat_key = (stat_type or "points").strip().lower()

    # Mapeo de nombres de categorías y columnas en ESPN boxscore
    stat_aliases: Dict[str, Tuple[Optional[str], List[str], str]] = {
        "points": (None, ["pts", "points"], "PTS"),
        "pts": (None, ["pts", "points"], "PTS"),
        "rebounds": (None, ["reb", "rebounds"], "REB"),
        "reb": (None, ["reb", "rebounds"], "REB"),
        "assists": (None, ["ast", "assists"], "AST"),
        "ast": (None, ["ast", "assists"], "AST"),
        "threes": (None, ["3pt", "3pm"], "3PM"),
        "passing_yards": ("passing", ["yds", "passing yards"], "PASS YDS"),
        "pass_yds": ("passing", ["yds", "passing yards"], "PASS YDS"),
        "rushing_yards": ("rushing", ["yds", "rushing yards"], "RUSH YDS"),
        "rush_yds": ("rushing", ["yds", "rushing yards"], "RUSH YDS"),
        "receiving_yards": ("receiving", ["yds", "receiving yards"], "REC YDS"),
        "rec_yds": ("receiving", ["yds", "receiving yards"], "REC YDS"),
        "receptions": ("receiving", ["rec", "receptions"], "REC"),
        "hits": ("batting", ["h", "hits"], "H"),
        "strikeouts": ("pitching", ["k", "so", "strikeouts"], "K"),
        "goals": (None, ["g", "goals"], "G"),
        "shots": (None, ["s", "sog", "shots"], "SOG"),
    }

    category_filter, label_candidates, display_unit = stat_aliases.get(
        stat_key, (None, [stat_key, "pts", "yds"], stat_key.upper())
    )

    boxscore = summary_data.get("boxscore", {})
    players_sections = boxscore.get("players", [])

    for team_section in players_sections:
        for stat_group in team_section.get("statistics", []):
            group_name = (stat_group.get("name") or "").lower()
            if category_filter and category_filter not in group_name:
                continue

            labels = [lbl.lower() for lbl in stat_group.get("labels", [])]
            names = [nm.lower() for nm in stat_group.get("names", [])]

            col_idx: Optional[int] = None
            for cand in label_candidates:
                if cand in labels:
                    col_idx = labels.index(cand)
                    break
                if cand in names:
                    col_idx = names.index(cand)
                    break
            if col_idx is None and labels:
                col_idx = 0

            for athlete_entry in stat_group.get("athletes", []):
                athlete = athlete_entry.get("athlete", {})
                disp_name = (athlete.get("displayName") or "").lower()
                short_name = (athlete.get("shortName") or "").lower()

                if target_name in disp_name or disp_name in target_name or target_name in short_name:
                    stats_list = athlete_entry.get("stats", [])
                    if col_idx is not None and col_idx < len(stats_list):
                        raw_val = str(stats_list[col_idx])
                        # Manejo de formatos como "3-7" en triples o "22/31" en pases
                        if "-" in raw_val and not raw_val.startswith("-"):
                            raw_val = raw_val.split("-")[0]
                        elif "/" in raw_val:
                            raw_val = raw_val.split("/")[0]
                        try:
                            return float(raw_val), display_unit
                        except ValueError:
                            return 0.0, display_unit

    return 0.0, display_unit


def evaluate_selection(
    selection: Dict[str, Any],
    scoreboard_cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Evalúa una selección del parlay contra los datos en vivo de ESPN.
    Devuelve:
      - state: 'pre' | 'in' | 'post'
      - status: 'pending' | 'covering' | 'trailing' | 'won' | 'lost' | 'push'
      - progress_pct: float (0 a 100) para el anillo SVG circular
      - score_text: ej. 'LAL 75 - 57 PHX · 3rd 8:51'
      - logo_url: URL del logo en CDN de ESPN
      - current_value: float (marcador relevante o estadística actual)
      - is_covering: bool
    """
    sport = selection.get("sport", "basketball/nba")
    team_abbr = (selection.get("team") or "").strip().upper()
    opponent_abbr = (selection.get("opponent") or "").strip().upper()
    market_type = (selection.get("market_type") or "moneyline").strip().lower()
    line = selection.get("line")
    line_val = float(line) if line is not None and str(line) != "" else 0.0
    player_name = selection.get("player_name")
    stat_type = selection.get("stat_type")

    if scoreboard_cache is not None and sport in scoreboard_cache:
        sb_data = scoreboard_cache[sport]
    else:
        sb_data = fetch_scoreboard(sport)
        if scoreboard_cache is not None:
            scoreboard_cache[sport] = sb_data

    events = sb_data.get("events", [])
    event = _find_event_for_team(events, team_abbr, opponent_abbr)

    logo_url = get_cdn_logo(sport, team_abbr)

    if not event:
        opp_display = f" vs {opponent_abbr}" if opponent_abbr else ""
        return {
            "state": "pre",
            "status": "pending",
            "progress_pct": 0.0,
            "score_text": f"{team_abbr}{opp_display} · Programado",
            "logo_url": logo_url,
            "current_value": 0.0,
            "is_covering": False,
            "event_id": None,
        }

    event_id = str(event.get("id", ""))
    competition = (event.get("competitions") or [{}])[0]
    status_obj = competition.get("status") or event.get("status") or {}
    status_type = status_obj.get("type", {})

    state = status_type.get("state", "pre")  # 'pre', 'in', 'post'
    short_detail = status_type.get("shortDetail") or status_type.get("detail") or ""

    competitors = competition.get("competitors", [])
    team_comp: Optional[Dict[str, Any]] = None
    opp_comp: Optional[Dict[str, Any]] = None

    for comp in competitors:
        c_abbr = (comp.get("team", {}).get("abbreviation") or "").upper()
        c_short = (comp.get("team", {}).get("shortDisplayName") or "").upper()
        if c_abbr == team_abbr or c_short == team_abbr:
            team_comp = comp
        else:
            opp_comp = comp

    if team_comp is None and competitors:
        team_comp = competitors[0]
        opp_comp = competitors[1] if len(competitors) > 1 else {}

    team_info = (team_comp or {}).get("team", {})
    opp_info = (opp_comp or {}).get("team", {})

    team_code = team_info.get("abbreviation", team_abbr or "TM1")
    opp_code = opp_info.get("abbreviation", opponent_abbr or "TM2")
    if team_info.get("logo"):
        logo_url = team_info["logo"]

    try:
        team_score = int(float((team_comp or {}).get("score", 0) or 0))
    except (ValueError, TypeError):
        team_score = 0

    try:
        opp_score = int(float((opp_comp or {}).get("score", 0) or 0))
    except (ValueError, TypeError):
        opp_score = 0

    if state == "pre":
        score_text = f"{team_code} vs {opp_code} · {short_detail or 'Por iniciar'}"
        return {
            "state": "pre",
            "status": "pending",
            "progress_pct": 0.0,
            "score_text": score_text,
            "logo_url": logo_url,
            "current_value": 0.0,
            "is_covering": False,
            "event_id": event_id,
        }

    base_score_str = f"{team_code} {team_score} - {opp_score} {opp_code} · {short_detail}"
    is_covering = False
    progress_pct = 0.0
    current_value = float(team_score)
    prop_suffix = ""

    if market_type == "moneyline":
        diff = team_score - opp_score
        is_covering = diff > 0
        # Cálculo visual del porcentaje de cobertura en vivo
        if diff > 0:
            progress_pct = min(95.0, 55.0 + diff * 3.0)
        elif diff == 0:
            progress_pct = 50.0
        else:
            progress_pct = max(10.0, 45.0 + diff * 3.0)

    elif market_type == "spread":
        adjusted_diff = (team_score + line_val) - opp_score
        is_covering = adjusted_diff > 0
        if adjusted_diff > 0:
            progress_pct = min(95.0, 55.0 + adjusted_diff * 3.0)
        elif adjusted_diff == 0:
            progress_pct = 50.0
        else:
            progress_pct = max(10.0, 45.0 + adjusted_diff * 3.0)

    elif market_type == "total_over":
        total_pts = float(team_score + opp_score)
        current_value = total_pts
        is_covering = total_pts > line_val
        if line_val > 0:
            progress_pct = min(100.0, max(5.0, (total_pts / line_val) * 100.0))
        prop_suffix = f" (Total: {int(total_pts)}/{line_val})"

    elif market_type == "total_under":
        total_pts = float(team_score + opp_score)
        current_value = total_pts
        is_covering = total_pts < line_val
        if line_val > 0:
            rem_ratio = max(0.0, (line_val - total_pts) / line_val)
            progress_pct = min(95.0, max(10.0, rem_ratio * 100.0)) if is_covering else 0.0
        prop_suffix = f" (Total: {int(total_pts)}/{line_val})"

    elif market_type == "player_prop":
        summary_data = fetch_game_summary(sport, event_id)
        stat_val, unit = extract_player_stat_from_summary(
            summary_data, player_name or "", stat_type
        )
        stat_num = float(stat_val or 0.0)
        current_value = stat_num
        is_covering = stat_num > line_val
        if line_val > 0:
            progress_pct = min(100.0, max(5.0, (stat_num / line_val) * 100.0))
        disp_val = int(stat_num) if stat_num.is_integer() else stat_num
        prop_suffix = f" · {player_name}: {disp_val}/{line_val} {unit}".rstrip()

    score_text = f"{base_score_str}{prop_suffix}"

    if state == "post":
        if is_covering:
            status = "won"
            progress_pct = 100.0
        else:
            status = "lost"
            progress_pct = 100.0
    else:
        status = "covering" if is_covering else "trailing"
        if is_covering and progress_pct < 25.0:
            progress_pct = 35.0

    return {
        "state": state,
        "status": status,
        "progress_pct": round(progress_pct, 1),
        "score_text": score_text,
        "logo_url": logo_url,
        "current_value": current_value,
        "is_covering": is_covering,
        "event_id": event_id,
    }
