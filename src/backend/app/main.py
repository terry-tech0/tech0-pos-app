"""FastAPI アプリの組み立て。設計仕様書 §5 API設計・§7 エラー処理・§8 セキュリティ設計。

ここでやること:
  - 本番では Swagger と OpenAPI JSON の両方を止める（§8.7）
  - CORS を設定する（§8.5）
  - 例外をすべて設計 §5.3 のエラー形式に揃える（§7.2 ER-3, ER-6）
  - ルーターを取り付ける（§5.2 B-01〜B-07）
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.config import Settings, get_settings
from app.errors import ERROR_SPEC, AppError, ErrorCode
from app.routers import auth, catalog, health, transactions

logger = logging.getLogger("pos")


def create_app(settings: Settings | None = None) -> FastAPI:
    """アプリを組み立てて返す。テストから設定を差し替えられるようにする。"""
    settings = settings or get_settings()

    # 設計 §8.7: docs_url だけ消しても足りない。
    # /openapi.json が生きていると、API定義（全エンドポイント・全パラメータ・型）が
    # そのまま読めてしまう。本番では両方 None にする
    docs_url = None if settings.is_production else "/docs"
    openapi_url = None if settings.is_production else "/openapi.json"

    app = FastAPI(
        title="tech0-pos-app backend",
        version="1.0.0",
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
    )

    # 設計 §8.5: 既定は空＝誰も許可しない。
    # allow_origins=["*"] は開発中の一時しのぎでも書かない
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,  # Bearer運用なのでCookieを跨がせない
        allow_methods=["GET", "POST"],  # 削除・更新APIは存在しないので開けない
        allow_headers=["Authorization", "Content-Type"],
    )

    _register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(catalog.router)
    app.include_router(transactions.router)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """例外を設計 §5.3 の共通エラー形式に揃える。"""

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        # 業務エラーは想定内。警告レベルで、コードだけをログに残す（設計 §7.3）
        logger.warning("%s %s -> %s", request.method, request.url.path, exc.code)
        return JSONResponse(status_code=exc.status_code, content=exc.to_response())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic の 422 をそのまま返さない。
        # 既定の 422 は項目名や型の詳細を含み、内部構造のヒントになる（ER-3）
        mapped = _map_validation_error(exc)
        logger.warning("%s %s -> %s (validation)", request.method, request.url.path, mapped.code)
        return JSONResponse(status_code=mapped.status_code, content=mapped.to_response())

    @app.exception_handler(OperationalError)
    async def _db_error(request: Request, exc: OperationalError) -> JSONResponse:
        # DBに繋がらない。画面は手動レジ運用へ切り替える（NFR-OPS-02 / E-SYS-002）
        logger.error("DB connection failed: %s %s", request.method, request.url.path)
        error = AppError(ErrorCode.SYS_UNAVAILABLE)
        return JSONResponse(status_code=error.status_code, content=error.to_response())

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # ER-6: 想定外の例外は必ず E-SYS-001 に丸めて返し、握りつぶさない。
        # スタックトレースはサーバログにだけ出す（ER-3 / 設計 §7.3）
        logger.exception("unhandled error: %s %s", request.method, request.url.path)
        error = AppError(ErrorCode.SYS_UNEXPECTED)
        return JSONResponse(status_code=error.status_code, content=error.to_response())


def _map_validation_error(exc: RequestValidationError) -> AppError:
    """Pydantic の検証エラーを設計 §7.1 のエラーコードに割り当てる。

    設計 §6 で上下限を3種類に分けているので、返すコードも分ける。
      明細0件        -> E-TXN-002（商品が登録されていません）
      明細101行以上  -> E-VAL-003（1回の会計に登録できるのは100行までです）
      数量が範囲外   -> E-VAL-002（数量は1〜99で入力してください）
      それ以外の形式 -> E-VAL-001（入力の形式が正しくありません）

    「1行の数量」と「1会計の行数」は別の上限。混同するとどちらかのチェックが抜ける。
    """
    errors = exc.errors()

    # 明細そのものの件数エラーを最優先で見る
    for err in errors:
        loc = tuple(str(part) for part in err.get("loc", ()))
        if loc and loc[-1] == "lines":
            error_type = str(err.get("type", ""))
            if error_type in ("too_short", "missing"):
                return AppError(ErrorCode.TXN_NO_LINES)
            if error_type == "too_long":
                return AppError(ErrorCode.VAL_LINE_COUNT)

    # 次に数量。明細のどこかで数量が範囲外
    for err in errors:
        loc = tuple(str(part) for part in err.get("loc", ()))
        if "quantity" in loc:
            return AppError(ErrorCode.VAL_QUANTITY)

    return AppError(ErrorCode.VAL_FORMAT)


# uvicorn app.main:app で起動する
app = create_app()

__all__ = ["app", "create_app", "ERROR_SPEC"]
