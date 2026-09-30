"""Desktop entry point; --smoke-test validates Tk without leaving a window open."""

import sys


if __name__ == "__main__":
    if "--diagnose-url" in sys.argv:
        import argparse
        import json
        from pathlib import Path
        from downloader.engine import DownloadEngine
        from downloader.models import DownloadRequest, PROFILE_BY_ID

        parser = argparse.ArgumentParser(description="Run one diagnostic download and save a JSON report.")
        parser.add_argument("--diagnose-url", required=True)
        parser.add_argument("--output-dir", type=Path, required=True)
        parser.add_argument("--report", type=Path, required=True)
        parser.add_argument("--profile", choices=tuple(PROFILE_BY_ID), default="best")
        parser.add_argument("--cookies", default="", help="選用的 cookies.txt 完整路徑")
        args = parser.parse_args()
        events = []
        error = None
        try:
            DownloadEngine(events.append).run(DownloadRequest(args.diagnose_url, args.output_dir, args.profile, args.cookies))
        except Exception as exc:
            error = str(exc)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"success": error is None, "error": error, "events": events},
                                         ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(1 if error else 0)
    elif "--smoke-test" in sys.argv:
        from downloader.gui import smoke_test
        smoke_test()
    else:
        from downloader.gui import main
        main()