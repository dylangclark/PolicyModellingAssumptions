from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .adapters import get_adapter
from .config import ConfigurationError, RegistryConfig, find_repo_root
from .db import RegistryDB
from .export import export_registry
from .http import HttpClient
from .legacy import migrate_legacy
from .pipeline import Pipeline
from .publication import PublicationError, validate_publication
from .regulatory.recipe import extract_candidates_from_pages, extract_pdf_pages, load_recipe
from .regulatory.review import ReviewQueue
from .release import release_blockers, source_is_required


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bc-assumptions",
        description="Build and publish the B.C. Assumptions Registry.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="Repository root. Defaults to auto-detection from the current directory.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("validate-config", help="Validate variable and source registries.")
    commands.add_parser("init-db", aliases=["init"], help="Initialize the SQLite registry.")

    run = commands.add_parser(
        "run", help="Collect authoritative sources and refresh public exports."
    )
    selection = run.add_mutually_exclusive_group()
    selection.add_argument("--all", action="store_true", help="Run all enabled sources.")
    selection.add_argument(
        "--source",
        action="append",
        default=[],
        help="Run only this source ID. Repeat to select more than one source.",
    )
    run.add_argument(
        "--full-refresh",
        "--bootstrap",
        dest="full_refresh",
        action="store_true",
        help="Ignore incremental lookbacks and rebuild source history where supported.",
    )
    run.add_argument(
        "--strict",
        action="store_true",
        help="Stop after the first failed, partial, or skipped required source.",
    )
    run.add_argument(
        "--no-export",
        action="store_true",
        help="Collect and evaluate the release gate without refreshing public files.",
    )

    export = commands.add_parser(
        "export",
        aliases=["build-site"],
        help="Refresh CSV, JSON and site data after evaluating the release gate.",
    )
    export.add_argument(
        "--force",
        action="store_true",
        help="Bypass the release gate for scaffold/recovery use. Never use in weekly automation.",
    )
    commands.add_parser(
        "validate-public",
        help="Validate generated GitHub-facing CSV and JSON without modifying them.",
    )
    commands.add_parser("status", help="Show source run status, coverage and release blockers.")
    commands.add_parser("list-sources", help="List configured sources and publication gates.")

    inspect = commands.add_parser(
        "inspect-statcan",
        help="Download and print Statistics Canada cube metadata for selector design.",
    )
    inspect.add_argument("product_id", type=int)
    inspect.add_argument(
        "--source",
        default="statistics_canada_wds",
        help="Configured Statistics Canada source ID.",
    )

    legacy = commands.add_parser(
        "import-legacy",
        help="Convert the original Markdown table into a provenance-gated staging CSV.",
    )
    legacy.add_argument("input", type=Path)
    legacy.add_argument(
        "--output",
        type=Path,
        help="Output CSV. Defaults to data/staging/legacy_seed.csv.",
    )

    regulatory_extract = commands.add_parser(
        "regulatory-extract",
        help="Run a deterministic PDF recipe and add candidates to the review queue.",
    )
    regulatory_extract.add_argument("--recipe", type=Path, required=True)
    regulatory_extract.add_argument("--document", type=Path, required=True)

    regulatory_list = commands.add_parser(
        "regulatory-list",
        help="List candidates in the regulatory review queue.",
    )
    regulatory_list.add_argument(
        "--status",
        choices=["pending", "approved", "rejected"],
    )

    regulatory_review = commands.add_parser(
        "regulatory-review",
        help="Approve or reject a regulatory extraction candidate.",
    )
    regulatory_review.add_argument("candidate_id")
    regulatory_review.add_argument(
        "--decision",
        choices=["approved", "rejected"],
        required=True,
    )
    regulatory_review.add_argument("--reviewer", required=True)
    regulatory_review.add_argument("--note")
    return parser


def _is_blocking_summary(config: RegistryConfig, summary: object) -> bool:
    status = getattr(summary, "status", None)
    if status in {"failed", "partial"}:
        return True
    if status == "skipped":
        source_id = getattr(summary, "source_id", "")
        source = config.sources.get(source_id, {})
        return source_is_required(source)
    return False


def _summary_rows(summaries: list) -> list[dict]:
    return [
        {
            "source_id": summary.source_id,
            "status": summary.status,
            "records_seen": summary.records_seen,
            "inserted": summary.records_inserted,
            "revised": summary.records_revised,
            "unchanged": summary.records_unchanged,
            "rejected": summary.records_rejected,
            "warnings": summary.warnings,
            "error": summary.error,
        }
        for summary in summaries
    ]


def _load_dotenv(root: Path | None) -> None:
    """Load simple KEY=VALUE entries from .env without overriding process values."""

    try:
        env_path = find_repo_root(root) / ".env"
    except ConfigurationError:
        return
    if not env_path.exists():
        return
    import os

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def _load_config(root: Path | None) -> RegistryConfig:
    return RegistryConfig.load(root)


def _initialized_db(config: RegistryConfig) -> RegistryDB:
    db = RegistryDB(config.paths.db)
    db.initialize()
    db.sync_config(config.variables, config.sources)
    return db


