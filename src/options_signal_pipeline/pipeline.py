import json
import logging
import re
from datetime import datetime
from io import StringIO
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

ETF_TICKERS = ["XLK", "XLE", "SMH", "XLF", "XLY", "XLI", "XLP", "XLV", "XLB", "XLU"]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

ETF_SSGA_TICKERS = {
    "xlk", "xle", "xlf", "xly", "xli", "xlp", "xlv", "xlb", "xlu"
}


def _normalize_company_name(name: str) -> str:
    cleaned = re.sub(r"\b(class|cl|corp|co|inc|corporation|company|shares|ordinary|preferred|pref|ser|series|class a|class b)\b", "", name, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", cleaned)
    return " ".join(cleaned.split()).strip()


def _score_yahoo_quote(quote: dict, query: str) -> int:
    symbol = quote.get("symbol", "")
    shortname = str(quote.get("shortname", "")).lower()
    longname = str(quote.get("longname", "")).lower()
    exchange = quote.get("exchange", "")
    query_lower = query.lower()

    score = 0
    if query_lower in shortname or query_lower in longname:
        score += 5
    if shortname in query_lower or longname in query_lower:
        score += 3
    if exchange in {"NMS", "NYQ", "NGM", "BATS"}:
        score += 2
    if "." not in symbol:
        score += 2
    if "preferred" in longname or "preferred" in shortname or "depositary" in longname or "depositary" in shortname or "perp" in longname or "perp" in shortname:
        score -= 6
    if "-" in symbol:
        score -= 2
        if re.search(r"-[A-Z]{1,3}$", symbol):
            score -= 1
    if not symbol.isupper() and not re.match(r"^[A-Z0-9\-\.]+$", symbol):
        score -= 2
    if shortname.lower() == query.lower() or longname.lower() == query.lower():
        score += 3
    return score


def resolve_symbol_from_name(name: str) -> Optional[str]:
    try:
        search_url = "https://query1.finance.yahoo.com/v1/finance/search"
        normalized_name = _normalize_company_name(name)
        fallback_query = " ".join(normalized_name.split()[:2])
        full_name_query = name
        queries = [full_name_query, normalized_name, fallback_query] if fallback_query else [full_name_query, normalized_name]

        for query in queries:
            if not query:
                continue
            params = {"q": query, "quotesCount": 12, "newsCount": 0}
            response = requests.get(search_url, params=params, headers=REQUEST_HEADERS, timeout=15)
            response.raise_for_status()
            result = response.json()

            candidates = []
            for quote in result.get("quotes", []):
                if quote.get("quoteType") != "EQUITY":
                    continue
                symbol = quote.get("symbol")
                if not symbol or "." in symbol:
                    continue
                score = _score_yahoo_quote(quote, query)
                candidates.append((score, symbol))

            if candidates:
                candidates.sort(reverse=True)
                best_score, best_symbol = candidates[0]
                if best_score > 0:
                    return best_symbol
    except Exception as exc:
        logger.warning("Yahoo search failed for %s: %s", name, exc)
    return None


def fetch_ssga_holdings(etf: str, top_n: int = 20) -> List[str]:
    holdings: List[str] = []
    page_url = f"https://www.ssga.com/us/en/individual/etfs/funds/spdr-select-sector-fund-{etf.lower()}"
    try:
        response = requests.get(page_url, headers=REQUEST_HEADERS, timeout=20)
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text))
        for table in tables:
            cols = [str(c).strip().lower() for c in table.columns]
            if "name" in cols and ("weight" in cols or "shares held" in cols):
                table.columns = [str(c).strip() for c in table.columns]
                if "Name" in table.columns:
                    names = table["Name"].astype(str).str.strip().tolist()
                    for name in names[:top_n]:
                        symbol = resolve_symbol_from_name(name)
                        if symbol:
                            holdings.append(symbol)
                break
        if not holdings:
            logger.warning("SSGA holdings page parsed but no symbols resolved for %s", etf)
    except Exception as exc:
        logger.warning("Failed to fetch SSGA holdings for %s: %s", etf, exc)
    return holdings


