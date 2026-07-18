#!/usr/bin/env python3
"""Fetch and verify the small, redistributable ACIS development corpus."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "corpus" / "sources.lock.json"
MANIFEST_PATH = ROOT / "corpus" / "manifest.jsonl"
sys.path.insert(0, str(ROOT / "src"))

from cq_acis import SatParseError, parse_sat  # noqa: E402


class CorpusError(RuntimeError):
    """Raised when an upstream or local corpus integrity check fails."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    prefix = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(prefix + data, usedforsecurity=False).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(data)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def raw_url(repository: str, commit: str, path: str) -> str:
    quoted_path = urllib.parse.quote(path, safe="/")
    return f"https://raw.githubusercontent.com/{repository}/{commit}/{quoted_path}"


def web_url(repository: str, commit: str, path: str) -> str:
    quoted_path = urllib.parse.quote(path, safe="/")
    return f"https://github.com/{repository}/blob/{commit}/{quoted_path}"


def download(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "cq-acis-corpus-fetcher/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise CorpusError(f"failed to download {url}: {error}") from error


def verify_upstream_blob(
    data: bytes, *, path: str, expected_sha1: str, expected_size: int
) -> None:
    if len(data) != expected_size:
        raise CorpusError(
            f"size mismatch for {path}: expected {expected_size}, got {len(data)}"
        )
    actual_sha1 = git_blob_sha1(data)
    if actual_sha1 != expected_sha1:
        raise CorpusError(
            f"Git blob SHA-1 mismatch for {path}: "
            f"expected {expected_sha1}, got {actual_sha1}"
        )


def constant_assignments(source: bytes, source_path: str) -> dict[str, ast.AST]:
    try:
        tree = ast.parse(source.decode("utf-8"), filename=source_path)
    except (UnicodeDecodeError, SyntaxError) as error:
        raise CorpusError(f"cannot parse fixture source {source_path}: {error}") from error

    assignments: dict[str, ast.AST] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                assignments[target.id] = node.value
    return assignments


def extract_python_constant(
    assignments: dict[str, ast.AST], constant: str, source_path: str
) -> bytes:
    try:
        value = assignments[constant]
    except KeyError as error:
        raise CorpusError(f"constant {constant!r} not found in {source_path}") from error

    if isinstance(value, ast.Constant):
        if isinstance(value.value, str):
            return value.value.encode("utf-8")
        if isinstance(value.value, bytes):
            return value.value

    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in {"bytes", "bytearray"}
        and len(value.args) == 1
        and not value.keywords
    ):
        try:
            return bytes(ast.literal_eval(value.args[0]))
        except (TypeError, ValueError, SyntaxError) as error:
            raise CorpusError(
                f"constant {constant!r} in {source_path} is not a literal byte array"
            ) from error

    raise CorpusError(
        f"constant {constant!r} in {source_path} has an unsupported expression"
    )


