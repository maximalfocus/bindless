"""Shared HTTP wiring.

Every application variant is built from this factory, so method, path, authentication contract, and
successful response shape are identical by construction. Only the listing query differs — which is
exactly the difference the walkthrough is about.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Protocol, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from bindless.audit import SortRejection
from bindless.auth import (
    BEARER_CHALLENGE,
    GENERIC_UNAUTHORIZED_DETAIL,
    Principal,
    resolve_principal,
)
from bindless.db import create_db_engine, create_session_factory, wait_until_ready
from bindless.listing import ListingResult, UnknownSortError
from bindless.schemas import (
    HealthResponse,
    InvoiceListResponse,
    InvoiceOut,
    OrganizationOut,
    UserOut,
)

#: Returned for any non-allowlisted sort value. It names the rejected parameter and nothing else:
#: no valid identifiers, no table or column structure, no indication of whether rows exist.
INVALID_SORT_DETAIL = "Invalid sort parameter."

#: Header the vulnerable application uses to surface the statement it assembled. It is a header
#: rather than a response field so that both applications' JSON bodies stay directly comparable.
EFFECTIVE_QUERY_HEADER = "X-Bindless-Effective-Query"

#: Callers may supply their own correlation id; otherwise one is generated per request.
REQUEST_ID_HEADER = "X-Request-ID"

#: Emits the audit event for a refused sort identifier. Only the secure application has one.
AuditEmitter = Callable[[SortRejection], None]


class ListingQuery(Protocol):
    """How an application variant turns caller input into invoice rows."""

    def __call__(
        self,
        connection: Connection,
        *,
        org_id: int,
        supplier: str,
        sort: str | None,
    ) -> ListingResult: ...


@dataclass(slots=True)
class AppResources:
    engine: Engine
    session_factory: sessionmaker[Session]


def _database_error_detail(error: SQLAlchemyError) -> str:
    """The database's own complaint about a malformed injected identifier."""
    original: object = getattr(error, "orig", None)
    return str(original if original is not None else error).strip()


def _resources(app: FastAPI) -> AppResources:
    return cast(AppResources, app.state.resources)


def get_db_session(request: Request) -> Iterator[Session]:
    session = _resources(request.app).session_factory()
    try:
        yield session
    finally:
        # Nothing here ever commits: the listing is a read-only, single-statement query.
        session.rollback()
        session.close()


SessionDep = Annotated[Session, Depends(get_db_session)]


def require_principal(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    principal = resolve_principal(session, authorization)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_UNAUTHORIZED_DETAIL,
            headers=BEARER_CHALLENGE,
        )
    return principal


PrincipalDep = Annotated[Principal, Depends(require_principal)]


def create_app(
    *,
    title: str,
    description: str,
    list_invoices: ListingQuery,
    audit: AuditEmitter | None = None,
    expose_statement: bool = False,
) -> FastAPI:
    """Build one application variant.

    `audit` is supplied only by the secure application, which is the only one that can refuse a
    sort identifier. `expose_statement` is enabled only by the vulnerable application, so the
    secure one never hands out its query as a starting point.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_db_engine()
        wait_until_ready(engine)
        app.state.resources = AppResources(
            engine=engine, session_factory=create_session_factory(engine)
        )
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title=title, description=description, version="0.1.0", lifespan=lifespan)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz(session: SessionDep) -> HealthResponse:
        session.execute(text("SELECT 1"))
        return HealthResponse(status="ok")

    @app.get("/invoices", response_model=InvoiceListResponse)
    def list_invoices_endpoint(
        principal: PrincipalDep,
        session: SessionDep,
        response: Response,
        supplier: Annotated[str, Query(description="Supplier name to match.")],
        sort: Annotated[str | None, Query(description="Column to order by.")] = None,
        x_request_id: Annotated[str | None, Header()] = None,
    ) -> InvoiceListResponse:
        request_id = x_request_id or str(uuid.uuid4())
        try:
            result = list_invoices(
                session.connection(),
                org_id=principal.org_id,
                supplier=supplier,
                sort=sort,
            )
        except UnknownSortError:
            if audit is not None:
                audit(
                    SortRejection(
                        request_id=request_id,
                        user_id=principal.user_id,
                        org_id=principal.org_id,
                    )
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=INVALID_SORT_DETAIL,
            ) from None
        except SQLAlchemyError as error:
            if not expose_statement:
                # Fail closed: the secure application must never turn a database error into an
                # oracle for what tables, columns, or rows exist.
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal error.",
                ) from None
            # The vulnerable application hands back the database's own complaint, which is exactly
            # the structural oracle the secure path refuses to provide. Seeing that difference is
            # part of the demonstration.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_database_error_detail(error),
            ) from None
        if expose_statement:
            response.headers[EFFECTIVE_QUERY_HEADER] = result.statement
        invoices = [
            InvoiceOut(
                invoice_number=row.invoice_number,
                supplier=row.supplier,
                amount=row.amount,
                status=row.status,
            )
            for row in result.rows
        ]
        return InvoiceListResponse(
            organization=OrganizationOut(id=principal.org_id, name=principal.org_name),
            user=UserOut(
                id=principal.user_id,
                email=principal.email,
                display_name=principal.display_name,
            ),
            sort=result.sort,
            count=len(invoices),
            invoices=invoices,
        )

    return app
