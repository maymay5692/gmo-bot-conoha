"""Metrics and trades CSV download API routes."""
import re

from flask import Blueprint, Response, jsonify, request

from auth import requires_auth
from services import metrics_service

metrics_bp = Blueprint("metrics", __name__)

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@metrics_bp.route("/metrics/csv")
@requires_auth
def metrics_csv() -> Response:
    """Get metrics CSV data as JSON for a given date."""
    date = request.args.get("date", "")
    if not date or not DATE_PATTERN.match(date):
        return jsonify({"error": "Missing or invalid 'date' parameter (YYYY-MM-DD)"}), 400

    rows = metrics_service.get_metrics_csv(date)
    if rows is None:
        return jsonify({"error": f"No metrics data for {date}"}), 404

    return jsonify({"date": date, "type": "metrics", "count": len(rows), "rows": rows})


@metrics_bp.route("/trades/csv")
@requires_auth
def trades_csv() -> Response:
    """Get trades CSV data as JSON for a given date."""
    date = request.args.get("date", "")
    if not date or not DATE_PATTERN.match(date):
        return jsonify({"error": "Missing or invalid 'date' parameter (YYYY-MM-DD)"}), 400

    rows = metrics_service.get_trades_csv(date)
    if rows is None:
        return jsonify({"error": f"No trades data for {date}"}), 404

    return jsonify({"date": date, "type": "trades", "count": len(rows), "rows": rows})


VALID_CSV_TYPES = ("metrics", "trades")


@metrics_bp.route("/metrics/dates")
@requires_auth
def available_dates() -> Response:
    """List available CSV dates."""
    csv_type = request.args.get("type", "metrics")
    if csv_type not in VALID_CSV_TYPES:
        return jsonify({"error": "Invalid type. Must be 'metrics' or 'trades'"}), 400
    dates = metrics_service.list_available_dates(csv_type)
    return jsonify({"type": csv_type, "dates": dates})