def sat_summary(data: bytes, artifact_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        document = parse_sat(data)
    except SatParseError as error:
        raise CorpusError(f"cannot frame SAT artifact {artifact_id}: {error}") from error

    header = document.header
    return {
        "save_version": header.save_version,
        "declared_record_count": header.declared_record_count,
        "declared_entity_count": header.declared_entity_count,
        "history_flag": header.history_flag,
        "product_id": header.product_id,
        "modeler_version": header.modeler_version,
        "creation_date": header.creation_date,
        "units_mm": header.units_mm,
        "resabs": header.resabs,
        "resnor": header.resnor,
    }, {
        "actual_record_count": len(document.records),
        "has_end_marker": document.has_end_marker,
        "entity_type_counts": dict(
            sorted(Counter(record.entity_type for record in document.records).items())
        ),
    }


def load_lock() -> dict[str, Any]:
    try:
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CorpusError(f"cannot read {LOCK_PATH}: {error}") from error
    if lock.get("schema_version") != 1:
        raise CorpusError("unsupported corpus source lock schema")
    return lock


def fetch_corpus() -> list[dict[str, Any]]:
    lock = load_lock()
    cache: dict[tuple[str, str, str], bytes] = {}
    assignment_cache: dict[tuple[str, str, str], dict[str, ast.AST]] = {}
    manifest: list[dict[str, Any]] = []

    def get_blob(
        repository: str,
        commit: str,
        path: str,
        expected_sha1: str,
        expected_size: int,
    ) -> bytes:
        key = (repository, commit, path)
        if key not in cache:
            data = download(raw_url(repository, commit, path))
            verify_upstream_blob(
                data,
                path=f"{repository}@{commit}:{path}",
                expected_sha1=expected_sha1,
                expected_size=expected_size,
            )
            cache[key] = data
        return cache[key]

    for source in lock["sources"]:
        repository = source["repository"]
        commit = source["commit"]
        license_info = source["license"]

        license_data = get_blob(
            repository,
            commit,
            license_info["source_path"],
            license_info["source_blob_sha1"],
            license_info["source_size"],
        )
        atomic_write(ROOT / license_info["target_path"], license_data)

        for artifact in source["artifacts"]:
            source_data = get_blob(
                repository,
                commit,
                artifact["source_path"],
                artifact["source_blob_sha1"],
                artifact["source_size"],
            )
            if artifact["kind"] == "file":
                data = source_data
                source_reference = artifact["source_path"]
            elif artifact["kind"] == "python_constant":
                key = (repository, commit, artifact["source_path"])
                assignments = assignment_cache.setdefault(
                    key,
                    constant_assignments(source_data, artifact["source_path"]),
                )
                data = extract_python_constant(
                    assignments, artifact["constant"], artifact["source_path"]
                )
                source_reference = (
                    f"{artifact['source_path']}#{artifact['constant']}"
                )
            else:
                raise CorpusError(
                    f"unsupported artifact kind {artifact['kind']!r}"
                )

            target_path = ROOT / artifact["target_path"]
            atomic_write(target_path, data)

            is_sat = artifact["dialect"].endswith("_sat")
            if is_sat:
                header, contents = sat_summary(data, artifact["id"])
            else:
                header, contents = None, None
            if header and header["save_version"] != artifact["expected_save_version"]:
                raise CorpusError(
                    f"save version mismatch for {artifact['id']}: "
                    f"expected {artifact['expected_save_version']}, "
                    f"got {header['save_version']}"
                )

            record: dict[str, Any] = {
                "id": artifact["id"],
                "path": artifact["target_path"],
                "format": "sat" if is_sat else "sab",
                "dialect": artifact["dialect"],
                "save_version": artifact["expected_save_version"],
                "size_bytes": len(data),
                "sha256": sha256_hex(data),
                "source": {
                    "repository": repository,
                    "commit": commit,
                    "reference": source_reference,
                    "url": web_url(
                        repository, commit, artifact["source_path"]
                    ),
                    "blob_sha1": artifact["source_blob_sha1"],
                },
                "license": {
                    "spdx": license_info["spdx"],
                    "notice": license_info["target_path"],
                },
                "redistribution": "see_upstream_notice",
            }
            if header:
                record["header"] = header
                record["contents"] = contents
            manifest.append(record)

    manifest.sort(key=lambda item: item["id"])
    manifest_bytes = b"".join(
        (json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        for item in manifest
    )
    atomic_write(MANIFEST_PATH, manifest_bytes)
    return manifest


def read_manifest() -> list[dict[str, Any]]:
    try:
        lines = MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError) as error:
        raise CorpusError(f"cannot read {MANIFEST_PATH}: {error}") from error


def check_corpus() -> list[dict[str, Any]]:
    lock = load_lock()
    manifest = read_manifest()
    expected_ids = {
        artifact["id"]
        for source in lock["sources"]
        for artifact in source["artifacts"]
    }
    actual_ids = {record["id"] for record in manifest}
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        raise CorpusError(f"manifest ID mismatch: missing={missing}, extra={extra}")

    for record in manifest:
        path = ROOT / record["path"]
        try:
            data = path.read_bytes()
        except OSError as error:
            raise CorpusError(f"cannot read corpus artifact {path}: {error}") from error
        if len(data) != record["size_bytes"]:
            raise CorpusError(
                f"size mismatch for {record['id']}: "
                f"expected {record['size_bytes']}, got {len(data)}"
            )
        actual_sha256 = sha256_hex(data)
        if actual_sha256 != record["sha256"]:
            raise CorpusError(
                f"SHA-256 mismatch for {record['id']}: "
                f"expected {record['sha256']}, got {actual_sha256}"
            )

    for source in lock["sources"]:
        license_info = source["license"]
        path = ROOT / license_info["target_path"]
        try:
            data = path.read_bytes()
        except OSError as error:
            raise CorpusError(f"cannot read license notice {path}: {error}") from error
        verify_upstream_blob(
            data,
            path=license_info["target_path"],
            expected_sha1=license_info["source_blob_sha1"],
            expected_size=license_info["source_size"],
        )

    return manifest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch or verify the pinned cq-acis development corpus."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify existing files without network access",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        manifest = check_corpus() if args.check else fetch_corpus()
    except CorpusError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    action = "verified" if args.check else "fetched"
    total_size = sum(record["size_bytes"] for record in manifest)
    print(f"{action} {len(manifest)} artifacts ({total_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
