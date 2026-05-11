import csv
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from langchain_core.prompts import ChatPromptTemplate
except ImportError:
    ChatPromptTemplate = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

from aiagent.blockchain.ethereum_client import EthereumClient
from aiagent.blockchain.metrics_builder import (
    build_ethereum_metrics_report,
    build_rolling_ethereum_metric_reports,
    metrics_report_to_csv_row,
)
from aiagent.blockchain.mock_chain import get_mock_chain_metrics
from aiagent.blockchain.schemas import EthereumBlockRecord, MetricsBuildResult
from aiagent.detectors.csv_loader import load_metrics_samples_from_csv
from aiagent.detectors.evaluation import evaluate_detection_results
from aiagent.detectors.isolation_forest_detector import (
    fit_isolation_forest,
    score_metrics_with_isolation_forest,
    score_samples_with_isolation_forest,
)
from aiagent.detectors.schemas import FEATURE_NAMES
from aiagent.detectors.simple_anomaly import simple_consensus_anomaly_detector
from aiagent.detectors.training import (
    fit_statistical_baseline,
    generate_mock_training_samples,
    get_training_recommendations,
    score_with_statistical_baseline,
)
from aiagent.env_utils import get_openai_api_key

DEFAULT_ETH_BLOCK_WINDOW = 100
DEFAULT_ETH_WINDOW_STEP = 50
DEFAULT_ETH_DATASET_PATH = "data/eth_metrics_latest.csv"
DEFAULT_MOCK_DATASET_PATH = "data/mock_metrics.csv"
MIN_ETH_BLOCKS_FOR_METRICS = 2
OUTPUTS_DIR = "outputs"

