from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.database import connect_db, close_db
from app.routes import (
    menu_item_rules_routes,
    rule_multipliers_routes,
    rule_versions_routes,
    excel_import_routes,
    calculation_requests_routes,
    calculation_results_routes,
    override_requests_routes,
    override_approvals_routes,
    actual_order_outcomes_routes,
    rule_recommendations_routes,
    learning_cycle_config_routes,
    auth_routes,
)
from app.services import (
    menu_item_rules_service,
    rule_multipliers_service,
    rule_versions_service,
    excel_import_jobs_service,
    calculation_requests_service,
    calculation_results_service,
    override_requests_service,
    override_approvals_service,
    actual_order_outcomes_service,
    rule_recommendations_service,
    learning_cycle_config_service,
)
from app.services.learning_cycle_config_service import (
    check_and_update_conditions,
    mark_recommendations_generated,
)
from app.services.rule_recommendations_service import run_learning_engine

# ── Scheduler ─────────────────────────────────────────────────────────────────
scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("cron", hour=6, minute=0)
async def daily_learning_job():
    config = await check_and_update_conditions()
    if config.get("currentCycle", {}).get("bothConditionsMet"):
        cycle_id    = config["currentCycle"]["cycleId"]
        cycle_start = config["currentCycle"]["cycleStartDate"]
        cycle_end   = config["currentCycle"]["cycleEndDate"]
        count = await run_learning_engine(cycle_id, cycle_start, cycle_end)
        await mark_recommendations_generated(cycle_id, count)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()

    # create indexes for all collections
    await menu_item_rules_service.create_indexes()
    await rule_multipliers_service.create_indexes()
    await rule_versions_service.create_indexes()
    await excel_import_jobs_service.create_indexes()
    await calculation_requests_service.create_indexes()
    await calculation_results_service.create_indexes()
    await override_requests_service.create_indexes()
    await override_approvals_service.create_indexes()
    await actual_order_outcomes_service.create_indexes()
    await rule_recommendations_service.create_indexes()
    await learning_cycle_config_service.create_indexes()
    await auth_routes.create_indexes()

    scheduler.start()
    yield
    scheduler.shutdown()
    await close_db()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CraveCall.ai Catering Engine",
    description="Rule-based catering tray calculation engine",
    version="1.0.0",
    lifespan=lifespan
)

# ── CORS — must be before routes ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "https://cravel-frontend.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(auth_routes.router,                  prefix="/api/v1")
app.include_router(menu_item_rules_routes.router,       prefix="/api/v1")
app.include_router(rule_multipliers_routes.router,      prefix="/api/v1")
app.include_router(rule_versions_routes.router,         prefix="/api/v1")
app.include_router(excel_import_routes.router,          prefix="/api/v1")
app.include_router(calculation_requests_routes.router,  prefix="/api/v1")
app.include_router(calculation_results_routes.router,   prefix="/api/v1")
app.include_router(override_requests_routes.router,     prefix="/api/v1")
app.include_router(override_approvals_routes.router,    prefix="/api/v1")
app.include_router(actual_order_outcomes_routes.router, prefix="/api/v1")
app.include_router(rule_recommendations_routes.router,  prefix="/api/v1")
app.include_router(learning_cycle_config_routes.router, prefix="/api/v1")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "engine":  "CraveCall.ai Catering Engine",
        "version": "1.0.0",
        "status":  "running",
        "docs":    "/docs"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}