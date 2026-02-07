"""P&L (Profit & Loss) routes."""
from flask import Blueprint, Response, jsonify, render_template, request

from auth import requires_auth
from services import pnl_service

pnl_bp = Blueprint("pnl", __name__)


@pnl_bp.route("/pnl")
@requires_auth
def pnl_page() -> Response:
    """P&L chart page."""
    pnl_service.take_snapshot()
    current = pnl_service.get_current_pnl()
    return render_template("pnl.html", current=current)


@pnl_bp.route("/api/pnl/data")
@requires_auth
def pnl_data() -> Response:
    """Get P&L chart data as JSON."""
    hours = request.args.get("hours", 24, type=int)
    hours = max(1, min(hours, 240))

    pnl_service.take_snapshot()
    chart_data = pnl_service.get_chart_data(hours=hours)
    return jsonify(chart_data)


@pnl_bp.route("/api/pnl/current")
@requires_auth
def pnl_current() -> Response:
    """Get current P&L snapshot."""
    current = pnl_service.get_current_pnl()
    if current is None:
        return jsonify({"error": "Failed to fetch P&L data"}), 503
    return jsonify(current)
