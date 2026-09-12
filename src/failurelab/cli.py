import argparse
import json
import logging
import signal

from failurelab.config import Settings


def main():
    parser = argparse.ArgumentParser(prog="failurelab")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Serve the API, built UI, and local worker")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    sub.add_parser("worker", help="Run a durable investigation worker")
    sub.add_parser("seed", help="Create the four owned demo incidents, idempotently")
    sub.add_parser("doctor", help="Check local configuration and runtime dependencies")
    evaluation = sub.add_parser("evaluate", help="Run the authored regression benchmark")
    evaluation.add_argument(
        "--model",
        action="store_true",
        help="Use configured inference provider; consumes model tokens",
    )
    evaluation.add_argument("--min-accuracy", type=float, default=0.8)
    args = parser.parse_args()
    settings = Settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if args.command == "serve":
        import uvicorn

        from failurelab.api import create_app

        settings = Settings(
            **{
                **settings.model_dump(),
                **({"host": args.host} if args.host else {}),
                **({"port": args.port} if args.port else {}),
            }
        )
        uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
    elif args.command == "evaluate":
        from failurelab.evaluation import evaluate

        if args.model and settings.model_mode != "chat":
            parser.error("--model requires FAILURELAB_MODEL_MODE=chat")
        result = evaluate(settings, use_model=args.model)
        print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))
        if any(v["top1_accuracy"] < args.min_accuracy for v in result["variants"]):
            raise SystemExit(1)
    elif args.command == "doctor":
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            print(f"Chromium {browser.version}: OK")
            browser.close()
        print(f"Model mode: {settings.model_mode}")
        print(f"Retrieval: {settings.retrieval_mode}")
        print(f"Allowed repositories: {len(settings.allowed_repositories)}")
        print(
            f"Remote runner: {'configured' if settings.runner_url else 'not configured; owned fixtures only'}"
        )
        print(f"Database: {'PostgreSQL' if settings.database_url else 'local SQLite'}")
    else:
        from failurelab.fixtures import seed
        from failurelab.store import Store
        from failurelab.workflow import Worker

        store = Store(settings)
        if args.command == "seed":
            seed(store)
            print("Owned fixtures created (existing fixture IDs preserved).")
        else:
            worker = Worker(settings, store)
            signal.signal(signal.SIGINT, lambda *_: worker.stop_event.set())
            signal.signal(signal.SIGTERM, lambda *_: worker.stop_event.set())
            worker.loop()
        store.close()


if __name__ == "__main__":
    main()
