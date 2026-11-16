"""
app.py
Aplicación en Streamlit con estética Dark Mode idéntica a la pestaña "My Action"
de Action Network para seguir en vivo múltiples parlays activos de Caliente.mx,
extraer tickets con Gemini y sincronizar automáticamente con GitHub y ntfy.sh.
"""

from __future__ import annotations

import base64
import html
import io
import json
import math
import os
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from espn_live import SUPPORTED_SPORTS, evaluate_selection
from monitor import (
    NTFY_TOPIC,
    migrate_to_parlays_dict,
    run_monitor,
    send_ntfy_notification,
)

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
            margin-bottom: 8px;
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
            flex-wrap: wrap;
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
            flex-shrink: 0;
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


def load_active_parlays() -> Dict[str, List[Dict[str, Any]]]:
    """
    Carga `active_parlay.json` y garantiza la estructura `{"parlays": [...]}`.
    Si el archivo existente tiene el formato anterior (un solo diccionario sin la llave `parlays`),
    migra automáticamente ese ticket dentro de `{"parlays": [...]}` para evitar cualquier KeyError.
    """
    if not ACTIVE_PARLAY_PATH.exists():
        return {"parlays": []}
    try:
        with ACTIVE_PARLAY_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        migrated = migrate_to_parlays_dict(raw)
        # Si el archivo local tenía el formato viejo sin la llave 'parlays', lo migramos en disco
        if isinstance(raw, dict) and "parlays" not in raw:
            with ACTIVE_PARLAY_PATH.open("w", encoding="utf-8") as fw:
                json.dump(migrated, fw, indent=2, ensure_ascii=False)
        return migrated
    except Exception:
        traceback.print_exc()
        return {"parlays": []}


