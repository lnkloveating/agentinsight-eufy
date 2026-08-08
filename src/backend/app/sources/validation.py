"""原始资料入口的确定性格式和 URL 安全校验。"""

from dataclasses import dataclass
from hashlib import sha256
from ipaddress import ip_address
from pathlib import PurePath
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.errors import AppError
from app.schemas.source import SourceMediaCategory


@dataclass(frozen=True)
class SourceFileProfile:
    display_name: str
    suffix: str
    media_type: str
    media_category: SourceMediaCategory


_FILE_TYPES: dict[str, tuple[str, SourceMediaCategory]] = {
    ".pdf": ("application/pdf", SourceMediaCategory.DOCUMENT),
    ".txt": ("text/plain", SourceMediaCategory.DOCUMENT),
    ".md": ("text/markdown", SourceMediaCategory.DOCUMENT),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        SourceMediaCategory.DOCUMENT,
    ),
    ".csv": ("text/csv", SourceMediaCategory.DATASET),
    ".json": ("application/json", SourceMediaCategory.DATASET),
    ".jpg": ("image/jpeg", SourceMediaCategory.IMAGE),
    ".jpeg": ("image/jpeg", SourceMediaCategory.IMAGE),
    ".png": ("image/png", SourceMediaCategory.IMAGE),
    ".webp": ("image/webp", SourceMediaCategory.IMAGE),
    ".mp4": ("video/mp4", SourceMediaCategory.VIDEO),
    ".mov": ("video/quicktime", SourceMediaCategory.VIDEO),
    ".webm": ("video/webm", SourceMediaCategory.VIDEO),
    ".mp3": ("audio/mpeg", SourceMediaCategory.AUDIO),
    ".wav": ("audio/wav", SourceMediaCategory.AUDIO),
    ".m4a": ("audio/mp4", SourceMediaCategory.AUDIO),
}

_MIME_ALIASES = {
    "application/csv": "text/csv",
    "application/vnd.ms-excel": "text/csv",
    "application/x-pdf": "application/pdf",
    "audio/x-wav": "audio/wav",
}


def classify_source_file(
    filename: str | None, declared_media_type: str | None
) -> SourceFileProfile:
    if filename is None or not filename.strip() or "\x00" in filename:
        raise AppError(
            code="SOURCE_FILENAME_INVALID",
            message="上传文件必须包含有效文件名。",
            status_code=422,
        )
    display_name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not display_name or len(display_name) > 255:
        raise AppError(
            code="SOURCE_FILENAME_INVALID",
            message="上传文件名无效或超过 255 个字符。",
            status_code=422,
        )
    suffix = PurePath(display_name).suffix.lower()
    configured = _FILE_TYPES.get(suffix)
    if configured is None:
        raise AppError(
            code="SOURCE_FILE_TYPE_UNSUPPORTED",
            message="当前仅支持 PDF、文本、DOCX、CSV、JSON、图片、音频和视频资料。",
            status_code=415,
            details={"extension": suffix or None},
        )
    canonical_type, category = configured
    normalized_declared = (declared_media_type or "").split(";", 1)[0].strip().lower()
    normalized_declared = _MIME_ALIASES.get(normalized_declared, normalized_declared)
    if normalized_declared and normalized_declared != "application/octet-stream":
        declared_category = next(
            (
                candidate_category
                for candidate_type, candidate_category in _FILE_TYPES.values()
                if candidate_type == normalized_declared
            ),
            None,
        )
        if declared_category is not None and declared_category is not category:
            raise AppError(
                code="SOURCE_MEDIA_TYPE_MISMATCH",
                message="文件扩展名与声明的媒体类型不一致。",
                status_code=415,
                details={"filename": display_name, "media_type": normalized_declared},
            )
    return SourceFileProfile(
        display_name=display_name,
        suffix=suffix,
        media_type=canonical_type,
        media_category=category,
    )


def normalize_public_url(source_url: str) -> str:
    parts = urlsplit(source_url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise AppError(
            code="SOURCE_URL_INVALID",
            message="资料链接必须是有效的 HTTP 或 HTTPS 地址。",
            status_code=422,
        )
    if parts.username is not None or parts.password is not None:
        raise AppError(
            code="SOURCE_URL_CREDENTIALS_FORBIDDEN",
            message="资料链接不能包含用户名或密码。",
            status_code=422,
        )
    hostname = parts.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        _raise_private_url(hostname)
    try:
        address = ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        _raise_private_url(hostname)
    try:
        port = parts.port
    except ValueError as exc:
        raise AppError(
            code="SOURCE_URL_INVALID",
            message="资料链接端口无效。",
            status_code=422,
        ) from exc
    default_port = (parts.scheme.lower() == "http" and port == 80) or (
        parts.scheme.lower() == "https" and port == 443
    )
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"
    path = parts.path or "/"
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    query = urlencode(sorted(query_items))
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def source_url_hash(normalized_url: str) -> str:
    return sha256(normalized_url.encode("utf-8")).hexdigest()


def _raise_private_url(hostname: str) -> None:
    raise AppError(
        code="SOURCE_URL_PRIVATE_NETWORK_FORBIDDEN",
        message="为避免访问内网资源，只能登记公开网络地址。",
        status_code=422,
        details={"hostname": hostname},
    )
