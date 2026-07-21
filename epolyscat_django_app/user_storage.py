"""Drop-in replacement for ``airavata_django_portal_sdk.user_storage``.

The rebuilt (gRPC-only) Airavata Django Portal no longer ships the
``airavata-django-portal-sdk``; storage goes through the raw
``UserStorageService`` / ``DataProductService`` gRPC stubs over the
Bearer-authenticated channel the portal middleware attaches as
``request.airavata_channel``. This module reimplements just the slice of the
old SDK's ``user_storage`` API that the ePolyScat app uses, with the same
signatures and return shapes, so view/model/serializer code keeps working.
"""

import io
import logging
import os

from django.urls import reverse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# stubs / helpers
# ---------------------------------------------------------------------------


def _storage(request):
    from airavata.services.file_service_pb2_grpc import UserStorageServiceStub

    return UserStorageServiceStub(request.airavata_channel)


def _data_products(request):
    from airavata.services.data_product_service_pb2_grpc import (
        DataProductServiceStub,
    )

    return DataProductServiceStub(request.airavata_channel)


def _fs_pb2():
    from airavata.services import file_service_pb2

    return file_service_pb2


def _dp_pb2():
    from airavata.services import data_product_service_pb2

    return data_product_service_pb2


def _user_storage_path(path, experiment_id=None, request=None):
    """Resolve a portal-relative path to the ``~/``-anchored facade path.

    Mirrors the host portal's ``_user_storage_path``: a bare relative path is
    relative to the user's storage root; with *experiment_id* it is relative
    to that experiment's data directory.
    """
    rel = (path or "").lstrip("/")
    if experiment_id:
        from airavata.services import experiment_service_pb2 as exp_pb2
        from airavata.services.experiment_service_pb2_grpc import (
            ExperimentServiceStub,
        )

        experiment = ExperimentServiceStub(request.airavata_channel).GetExperiment(
            exp_pb2.GetExperimentRequest(experiment_id=experiment_id)
        )
        data_dir = (
            experiment.user_configuration_data.experiment_data_dir
            if experiment.HasField("user_configuration_data")
            else None
        ) or ""
        base = data_dir.strip("/")
        full = base + ("/" + rel if rel else "")
        if full.startswith("~/"):
            return full
        return "~/" + full
    if rel.startswith("~"):
        return rel
    return "~/" + rel


class _DataProduct:
    """Tiny facade over the proto ``DataProductModel`` exposing the Thrift-era
    attribute names call sites still use (``productUri``)."""

    def __init__(self, proto):
        self._proto = proto

    @property
    def productUri(self):  # noqa: N802 (legacy SDK camelCase)
        return self._proto.product_uri

    @property
    def product_uri(self):
        return self._proto.product_uri

    def __getattr__(self, name):
        return getattr(self._proto, name)


def _get_data_product(request, data_product_uri):
    dp_pb2 = _dp_pb2()
    return _data_products(request).GetDataProduct(
        dp_pb2.GetDataProductRequest(product_uri=data_product_uri)
    )


def _data_product_file_path(data_product):
    """First replica's file path (facade path) from a ``DataProductModel``."""
    for replica in data_product.replica_locations:
        if replica.file_path:
            file_path = replica.file_path
            if file_path.startswith("file://"):
                file_path = file_path[len("file://") :]
            return file_path
    return None


def _register_data_product(
    request, *, name, file_path, content_type=None, product_size=0
):
    """Register a data product for a file the storage facade wrote (mirrors the
    host portal's ``_storage_upload_and_register`` registration step)."""
    from django.conf import settings

    from airavata.model.data.replica import replica_catalog_pb2 as rc

    dp_pb2 = _dp_pb2()
    fs_pb2 = _fs_pb2()
    storage_resource_id = (
        _storage(request)
        .GetDefaultStorageResourceId(fs_pb2.GetDefaultStorageResourceIdRequest())
        .storage_resource_id
    )
    product_metadata = {"mime-type": content_type} if content_type else {}
    data_product = rc.DataProductModel(
        gateway_id=settings.GATEWAY_ID or "",
        owner_name=request.user.username,
        product_name=name or "",
        data_product_type=rc.DataProductType.FILE,
        product_size=product_size or 0,
        product_metadata=product_metadata,
        replica_locations=[
            rc.DataReplicaLocationModel(
                replica_name=f"{name} gateway data store copy",
                replica_location_category=rc.ReplicaLocationCategory.GATEWAY_DATA_STORE,
                replica_persistent_type=rc.ReplicaPersistentType.TRANSIENT,
                storage_resource_id=storage_resource_id or "",
                file_path=file_path,
            )
        ],
    )
    product_uri = (
        _data_products(request)
        .RegisterDataProduct(dp_pb2.RegisterDataProductRequest(data_product=data_product))
        .product_uri
    )
    return _get_data_product(request, product_uri)


