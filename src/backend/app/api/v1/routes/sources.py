from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.dependencies import SourceAssetServiceDependency
from app.schemas.source import (
    SourceAsset,
    SourceAssetIngestResult,
    SourceAssetKind,
    SourceAssetPage,
    SourceAssetStatus,
    SourceAuthorizationBasis,
    SourceFileMetadata,
    SourceLinkCreate,
)

router = APIRouter()


@router.get("/{project_id}/sources", response_model=SourceAssetPage)
async def list_source_assets(
    project_id: str,
    service: SourceAssetServiceDependency,
    cursor: str | None = None,
    kind: SourceAssetKind | None = None,
    status_filter: Annotated[SourceAssetStatus | None, Query(alias="status")] = None,
) -> SourceAssetPage:
    return await service.list(
        project_id,
        cursor=cursor,
        kind=kind,
        status=status_filter,
    )


@router.post(
    "/{project_id}/sources/files",
    response_model=SourceAssetIngestResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_source_file(
    project_id: str,
    service: SourceAssetServiceDependency,
    file: Annotated[UploadFile, File()],
    authorization_basis: Annotated[SourceAuthorizationBasis, Form()],
    authorization_confirmed: Annotated[bool, Form()],
    authorized_by: Annotated[str, Form(min_length=1, max_length=120)],
    purpose: Annotated[str, Form(min_length=1, max_length=500)],
) -> SourceAssetIngestResult:
    try:
        return await service.upload_file(
            project_id,
            filename=file.filename,
            declared_media_type=file.content_type,
            metadata=SourceFileMetadata(
                authorization_basis=authorization_basis,
                authorization_confirmed=authorization_confirmed,
                authorized_by=authorized_by,
                purpose=purpose,
            ),
            stream=file,
        )
    finally:
        await file.close()


@router.post(
    "/{project_id}/sources/links",
    response_model=SourceAssetIngestResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_source_link(
    project_id: str,
    payload: SourceLinkCreate,
    service: SourceAssetServiceDependency,
) -> SourceAssetIngestResult:
    return await service.create_link(project_id, payload)


@router.get("/{project_id}/sources/{source_asset_id}", response_model=SourceAsset)
async def get_source_asset(
    project_id: str,
    source_asset_id: str,
    service: SourceAssetServiceDependency,
) -> SourceAsset:
    return await service.get(project_id, source_asset_id)


@router.delete("/{project_id}/sources/{source_asset_id}", response_model=SourceAsset)
async def delete_source_asset(
    project_id: str,
    source_asset_id: str,
    service: SourceAssetServiceDependency,
) -> SourceAsset:
    return await service.delete(project_id, source_asset_id)
