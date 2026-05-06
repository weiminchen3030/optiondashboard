import argparse
import logging
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from options_signal_pipeline.pipeline import (
    ETF_TICKERS,
    confirm_oi_changes,
    compute_signals,
    get_etf_holdings,
    load_signals,
    save_signals,
    fetch_options_data,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_day0():
    holdings = get_etf_holdings(ETF_TICKERS, top_n=8)
    daily_signals = []
    for etf, symbols in holdings.items():
        for symbol in symbols:
            options_df = fetch_options_data(symbol)
            if options_df is None:
                continue
            signal = compute_signals(symbol, etf, options_df)
            if signal:
                daily_signals.append(signal)

    save_signals(daily_signals, path="signals_day0.json")
    logger.info("Day-0 signal generation complete: %d signals", len(daily_signals))


def run_confirmation():
    previous_signals = load_signals("signals_day0.json")
    if not previous_signals:
        logger.info("No previous signals to confirm")
        return

    confirmed = confirm_oi_changes(previous_signals)
    save_signals(confirmed, path="signals_confirmed.json")
    logger.info("Confirmation complete: %d confirmed signals", len(confirmed))


def parse_args():
    parser = argparse.ArgumentParser(description="Options swing signal pipeline")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Run next-day confirmation on existing signals",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    logger.info("Starting options swing signal pipeline")
    if args.confirm:
        run_confirmation()
    else:
        run_day0()
    logger.info("Done")