def get_etf_holdings(etf_tickers: List[str], top_n: int = 10) -> Dict[str, List[str]]:
    holdings: Dict[str, List[str]] = {}
    for etf in etf_tickers:
        holdings[etf] = []
        try:
            logger.info("Fetching holdings for ETF %s", etf)
            ticker = yf.Ticker(etf)
            if etf.lower() in ETF_SSGA_TICKERS:
                symbols = fetch_ssga_holdings(etf.lower(), top_n=top_n)
                if symbols:
                    holdings[etf] = symbols[:top_n]
                    logger.info("Found %d holdings via SSGA scrape for %s", len(symbols), etf)
                    continue

            info = ticker.info
            if info is None:
                logger.warning("No info returned for ETF %s", etf)
                continue

            components = info.get("holdings") or info.get("topHoldings") or info.get("holdingsTicker")
            if isinstance(components, list) and components:
                if isinstance(components[0], dict):
                    symbols = [item.get("symbol") for item in components if item.get("symbol")]
                else:
                    symbols = [item for item in components if isinstance(item, str)]
            else:
                symbols = []

            symbols = [s for s in symbols if s]
            if not symbols:
                logger.warning("ETF %s did not return structured holdings; results may be empty", etf)
            holdings[etf] = symbols[:top_n]
        except Exception as exc:
            logger.exception("Failed to get holdings for ETF %s: %s", etf, exc)
    return holdings


def fetch_options_data(symbol: str) -> Optional[pd.DataFrame]:
    try:
        logger.info("Fetching options chain for %s", symbol)
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            logger.warning("No option expirations found for %s", symbol)
            return None

        rows = []
        for expiry in expirations:
            chain = ticker.option_chain(expiry)
            for option_type, df in [("call", chain.calls), ("put", chain.puts)]:
                if df is None or df.empty:
                    continue
                df = df.copy()
                df["type"] = option_type
                df["expiry"] = pd.to_datetime(expiry)
                rows.append(df)

        if not rows:
            return None

        options_df = pd.concat(rows, ignore_index=True)
        options_df["symbol"] = symbol
        options_df["volume_to_oi"] = np.where(
            options_df["openInterest"].fillna(0) > 0,
            options_df["volume"].fillna(0) / options_df["openInterest"].replace(0, np.nan),
            0,
        )
        options_df["premium_traded"] = options_df["volume"].fillna(0) * options_df["lastPrice"].fillna(0) * 100
        options_df["dte"] = (options_df["expiry"] - pd.Timestamp.now(tz=options_df["expiry"].dt.tz)).dt.days
        options_df = options_df.rename(columns={
            "strike": "strike",
            "openInterest": "open_interest",
            "lastPrice": "last_price",
        })
        return options_df
    except Exception as exc:
        logger.exception("Error fetching options data for %s: %s", symbol, exc)
        return None


def filter_contracts(options_df: pd.DataFrame, atm_pct: float = 0.15) -> pd.DataFrame:
    if options_df is None or options_df.empty:
        return pd.DataFrame()

    if "contractSymbol" not in options_df.columns:
        options_df = options_df.copy()
        options_df["contractSymbol"] = options_df.get("contractSymbol", "")

    underlying_price = yf.Ticker(options_df["symbol"].iat[0]).history(period="1d").get("Close")
    if underlying_price is not None and not underlying_price.empty:
        current_price = float(underlying_price.iloc[-1])
    else:
        current_price = np.nan

    filtered = options_df.copy()
    filtered = filtered[filtered["volume_to_oi"] > 2]
    filtered = filtered[filtered["dte"] > 7]
    if not np.isnan(current_price):
        filtered = filtered[filtered["strike"].between(current_price * (1 - atm_pct), current_price * (1 + atm_pct))]
    filtered = filtered.sort_values(by=["premium_traded", "volume"], ascending=[False, False])
    return filtered


def detect_clustering(filtered_df: pd.DataFrame, cluster_pct: float = 0.05, min_contracts: int = 2) -> bool:
    if filtered_df is None or filtered_df.empty:
        return False

    strikes = np.sort(filtered_df["strike"].unique())
    if len(strikes) < min_contracts:
        return False

    underlying_price = yf.Ticker(filtered_df["symbol"].iat[0]).history(period="1d").get("Close")
    if underlying_price is not None and not underlying_price.empty:
        current_price = float(underlying_price.iloc[-1])
    else:
        return np.nanmean(strikes) > 0

    target_range = current_price * cluster_pct
    for strike in strikes:
        nearby = strikes[(strikes >= strike - target_range) & (strikes <= strike + target_range)]
        if nearby.size >= min_contracts:
            return True
    return False


