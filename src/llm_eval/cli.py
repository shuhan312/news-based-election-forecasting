"""Command line: python -m llm_eval {run,audit,estimate} --config FILE

    run       every stage; writes report.md and results.json
    audit     load and audit the reference labels only (free)
    estimate  the cost an API run would have (free: token counting only)

An API key is needed only for `estimate`, and for `run` when
predictions.source = "api". It is read from the environment or a .env file,
never from the config.
"""

from __future__ import annotations

import argparse
import json
import sys

from llm_eval import pipeline, report


def _client():
    import anthropic
    from dotenv import load_dotenv
    load_dotenv()
    return anthropic.Anthropic()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llm_eval")
    parser.add_argument("command", choices=["run", "audit", "estimate"])
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    cfg = pipeline.load_config(args.config)

    if args.command == "audit":
        result = pipeline.audit.run_audit(
            pipeline.load_examples(cfg),
            stratum_field=cfg.get("audit", {}).get("stratum_field"),
            allowed_prefixes=cfg.get("audit", {}).get("allowed_prefixes"),
            drift_within=cfg.get("audit", {}).get("drift_within"),
            classifier_is_llm=cfg["task"].get("classifier_is_llm", True))
        print(json.dumps(result, indent=2))
        return 0 if result["clean"] else 1

    if args.command == "estimate":
        examples = pipeline.select_split(cfg, pipeline.load_examples(cfg))
        print(json.dumps(pipeline.estimate_cost(cfg, examples,
                                                client=_client()), indent=2))
        return 0

    # Multiclass tasks score archived pairs and have no predictions block.
    needs_api = cfg.get("predictions", {}).get("source") == "api"
    result = pipeline.run_pipeline(cfg, client=_client() if needs_api else None)
    md, js = report.write(result, cfg["output"]["dir"])
    print(f"-> {md}\n-> {js}")
    gate = result.get("gate")
    return 0 if gate is None or gate["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
