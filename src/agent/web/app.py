from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent.config import AppConfig, load_config
from agent.demo_data import create_demo_config_and_ledger
from agent.ledger import Ledger
from agent.web.service import (
    DashboardService,
    compact_items,
    format_money,
    format_number,
    format_percent,
    status_class,
)


PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
templates.env.filters["pct"] = format_percent
templates.env.filters["num"] = format_number
templates.env.filters["money"] = format_money
templates.env.filters["status_class"] = status_class
templates.env.filters["items_compact"] = compact_items


def create_app(
    *,
    config_path: str = "config/strategy.toml",
    limit: int = 25,
    demo_data: bool = False,
) -> FastAPI:
    if demo_data:
        config, ledger = create_demo_config_and_ledger()
        return create_app_from_config(config, ledger, limit=limit, demo_data=True)
    config = load_config(config_path)
    ledger = Ledger(config.storage.sqlite_path, config.storage.audit_log_path)
    return create_app_from_config(config, ledger, limit=limit)


def create_app_from_config(
    config: AppConfig,
    ledger: Ledger,
    *,
    limit: int = 25,
    demo_data: bool = False,
) -> FastAPI:
    app = FastAPI(
        title="Taurus Dashboard",
        description="Read-only local dashboard for Taurus governance evidence.",
        version="0.1.0",
    )
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    def service() -> DashboardService:
        return DashboardService(config, ledger, limit=limit, demo_data=demo_data)

    def render(request: Request, template: str, active: str, payload: dict[str, object]):
        context = {"request": request}
        dashboard = service()
        context.update(dashboard.base_context(active=active))
        context.update(payload)
        return templates.TemplateResponse(request=request, name=template, context=context)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        return render(request, "dashboard.html", "dashboard", service().overview())

    @app.get("/decisions", response_class=HTMLResponse)
    def decisions(request: Request):
        return render(request, "decisions.html", "decisions", service().decisions())

    @app.get("/decisions/{snapshot_id}", response_class=HTMLResponse)
    def decision_detail(request: Request, snapshot_id: int):
        return render(request, "decision_detail.html", "decisions", service().decision_detail(snapshot_id))

    @app.get("/timeline", response_class=HTMLResponse)
    def timeline(request: Request):
        return render(request, "timeline.html", "timeline", service().timeline())

    @app.get("/risk", response_class=HTMLResponse)
    def risk(request: Request):
        return render(request, "risk.html", "risk", service().risk())

    @app.get("/risk/controls", response_class=HTMLResponse)
    def risk_controls(request: Request):
        return render(request, "risk_controls.html", "risk", service().risk_controls())

    @app.get("/models", response_class=HTMLResponse)
    def models(request: Request):
        return render(request, "models.html", "models", service().models())

    @app.get("/models/{model_version}", response_class=HTMLResponse)
    def model_card(request: Request, model_version: str):
        return render(request, "model_card.html", "models", service().model_card(model_version))

    @app.get("/reliability", response_class=HTMLResponse)
    def reliability(request: Request):
        return render(request, "reliability.html", "reliability", service().reliability())

    @app.get("/reconciliation", response_class=HTMLResponse)
    def reconciliation(request: Request):
        return render(request, "reconciliation.html", "reconciliation", service().reconciliation())

    @app.get("/incidents", response_class=HTMLResponse)
    def incidents(request: Request):
        return render(request, "incidents.html", "incidents", service().incidents())

    @app.get("/governance/roles", response_class=HTMLResponse)
    def governance_roles(request: Request):
        return render(request, "governance_roles.html", "roles", service().governance_roles())

    @app.get("/replay", response_class=HTMLResponse)
    def replay(request: Request):
        return render(request, "replay.html", "replay", service().replay_index())

    @app.get("/replay/decision/{snapshot_id}", response_class=HTMLResponse)
    def replay_decision(request: Request, snapshot_id: int):
        return render(request, "replay_decision.html", "replay", service().replay_decision(snapshot_id))

    @app.get("/audit", response_class=HTMLResponse)
    def audit(request: Request):
        return render(request, "audit.html", "audit", service().audit())

    return app
