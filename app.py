"""
app.py
Aplicación en Streamlit con estética Dark Mode idéntica a la pestaña "My Action"
de Action Network para seguir en vivo parlays de Caliente.mx y extraer tickets con Gemini.
"""

from __future__ import annotations

import base64
import html
import json
import math
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from espn_live import SUPPORTED_SPORTS, evaluate_selection
from monitor import NTFY_TOPIC, run_monitor, send_ntfy_notification

BASE_DIR = Path(__file__).resolve().parent
ACTIVE_PARLAY_PATH = BASE_DIR / "active_parlay.json"
LAST_NOTIFIED_PATH = BASE_DIR / "last_notified.json"

st.set_page_config(
    page_title="My Action · Caliente Parlay Tracker",
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Auto-refresco cada 30 segundos (30,000 ms)
st_autorefresh(interval=30_000, key="parlay_live_autorefresh")


def inject_action_network_css() -> None:
    """Inyecta el diseño móvil Dark Mode idéntico a la pestaña 'My Action' de Action Network."""
    st.markdown(
        """
        <style>
        /* Fondo principal #121318 y tipografía limpia */
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            background-color: #121318 !important;
            color: #F9FAFB !important;
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif;
        }
        .block-container {
            max-width: 500px !important;
            padding-top: 1.2rem !important;
            padding-bottom: 3rem !important;
        }
        /* Barra superior estilo My Action */
        .my-action-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 14px;
            padding-bottom: 8px;
            border-bottom: 1px solid #262936;
        }
        .my-action-title {
            font-size: 1.35rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: #FFFFFF;
            margin: 0;
        }
        .live-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(16, 185, 129, 0.14);
            color: #10B981;
            border: 1px solid rgba(16, 185, 129, 0.35);
            font-size: 0.72rem;
            font-weight: 700;
            padding: 3px 9px;
            border-radius: 999px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .live-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background-color: #10B981;
            box-shadow: 0 0 8px #10B981;
        }
        /* Tarjeta principal del Parlay (#1C1E26) */
        .parlay-card {
            background-color: #1C1E26;
            border: 1px solid #2A2D3A;
            border-radius: 14px;
            overflow: hidden;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.45);
            margin-bottom: 18px;
        }
        .parlay-card-header {
            padding: 15px 16px 13px 16px;
            border-bottom: 1px solid #282B37;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .parlay-header-left {
            display: flex;
            flex-direction: column;
            gap: 3px;
        }
        .parlay-title-row {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .parlay-legs-title {
            font-size: 1.02rem;
            font-weight: 700;
            color: #FFFFFF;
        }
        .parlay-odds-badge {
            background-color: #262936;
            color: #D1D5DB;
            font-size: 0.78rem;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 6px;
        }
        .parlay-book-sub {
            font-size: 0.76rem;
            color: #9CA3AF;
        }
        .parlay-header-right {
            text-align: right;
        }
        .parlay-wager-label {
            font-size: 0.74rem;
            color: #9CA3AF;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .parlay-wager-amount {
            font-size: 0.98rem;
            font-weight: 700;
            color: #10B981;
        }
        /* Filas de cada selección del parlay */
        .leg-row {
            display: flex;
            align-items: center;
            padding: 13px 16px;
            border-bottom: 1px solid #252834;
            gap: 13px;
        }
        .leg-row:last-child {
            border-bottom: none;
        }
        .leg-ring-wrapper {
            position: relative;
            width: 44px;
            height: 44px;
            flex-shrink: 0;
        }
        .leg-team-logo {
            position: absolute;
            bottom: -2px;
            right: -2px;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background-color: #121318;
            border: 1.5px solid #2A2D3A;
            object-fit: contain;
            padding: 1px;
        }
        .leg-details {
            flex: 1;
            min-width: 0;
        }
        .leg-pick-title {
            font-size: 0.96rem;
            font-weight: 700;
            color: #FFFFFF;
            line-height: 1.25;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .leg-score-sub {
            font-size: 0.80rem;
            color: #9CA3AF;
            margin-top: 3px;
            line-height: 1.25;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .leg-status-pill {
            font-size: 0.72rem;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            flex-shrink: 0;
        }
        .pill-won, .pill-covering {
            background-color: rgba(16, 185, 129, 0.15);
            color: #10B981;
        }
        .pill-lost, .pill-trailing {
            background-color: rgba(239, 68, 68, 0.15);
            color: #EF4444;
        }
        .pill-pending {
            background-color: #262936;
            color: #9CA3AF;
        }
        /* Ajustes de widgets Streamlit en Dark Mode */
        div[data-testid="stExpander"] {
            background-color: #1C1E26 !important;
            border: 1px solid #2A2D3A !important;
            border-radius: 12px !important;
            margin-bottom: 12px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def load_active_parlay() -> Dict[str, Any]:
    """Carga `active_parlay.json` o devuelve una estructura vacía válida."""
    default_parlay: Dict[str, Any] = {
        "wager_mxn": 500.0,
        "total_odds": "+100",
        "potential_payout_mxn": 1000.0,
        "selections": [],
    }
    if not ACTIVE_PARLAY_PATH.exists():
        return default_parlay
    try:
        with ACTIVE_PARLAY_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "selections" in data:
                return data
    except Exception:
        pass
    return default_parlay


def get_secret_or_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Obtiene una variable desde el entorno o desde `st.secrets`."""
    val = os.getenv(key)
    if val:
        return val.strip()
    try:
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return default


def _github_upsert_file(
    repo: str,
    token: str,
    file_path: str,
    content_str: str,
    commit_message: str,
    branch: Optional[str] = None,
) -> Tuple[bool, str]:
    """Crea o actualiza un archivo en GitHub usando la API REST de contenidos."""
    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params: Dict[str, str] = {}
    if branch:
        params["ref"] = branch

    sha: Optional[str] = None
    try:
        get_resp = requests.get(api_url, headers=headers, params=params, timeout=10)
        if get_resp.status_code == 200:
            sha = get_resp.json().get("sha")
        elif get_resp.status_code != 404:
            return False, f"GET {file_path} devolvió {get_resp.status_code}: {get_resp.text}"
    except Exception as exc:
        return False, f"Error de red consultando {file_path} en GitHub: {exc}"

    encoded_content = base64.b64encode(content_str.encode("utf-8")).decode("ascii")
    payload: Dict[str, Any] = {
        "message": commit_message,
        "content": encoded_content,
    }
    if sha:
        payload["sha"] = sha
    if branch:
        payload["branch"] = branch

    try:
        put_resp = requests.put(api_url, headers=headers, json=payload, timeout=12)
        if put_resp.status_code in (200, 201):
            return True, "OK"
        return False, f"PUT {file_path} devolvió {put_resp.status_code}: {put_resp.text}"
    except Exception as exc:
        return False, f"Error de red subiendo {file_path} a GitHub: {exc}"


def sync_parlay_to_github(parlay_json_str: str) -> Tuple[bool, str]:
    """
    Sincroniza `active_parlay.json` y reinicia `last_notified.json` directamente
    en el repositorio de GitHub vía REST API usando GITHUB_TOKEN y GITHUB_REPO.
    """
    token = get_secret_or_env("GITHUB_TOKEN")
    repo = get_secret_or_env("GITHUB_REPO")
    branch = get_secret_or_env("GITHUB_BRANCH")

    if not token or not repo:
        return (
            False,
            "Guardado localmente (configura GITHUB_TOKEN y GITHUB_REPO para sincronizar con GitHub).",
        )

    ok_parlay, msg_parlay = _github_upsert_file(
        repo=repo,
        token=token,
        file_path="active_parlay.json",
        content_str=parlay_json_str,
        commit_message="chore(parlay): update active_parlay.json from Streamlit",
        branch=branch,
    )
    if not ok_parlay:
        return False, msg_parlay

    ok_reset, msg_reset = _github_upsert_file(
        repo=repo,
        token=token,
        file_path="last_notified.json",
        content_str="{}\n",
        commit_message="chore(monitor): reset last_notified.json for new ticket [skip ci]",
        branch=branch,
    )
    if not ok_reset:
        return False, msg_reset

    return True, f"Sincronizado en GitHub ({repo})"


def save_active_parlay(parlay_data: Dict[str, Any]) -> None:
    """
    Guarda los datos del parlay en `active_parlay.json`, reinicia `last_notified.json`
    para que `monitor.py` detecte el nuevo ticket y sincroniza ambos archivos en GitHub.
    """
    parlay_json_str = json.dumps(parlay_data, indent=2, ensure_ascii=False) + "\n"
    with ACTIVE_PARLAY_PATH.open("w", encoding="utf-8") as f:
        f.write(parlay_json_str)

    # Reiniciar last_notified.json localmente para que monitor.py detecte el nuevo ticket
    try:
        with LAST_NOTIFIED_PATH.open("w", encoding="utf-8") as f:
            f.write("{}\n")
    except Exception:
        pass

    ok, sync_msg = sync_parlay_to_github(parlay_json_str)
    st.session_state["last_sync_status"] = (ok, sync_msg)


def build_leg_svg_ring(status: str, progress_pct: float, logo_url: str) -> str:
    """
    Construye el anillo de progreso SVG circular (44x44px) con el logo oficial
    del equipo desde el CDN de ESPN en la esquina inferior derecha:
      - Verde sólido (#10B981) con palomita blanca al ganarse ('won')
      - Rojo sólido (#EF4444) con una X blanca al perderse ('lost')
      - Anillo circular dinámico en verde (#10B981) según porcentaje de cobertura en vivo
    """
    safe_logo = html.escape(logo_url or "")
    radius = 18
    circumference = 2 * math.pi * radius

    if status == "won":
        svg = (
            '<svg width="44" height="44" viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg">'
            '<circle cx="22" cy="22" r="19" fill="#10B981" />'
            '<path d="M14.5 22.5L19.5 27.5L29.5 16.5" stroke="#FFFFFF" stroke-width="2.8" '
            'stroke-linecap="round" stroke-linejoin="round" fill="none" />'
            "</svg>"
        )
    elif status == "lost":
        svg = (
            '<svg width="44" height="44" viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg">'
            '<circle cx="22" cy="22" r="19" fill="#EF4444" />'
            '<path d="M16 16L28 28M28 16L16 28" stroke="#FFFFFF" stroke-width="2.8" '
            'stroke-linecap="round" fill="none" />'
            "</svg>"
        )
    else:
        pct = max(0.0, min(100.0, float(progress_pct or 0.0)))
        offset = circumference * (1.0 - pct / 100.0)
        stroke_color = "#10B981" if status == "covering" else ("#EF4444" if status == "trailing" else "#374151")
        inner_text = f"{int(round(pct))}%" if status in ("covering", "trailing") else "—"
        svg = (
            '<svg width="44" height="44" viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg">'
            '<circle cx="22" cy="22" r="18" stroke="#2A2D3A" stroke-width="3.5" fill="#161820" />'
            f'<circle cx="22" cy="22" r="18" stroke="{stroke_color}" stroke-width="3.5" '
            f'fill="none" stroke-dasharray="{circumference:.2f}" stroke-dashoffset="{offset:.2f}" '
            'stroke-linecap="round" transform="rotate(-90 22 22)" />'
            f'<text x="22" y="25" text-anchor="middle" fill="#D1D5DB" font-size="9.5" font-weight="700">'
            f"{inner_text}</text>"
            "</svg>"
        )

    return (
        f'<div class="leg-ring-wrapper">'
        f"{svg}"
        f'<img class="leg-team-logo" src="{safe_logo}" alt="logo" '
        'onerror="this.style.display=\'none\'" />'
        f"</div>"
    )


def get_gemini_api_key() -> Optional[str]:
    """Obtiene GEMINI_API_KEY de variables de entorno o de st.secrets."""
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return env_key
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return str(st.secrets["GEMINI_API_KEY"])
    except Exception:
        pass
    return None


def parse_caliente_screenshot_with_gemini(image: Image.Image, api_key: str) -> Dict[str, Any]:
    """
    Usa google-genai (gemini-3.8-flash) para extraer todas las selecciones
    de una captura de pantalla de Caliente.mx.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    prompt = """
Analiza esta captura de pantalla de un ticket/parlay de Caliente.mx y extrae todas las selecciones en formato JSON estricto.

Para cada selección determina:
- "sport": una de ["basketball/nba", "football/nfl", "baseball/mlb", "hockey/nhl", "soccer/mex.1"]
- "team": abreviatura oficial de ESPN en mayúsculas (ej. "LAL", "BOS", "KC", "NYK", "AME", "GDL")
- "opponent": abreviatura oficial de ESPN del equipo rival si aparece, o ""
- "market_type": exactamente uno de ["moneyline", "spread", "total_over", "total_under", "player_prop"]
- "line": número flotante con la línea (ej. -5.5, 16.5, 224.5, 250.5) o null si es moneyline
- "odds": momio americano como string (ej. "-154", "+120", "-111")
- "player_name": nombre del jugador si market_type == "player_prop", o null
- "stat_type": si es player_prop, categoría entre ["points", "rebounds", "assists", "threes", "passing_yards", "rushing_yards", "receiving_yards", "receptions", "hits", "strikeouts", "goals", "shots"] o null
- "label": texto corto estilo Action Network (ej. "LAL -154", "UTA +16.5 -111", "Patrick Mahomes Over 250.5 Pass Yds -115")

Devuelve exclusivamente un objeto JSON con esta estructura:
{
  "wager_mxn": 500.0,
  "total_odds": "+425",
  "potential_payout_mxn": 2625.0,
  "selections": [ ... ]
}
"""

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[image, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    parsed = json.loads(response.text)
    selections = parsed.get("selections", [])
    for idx, sel in enumerate(selections):
        if not sel.get("id"):
            sel["id"] = f"leg_{idx + 1}_{uuid.uuid4().hex[:6]}"
    return parsed


def format_pick_title(sel: Dict[str, Any]) -> str:
    """Formatea el título del pick al estilo Action Network (ej. LAL -154 o UTA +16.5 -111)."""
    if sel.get("label"):
        return str(sel["label"])
    team = sel.get("team", "TEAM")
    market = sel.get("market_type", "moneyline")
    line = sel.get("line")
    odds = sel.get("odds", "-110")
    player = sel.get("player_name")

    if market == "moneyline":
        return f"{team} {odds}"
    if market == "spread" and line is not None:
        sign = "+" if float(line) > 0 else ""
        return f"{team} {sign}{line} {odds}"
    if market == "total_over" and line is not None:
        return f"{team} Over {line} {odds}"
    if market == "total_under" and line is not None:
        return f"{team} Under {line} {odds}"
    if market == "player_prop" and player:
        stat_label = (sel.get("stat_type") or "Stat").replace("_", " ").title()
        return f"{player} O {line} {stat_label} {odds}"
    return f"{team} {odds}"


def main() -> None:
    inject_action_network_css()

    # Encabezado superior estilo Action Network
    st.markdown(
        """
        <div class="my-action-topbar">
            <h1 class="my-action-title">My Action</h1>
            <span class="live-pill"><span class="live-dot"></span>LIVE · 30S</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "last_sync_status" in st.session_state:
        sync_ok, sync_msg = st.session_state.pop("last_sync_status")
        if sync_ok:
            st.toast(f"✅ {sync_msg}")
        else:
            st.toast(f"ℹ️ {sync_msg}")

    parlay_data = load_active_parlay()
    selections: List[Dict[str, Any]] = parlay_data.get("selections", [])

    # 1. Panel desplegable para cargar captura de Caliente.mx con Gemini 2.5 Flash
    with st.expander("📸 Cargar captura de Caliente", expanded=False):
        st.caption(
            "Sube una captura de tu ticket de Caliente.mx para extraer automáticamente las selecciones con `gemini-3.8-flash`."
        )
        uploaded_file = st.file_uploader(
            "Captura del parlay (PNG, JPG, WEBP)",
            type=["png", "jpg", "jpeg", "webp"],
            key="caliente_uploader",
        )
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="Ticket cargado", use_container_width=True)
            if st.button("✨ Extraer selecciones con Gemini", use_container_width=True):
                api_key = get_gemini_api_key()
                if not api_key:
                    st.error(
                        "Falta `GEMINI_API_KEY`. Configúrala en las variables de entorno o en `.streamlit/secrets.toml`."
                    )
                else:
                    with st.spinner("Analizando captura de Caliente.mx con Gemini 2.5 Flash..."):
                        try:
                            extracted = parse_caliente_screenshot_with_gemini(image, api_key)
                            save_active_parlay(extracted)
                            st.success(
                                f"¡Se extrajeron {len(extracted.get('selections', []))} selecciones del ticket!"
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Error al procesar la imagen con Gemini: {exc}")

    # 2. Renderizado de la tarjeta principal del Parlay y evaluación en vivo desde ESPN
    wager_mxn = float(parlay_data.get("wager_mxn") or 0.0)
    total_odds = str(parlay_data.get("total_odds") or "+100")
    potential_payout = float(parlay_data.get("potential_payout_mxn") or 0.0)
    legs_count = len(selections)

    scoreboard_cache: Dict[str, Dict[str, Any]] = {}
    legs_html_parts: List[str] = []

    status_labels = {
        "won": ("GANADA", "pill-won"),
        "lost": ("PERDIDA", "pill-lost"),
        "covering": ("CUBRIENDO", "pill-covering"),
        "trailing": ("ABAJO", "pill-trailing"),
        "pending": ("PENDIENTE", "pill-pending"),
    }

    for sel in selections:
        live = evaluate_selection(sel, scoreboard_cache=scoreboard_cache)
        ring_html = build_leg_svg_ring(
            status=live["status"],
            progress_pct=live["progress_pct"],
            logo_url=live["logo_url"],
        )
        pick_title = html.escape(format_pick_title(sel))
        score_sub = html.escape(live["score_text"])
        badge_text, badge_cls = status_labels.get(
            live["status"], ("PENDIENTE", "pill-pending")
        )

        leg_row_html = (
            f'<div class="leg-row">'
            f"{ring_html}"
            f'<div class="leg-details">'
            f'<div class="leg-pick-title">{pick_title}</div>'
            f'<div class="leg-score-sub">{score_sub}</div>'
            f"</div>"
            f'<span class="leg-status-pill {badge_cls}">{badge_text}</span>'
            f"</div>"
        )
        legs_html_parts.append(leg_row_html)

    if not legs_html_parts:
        legs_html_parts.append(
            '<div class="leg-row"><div class="leg-details">'
            '<div class="leg-pick-title">Sin selecciones activas</div>'
            '<div class="leg-score-sub">Carga una captura de Caliente.mx o añade un pick manualmente.</div>'
            "</div></div>"
        )

    payout_str = (
        f" · Pago: ${potential_payout:,.2f} MXN" if potential_payout > 0 else ""
    )
    card_html = (
        f'<div class="parlay-card">'
        f'<div class="parlay-card-header">'
        f'<div class="parlay-header-left">'
        f'<div class="parlay-title-row">'
        f'<span class="parlay-legs-title">{legs_count}-Leg Parlay</span>'
        f'<span class="parlay-odds-badge">{html.escape(total_odds)}</span>'
        f"</div>"
        f'<div class="parlay-book-sub">Caliente.mx{html.escape(payout_str)}</div>'
        f"</div>"
        f'<div class="parlay-header-right">'
        f'<div class="parlay-wager-label">Apostado</div>'
        f'<div class="parlay-wager-amount">${wager_mxn:,.2f} MXN</div>'
        f"</div>"
        f"</div>"
        f'{"".join(legs_html_parts)}'
        f"</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)

    # 3. Formulario rápido para gestionar selecciones manualmente y limpiar el ticket
    with st.expander("⚙️ Gestionar selecciones / Añadir pick manual", expanded=False):
        st.subheader("Encabezado del Ticket")
        col_w, col_o, col_p = st.columns(3)
        with col_w:
            new_wager = st.number_input(
                "Monto (MXN)", min_value=0.0, value=wager_mxn, step=50.0
            )
        with col_o:
            new_odds = st.text_input("Momio Total", value=total_odds)
        with col_p:
            new_payout = st.number_input(
                "Pago Potencial (MXN)", min_value=0.0, value=potential_payout, step=100.0
            )
        if st.button("💾 Actualizar encabezado", use_container_width=True):
            parlay_data["wager_mxn"] = new_wager
            parlay_data["total_odds"] = new_odds
            parlay_data["potential_payout_mxn"] = new_payout
            save_active_parlay(parlay_data)
            st.rerun()

        st.divider()
        st.subheader("Añadir Selección Manual")
        with st.form("add_manual_leg_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                sport_label = st.selectbox("Liga", list(SUPPORTED_SPORTS.keys()))
            with c2:
                team_input = st.text_input("Equipo (ESPN Abbr)", placeholder="LAL")
            with c3:
                opp_input = st.text_input("Rival (Opcional)", placeholder="PHX")

            c4, c5, c6 = st.columns(3)
            with c4:
                market_input = st.selectbox(
                    "Mercado",
                    ["moneyline", "spread", "total_over", "total_under", "player_prop"],
                )
            with c5:
                line_input = st.number_input(
                    "Línea (0 si ML)", value=0.0, step=0.5, format="%.1f"
                )
            with c6:
                odds_input = st.text_input("Momio", value="-110")

            c7, c8 = st.columns(2)
            with c7:
                player_input = st.text_input(
                    "Jugador (solo player_prop)", placeholder="LeBron James"
                )
            with c8:
                stat_input = st.selectbox(
                    "Estadística (solo player_prop)",
                    [
                        "",
                        "points",
                        "rebounds",
                        "assists",
                        "threes",
                        "passing_yards",
                        "rushing_yards",
                        "receiving_yards",
                        "receptions",
                        "hits",
                        "strikeouts",
                        "goals",
                    ],
                )

            submitted = st.form_submit_button("➕ Agregar selección al Parlay", use_container_width=True)
            if submitted and team_input.strip():
                sport_code = SUPPORTED_SPORTS[sport_label]
                team_clean = team_input.strip().upper()
                opp_clean = opp_input.strip().upper()
                line_val = None if market_input == "moneyline" else float(line_input)
                new_leg: Dict[str, Any] = {
                    "id": f"leg_{uuid.uuid4().hex[:6]}",
                    "sport": sport_code,
                    "team": team_clean,
                    "opponent": opp_clean,
                    "market_type": market_input,
                    "line": line_val,
                    "odds": odds_input.strip() or "-110",
                    "player_name": player_input.strip() or None,
                    "stat_type": stat_input or None,
                }
                new_leg["label"] = format_pick_title(new_leg)
                parlay_data.setdefault("selections", []).append(new_leg)
                save_active_parlay(parlay_data)
                st.rerun()

        if selections:
            st.divider()
            st.subheader("Eliminar Selecciones")
            for idx, sel in enumerate(selections):
                rc1, rc2 = st.columns([4, 1])
                rc1.write(f"**{idx + 1}.** {format_pick_title(sel)} (`{sel.get('sport')}`)")
                if rc2.button("🗑️", key=f"del_{sel.get('id', idx)}"):
                    parlay_data["selections"].pop(idx)
                    save_active_parlay(parlay_data)
                    st.rerun()

        st.divider()
        col_clear, col_ntfy = st.columns(2)
        with col_clear:
            if st.button("🧹 Limpiar ticket activo", use_container_width=True):
                parlay_data["selections"] = []
                save_active_parlay(parlay_data)
                st.rerun()
        with col_ntfy:
            if st.button("📲 Probar / Sincronizar ntfy.sh", use_container_width=True):
                run_monitor()
                ok = send_ntfy_notification(
                    title="My Action · Caliente Tracker",
                    message=f"Monitoreando {len(selections)} selecciones en vivo (Topic: {NTFY_TOPIC}).",
                    tags=["iphone", "white_check_mark"],
                )
                if ok:
                    st.toast(f"Notificación enviada a ntfy.sh/{NTFY_TOPIC}")
                else:
                    st.warning("No se pudo conectar con ntfy.sh en este momento.")


if __name__ == "__main__":
    main()