ETH_TELEMETRY_WARNINGS = [
    "hashrate_concentration_top1/top3 are proposer / fee-recipient concentration proxies on Ethereum post-Merge, not PoW hashrate.",
    "miner_entropy is entropy over proposer / fee-recipient addresses on Ethereum post-Merge.",
    "fork_rate, orphan_rate, and reorg_depth_max are placeholders for canonical RPC-only telemetry.",
]
ETH_LLM_INTERPRETATION_INSTRUCTIONS = (
    "Ethereum interpretation instructions:\n"
    "- Do not interpret hashrate_concentration_top1/top3 as PoW hashrate.\n"
    "- Do not call fee recipients miners in Ethereum post-Merge analysis.\n"
    "- Describe hashrate_concentration_top1/top3 as proposer / fee-recipient concentration proxies.\n"
    "- Describe miner_entropy as entropy over proposer / fee-recipient addresses.\n"
    "- Explain that fork_rate, orphan_rate, and reorg_depth_max are placeholders under canonical JSON-RPC.\n"
)
NEXT_ETH_TELEMETRY_SOURCES = [
    "Beacon-chain proposer and validator telemetry",
    "P2P block propagation and peer-level latency measurements",
    "Mempool and transaction propagation telemetry",
    "MEV relay / builder delivery telemetry",
    "Archive-node history and explicit reorg tracking",
    "Client or node logs for fork-choice and networking events",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_timestamp_slug() -> str:
    return _utc_now().strftime("%Y%m%d_%H%M%S_%f")


def _ensure_parent_dir(file_path: str) -> None:
    parent = os.path.dirname(file_path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _write_json(file_path: str, payload: Any) -> None:
    _ensure_parent_dir(file_path)
    with open(file_path, "w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, indent=2)


def _write_text(file_path: str, text: str) -> None:
    _ensure_parent_dir(file_path)
    with open(file_path, "w", encoding="utf-8") as output_file:
        output_file.write(text)


def _parse_positive_int(raw_value: str, argument_name: str) -> int:
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{argument_name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{argument_name} must be positive.")
    return value


def _parse_positive_int_at_least(
    raw_value: str,
    argument_name: str,
    minimum_value: int,
) -> int:
    value = _parse_positive_int(raw_value, argument_name)
    if value < minimum_value:
        raise ValueError(f"{argument_name} must be at least {minimum_value}.")
    return value


def _validate_eth_n_blocks(n_blocks: int) -> None:
    if n_blocks < MIN_ETH_BLOCKS_FOR_METRICS:
        raise ValueError(
            f"n_blocks must be at least {MIN_ETH_BLOCKS_FOR_METRICS} for Ethereum metrics analysis."
        )


def _format_artifact_summary(artifact_paths: Dict[str, str]) -> str:
    return (
        "Artifacts saved:\n"
        f"- {artifact_paths['blocks']}\n"
        f"- {artifact_paths['metrics']}\n"
        f"- {artifact_paths['detection']}\n"
        f"- {artifact_paths['report']}\n"
        f"- {artifact_paths['latest_index']}"
    )


def _format_utc_timestamp(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _detector_label_from_result(result: Dict[str, Any]) -> str:
    prediction = result.get("prediction")
    if isinstance(prediction, str):
        return prediction
    if result.get("flags"):
        return "anomalous"
    if float(result.get("anomaly_score", 0.0)) >= 0.5:
        return "anomalous"
    return "normal_like"


def _summarize_detector_result(result: Dict[str, Any]) -> Tuple[str, float]:
    label = _detector_label_from_result(result)
    score = float(result.get("anomaly_score", 0.0))
    return label, score


def _latest_eth_run_index_path() -> str:
    return os.path.join(OUTPUTS_DIR, "latest_eth_run.json")


def _update_latest_eth_run_index(
    requested_n_blocks: int,
    metrics_report: MetricsBuildResult,
    detector_result: Dict[str, Any],
    artifact_paths: Dict[str, str],
    warnings: Sequence[str],
) -> str:
    latest_index_path = _latest_eth_run_index_path()
    latest_payload = {
        "chain": metrics_report.chain,
        "n_blocks": requested_n_blocks,
        "start_block": metrics_report.start_block,
        "end_block": metrics_report.end_block,
        "timestamp": _utc_now().isoformat(),
        "detector": detector_result.get("detector"),
        "detector_label": detector_result.get("detector_label"),
        "anomaly_score": detector_result.get("anomaly_score"),
        "warnings": list(warnings),
        "artifacts": dict(artifact_paths),
    }
    _write_json(latest_index_path, latest_payload)
    return latest_index_path


def _save_real_chain_artifacts(
    prefix: str,
    requested_n_blocks: int,
    blocks: Sequence[EthereumBlockRecord],
    metrics_report: MetricsBuildResult,
    detector_result: Dict[str, Any],
    report_markdown: str,
    warnings: Sequence[str],
) -> Dict[str, str]:
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    stamp = _utc_timestamp_slug()

    artifact_paths = {
        "blocks": os.path.join(OUTPUTS_DIR, f"{prefix}_blocks_{stamp}.json"),
        "metrics": os.path.join(OUTPUTS_DIR, f"{prefix}_metrics_{stamp}.json"),
        "detection": os.path.join(OUTPUTS_DIR, f"{prefix}_detection_{stamp}.json"),
        "report": os.path.join(OUTPUTS_DIR, f"{prefix}_report_{stamp}.md"),
    }

    _write_json(artifact_paths["blocks"], [block.to_dict() for block in blocks])
    _write_json(artifact_paths["metrics"], metrics_report.to_dict())
    _write_json(artifact_paths["detection"], detector_result)
    _write_text(artifact_paths["report"], report_markdown)

    latest_index_path = _update_latest_eth_run_index(
        requested_n_blocks=requested_n_blocks,
        metrics_report=metrics_report,
        detector_result=detector_result,
        artifact_paths=artifact_paths,
        warnings=warnings,
    )
    artifact_paths["latest_index"] = latest_index_path
    return artifact_paths


def _build_eth_chain_analysis_prompt(
    metrics_report: MetricsBuildResult,
    detector_result: Dict[str, Any],
) -> str:
    metrics_json = json.dumps(metrics_report.to_dict(), indent=2)
    detector_json = json.dumps(detector_result, indent=2)

    return (
        "We executed a real-chain Ethereum canonical RPC telemetry pipeline.\n\n"
        "Pipeline steps:\n"
        "1. Fetch a recent canonical block window using Ethereum JSON-RPC.\n"
        "2. Derive detector-compatible consensus-like metrics from the block window.\n"
        "3. Run a simple rule-based anomaly detector on those metrics.\n\n"
        f"{ETH_LLM_INTERPRETATION_INSTRUCTIONS}\n"
        f"Metrics report (JSON):\n{metrics_json}\n\n"
        f"Detector result (JSON):\n{detector_json}\n\n"
        "Please do the following:\n"
        "1. Explain the current consensus and proposer health of the chain window.\n"
        "2. Interpret whether the anomaly score is concerning and why.\n"
        "3. Explicitly separate directly observed metrics, proxy metrics, and unavailable placeholder metrics.\n"
        "4. Discuss block timing variability and proposer concentration proxy findings.\n"
        "5. If helpful, use transaction and gas activity context from the activity summary.\n"
        "6. State the limits of canonical RPC visibility, including forks, orphan blocks, mempool, propagation, and network latency.\n"
        "7. Recommend the next telemetry sources needed for stronger blockchain-security conclusions, such as beacon-chain APIs, p2p telemetry, MEV relay data, or archive-node history.\n"
        "Do not overclaim. If a conclusion depends on proxy or placeholder metrics, say that clearly."
    )


def _build_eth_detector_analysis_prompt(
    metrics_report: MetricsBuildResult,
    rule_detection: Dict[str, Any],
    ml_detection: Dict[str, Any],
    training_dataset_path: str,
    dataset_warning: Optional[str],
) -> str:
    metrics_json = json.dumps(metrics_report.to_dict(), indent=2)
    rule_detection_json = json.dumps(rule_detection, indent=2)
    ml_detection_json = json.dumps(ml_detection, indent=2)
    warning_text = dataset_warning or "No dataset warning."

    return (
        "We executed a real-chain Ethereum anomaly-detection workflow using both a rule-based baseline and Isolation Forest.\n\n"
        "Pipeline steps:\n"
        f"1. Fetch recent canonical Ethereum blocks and derive the current metric window.\n"
        f"2. Load training samples from {training_dataset_path}.\n"
        "3. Fit an Isolation Forest model and score the current Ethereum metric window.\n"
        "4. Also run the simple rule-based detector for comparison.\n\n"
        f"{ETH_LLM_INTERPRETATION_INSTRUCTIONS}\n"
        f"Metrics report (JSON):\n{metrics_json}\n\n"
        f"Rule-based detector result (JSON):\n{rule_detection_json}\n\n"
        f"Isolation Forest result (JSON):\n{ml_detection_json}\n\n"
        f"Dataset warning:\n{warning_text}\n\n"
        "Please do the following:\n"
        "1. Interpret the ML detector result in blockchain-security terms.\n"
        "2. Compare the ML score to the rule-based result.\n"
        "3. Explain the reliability limits when the training data may not match real Ethereum telemetry.\n"
        "4. Explicitly separate observed metrics, proxy metrics, and unavailable placeholder metrics.\n"
        "5. Recommend how to collect a stronger real-chain baseline dataset for future detector training.\n"
        "Do not overclaim. Treat canonical RPC-only visibility as limited."
    )


def _build_llm_error_report(error: Exception) -> str:
    return (
        "# LLM Report Unavailable\n\n"
        f"The analysis pipeline completed, but the LLM explanation failed: {error}\n\n"
        "You can still review the saved JSON artifacts or rerun the command in dry-run mode."
    )


def _fetch_recent_eth_blocks(n_blocks: int) -> List[EthereumBlockRecord]:
    client = EthereumClient.from_env()
    return client.get_recent_blocks(n=n_blocks)


def _fetch_recent_eth_window(n_blocks: int) -> Tuple[List[EthereumBlockRecord], List[str]]:
    _validate_eth_n_blocks(n_blocks)
    blocks = _fetch_recent_eth_blocks(n_blocks)
    warnings: List[str] = []
    if len(blocks) < n_blocks:
        warnings.append(
            f"Requested {n_blocks} blocks, but only {len(blocks)} canonical blocks were returned."
        )
    return blocks, warnings


def _format_metric_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _build_metric_lines(
    metrics_report: MetricsBuildResult,
    reliability: str,
) -> List[str]:
    lines: List[str] = []
    for feature_name in FEATURE_NAMES:
        detail = metrics_report.metric_details[feature_name]
        if detail.reliability != reliability:
            continue
        lines.append(
            f"- `{feature_name}`: {_format_metric_value(detail.value)}"
            f" ({detail.method})"
        )
        lines.append(f"  - {detail.note}")
    if not lines:
        lines.append("- None.")
    return lines


def _build_activity_summary_lines(metrics_report: MetricsBuildResult) -> List[str]:
    lines: List[str] = []
    for name, value in sorted(metrics_report.activity_summary.items()):
        lines.append(f"- `{name}`: {_format_metric_value(value)}")
    return lines or ["- None."]


def _build_dry_run_markdown_report(
    requested_n_blocks: int,
    metrics_report: MetricsBuildResult,
    detector_result: Dict[str, Any],
    warnings: Sequence[str],
) -> str:
    detector_payload = detector_result["result"]
    flag_lines = [
        f"- {_format_eth_detector_flag(flag)}" for flag in detector_payload.get("flags", [])
    ] or ["- None."]
    warning_lines = [f"- {warning}" for warning in warnings] or ["- None."]
    note_lines = [f"- {note}" for note in metrics_report.notes] or ["- None."]
    telemetry_lines = [f"- {item}" for item in NEXT_ETH_TELEMETRY_SOURCES]

    lines = [
        "# Ethereum Dry-Run Report",
        "",
        "## Run Summary",
        f"- Generated at: {_utc_now().isoformat()}",
        f"- Chain: {metrics_report.chain}",
        f"- Source: {metrics_report.source}",
        f"- Requested blocks: {requested_n_blocks}",
        f"- Returned blocks: {metrics_report.block_count}",
        f"- Block range: {metrics_report.start_block} - {metrics_report.end_block}",
        f"- Time range: {_format_utc_timestamp(metrics_report.start_timestamp)} to {_format_utc_timestamp(metrics_report.end_timestamp)}",
        "",
        "## Detector Result",
        f"- Detector: {detector_result['detector']}",
        f"- Label: {detector_result['detector_label']}",
        f"- Anomaly score: {detector_result['anomaly_score']:.6f}",
        f"- Summary: {detector_payload.get('summary', 'No summary provided.')}",
        "- Flags:",
        *flag_lines,
        "",
        "## Observed Metrics",
        * _build_metric_lines(metrics_report, "observed"),
        "",
        "## Proxy Metrics",
        *_build_metric_lines(metrics_report, "proxy"),
        "",
        "## Unavailable Placeholder Metrics",
        *_build_metric_lines(metrics_report, "placeholder"),
        "",
        "## Activity Summary",
        *_build_activity_summary_lines(metrics_report),
        "",
        "## Warnings",
        *warning_lines,
        "",
        "## Metric Interpretation Notes",
        *note_lines,
        "",
        "## Recommended Next Telemetry Sources",
        *telemetry_lines,
        "",
    ]
    return "\n".join(lines)


def _format_eth_detector_flag(flag: str) -> str:
    if flag == "hashrate highly concentrated in top miner":
        return "proposer / fee-recipient concentration proxy is high"
    return flag


def _format_eth_detector_result(detection: Dict[str, Any]) -> Dict[str, Any]:
    formatted = dict(detection)
    formatted["flags"] = [
        _format_eth_detector_flag(flag) for flag in detection.get("flags", [])
    ]
    summary = formatted.get("summary")
    if isinstance(summary, str):
        formatted["summary"] = summary.replace(
            "hashrate highly concentrated in top miner",
            "proposer / fee-recipient concentration proxy is high",
        )
    return formatted


def _choose_eth_training_dataset(csv_path: Optional[str] = None) -> Tuple[str, Optional[str]]:
    if csv_path:
        return csv_path, None

    if os.path.exists(DEFAULT_ETH_DATASET_PATH):
        return DEFAULT_ETH_DATASET_PATH, None

    return (
        DEFAULT_MOCK_DATASET_PATH,
        "No real Ethereum CSV baseline was found, so the detector used data/mock_metrics.csv. "
        "This is a distribution mismatch and is only a demonstration baseline, not a valid real-chain normal model.",
    )


def _get_llm(llm):
    if llm is not None:
        return llm
    get_openai_api_key()
    if ChatOpenAI is None:
        raise RuntimeError(
            "langchain-openai is not installed. Run `pip install -r requirements.txt` "
            "to enable research-mode LLM analysis."
        )
    return ChatOpenAI(model="gpt-4o-mini")


def _run_mock_chain_command(llm) -> str:
    metrics = get_mock_chain_metrics.invoke({"chain": "mockchain"})
    detection = simple_consensus_anomaly_detector.invoke({"metrics": metrics})

    analysis_input = (
        "We just executed a mock blockchain monitoring pipeline that "
        "(1) fetched consensus-level metrics and (2) applied a simple "
        "rule-based anomaly detector.\n\n"
        f"Raw metrics (JSON):\n{json.dumps(metrics, indent=2)}\n\n"
        f"Detector output (JSON):\n{json.dumps(detection, indent=2)}\n\n"
        "Please do the following:\n"
        "1. Summarize what the metrics and detector output suggest about the chain's security state.\n"
        "2. Hypothesize what type(s) of consensus attack, if any, these indicators might be consistent with.\n"
        "3. Suggest at least three follow-up metrics or checks you would add in a real system.\n"
    )
    return llm.invoke(analysis_input).content


def _run_train_mock_detector_command(llm) -> str:
    samples = generate_mock_training_samples(sample_count=120)
    baseline = fit_statistical_baseline(samples)
    metrics = get_mock_chain_metrics.invoke({"chain": "mockchain"})
    baseline_detection = score_with_statistical_baseline(metrics, baseline)
    recommendations = get_training_recommendations()

    analysis_input = (
        "We just executed a mock detector training and scoring pipeline.\n\n"
        "Pipeline steps:\n"
        "1. Generate labeled mock training samples with both normal and abnormal windows.\n"
        "2. Fit a statistical baseline using only normal samples.\n"
        "3. Score the current mock chain metrics against the fitted baseline.\n"
        "4. Review training recommendations for a real detector.\n\n"
        f"Fitted baseline (JSON):\n{json.dumps(baseline, indent=2)}\n\n"
        f"Current metrics (JSON):\n{json.dumps(metrics, indent=2)}\n\n"
        f"Baseline scoring result (JSON):\n{json.dumps(baseline_detection, indent=2)}\n\n"
        f"Training recommendations (JSON):\n{json.dumps(recommendations, indent=2)}\n\n"
        "Please do the following:\n"
        "1. Explain what the fitted baseline and scoring result tell us.\n"
        "2. Explain why a statistical baseline is useful as an initial detector in blockchain security monitoring.\n"
        "3. Summarize the most important next steps for building a stronger ML detector.\n"
    )
    return llm.invoke(analysis_input).content


def _run_csv_detector_command(llm, csv_path: str) -> str:
    samples = load_metrics_samples_from_csv(csv_path)
    model = fit_isolation_forest(samples, contamination=0.3)
    batch_results = score_samples_with_isolation_forest(samples, model)
    evaluation = evaluate_detection_results(batch_results)
    current_metrics = get_mock_chain_metrics.invoke({"chain": "mockchain"})
    current_result = score_metrics_with_isolation_forest(current_metrics, model)

    analysis_input = (
        "We just executed a CSV-based anomaly detection workflow using Isolation Forest.\n\n"
        "Pipeline steps:\n"
        f"1. Load labeled consensus-metric windows from {csv_path}.\n"
        "2. Train an Isolation Forest model, prioritizing normal samples when available.\n"
        "3. Score the CSV samples and also score the current mock chain metrics.\n"
        "4. Compute basic evaluation statistics over the CSV predictions.\n\n"
        f"Sample scoring preview (JSON):\n{json.dumps(batch_results[:5], indent=2)}\n\n"
        f"Evaluation summary (JSON):\n{json.dumps(evaluation, indent=2)}\n\n"
        f"Current mock chain metrics (JSON):\n{json.dumps(current_metrics, indent=2)}\n\n"
        f"Current mock chain Isolation Forest result (JSON):\n{json.dumps(current_result, indent=2)}\n\n"
        "Please do the following:\n"
        "1. Explain what the CSV-trained detector appears to learn from the samples.\n"
        "2. Interpret the evaluation summary, especially the per-label detection rates.\n"
        "3. Interpret the current mock chain result in blockchain-security terms.\n"
        "4. Explain the limitations of this small dataset and how to improve it for real research use.\n"
    )
    return llm.invoke(analysis_input).content


def _build_rule_based_eth_detector_result(
    detection: Dict[str, Any],
    warnings: Sequence[str],
) -> Dict[str, Any]:
    label, score = _summarize_detector_result(detection)
    return {
        "detector": "simple_rule_based",
        "detector_label": label,
        "anomaly_score": score,
        "result": _format_eth_detector_result(detection),
        "telemetry_warnings": list(ETH_TELEMETRY_WARNINGS),
        "fetch_warnings": list(warnings),
    }


def _run_analyze_eth_chain_command(
    llm,
    n_blocks: int,
    use_llm: bool = True,
) -> str:
    blocks, warnings = _fetch_recent_eth_window(n_blocks)
    metrics_report = build_ethereum_metrics_report(blocks)
    detection = simple_consensus_anomaly_detector.invoke({"metrics": metrics_report.metrics})
    detector_result = _build_rule_based_eth_detector_result(detection, warnings)

    if use_llm:
        try:
            report_markdown = llm.invoke(
                _build_eth_chain_analysis_prompt(metrics_report, detector_result)
            ).content
        except Exception as exc:
            report_markdown = _build_llm_error_report(exc)
    else:
        report_markdown = _build_dry_run_markdown_report(
            requested_n_blocks=n_blocks,
            metrics_report=metrics_report,
            detector_result=detector_result,
            warnings=warnings,
        )

    artifact_paths = _save_real_chain_artifacts(
        "eth",
        requested_n_blocks=n_blocks,
        blocks=blocks,
        metrics_report=metrics_report,
        detector_result=detector_result,
        report_markdown=report_markdown,
        warnings=warnings,
    )
    return f"{report_markdown}\n\n{_format_artifact_summary(artifact_paths)}"


def _run_analyze_eth_detector_command(
    llm,
    n_blocks: int,
    csv_path: Optional[str] = None,
) -> str:
    blocks, warnings = _fetch_recent_eth_window(n_blocks)
    metrics_report = build_ethereum_metrics_report(blocks)
    rule_detection = _format_eth_detector_result(
        simple_consensus_anomaly_detector.invoke({"metrics": metrics_report.metrics})
    )

    training_dataset_path, dataset_warning = _choose_eth_training_dataset(csv_path)
    training_samples = load_metrics_samples_from_csv(training_dataset_path)
    model = fit_isolation_forest(training_samples, contamination=0.3)
    ml_detection = score_metrics_with_isolation_forest(metrics_report.metrics, model)
    detector_label, anomaly_score = _summarize_detector_result(ml_detection)

    detector_result = {
        "detector": "isolation_forest",
        "detector_label": detector_label,
        "anomaly_score": anomaly_score,
        "training_dataset_path": training_dataset_path,
        "training_dataset_warning": dataset_warning,
        "rule_based_result": rule_detection,
        "ml_result": ml_detection,
        "telemetry_warnings": list(ETH_TELEMETRY_WARNINGS),
        "fetch_warnings": list(warnings),
    }

    try:
        report_markdown = llm.invoke(
            _build_eth_detector_analysis_prompt(
                metrics_report,
                rule_detection,
                ml_detection,
                training_dataset_path,
                dataset_warning,
            )
        ).content
    except Exception as exc:
        report_markdown = _build_llm_error_report(exc)

    artifact_paths = _save_real_chain_artifacts(
        "eth",
        requested_n_blocks=n_blocks,
        blocks=blocks,
        metrics_report=metrics_report,
        detector_result=detector_result,
        report_markdown=report_markdown,
        warnings=warnings,
    )
    warning_block = f"\nDataset warning: {dataset_warning}\n" if dataset_warning else "\n"
    return f"{report_markdown}{warning_block}\n{_format_artifact_summary(artifact_paths)}"


def collect_eth_metrics_to_csv(
    n_blocks: int,
    output_csv_path: str,
    window_size: int = DEFAULT_ETH_BLOCK_WINDOW,
    step_size: Optional[int] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Fetch recent Ethereum blocks, build rolling metrics, and write them to CSV."""
    _validate_eth_n_blocks(n_blocks)
    if window_size < MIN_ETH_BLOCKS_FOR_METRICS:
        raise ValueError(
            f"window_size must be at least {MIN_ETH_BLOCKS_FOR_METRICS}."
        )
    if step_size is not None and step_size <= 0:
        raise ValueError("step_size must be positive.")
    if os.path.exists(output_csv_path) and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing CSV file: {output_csv_path}"
        )

    recent_blocks, warnings = _fetch_recent_eth_window(n_blocks)
    effective_window_size = max(
        MIN_ETH_BLOCKS_FOR_METRICS,
        min(window_size, len(recent_blocks)),
    )
    effective_step_size = step_size or max(1, effective_window_size // 2)
    reports = build_rolling_ethereum_metric_reports(
        recent_blocks,
        window_size=effective_window_size,
        step=effective_step_size,
    )

    rows = [metrics_report_to_csv_row(report) for report in reports]
    fieldnames = list(FEATURE_NAMES) + [
        "chain",
        "start_block",
        "end_block",
        "start_timestamp",
        "end_timestamp",
        "source",
        "metric_notes",
    ]

    _ensure_parent_dir(output_csv_path)
    with open(output_csv_path, "w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "output_csv_path": output_csv_path,
        "rows_written": len(rows),
        "blocks_fetched": len(recent_blocks),
        "window_size": effective_window_size,
        "step_size": effective_step_size,
        "overwrite_mode": "overwrite" if overwrite else "refuse_if_exists",
        "warnings": warnings,
    }


def _parse_eth_chain_command_args(command_text: str) -> Tuple[int, bool]:
    tokens = command_text.split()[3:]
    n_blocks = DEFAULT_ETH_BLOCK_WINDOW
    use_llm = True

    for token in tokens:
        normalized = token.lower()
        if normalized in {"dryrun", "--no-llm"}:
            use_llm = False
            continue
        n_blocks = _parse_positive_int_at_least(
            token,
            "n_blocks",
            MIN_ETH_BLOCKS_FOR_METRICS,
        )

    return n_blocks, use_llm


def _print_banner() -> None:
    print("=== ChainGuardian Research CLI Chat (LangChain) ===")
    print("Type 'exit' or 'quit' to leave the chat.")
    print("Type 'analyze mock chain' to run the mock metrics + anomaly detection pipeline.")
    print("Type 'train mock detector' to fit a statistical baseline on mock samples and score the current mock chain.")
    print("Type 'analyze csv detector' to train an Isolation Forest on data/mock_metrics.csv and explain the results.")
    print("Type 'analyze csv detector <path-to-csv>' to use a custom training dataset.")
    print("Type 'analyze eth chain' or 'analyze eth chain <n_blocks>' to analyze recent Ethereum telemetry.")
    print("Type 'analyze eth chain dryrun <n_blocks>' or 'analyze eth chain --no-llm <n_blocks>' for a deterministic local report.")
    print("Type 'analyze eth detector' to score real Ethereum telemetry with Isolation Forest.")
    print("Type 'collect eth metrics <n_blocks> <output_csv_path>' to build a reusable Ethereum metrics CSV.")
    print("Type 'analyze real chain' as an alias for Ethereum for now.\n")


def run_cli_research_chat() -> None:
    base_prompt = None
    if ChatPromptTemplate is not None:
        base_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an AI research assistant specialized in blockchain security, "
                    "consensus attacks, anomaly detection, and telemetry design. "
                    "Be clear and rigorous. Explicitly distinguish directly observed metrics, "
                    "proxy metrics, unavailable metrics, detector assumptions, and what extra "
                    "telemetry would be required before making stronger security claims.",
                ),
                ("human", "{input}"),
            ]
        )

    _print_banner()

    history: List[str] = []
    llm = None

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("AI: Bye~")
            break

        history.append(f"User: {user_input}")

        try:
            if user_input.lower().startswith("analyze mock chain"):
                llm = _get_llm(llm)
                content = _run_mock_chain_command(llm)
            elif user_input.lower().startswith("train mock detector"):
                llm = _get_llm(llm)
                content = _run_train_mock_detector_command(llm)
            elif user_input.lower().startswith("analyze csv detector"):
                llm = _get_llm(llm)
                command_parts = user_input.split(maxsplit=3)
                csv_path = command_parts[3] if len(command_parts) == 4 else DEFAULT_MOCK_DATASET_PATH
                content = _run_csv_detector_command(llm, csv_path)
            elif user_input.lower().startswith("analyze eth chain"):
                n_blocks, use_llm = _parse_eth_chain_command_args(user_input)
                if use_llm:
                    llm = _get_llm(llm)
                content = _run_analyze_eth_chain_command(llm, n_blocks, use_llm=use_llm)
            elif user_input.lower().startswith("analyze eth detector"):
                llm = _get_llm(llm)
                command_parts = user_input.split(maxsplit=3)
                csv_path = command_parts[3] if len(command_parts) == 4 else None
                content = _run_analyze_eth_detector_command(
                    llm,
                    DEFAULT_ETH_BLOCK_WINDOW,
                    csv_path=csv_path,
                )
            elif user_input.lower().startswith("collect eth metrics"):
                command_parts = user_input.split(maxsplit=4)
                if len(command_parts) != 5:
                    raise ValueError(
                        "Usage: collect eth metrics <n_blocks> <output_csv_path>"
                    )
                n_blocks = _parse_positive_int_at_least(
                    command_parts[3],
                    "n_blocks",
                    MIN_ETH_BLOCKS_FOR_METRICS,
                )
                output_csv_path = command_parts[4]
                collection_result = collect_eth_metrics_to_csv(n_blocks, output_csv_path)
                warning_text = ""
                if collection_result["warnings"]:
                    warning_text = "\nWarnings:\n- " + "\n- ".join(collection_result["warnings"])
                content = (
                    "Ethereum metrics collected successfully.\n"
                    f"Blocks fetched: {collection_result['blocks_fetched']}\n"
                    f"Rows written: {collection_result['rows_written']}\n"
                    f"Window size: {collection_result['window_size']}\n"
                    f"Step size: {collection_result['step_size']}\n"
                    f"Overwrite mode: {collection_result['overwrite_mode']}\n"
                    f"CSV path: {collection_result['output_csv_path']}"
                    f"{warning_text}"
                )
            elif user_input.lower().startswith("analyze real chain"):
                n_blocks, use_llm = _parse_eth_chain_command_args(
                    user_input.replace("analyze real chain", "analyze eth chain", 1)
                )
                if use_llm:
                    llm = _get_llm(llm)
                content = _run_analyze_eth_chain_command(llm, n_blocks, use_llm=use_llm)
            else:
                llm = _get_llm(llm)
                if base_prompt is not None:
                    chain = base_prompt | llm
                    content = chain.invoke({"input": user_input}).content
                else:
                    content = llm.invoke(user_input).content
        except Exception as exc:
            print(f"[Error] {exc}")
            continue

        print(f"AI: {content}\n")
        history.append(f"AI: {content}")
