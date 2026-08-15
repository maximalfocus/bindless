"""Shared HTTP wiring.

Every application variant is built from this factory, so method, path, authentication contract, and
successful response shape are identical by construction. Only the listing query differs — which is
exactly the difference the walkthrough is about.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Protocol, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session, sessionmaker

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


def create_app(*, title: str, description: str, list_invoices: ListingQuery) -> FastAPI:
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
        supplier: Annotated[str, Query(description="Supplier name to match.")],
        sort: Annotated[str | None, Query(description="Column to order by.")] = None,
    ) -> InvoiceListResponse:
        try:
            result = list_invoices(
                session.connection(),
                org_id=principal.org_id,
                supplier=supplier,
                sort=sort,
            )
        except UnknownSortError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=INVALID_SORT_DETAIL,
            ) from None
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
