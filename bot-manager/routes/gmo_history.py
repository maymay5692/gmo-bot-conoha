"""GMO Coin trade history routes (real executions via Private API)."""
import re
from typing import Tuple, Union

import requests
from flask import Blueprint, Response, jsonify, request

from auth import requires_auth
from services.gmo_api_service import (
    GmoApiError,
    fetch_executions_for_date,
    summarize_executions,
)

gmo_history_bp = Blueprint("gmo_history", __name__)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SYMBOL_RE = re.compile(r"^[A-Z0-9_]{3,20}$")

FlaskResponse = Union[Response, Tuple[Response, int]]


@gmo_history_bp.route("/gmo/executions")
@requires_auth
def api_gmo_executions() -> FlaskResponse:
    """Return all real executions for a given JST date, fetched live from GMO.

    Query params:
        date   — required, YYYY-MM-DD (JST)
        symbol — optional, default BTC_JPY
        max_pages — optional, default 50 (safety cap)

    Response:
        {
          "date": "...",
          "symbol": "...",
          "executions": [...],
          "total": N,
          "pages_fetched": M,
          "complete": bool,
          "summary": {
            "total_fills", "open_fills", "close_fills",
            "realized_pnl", "total_fee", "net_pnl"
          }
        }
    """
    date_arg = request.args.get("date", "")
    if not _DATE_RE.match(date_arg):
        return jsonify({
            "error": "Missing or invalid 'date' parameter (YYYY-MM-DD)"
        }), 400

    symbol = request.args.get("symbol", "BTC_JPY")
    if not _SYMBOL_RE.match(symbol):
        return jsonify({"error": "Invalid 'symbol' parameter"}), 400

    try:
        max_pages = int(request.args.get("max_pages", "50"))
    except ValueError:
        return jsonify({"error": "max_pages must be an integer"}), 400
    if max_pages < 1 or max_pages > 200:
        return jsonify({"error": "max_pages must be between 1 and 200"}), 400

    try:
        result = fetch_executions_for_date(
            date_jst=date_arg, symbol=symbol, max_pages=max_pages
        )
    except GmoApiError as e:
        return jsonify({
            "error": f"GMO API error: {e}",
        }), 502
    except (requests.RequestException, OSError) as e:
        return jsonify({"error": f"Network error: {e}"}), 502

    result["symbol"] = symbol
    result["summary"] = summarize_executions(result["executions"])
    return jsonify(result)