def _read_file_bytes(file):
    """Bytes of *file*, accepting both binary and text file-likes."""
    content = file.read()
    if isinstance(content, str):
        content = content.encode("utf-8")
    return content


# ---------------------------------------------------------------------------
# public API (mirrors airavata_django_portal_sdk.user_storage)
# ---------------------------------------------------------------------------

# Input files staged for an experiment go under this directory in the user's
# storage (same convention as the legacy SDK / the host portal upload view).
TMP_INPUT_FILE_UPLOAD_DIR = "tmp"


def open_file(request, data_product_uri=None):
    """Open the file behind *data_product_uri*; returns a binary file-like
    object with a ``name`` attribute (like the legacy SDK)."""
    fs_pb2 = _fs_pb2()
    resp = _storage(request).DownloadDataProduct(
        fs_pb2.DownloadDataProductRequest(product_uri=data_product_uri)
    )
    f = io.BytesIO(resp.content)
    f.name = resp.name or ""
    return f


def exists(request, data_product_uri=None):
    """True if the file behind *data_product_uri* exists in storage."""
    fs_pb2 = _fs_pb2()
    try:
        data_product = _get_data_product(request, data_product_uri)
    except Exception:
        logger.debug("No data product for %s", data_product_uri, exc_info=True)
        return False
    file_path = _data_product_file_path(data_product)
    if file_path is None:
        return False
    return (
        _storage(request)
        .FileExists(fs_pb2.FileExistsRequest(storage_resource_id="", path=file_path))
        .exists
    )


def save(request, path, file, name=None, content_type=None):
    """Save *file* under *path* (relative to the user's storage root) and
    register a data product for it. Returns an object with ``productUri``."""
    fs_pb2 = _fs_pb2()
    storage = _storage(request)
    name = name or os.path.basename(getattr(file, "name", "") or "")
    upload_path = _user_storage_path(os.path.join(path or "", name))
    content = _read_file_bytes(file)
    storage.UploadFile(
        fs_pb2.UploadFileRequest(
            storage_resource_id="",
            path=upload_path,
            name=name,
            content_type=content_type or "",
            content=content,
        )
    )
    metadata = storage.GetFileMetadata(
        fs_pb2.GetFileMetadataRequest(storage_resource_id="", path=upload_path)
    )
    data_product = _register_data_product(
        request,
        name=name,
        file_path=metadata.path,
        content_type=content_type,
        product_size=metadata.size,
    )
    return _DataProduct(data_product)


def save_input_file(request, file, name=None, content_type=None):
    """Stage an experiment input file under the tmp upload dir (mirrors the
    legacy SDK's ``save_input_file``). Returns an object with ``productUri``."""
    return save(
        request,
        TMP_INPUT_FILE_UPLOAD_DIR,
        file,
        name=name,
        content_type=content_type,
    )


def get_download_url(request, data_product_uri=None, data_product=None):
    """URL the browser can hit to download the data product (the host portal
    still serves ``/sdk/download/``)."""
    from urllib.parse import urlencode

    if data_product_uri is None and data_product is not None:
        data_product_uri = getattr(data_product, "productUri", None) or getattr(
            data_product, "product_uri", ""
        )
    return (
        reverse("sdk_download") + "?" + urlencode({"data-product-uri": data_product_uri})
    )


def get_data_product_metadata(request, data_product_uri=None):
    """Metadata dict for the data product; provides ``mime_type`` like the
    legacy SDK."""
    data_product = _get_data_product(request, data_product_uri)
    metadata = dict(data_product.product_metadata)
    return {
        "mime_type": metadata.get("mime-type", ""),
        "name": data_product.product_name,
        "size": data_product.product_size,
    }


