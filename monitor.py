"""
monitor.py
Script independiente para monitorear múltiples parlays activos en active_parlay.json
en segundo plano o vía GitHub Actions / cron y enviar notificaciones push a iPhone
mediante ntfy.sh indicando el nombre del ticket en el título.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List
import requests

from espn_live import evaluate_selection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
ACTIVE_PARLAY_PATH = BASE_DIR / "active_parlay.json"
LAST_NOTIFIED_PATH = BASE_DIR / "last_notified.json"

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "caliente_parlay_marcelo")
NTFY_BASE_URL = "https://ntfy.sh"


def load_json_file(path: Path, default: Any) -> Any:
    """Lee un archivo JSON de forma segura."""
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("No se pudo leer %s: %s", path, exc)
        return default


def save_json_file(path: Path, data: Any) -> None:
    """Guarda un diccionario en JSON con formato legible."""
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.error("Error guardando %s: %s", path, exc)


def normalize_parlays_list(raw_data: Any) -> List[Dict[str, Any]]:
    """
    Normaliza el contenido de `active_parlay.json` para devolver siempre
    una lista de tickets `[{'id', 'name', 'stake', 'odds', 'payout', 'legs'}, ...]`.
    Soporta retrocompatibilidad con el formato antiguo de un solo ticket.
    """
    if not isinstance(raw_data, dict):
        return []
    if isinstance(raw_data.get("parlays"), list):
        return raw_data["parlays"]
    # Retrocompatibilidad si aún tiene 'selections' o 'legs' en la raíz
    legacy_legs = raw_data.get("legs") or raw_data.get("selections") or []
    if legacy_legs:
        return [
            {
                "id": str(raw_data.get("id") or "parlay_1"),
                "name": str(raw_data.get("name") or "Parlay #1"),
                "stake": float(raw_data.get("stake") or raw_data.get("wager_mxn") or 0.0),
                "odds": str(raw_data.get("odds") or raw_data.get("total_odds") or "+100"),
                "payout": float(
                    raw_data.get("payout") or raw_data.get("potential_payout_mxn") or 0.0
                ),
                "legs": legacy_legs,
            }
        ]
    return []


def send_ntfy_notification(
    title: str,
    message: str,
    tags: List[str],
    priority: str = "default",
    topic: str = NTFY_TOPIC,
) -> bool:
    """Envía una notificación push HTTP POST a https://ntfy.sh/{NTFY_TOPIC}."""
    url = f"{NTFY_BASE_URL}/{topic}"
    headers = {
        "Title": title,
        "Tags": ",".join(tags),
        "Priority": priority,
    }
    try:
        resp = requests.post(
            url,
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Notificación enviada a %s: %s -> %s", url, title, message)
        return True
    except Exception as exc:
        logger.warning("Fallo enviando notificación a ntfy.sh: %s", exc)
        return False


def run_monitor() -> Dict[str, Any]:
    """
    Recorre todos los parlays activos en `active_parlay.json`, compara con `last_notified.json`
    y dispara notificaciones push indicando el nombre del ticket en el título cuando:
      1. Cambia el marcador en un partido activo (indicando si va cubriendo o abajo).
      2. Un player prop supera un hito (25%, 50%, 75%, 100%) o se cumple.
      3. Termina un partido y la selección se marca como ganada (white_check_mark) o perdida (x).
    """
    raw_data = load_json_file(ACTIVE_PARLAY_PATH, {"parlays": []})
    parlays = normalize_parlays_list(raw_data)

    if not parlays:
        logger.info("No hay parlays activos en active_parlay.json.")
        return {}

    last_notified: Dict[str, Dict[str, Any]] = load_json_file(LAST_NOTIFIED_PATH, {})
    updated_state: Dict[str, Dict[str, Any]] = dict(last_notified)
    scoreboard_cache: Dict[str, Dict[str, Any]] = {}

    for p_idx, parlay in enumerate(parlays):
        parlay_id = str(parlay.get("id") or f"parlay_{p_idx + 1}")
        parlay_name = str(parlay.get("name") or f"Parlay #{p_idx + 1}")
        legs: List[Dict[str, Any]] = parlay.get("legs") or parlay.get("selections") or []

        for l_idx, sel in enumerate(legs):
            leg_id = str(sel.get("id") or f"leg_{l_idx + 1}")
            state_key = f"{parlay_id}:{leg_id}"
            label = (
                sel.get("label")
                or f"{sel.get('team', '')} {sel.get('odds', '')}".strip()
            )
            market_type = (sel.get("market_type") or "moneyline").lower()
            line_val = float(sel.get("line") or 0.0)

            live_info = evaluate_selection(sel, scoreboard_cache=scoreboard_cache)
            state = live_info["state"]
            status = live_info["status"]
            score_text = live_info["score_text"]
            is_covering = live_info["is_covering"]
            current_val = float(live_info["current_value"])

            # Soporta buscar tanto por state_key nuevo como por leg_id legado
            prev = last_notified.get(state_key) or last_notified.get(leg_id) or {}
            prev_score_text = prev.get("score_text", "")
            prev_milestone = int(prev.get("milestone", 0))
            prev_final_notified = bool(prev.get("final_notified", False))

            new_milestone = prev_milestone
            if market_type == "player_prop" and line_val > 0:
                pct = (current_val / line_val) * 100.0
                for threshold in (100, 75, 50, 25):
                    if pct >= threshold:
                        new_milestone = max(new_milestone, threshold)
                        break

            # 1. Partido finalizado -> Notificar resultado definitivo (white_check_mark / x)
            if state == "post" and not prev_final_notified:
                if status == "won":
                    send_ntfy_notification(
                        title=f"[{parlay_name}] Pick Ganado: {label}",
                        message=f"{score_text} — ¡Selección cobrada!",
                        tags=["white_check_mark", "moneybag"],
                        priority="high",
                    )
                else:
                    send_ntfy_notification(
                        title=f"[{parlay_name}] Pick Perdido: {label}",
                        message=f"{score_text} — Selección finalizada sin cubrir.",
                        tags=["x", "rotating_light"],
                        priority="high",
                    )
                prev_final_notified = True

            # 2. Partido en vivo -> Hitos de Player Prop o cambio en el marcador
            elif state == "in":
                if market_type == "player_prop" and new_milestone > prev_milestone:
                    if new_milestone >= 100:
                        send_ntfy_notification(
                            title=f"[{parlay_name}] ¡Player Prop Cumplido! {label}",
                            message=f"{score_text} (Meta de {line_val} superada)",
                            tags=["white_check_mark", "fire"],
                            priority="high",
                        )
                    else:
                        send_ntfy_notification(
                            title=f"[{parlay_name}] Avance de Prop ({new_milestone}%): {label}",
                            message=score_text,
                            tags=["chart_with_upwards_trend"],
                        )
                elif score_text != prev_score_text:
                    cover_badge = "Cubriendo en vivo" if is_covering else "Abajo en la línea"
                    tag = "green_circle" if is_covering else "red_circle"
                    send_ntfy_notification(
                        title=f"[{parlay_name}] {cover_badge}: {label}",
                        message=score_text,
                        tags=[tag],
                    )

            updated_state[state_key] = {
                "parlay_id": parlay_id,
                "parlay_name": parlay_name,
                "label": label,
                "state": state,
                "status": status,
                "score_text": score_text,
                "current_value": current_val,
                "milestone": new_milestone,
                "final_notified": prev_final_notified,
            }

    if updated_state != last_notified:
        save_json_file(LAST_NOTIFIED_PATH, updated_state)
        logger.info("Estado actualizado en last_notified.json.")
    else:
        logger.info("Sin cambios nuevos que notificar.")

    return updated_state


if __name__ == "__main__":
    run_monitor()