def _github_get_file(
    repo: str,
    token: str,
    file_path: str,
    branch: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Obtiene `(sha, decoded_content)` de un archivo en GitHub si existe.
    Devuelve `(None, None)` si es 404.
    """
    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params: Dict[str, str] = {}
    if branch:
        params["ref"] = branch

    get_resp = requests.get(api_url, headers=headers, params=params, timeout=10)
    if get_resp.status_code == 200:
        body = get_resp.json()
        sha = body.get("sha")
        content_b64 = body.get("content", "")
        decoded = ""
        if content_b64:
            try:
                decoded = base64.b64decode(content_b64).decode("utf-8")
            except Exception:
                decoded = ""
        return sha, decoded
    if get_resp.status_code == 404:
        return None, None
    raise RuntimeError(
        f"GET {file_path} en GitHub devolvió {get_resp.status_code}: {get_resp.text}"
    )


def _github_upsert_file(
    repo: str,
    token: str,
    file_path: str,
    content_str: str,
    commit_message: str,
    branch: Optional[str] = None,
    known_sha: Optional[str] = None,
) -> Tuple[bool, str]:
    """Crea o actualiza un archivo en GitHub usando la API REST de contenidos."""
    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    sha = known_sha
    if sha is None:
        sha, _ = _github_get_file(repo=repo, token=token, file_path=file_path, branch=branch)

    encoded_content = base64.b64encode(content_str.encode("utf-8")).decode("ascii")
    payload: Dict[str, Any] = {
        "message": commit_message,
        "content": encoded_content,
    }
    if sha:
        payload["sha"] = sha
    if branch:
        payload["branch"] = branch

    put_resp = requests.put(api_url, headers=headers, json=payload, timeout=15)
    if put_resp.status_code in (200, 201):
        return True, "OK"
    raise RuntimeError(
        f"PUT {file_path} en GitHub devolvió {put_resp.status_code}: {put_resp.text}"
    )


def sync_parlay_to_github(
    local_data: Dict[str, List[Dict[str, Any]]],
    added_ticket: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Sincroniza `active_parlay.json` y reinicia `last_notified.json` directamente
    en el repositorio de GitHub vía REST API usando GITHUB_TOKEN y GITHUB_REPO.
    Si el archivo remoto en GitHub aún tiene el formato anterior (un solo diccionario
    sin la llave `parlays`), lo migra automáticamente dentro de `{"parlays": [...]}`
    antes de agregar el nuevo ticket.
    """
    token = get_secret_or_env("GITHUB_TOKEN")
    repo = get_secret_or_env("GITHUB_REPO")
    branch = get_secret_or_env("GITHUB_BRANCH")

    if not token or not repo:
        return (
            True,
            "Guardado localmente (configura GITHUB_TOKEN y GITHUB_REPO para sincronizar con GitHub).",
        )

    sha_remote, remote_content = _github_get_file(
        repo=repo, token=token, file_path="active_parlay.json", branch=branch
    )

    if added_ticket is not None and remote_content:
        try:
            remote_raw = json.loads(remote_content)
            # Si en GitHub había un ticket en formato antiguo sin 'parlays', lo migramos
            remote_migrated = migrate_to_parlays_dict(remote_raw)
            existing_ids = {p.get("id") for p in local_data.get("parlays", [])}
            merged_parlays: List[Dict[str, Any]] = []
            for rp in remote_migrated.get("parlays", []):
                if rp.get("id") not in existing_ids:
                    merged_parlays.append(rp)
            merged_parlays.extend(local_data.get("parlays", []))
            local_data["parlays"] = merged_parlays
        except Exception:
            traceback.print_exc()

    parlay_json_str = json.dumps(local_data, indent=2, ensure_ascii=False) + "\n"
    with ACTIVE_PARLAY_PATH.open("w", encoding="utf-8") as f:
        f.write(parlay_json_str)

    _github_upsert_file(
        repo=repo,
        token=token,
        file_path="active_parlay.json",
        content_str=parlay_json_str,
        commit_message="chore(parlay): update active_parlay.json from Streamlit",
        branch=branch,
        known_sha=sha_remote,
    )

    _github_upsert_file(
        repo=repo,
        token=token,
        file_path="last_notified.json",
        content_str="{}\n",
        commit_message="chore(monitor): reset last_notified.json for updated parlays [skip ci]",
        branch=branch,
    )

    return True, f"Sincronizado en GitHub ({repo})"


def save_active_parlay(
    data: Dict[str, Any],
    added_ticket: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Migra/normaliza `data` a `{"parlays": [...]}`, guarda `active_parlay.json` localmente,
    reinicia `last_notified.json` y sincroniza ambos archivos en GitHub.
    Devuelve `True` si completó con éxito.
    """
    normalized_data = migrate_to_parlays_dict(data)
    parlay_json_str = json.dumps(normalized_data, indent=2, ensure_ascii=False) + "\n"
    with ACTIVE_PARLAY_PATH.open("w", encoding="utf-8") as f:
        f.write(parlay_json_str)

    with LAST_NOTIFIED_PATH.open("w", encoding="utf-8") as f:
        f.write("{}\n")

    ok, sync_msg = sync_parlay_to_github(normalized_data, added_ticket=added_ticket)
    st.session_state["last_sync_status"] = (ok, sync_msg)
    return True


# Alias por claridad
save_active_parlays = save_active_parlay


def compress_image_for_gemini(image: Image.Image, max_width: int = 1080, quality: int = 80) -> Image.Image:
    """
    Redimensiona la captura a máximo `max_width` (1080px) de ancho manteniendo proporción
    y la comprime a JPEG (calidad 80) en memoria antes de enviarla a Gemini.
    """
    rgb_img = image.convert("RGB")
    if rgb_img.width > max_width:
        ratio = max_width / float(rgb_img.width)
        new_height = max(1, int(round(rgb_img.height * ratio)))
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        rgb_img = rgb_img.resize((max_width, new_height), resample_filter)

    buffer = io.BytesIO()
    rgb_img.save(buffer, format="JPEG", quality=quality, optimize=True)
    buffer.seek(0)
    compressed_img = Image.open(buffer)
    compressed_img.load()
    return compressed_img


def build_leg_svg_ring(status: str, progress_pct: float, logo_url: str) -> str:
    """
    Construye el anillo de progreso SVG circular (44x44px) con el logo oficial
    del equipo desde el CDN de ESPN en la esquina inferior derecha.
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
        stroke_color = (
            "#10B981"
            if status == "covering"
            else ("#EF4444" if status == "trailing" else "#374151")
        )
        inner_text = (
            f"{int(round(pct))}%" if status in ("covering", "trailing") else "—"
        )
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
    return get_secret_or_env("GEMINI_API_KEY")


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


def parse_caliente_screenshot_with_gemini(
    image: Image.Image,
    api_key: str,
    default_ticket_name: str = "Parlay #1",
) -> Tuple[Dict[str, Any], str]:
    """
    Comprime la imagen a máx 1080px JPEG (calidad 80) y usa google-genai (`gemini-3.8-flash`)
    con `http_options={'timeout': 25.0}` y `automatic_function_calling` desactivado
    para extraer todas las selecciones (`legs`) de una captura de Caliente.mx.
    """
    from google import genai
    from google.genai import types

    compressed_image = compress_image_for_gemini(image, max_width=1080, quality=80)

    client = genai.Client(api_key=api_key, http_options={"timeout": 60.0})
    # Cliente de respaldo con timeout en milisegundos (60,000 ms = 60s) para versiones de google-genai que dividen entre 1000
    fallback_client = genai.Client(api_key=api_key, http_options={"timeout": 60000})

    leg_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "sport": types.Schema(
                type=types.Type.STRING,
                description="Liga en formato ESPN: 'basketball/nba', 'football/nfl', 'baseball/mlb', 'hockey/nhl' o 'soccer/mex.1'",
            ),
            "team": types.Schema(
                type=types.Type.STRING,
                description="Abreviatura oficial de ESPN en mayúsculas del equipo elegido (ej. LAL, BOS, KC, LAR, BAL, CIN, SF, SEA, MIL, LAC, NYK, OKC, AME, GDL)",
            ),
            "opponent": types.Schema(
                type=types.Type.STRING,
                description="Abreviatura oficial de ESPN del equipo rival si aparece en el partido, o cadena vacía",
            ),
            "market_type": types.Schema(
                type=types.Type.STRING,
                enum=["moneyline", "spread", "total_over", "total_under", "player_prop"],
                description="Tipo de mercado normalizado",
            ),
            "line": types.Schema(
                type=types.Type.NUMBER,
                nullable=True,
                description="Línea numérica flotante (ej. -5.5, 12.5, 114.5, 250.5) o null si es moneyline",
            ),
            "odds": types.Schema(
                type=types.Type.STRING,
                description="Momio americano como string (ej. '-154', '+120', '-200')",
            ),
            "player_name": types.Schema(
                type=types.Type.STRING,
                nullable=True,
                description="Nombre del jugador si market_type es 'player_prop', o null",
            ),
            "stat_type": types.Schema(
                type=types.Type.STRING,
                nullable=True,
                description="Si es player_prop: 'points', 'rebounds', 'assists', 'threes', 'passing_yards', 'rushing_yards', 'receiving_yards', 'receptions', 'hits', 'strikeouts', 'goals' o 'shots'",
            ),
            "label": types.Schema(
                type=types.Type.STRING,
                description="Etiqueta corta estilo Action Network (ej. 'LAR -500', 'MIL +12.5 -213', 'BOS Over 114.5 -163')",
            ),
        },
        required=["sport", "team", "market_type", "odds", "label"],
    )

    parlay_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "name": types.Schema(
                type=types.Type.STRING,
                description="Nombre descriptivo corto del parlay (ej. 'Parlay NFL + NBA')",
            ),
            "stake": types.Schema(
                type=types.Type.NUMBER,
                nullable=True,
                description="Monto apostado en MXN (0.0 si no es visible en la captura)",
            ),
            "odds": types.Schema(
                type=types.Type.STRING,
                nullable=True,
                description="Momio total del parlay en formato americano (ej. '+1850')",
            ),
            "payout": types.Schema(
                type=types.Type.NUMBER,
                nullable=True,
                description="Pago potencial total en MXN (0.0 si no es visible)",
            ),
            "legs": types.Schema(
                type=types.Type.ARRAY,
                items=leg_schema,
                description="Lista obligatoria con TODAS las selecciones individuales que aparecen en la captura de Caliente.mx",
            ),
        },
        required=["name", "stake", "odds", "payout", "legs"],
    )

    prompt = """
Analiza esta captura de pantalla de un boleto/parlay de Caliente.mx y extrae TODAS las selecciones individuales dentro de la lista `legs`.
Es obligatorio que `legs` contenga cada uno de los picks visibles en la imagen (nunca devuelvas `legs` vacío si hay selecciones en la imagen).

Mapea los mercados en español de Caliente.mx así:
- "Ganador del Partido", "Ganador (Incl. Prórroga)", "Ganador", "Resultado Final", "Moneyline", "A Ganar" -> `market_type`: "moneyline", `line`: null
- "Hándicap", "Hándicap Alternativo", "Spread", "Línea de puntos" (ej. +12.5, -5.5, +5) -> `market_type`: "spread", `line`: valor numérico con su signo (ej. 12.5 o -5.5)
- "Total de Puntos - Más de", "Más de (Over)", "Total Equipo Más de", "Más de X.5" -> `market_type`: "total_over", `line`: valor numérico (ej. 114.5)
- "Total de Puntos - Menos de", "Menos de (Under)", "Total Equipo Menos de", "Menos de X.5" -> `market_type`: "total_under", `line`: valor numérico (ej. 220.5)
- Proposiciones de jugador ("Puntos del jugador", "Rebotes", "Asistencias", "Triples", "Yardas por pase", "Yardas por acarreo", "Recepciones", "Hits", "Ponches") -> `market_type`: "player_prop", `player_name`: nombre del jugador, `line`: línea numérica, `stat_type`: categoría en inglés.

Convierte los nombres de equipos en español/inglés de Caliente.mx a su abreviatura oficial de ESPN en mayúsculas (ej. Los Angeles Rams -> LAR, Baltimore Ravens -> BAL, Cincinnati Bengals -> CIN, San Francisco 49ers -> SF, Seattle Seahawks -> SEA, Boston Celtics -> BOS, Oklahoma City Thunder -> OKC, Milwaukee Bucks -> MIL, LA Clippers -> LAC, New York Knicks -> NYK, Los Angeles Lakers -> LAL, Phoenix Suns -> PHX, Utah Jazz -> UTA).
"""

    config_with_thinking_off = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=parlay_schema,
        temperature=0.1,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    config_basic = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=parlay_schema,
        temperature=0.1,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    response = None
    last_error: Optional[Exception] = None
    candidate_models = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"]

    for model_name in candidate_models:
        cfg = (
            config_basic
            if model_name.startswith("gemini-2.0")
            else config_with_thinking_off
        )
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[compressed_image, prompt],
                config=cfg,
            )
            break
        except Exception as err_primary:
            last_error = err_primary
            # Si fue ReadTimeout inmediato por unidades de timeout en ms, reintentar con fallback_client (60000 ms)
            try:
                response = fallback_client.models.generate_content(
                    model=model_name,
                    contents=[compressed_image, prompt],
                    config=cfg,
                )
                break
            except Exception as err_fallback:
                last_error = err_fallback
                continue

    if response is None and last_error is not None:
        raise last_error

    raw_text = response.text or "{}"
    st.session_state["last_raw_gemini_json"] = raw_text

    parsed = json.loads(raw_text)

    legs = parsed.get("legs")
    if not isinstance(legs, list) or not legs:
        legs = parsed.get("selections") or []

    for idx, sel in enumerate(legs):
        if not sel.get("id"):
            sel["id"] = f"leg_{idx + 1}_{uuid.uuid4().hex[:6]}"
        if not sel.get("label"):
            sel["label"] = format_pick_title(sel)

    ticket: Dict[str, Any] = {
        "id": f"parlay_{uuid.uuid4().hex[:8]}",
        "name": str(default_ticket_name or parsed.get("name") or "Parlay Caliente"),
        "stake": float(parsed.get("stake") or parsed.get("wager_mxn") or 0.0),
        "odds": str(parsed.get("odds") or parsed.get("total_odds") or "+100"),
        "payout": float(
            parsed.get("payout") or parsed.get("potential_payout_mxn") or 0.0
        ),
        "legs": legs,
    }
    return ticket, raw_text


