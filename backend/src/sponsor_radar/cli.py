from __future__ import annotations

import argparse
import logging

import httpx

from . import db, ingest, matching, register, report

USER_AGENT = "SponsorRadar/0.1 (+https://github.com/optiplex331/SponsorRadar)"


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sponsor-radar")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply pending SQL migrations")
    sub.add_parser("seed", help="load seed sources from seeds.toml")
    sub.add_parser("register", help="snapshot the IND register when it changed")
    collect = sub.add_parser("collect", help="fetch job boards")
    collect.add_argument("--only", metavar="KIND:BOARD")
    sub.add_parser("replay", help="rebuild postings from the latest raw captures")
    sub.add_parser("match", help="link employers to the latest register snapshot")
    rep = sub.add_parser("report", help="print coverage of junior NL postings")
    rep.add_argument("--days", type=int, default=7)
    sub.add_parser("run", help="migrate, seed, register, collect, match, report")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    with db.connect() as conn, _client() as client:
        steps = ["migrate", "seed", "register", "collect", "match", "report"] if args.command == "run" else [args.command]
        for step in steps:
            if step == "migrate":
                print("migrations applied:", db.migrate(conn) or "none")
            elif step == "seed":
                print("seed sources:", ingest.load_seeds(conn))
            elif step == "register":
                snapshot_id, created = register.sync_register(conn, client)
                print(f"register snapshot {snapshot_id} ({'new' if created else 'unchanged'})")
            elif step == "collect":
                results = ingest.collect_all(conn, client, getattr(args, "only", None))
                for r in results:
                    print(f"{'ok ' if r.ok else 'ERR'} {r.source} {r.postings if r.ok else r.error}")
                print(f"sources ok: {sum(r.ok for r in results)}/{len(results)}")
            elif step == "replay":
                print("sources replayed:", ingest.replay(conn))
            elif step == "match":
                print("match status:", matching.match_sources(conn))
            elif step == "report":
                print(report.build_report(conn, getattr(args, "days", 7)))