def _print_blockers(blockers: list[str]) -> None:
    print(
        json.dumps(
            {
                "publication_blocked": True,
                "blocker_count": len(blockers),
                "blockers": blockers,
            },
            indent=2,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _load_dotenv(args.root)
    try:
        config = _load_config(args.root)
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.command == "validate-config":
        print(
            f"Configuration valid: {len(config.variables)} variables, "
            f"{len(config.sources)} sources."
        )
        return 0

    if args.command in {"init-db", "init"}:
        pipeline = Pipeline(config)
        pipeline.initialize()
        print(f"Initialized {config.paths.db}")
        return 0

    if args.command == "run":
        pipeline = Pipeline(config)
        selected = None if args.all or not args.source else args.source
        full_selection = selected is None
        try:
            summaries = pipeline.run(
                selected,
                full_refresh=args.full_refresh,
                strict=args.strict,
            )
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(_summary_rows(summaries), indent=2))
        blocking_summaries = [
            summary for summary in summaries if _is_blocking_summary(config, summary)
        ]

        if not full_selection:
            if not args.no_export:
                print(
                    json.dumps(
                        {
                            "publication_not_attempted": True,
                            "reason": (
                                "Selective source runs are diagnostic and cannot refresh "
                                "the public release. Run --all after verification."
                            ),
                        },
                        indent=2,
                    )
                )
            return 1 if blocking_summaries else 0

        blockers = release_blockers(config, pipeline.db)
        if blockers:
            _print_blockers(blockers)
            return 1
        if blocking_summaries:
            return 1
        if args.no_export:
            print(json.dumps({"release_gate": "ready", "exported": False}, indent=2))
            return 0

        try:
            output = export_registry(config, db=pipeline.db)
            validation = validate_publication(config)
        except PublicationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "release_gate": "ready",
                    "exported_current_records": output["summary"]["current_record_count"],
                    "site_data": str(config.paths.site_data_dir),
                    "public_validation": validation,
                },
                indent=2,
            )
        )
        return 0

    if args.command in {"export", "build-site"}:
        db = _initialized_db(config)
        blockers = release_blockers(config, db)
        if blockers and not args.force:
            _print_blockers(blockers)
            return 1
        try:
            output = export_registry(config, db=db)
            validation = validate_publication(config)
        except PublicationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    **output["summary"],
                    "release_gate_bypassed": bool(blockers and args.force),
                    "public_validation": validation,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "validate-public":
        try:
            validation = validate_publication(config)
        except PublicationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps({"public_artifacts_valid": True, **validation}, indent=2))
        return 0

    if args.command == "status":
        pipeline = Pipeline(config)
        pipeline.initialize()
        db = pipeline.db
        current = db.current_records(False)
        blockers = release_blockers(config, db)
        print(
            json.dumps(
                {
                    "database": str(config.paths.db),
                    "current_records": len(current),
                    "release_ready": not blockers,
                    "release_blockers": blockers,
                    "sources": [
                        {
                            "source_id": source_id,
                            "enabled": bool(source.get("enabled")),
                            "required": source_is_required(source),
                            "publish_enabled": bool(source.get("publish_enabled")),
                            "latest_run": db.latest_run(source_id),
                            "coverage": db.coverage_rows(source_id),
                        }
                        for source_id, source in config.sources.items()
                    ],
                },
                indent=2,
            )
        )
        return 0

    if args.command == "list-sources":
        print(
            json.dumps(
                [
                    {
                        "id": source_id,
                        "name": source["name"],
                        "adapter": source["adapter"],
                        "enabled": bool(source.get("enabled")),
                        "required": source_is_required(source),
                        "publish_enabled": bool(source.get("publish_enabled")),
                        "collection_stale_after_days": source.get("collection_stale_after_days"),
                    }
                    for source_id, source in config.sources.items()
                ],
                indent=2,
            )
        )
        return 0

    if args.command == "inspect-statcan":
        if args.source not in config.sources:
            print(f"Unknown source: {args.source}", file=sys.stderr)
            return 2
        source = config.sources[args.source]
        if source.get("adapter") != "statcan_wds":
            print(f"Source {args.source} is not a Statistics Canada source", file=sys.stderr)
            return 2
        db = _initialized_db(config)
        adapter_class = get_adapter("statcan_wds")
        adapter = adapter_class(
            source,
            config.variables,
            db,
            HttpClient(config.paths.raw_dir),
        )
        metadata, artifact = adapter.inspect_product(args.product_id)
        db.register_document(artifact)
        print(json.dumps(metadata, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.command == "import-legacy":
        output = args.output or (config.paths.root / "data" / "staging" / "legacy_seed.csv")
        rows = migrate_legacy(args.input, output)
        print(json.dumps({"rows": len(rows), "output": str(output)}, indent=2))
        return 0

    queue = ReviewQueue(config.paths.review_queue)
    if args.command == "regulatory-extract":
        recipe = load_recipe(args.recipe)
        pages, document_sha256 = extract_pdf_pages(args.document)
        candidates = extract_candidates_from_pages(
            recipe,
            pages,
            document_path=str(args.document.resolve()),
            document_sha256=document_sha256,
        )
        added, unchanged = queue.add(candidates)
        print(
            json.dumps(
                {
                    "recipe_id": recipe["recipe_id"],
                    "document": str(args.document),
                    "candidates_found": len(candidates),
                    "added": added,
                    "unchanged": unchanged,
                    "queue": str(config.paths.review_queue),
                },
                indent=2,
            )
        )
        return 0

    if args.command == "regulatory-list":
        print(
            json.dumps(
                [candidate.as_dict() for candidate in queue.list(args.status)],
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "regulatory-review":
        try:
            candidate = queue.decide(
                args.candidate_id,
                decision=args.decision,
                reviewer=args.reviewer,
                note=args.note,
            )
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(candidate.as_dict(), indent=2, ensure_ascii=False))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