def render_parlay_card(
    parlay: Dict[str, Any],
    scoreboard_cache: Dict[str, Dict[str, Any]],
) -> None:
    """Renderiza una tarjeta individual estilo 'My Action' para un parlay."""
    parlay_name = str(parlay.get("name") or "Parlay")
    stake_mxn = float(parlay.get("stake") or parlay.get("wager_mxn") or 0.0)
    total_odds = str(parlay.get("odds") or parlay.get("total_odds") or "+100")
    potential_payout = float(
        parlay.get("payout") or parlay.get("potential_payout_mxn") or 0.0
    )
    legs: List[Dict[str, Any]] = parlay.get("legs") or parlay.get("selections") or []
    legs_count = len(legs)

    status_labels = {
        "won": ("GANADA", "pill-won"),
        "lost": ("PERDIDA", "pill-lost"),
        "covering": ("CUBRIENDO", "pill-covering"),
        "trailing": ("ABAJO", "pill-trailing"),
        "pending": ("PENDIENTE", "pill-pending"),
    }

    legs_html_parts: List[str] = []
    for sel in legs:
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
            '<div class="leg-score-sub">Añade un pick manualmente desde el panel inferior.</div>'
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
        f'<span class="parlay-legs-title">{html.escape(parlay_name)} · {legs_count}-Leg</span>'
        f'<span class="parlay-odds-badge">{html.escape(total_odds)}</span>'
        f"</div>"
        f'<div class="parlay-book-sub">Caliente.mx{html.escape(payout_str)}</div>'
        f"</div>"
        f'<div class="parlay-header-right">'
        f'<div class="parlay-wager-label">Apostado</div>'
        f'<div class="parlay-wager-amount">${stake_mxn:,.2f} MXN</div>'
        f"</div>"
        f"</div>"
        f'{"".join(legs_html_parts)}'
        f"</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)


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

    data = load_active_parlays()
    parlays: List[Dict[str, Any]] = data.get("parlays", [])

    # 1. Panel desplegable para cargar captura de Caliente.mx y añadir un nuevo ticket
    with st.expander("📸 Cargar captura de Caliente (Añadir Ticket)", expanded=False):
        st.caption(
            "Sube una captura de tu ticket de Caliente.mx para extraer sus selecciones con `gemini-3.8-flash` y añadirlo a tus parlays activos."
        )
        default_new_name = f"Parlay #{len(parlays) + 1}"
        ticket_name_input = st.text_input(
            "Nombre del Ticket (opcional)",
            value=default_new_name,
            key="gemini_ticket_name",
        )
        uploaded_file = st.file_uploader(
            "Captura del parlay (PNG, JPG, WEBP)",
            type=["png", "jpg", "jpeg", "webp"],
            key="caliente_uploader",
        )
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="Ticket cargado", width="stretch")
            if st.button("✨ Extraer y añadir Parlay con Gemini", width="stretch"):
                api_key = get_gemini_api_key()
                if not api_key:
                    st.error(
                        "Falta `GEMINI_API_KEY`. Configúrala en las variables de entorno o en `.streamlit/secrets.toml`."
                    )
                else:
                    save_completed = False
                    with st.spinner("Compriendo imagen y extrayendo picks con Gemini 3.8 Flash..."):
                        try:
                            new_ticket, raw_json = parse_caliente_screenshot_with_gemini(
                                image=image,
                                api_key=api_key,
                                default_ticket_name=ticket_name_input.strip() or default_new_name,
                            )
                            extracted_legs = new_ticket.get("legs", [])
                            if not extracted_legs:
                                st.warning(
                                    "Gemini procesó la imagen pero la lista `legs` llegó vacía. Revisa el JSON crudo abajo para depurar."
                                )
                            else:
                                migrated_current = migrate_to_parlays_dict(data)
                                migrated_current["parlays"].append(new_ticket)
                                data = migrated_current
                                save_completed = save_active_parlay(
                                    data, added_ticket=new_ticket
                                )
                                st.success(
                                    f"¡Ticket '{new_ticket['name']}' añadido con {len(extracted_legs)} selecciones!"
                                )
                        except Exception as e:
                            import traceback as tb

                            tb.print_exc()
                            st.error(f"Fallo exacto: {type(e).__name__} - {e}")
                            if st.session_state.get("last_raw_gemini_json"):
                                st.code(
                                    st.session_state["last_raw_gemini_json"],
                                    language="json",
                                )

                    if save_completed:
                        st.rerun()

        if st.session_state.get("last_raw_gemini_json"):
            with st.expander("Ver JSON crudo extraído", expanded=False):
                st.code(st.session_state["last_raw_gemini_json"], language="json")

    # 2. Renderizado apilado de todas las tarjetas de Parlays activos y botón individual de eliminar
    scoreboard_cache: Dict[str, Dict[str, Any]] = {}

    if not parlays:
        st.markdown(
            '<div class="parlay-card"><div class="leg-row"><div class="leg-details">'
            '<div class="leg-pick-title">No tienes parlays activos</div>'
            '<div class="leg-score-sub">Sube una captura de Caliente.mx arriba o crea un ticket manual abajo.</div>'
            "</div></div></div>",
            unsafe_allow_html=True,
        )
    else:
        for idx, parlay in enumerate(parlays):
            render_parlay_card(parlay, scoreboard_cache=scoreboard_cache)
            parlay_id = parlay.get("id") or f"parlay_{idx}"
            parlay_name = parlay.get("name") or f"Parlay #{idx + 1}"
            if st.button(
                f"🗑️ Eliminar ticket ({parlay_name})",
                key=f"delete_ticket_{parlay_id}_{idx}",
                width="stretch",
            ):
                deleted_ok = False
                try:
                    parlays.pop(idx)
                    data["parlays"] = parlays
                    deleted_ok = save_active_parlay(data)
                except Exception as e:
                    import traceback as tb

                    tb.print_exc()
                    st.error(f"Fallo exacto: {type(e).__name__} - {e}")
                if deleted_ok:
                    st.rerun()

    # 3. Panel para crear un parlay manual o editar / añadir selecciones a un ticket existente
    with st.expander("⚙️ Crear Parlay manual / Gestionar selecciones", expanded=False):
        tab_new, tab_edit = st.tabs(["➕ Nuevo Ticket Manual", "✏️ Editar Ticket Existente"])

        with tab_new:
            with st.form("create_manual_parlay_form", clear_on_submit=True):
                st.subheader("Crear nuevo ticket de Parlay")
                nc1, nc2 = st.columns(2)
                with nc1:
                    new_t_name = st.text_input(
                        "Nombre del Ticket", value=f"Parlay #{len(parlays) + 1}"
                    )
                    new_t_stake = st.number_input(
                        "Monto Apostado (MXN)", min_value=0.0, value=500.0, step=50.0
                    )
                with nc2:
                    new_t_odds = st.text_input("Momio Total", value="+100")
                    new_t_payout = st.number_input(
                        "Pago Potencial (MXN)", min_value=0.0, value=1000.0, step=100.0
                    )

                if st.form_submit_button("🎟️ Crear Ticket", width="stretch"):
                    created_ok = False
                    try:
                        created_ticket: Dict[str, Any] = {
                            "id": f"parlay_{uuid.uuid4().hex[:8]}",
                            "name": new_t_name.strip() or f"Parlay #{len(parlays) + 1}",
                            "stake": float(new_t_stake),
                            "odds": new_t_odds.strip() or "+100",
                            "payout": float(new_t_payout),
                            "legs": [],
                        }
                        migrated_current = migrate_to_parlays_dict(data)
                        migrated_current["parlays"].append(created_ticket)
                        data = migrated_current
                        created_ok = save_active_parlay(
                            data, added_ticket=created_ticket
                        )
                    except Exception as e:
                        import traceback as tb

                        tb.print_exc()
                        st.error(f"Fallo exacto: {type(e).__name__} - {e}")
                    if created_ok:
                        st.rerun()

        with tab_edit:
            if not parlays:
                st.info("Primero crea un ticket o sube una captura de Caliente.mx.")
            else:
                ticket_options = {
                    f"{i + 1}. {p.get('name', f'Parlay #{i + 1}')} ({len(p.get('legs', []))} picks)": i
                    for i, p in enumerate(parlays)
                }
                selected_label = st.selectbox(
                    "Selecciona el Parlay a editar", list(ticket_options.keys())
                )
                sel_idx = ticket_options[selected_label]
                target_parlay = parlays[sel_idx]

                st.subheader("Encabezado del Ticket")
                ec0, ec1, ec2, ec3 = st.columns(4)
                with ec0:
                    ed_name = st.text_input(
                        "Nombre",
                        value=str(target_parlay.get("name") or ""),
                        key=f"ed_name_{sel_idx}",
                    )
                with ec1:
                    ed_stake = st.number_input(
                        "Monto (MXN)",
                        min_value=0.0,
                        value=float(target_parlay.get("stake") or 0.0),
                        step=50.0,
                        key=f"ed_stake_{sel_idx}",
                    )
                with ec2:
                    ed_odds = st.text_input(
                        "Momio",
                        value=str(target_parlay.get("odds") or "+100"),
                        key=f"ed_odds_{sel_idx}",
                    )
                with ec3:
                    ed_payout = st.number_input(
                        "Pago (MXN)",
                        min_value=0.0,
                        value=float(target_parlay.get("payout") or 0.0),
                        step=100.0,
                        key=f"ed_payout_{sel_idx}",
                    )

                if st.button("💾 Guardar encabezado", width="stretch"):
                    header_ok = False
                    try:
                        target_parlay["name"] = ed_name.strip() or target_parlay["name"]
                        target_parlay["stake"] = float(ed_stake)
                        target_parlay["odds"] = ed_odds.strip() or "+100"
                        target_parlay["payout"] = float(ed_payout)
                        header_ok = save_active_parlay(data)
                    except Exception as e:
                        import traceback as tb

                        tb.print_exc()
                        st.error(f"Fallo exacto: {type(e).__name__} - {e}")
                    if header_ok:
                        st.rerun()

                st.divider()
                st.subheader(f"Añadir selección a '{target_parlay.get('name')}'")
                with st.form(f"add_manual_leg_form_{sel_idx}", clear_on_submit=True):
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
                            [
                                "moneyline",
                                "spread",
                                "total_over",
                                "total_under",
                                "player_prop",
                            ],
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

                    submitted = st.form_submit_button(
                        "➕ Agregar selección a este Parlay", width="stretch"
                    )
                    if submitted and team_input.strip():
                        leg_ok = False
                        try:
                            sport_code = SUPPORTED_SPORTS[sport_label]
                            team_clean = team_input.strip().upper()
                            opp_clean = opp_input.strip().upper()
                            line_val = (
                                None if market_input == "moneyline" else float(line_input)
                            )
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
                            target_parlay.setdefault("legs", []).append(new_leg)
                            leg_ok = save_active_parlay(data)
                        except Exception as e:
                            import traceback as tb

                            tb.print_exc()
                            st.error(f"Fallo exacto: {type(e).__name__} - {e}")
                        if leg_ok:
                            st.rerun()

                target_legs: List[Dict[str, Any]] = target_parlay.get("legs", [])
                if target_legs:
                    st.divider()
                    st.subheader("Eliminar selecciones individuales")
                    for l_idx, sel in enumerate(target_legs):
                        rc1, rc2 = st.columns([4, 1])
                        rc1.write(
                            f"**{l_idx + 1}.** {format_pick_title(sel)} (`{sel.get('sport')}`)"
                        )
                        if rc2.button(
                            "🗑️",
                            key=f"del_leg_{target_parlay.get('id')}_{sel.get('id', l_idx)}",
                        ):
                            rem_ok = False
                            try:
                                target_parlay["legs"].pop(l_idx)
                                rem_ok = save_active_parlay(data)
                            except Exception as e:
                                import traceback as tb

                                tb.print_exc()
                                st.error(f"Fallo exacto: {type(e).__name__} - {e}")
                            if rem_ok:
                                st.rerun()

        st.divider()
        col_clear, col_ntfy = st.columns(2)
        with col_clear:
            if st.button("🧹 Eliminar TODOS los tickets", width="stretch"):
                clear_ok = False
                try:
                    data["parlays"] = []
                    clear_ok = save_active_parlay(data)
                except Exception as e:
                    import traceback as tb

                    tb.print_exc()
                    st.error(f"Fallo exacto: {type(e).__name__} - {e}")
                if clear_ok:
                    st.rerun()
        with col_ntfy:
            if st.button("📲 Probar / Sincronizar ntfy.sh", width="stretch"):
                run_monitor()
                total_legs = sum(len(p.get("legs", [])) for p in parlays)
                ok = send_ntfy_notification(
                    title="My Action · Caliente Tracker",
                    message=(
                        f"Monitoreando {len(parlays)} parlays ({total_legs} picks) en vivo "
                        f"(Topic: {NTFY_TOPIC})."
                    ),
                    tags=["iphone", "white_check_mark"],
                )
                if ok:
                    st.toast(f"Notificación enviada a ntfy.sh/{NTFY_TOPIC}")
                else:
                    st.warning("No se pudo conectar con ntfy.sh en este momento.")


if __name__ == "__main__":
    main()