def dir_exists(request, path):
    fs_pb2 = _fs_pb2()
    return (
        _storage(request)
        .DirExists(
            fs_pb2.DirExistsRequest(
                storage_resource_id="", path=_user_storage_path(path)
            )
        )
        .exists
    )


def create_user_dir(request, dir_names=None, path=None):
    """Create a directory in the user's storage. Accepts ``dir_names`` (tuple
    of path segments, legacy SDK style) or ``path``."""
    fs_pb2 = _fs_pb2()
    if path is None:
        path = os.path.join(*dir_names) if dir_names else ""
    resolved = _user_storage_path(path)
    storage = _storage(request)
    if (
        not storage.DirExists(
            fs_pb2.DirExistsRequest(storage_resource_id="", path=resolved)
        ).exists
    ):
        storage.CreateDir(
            fs_pb2.CreateDirRequest(storage_resource_id="", path=resolved)
        )


def delete_dir(request, path):
    fs_pb2 = _fs_pb2()
    _storage(request).DeleteDir(
        fs_pb2.DeleteDirRequest(storage_resource_id="", path=_user_storage_path(path))
    )


def delete(request, data_product_uri=None):
    """Delete the file behind *data_product_uri*."""
    fs_pb2 = _fs_pb2()
    data_product = _get_data_product(request, data_product_uri)
    file_path = _data_product_file_path(data_product)
    if file_path is not None:
        _storage(request).DeleteFile(
            fs_pb2.DeleteFileRequest(storage_resource_id="", path=file_path)
        )


def update_data_product_content(request, data_product_uri=None, fileContentText=""):  # noqa: N803 (legacy SDK name)
    """Replace the contents of the file behind *data_product_uri*."""
    fs_pb2 = _fs_pb2()
    data_product = _get_data_product(request, data_product_uri)
    file_path = _data_product_file_path(data_product)
    if file_path is None:
        raise FileNotFoundError(f"{data_product_uri} has no replica to update")
    content = fileContentText
    if isinstance(content, str):
        content = content.encode("utf-8")
    _storage(request).UploadFile(
        fs_pb2.UploadFileRequest(
            storage_resource_id="",
            path=file_path,
            name=os.path.basename(file_path),
            content_type="",
            content=content,
        )
    )


def user_file_exists(request, path, experiment_id=None):
    """Data product URI for the file at *path* if it exists, else ``None``."""
    fs_pb2 = _fs_pb2()
    resolved = _user_storage_path(path, experiment_id, request)
    storage = _storage(request)
    if not storage.FileExists(
        fs_pb2.FileExistsRequest(storage_resource_id="", path=resolved)
    ).exists:
        return None
    metadata = storage.GetFileMetadata(
        fs_pb2.GetFileMetadataRequest(storage_resource_id="", path=resolved)
    )
    if metadata.data_product_uri:
        return metadata.data_product_uri
    # The file exists but has no registered data product yet; register one so
    # callers get a usable URI (the legacy SDK did the same on demand).
    data_product = _register_data_product(
        request,
        name=metadata.name or os.path.basename(resolved),
        file_path=metadata.path,
        content_type=metadata.content_type,
        product_size=metadata.size,
    )
    return data_product.product_uri


def list_experiment_dir(request, experiment_id, path=""):
    """(directories, files) listing of an experiment's data dir; entries are
    dicts with the legacy SDK's ``name`` / ``data-product-uri`` keys."""
    fs_pb2 = _fs_pb2()
    resolved = _user_storage_path(path, experiment_id, request)
    listing = _storage(request).ListDir(
        fs_pb2.ListDirRequest(storage_resource_id="", path=resolved)
    )

    def entry(meta):
        return {
            "name": meta.name,
            "path": meta.path,
            "size": meta.size,
            "data-product-uri": meta.data_product_uri,
        }

    directories = [entry(d) for d in listing.directories]
    files = [entry(f) for f in listing.files]
    return directories, files


def listdir(request, path):
    """(directories, files) listing of a user-storage directory."""
    fs_pb2 = _fs_pb2()
    listing = _storage(request).ListDir(
        fs_pb2.ListDirRequest(storage_resource_id="", path=_user_storage_path(path))
    )

    def entry(meta):
        return {
            "name": meta.name,
            "path": meta.path,
            "size": meta.size,
            "data-product-uri": meta.data_product_uri,
        }

    return [entry(d) for d in listing.directories], [entry(f) for f in listing.files]