def compute_signals(symbol: str, etf_source: str, options_df: pd.DataFrame) -> Optional[Dict]:
    filtered = filter_contracts(options_df)
    if filtered.empty:
        return None

    grouped = filtered.groupby("type")["volume"].sum().to_dict()
    call_volume = grouped.get("call", 0)
    put_volume = grouped.get("put", 0)
    if call_volume > put_volume * 1.5:
        direction = "bullish"
    elif put_volume > call_volume * 1.5:
        direction = "bearish"
    else:
        logger.info("Volume not strongly directional for %s", symbol)
        return None

    if not detect_clustering(filtered):
        logger.info("No strike clustering detected for %s", symbol)
        return None

    top_contracts = filtered.head(5).copy()
    top_contracts = top_contracts[["contractSymbol", "type", "strike", "expiry", "volume", "open_interest", "last_price", "premium_traded", "dte"]]
    top_contracts["expiry"] = top_contracts["expiry"].dt.date.astype(str)

    signal = {
        "ticker": symbol,
        "etf_source": etf_source,
        "direction": direction,
        "total_call_volume": int(call_volume),
        "total_put_volume": int(put_volume),
        "timestamp": datetime.now().strftime("%Y-%m-%d"),
        "top_contracts": top_contracts.to_dict(orient="records"),
    }
    return signal


def save_signals(signals: List[Dict], path: str = "signals_day0.json") -> None:
    try:
        logger.info("Saving %d signals to %s", len(signals), path)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(signals, handle, indent=2)
    except Exception as exc:
        logger.exception("Failed to save signals: %s", exc)


def load_signals(path: str = "signals_day0.json") -> List[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        logger.warning("Signal file not found: %s", path)
        return []
    except Exception as exc:
        logger.exception("Failed to load signals: %s", exc)
        return []


def confirm_oi_changes(signals: List[Dict]) -> List[Dict]:
    if not signals:
        return []

    confirmed_signals = []
    for signal in signals:
        symbol = signal["ticker"]
        contracts = signal.get("top_contracts", [])
        contract_symbols = [c["contractSymbol"] for c in contracts]
        logger.info("Confirming OI for %s with %d contracts", symbol, len(contract_symbols))

        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        daily_confirmed = []
        for contract in contracts:
            contract_symbol = contract["contractSymbol"]
            old_oi = int(contract.get("open_interest", 0))
            previous_volume = int(contract.get("volume", 0))
            if previous_volume <= 0:
                continue

            option_chain = None
            for expiry in expirations:
                if contract_symbol.endswith(expiry.replace("-", "")) or expiry in contract_symbol:
                    option_chain = ticker.option_chain(expiry)
                    break

            if option_chain is None:
                continue

            option_df = pd.concat([option_chain.calls, option_chain.puts], ignore_index=True)
            option_df = option_df[option_df["contractSymbol"] == contract_symbol]
            if option_df.empty:
                continue

            new_oi = int(option_df["openInterest"].iloc[0])
            oi_retention = (new_oi - old_oi) / previous_volume
            if oi_retention > 0.5:
                daily_confirmed.append({
                    "contractSymbol": contract_symbol,
                    "old_open_interest": old_oi,
                    "new_open_interest": new_oi,
                    "oi_retention": oi_retention,
                    "volume": previous_volume,
                })

        if len(daily_confirmed) >= 1:
            avg_retention = float(np.mean([c["oi_retention"] for c in daily_confirmed]))
            confirmed_signals.append({
                "ticker": symbol,
                "direction": signal["direction"],
                "confirmed_contracts": daily_confirmed,
                "average_oi_retention": avg_retention,
                "confirmed_contract_count": len(daily_confirmed),
                "timestamp": datetime.now().strftime("%Y-%m-%d"),
            })
    return confirmed_signals
