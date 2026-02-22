pub mod api;
pub mod bayes_prob;
pub mod logging;
pub mod model;
pub mod time_queue;
pub mod util;

use std::{
    collections::BTreeMap,
    collections::HashMap,
    sync::Arc,
    time::Duration,
    fs,
};

use tokio::time::Instant;

use crate::api::gmo;
use crate::api::gmo::api::ApiResponseError;
use crate::api::gmo::ws;
use crate::bayes_prob::{BayesProb, BetaDistribution};
use crate::logging::trade_logger::{TradeEvent, TradeLogger};
use crate::logging::metrics_logger::{MetricsLogger, MetricsSnapshot};
use crate::model::Position;
use crate::model::OrderSide;
use crate::model::BotConfig;
use crate::api::gmo::api::Symbol;
use crate::api::gmo::api::ChildOrderType;
// TimeInForce removed: SOK disabled (leverage trading has zero fees)

use chrono::{Timelike, Utc};
use futures::{SinkExt, StreamExt};
use parking_lot::{Mutex, RwLock};
use tokio::{runtime::Builder, time::sleep};
use tokio_tungstenite::{connect_async, tungstenite::{Message, Result}};
use rayon::prelude::*;
use tracing::{info, warn, error, debug};
use url::Url;

type Orders = Arc<Mutex<HashMap<String, model::OrderInfo>>>;
type Positions = RwLock<model::Position>;
use crate::model::FloatingExp;

type OrderBook = RwLock<BTreeMap<u64, f64>>;
type Executions = RwLock<Vec<(u64, f64, i64)>>;
type LastWsMessage = Arc<RwLock<i64>>;
type SharedU64 = Arc<RwLock<u64>>;
type GhostSuppression = Arc<RwLock<Option<Instant>>>;

fn expected_value(
    mid_price: f64,
    volatility: f64,
    alpha: f64,
    buy: &FloatingExp,
    sell: &FloatingExp,
    buy_data: &(f64, BayesProb),
    sell_data: &(f64, BayesProb),
) -> f64 {
    let buy_probability: f64 = buy_data.1.calc_average();
    let sell_probability: f64 = sell_data.1.calc_average();
    let buy_price: f64 = mid_price - (mid_price * buy.calc());
    let sell_price: f64 = mid_price + (mid_price * sell.calc());

    let expected_profit = buy_probability * sell_probability * (sell_price - buy_price);
    let expected_loss =
        (buy_probability * (1.0 - sell_probability) + sell_probability * (1.0 - buy_probability))
            * volatility
            * alpha;

    expected_profit - expected_loss
}

fn maximize_expected_value(
    mid_price: f64,
    volatility: f64,
    alpha: f64,
    buy: &BTreeMap<FloatingExp, (f64, BayesProb)>,
    sell: &BTreeMap<FloatingExp, (f64, BayesProb)>,
) -> Option<(FloatingExp, FloatingExp)> {
    let mut best_pair = None;
    let mut best_expected_value = f64::NEG_INFINITY;

    for (b_key, b_val) in buy {
        for (s_key, s_val) in sell {
            let ev = expected_value(mid_price, volatility, alpha, b_key, s_key, b_val, s_val);

            if ev > best_expected_value {
                best_pair = Some((b_key.clone(), s_key.clone()));
                best_expected_value = ev;
            }
        }
    }

    debug!("Best EV = {:?}", util::round_size(best_expected_value));
    best_pair
}

async fn cancel_child_order(
    client: &reqwest::Client,
    config: &BotConfig,
    order_list: &Orders,
    trade_logger: &Option<TradeLogger>,
    current_t_optimal_ms: &SharedU64,
) -> Result<()> {
    loop {
        sleep(Duration::from_millis(500)).await;

        let list = order_list.lock().clone();
        let t_optimal = *current_t_optimal_ms.read();

        for order in list.iter() {
            let now = Utc::now().timestamp_millis() as u64;
            let order_age = now - order.1.timestamp;

            // Use dynamic T_optimal for all orders; fall back to config for safety
            let cancel_threshold = if t_optimal > 0 { t_optimal } else { config.order_cancel_ms };

            if order_age < cancel_threshold {
                continue;
            }

            let child_order_acceptance_id = order.0.to_string();

            let parameter = gmo::cancel_child_order::CancelOrderParameter {
                order_id: child_order_acceptance_id.clone(),
            };

            let timestamp = Utc::now().to_rfc3339();

            match gmo::cancel_child_order::cancel_order(client, &parameter).await {
                Ok(_) => {
                    info!("Cancel Order {:?} (age={}ms, threshold={}ms)",
                        child_order_acceptance_id, order_age, cancel_threshold);
                    if let Some(logger) = trade_logger {
                        logger.log(TradeEvent::OrderCancelled {
                            timestamp,
                            order_id: child_order_acceptance_id.clone(),
                        });
                    }
                    order_list.lock().remove(&child_order_acceptance_id);
                }
                Err(ApiResponseError::ApiError(ref msgs))
                    if msgs.iter().any(|m| m.message_code == "ERR-5122") =>
                {
                    info!("Order already filled (ERR-5122): {:?} (age={}ms)",
                        child_order_acceptance_id, order_age);
                    if let Some(logger) = trade_logger {
                        let info = order.1;
                        logger.log(TradeEvent::OrderFilled {
                            timestamp,
                            order_id: child_order_acceptance_id.clone(),
                            side: info.side.to_string(),
                            price: info.price,
                            size: info.size,
                            order_age_ms: order_age,
                            is_close: info.is_close,
                            mid_price: info.mid_price,
                            t_optimal_ms: info.t_optimal_ms,
                            sigma_1s: info.sigma_1s,
                            spread_pct: info.spread_pct,
                        });
                    }
                    order_list.lock().remove(&child_order_acceptance_id);
                }
                Err(e) => {
                    error!("Cancel failed (will retry): {:?}", e);
                    // Do NOT remove - retry on next cycle
                }
            }
        }
    }
}

/// 注文パラメータを検証する
fn validate_order_params(
    price: u64,
    size: f64,
    config: &BotConfig,
) -> std::result::Result<(), &'static str> {
    // 価格の検証
    if price == 0 {
        return Err("Price cannot be zero");
    }

    // サイズの検証
    if size < config.min_lot {
        return Err("Size below minimum lot");
    }
    if size > config.max_lot * 10.0 {
        return Err("Size exceeds maximum allowed");
    }

    // 小数点精度の検証 (GMO BTC minimum unit: 0.0001)
    if (size * 10000.0).fract() != 0.0 {
        return Err("Size precision too high (max 4 decimal places)");
    }

    Ok(())
}

/// Order result indicating whether margin was insufficient
#[derive(Debug)]
enum OrderResult {
    Success,
    MarginInsufficient,
    NoOpenPosition,
    OtherError,
}

const ERR_MARGIN_INSUFFICIENT: &str = "ERR-201";
const ERR_SOK_TAKER: &str = "ERR-5003";
const ERR_NO_OPEN_POSITION: &str = "ERR-422";
const GHOST_POSITION_COOLDOWN_SECS: u64 = 60;

/// Reset position to zero on ghost detection.
/// get_position polls every 5s and may temporarily overwrite with stale data;
/// this is self-correcting on the next poll cycle.
fn reset_position(position: &Positions) {
    let mut pos = position.write();
    pos.long_size = 0.0;
    pos.short_size = 0.0;
    pos.long_open_price = 0.0;
    pos.short_open_price = 0.0;
}

/// Activate ghost protection: reset position and set suppression window.
/// Must be called atomically (reset + suppression) to prevent get_position from
/// overwriting the reset with stale data before the suppression takes effect.
fn activate_ghost_protection(
    position: &Positions,
    ghost_suppression: &GhostSuppression,
    cooldown_secs: u64,
) -> Instant {
    reset_position(position);
    let until = Instant::now() + Duration::from_secs(cooldown_secs);
    *ghost_suppression.write() = Some(until);
    until
}

/// Returns true if ghost position detected (ERR-422)
async fn send_market_close(
    client: &reqwest::Client,
    side: &OrderSide,
    size: f64,
    trade_logger: &Option<TradeLogger>,
    mid_price: u64,
    open_price: f64,
    unrealized_pnl: f64,
) -> bool {
    let parameter = gmo::close_bulk_order::CloseBulkOrderParameter {
        symbol: Symbol::BTC_JPY,
        side: side.clone(),
        execution_type: ChildOrderType::MARKET,
        price: None,
        size: size.to_string(),
        time_in_force: None,
    };

    let ghost_hit = match gmo::close_bulk_order::close_bulk_order(client, &parameter).await {
        Ok(response) => {
            info!("[STOP_LOSS] MARKET close sent: order_id={} side={:?} size={}", response.1.data, side, size);
            false
        }
        Err(ApiResponseError::ApiError(ref msgs))
            if msgs.iter().any(|m| m.message_code == ERR_NO_OPEN_POSITION) =>
        {
            warn!("[GHOST_POSITION] MARKET close ERR-422: no open positions to settle. side={:?} size={}", side, size);
            true
        }
        Err(e) => {
            error!("[STOP_LOSS] MARKET close failed: {:?}", e);
            false
        }
    };

    if !ghost_hit {
        if let Some(logger) = trade_logger {
            logger.log(TradeEvent::StopLossTriggered {
                timestamp: Utc::now().to_rfc3339(),
                side: side.to_string(),
                size,
                unrealized_pnl,
                mid_price,
                open_price,
            });
        }
    }

    ghost_hit
}

async fn send_order(
    client: &reqwest::Client,
    order_list: &Orders,
    side: OrderSide,
    price: u64,
    size: f64,
    is_close_order: bool,
    config: &BotConfig,
    trade_logger: &Option<TradeLogger>,
    mid_price: u64,
    t_optimal_ms: u64,
    sigma_1s: f64,
    spread_pct: f64,
) -> OrderResult {
    // バリデーション
    if let Err(reason) = validate_order_params(price, size, config) {
        warn!("Invalid Order: {} - side={:?} price={} size={}", reason, side, price, size);
        return OrderResult::Success;
    }

    let mut order_id = String::new();
    let mut order_success = false;
    let mut order_error: Option<String> = None;
    let mut margin_insufficient = false;
    let mut no_open_position = false;

    if is_close_order {
        let parameter = gmo::close_bulk_order::CloseBulkOrderParameter {
            symbol: Symbol::BTC_JPY,
            side: side.clone(),
            execution_type: ChildOrderType::LIMIT,
            price: Some(price.to_string()),
            size: size.to_string(),
            time_in_force: None,
        };

        let response = gmo::close_bulk_order::close_bulk_order(client, &parameter).await;
        match response {
            Ok(response) => {
                order_id = response.1.data;
                order_success = true;
            }
            Err(ApiResponseError::ApiError(ref msgs))
                if msgs.iter().any(|m| m.message_code == ERR_NO_OPEN_POSITION) =>
            {
                warn!("[GHOST_POSITION] Close Order ERR-422: no open positions. side={:?} price={}", side, price);
                no_open_position = true;
                order_error = Some(format!("{:?}", msgs));
            }
            Err(ApiResponseError::ApiError(ref msgs))
                if msgs.iter().any(|m| m.message_code == ERR_MARGIN_INSUFFICIENT) =>
            {
                warn!("Close Order rejected: margin insufficient (ERR-201)");
                margin_insufficient = true;
                order_error = Some(format!("{:?}", msgs));
            }
            Err(e) => {
                error!("Close Order Failed {:?}", e);
                order_error = Some(format!("{:?}", e));
            }
        }
    } else {
        let parameter = gmo::send_order::ChildOrderParameter {
            symbol: Symbol::BTC_JPY,
            side: side.clone(),
            execution_type: ChildOrderType::LIMIT,
            price: Some(price.to_string()),
            size: size.to_string(),
            time_in_force: None, // SOK disabled: leverage trading has zero fees for both Maker/Taker
        };

        let response = gmo::send_order::post_child_order(client, &parameter).await;
        match response {
            Ok(response) => {
                order_id = response.1.data;
                order_success = true;
            }
            Err(ApiResponseError::ApiError(ref msgs))
                if msgs.iter().any(|m| m.message_code == ERR_MARGIN_INSUFFICIENT) =>
            {
                warn!("Send Order rejected: margin insufficient (ERR-201)");
                margin_insufficient = true;
                order_error = Some(format!("{:?}", msgs));
            }
            Err(ApiResponseError::ApiError(ref msgs))
                if msgs.iter().any(|m| m.message_code == ERR_SOK_TAKER) =>
            {
                info!("SOK rejected (would take liquidity): side={:?} price={}", side, price);
            }
            Err(e) => {
                error!("Send Order Failed {:?}", e);
                order_error = Some(format!("{:?}", e));
            }
        }
    }

    let timestamp = Utc::now().to_rfc3339();

    // 成功した場合のみ注文リストに追加
    if order_success && !order_id.is_empty() {
        let order_info = model::OrderInfo {
            price,
            size,
            side: side.clone(),
            timestamp: Utc::now().timestamp_millis() as u64,
            is_close: is_close_order,
            mid_price,
            t_optimal_ms,
            sigma_1s,
            spread_pct,
        };

        if is_close_order {
            info!("Close Order sent: id={} {:?}", order_id, order_info);
        } else {
            info!("Send Order sent: id={} {:?}", order_id, order_info);
        }

        order_list.lock().insert(order_id.clone(), order_info);

        if let Some(logger) = trade_logger {
            logger.log(TradeEvent::OrderSent {
                timestamp,
                order_id,
                side: side.to_string(),
                price,
                size,
                is_close: is_close_order,
                mid_price,
                t_optimal_ms,
                sigma_1s,
                spread_pct,
            });
        }
    } else if let Some(err) = order_error {
        if let Some(logger) = trade_logger {
            logger.log(TradeEvent::OrderFailed {
                timestamp,
                side: side.to_string(),
                price,
                size,
                error: err,
                mid_price,
                t_optimal_ms,
                sigma_1s,
                spread_pct,
            });
        }
    }

    if no_open_position {
        OrderResult::NoOpenPosition
    } else if margin_insufficient {
        OrderResult::MarginInsufficient
    } else if order_success {
        OrderResult::Success
    } else {
        OrderResult::OtherError
    }
}

fn update_probabilities(
    probabilities: &mut BTreeMap<FloatingExp, (f64, BayesProb)>,
    executions: &[(u64, f64, i64)],
    is_buy: bool,
) {
    probabilities.iter_mut().for_each(|(_, (order_price, bayes))| {
        let filled = if is_buy {
            // Buy fills if any execution at or below the order price
            executions.iter().any(|e| (e.0 as f64) <= *order_price)
        } else {
            // Sell fills if any execution at or above the order price
            executions.iter().any(|e| (e.0 as f64) >= *order_price)
        };
        bayes.update(1, filled as u64);
    });
}

fn update_order_prices(
    probabilities: &mut BTreeMap<FloatingExp, (f64, BayesProb)>,
    mid_price: f64,
    price_fn: impl Fn(f64, f64) -> f64,
) {
    probabilities.iter_mut().for_each(|p| {
        p.1.0 = price_fn(mid_price, p.0.calc())
    });
}

/// Calculate optimal order lifetime in milliseconds based on spread and volatility.
/// T_optimal = (spread_pct / sigma_1s)²
/// Clamped between min_ms and max_ms.
fn calculate_t_optimal(spread_pct: f64, sigma_1s: f64, min_ms: u64, max_ms: u64) -> u64 {
    if sigma_1s <= 0.0 || spread_pct <= 0.0 {
        return max_ms;
    }
    let ratio = spread_pct / sigma_1s;
    let t_secs = ratio * ratio;
    let t_ms = (t_secs * 1000.0) as u64;
    t_ms.clamp(min_ms, max_ms)
}

/// Minimum volatility as a fraction of mean price (0.5 bps = 0.005%)
const MIN_VOLATILITY_BPS: f64 = 0.00005;

fn calculate_volatility(executions: &[(u64, f64, i64)]) -> f64 {
    // Need at least 2 data points for log-returns
    if executions.len() < 2 {
        let mean_price = executions.first().map(|e| e.0 as f64).unwrap_or(6_500_000.0);
        return mean_price * MIN_VOLATILITY_BPS;
    }

    let prices: Vec<f64> = executions.iter().map(|e| e.0 as f64).collect();
    let mean_price = prices.iter().sum::<f64>() / prices.len() as f64;

    // Calculate log-returns: ln(p[i] / p[i-1])
    let log_returns: Vec<f64> = prices
        .windows(2)
        .filter(|w| w[0] > 0.0 && w[1] > 0.0)
        .map(|w| (w[1] / w[0]).ln())
        .collect();

    if log_returns.is_empty() {
        return mean_price * MIN_VOLATILITY_BPS;
    }

    // EWMA variance: σ²_t = λ * σ²_{t-1} + (1-λ) * r²_t
    // RiskMetrics standard lambda = 0.94
    // Seed with initial window variance, then EWMA from remaining data only (no double-counting)
    // Mean-zero assumption: r² instead of (r-μ)², appropriate for HFT tick data
    // When data <= seed_n points, falls back to simple variance (no EWMA weighting).
    // With execution_retain_ms=30000 and typical 2-5 ticks/sec, we have 60-150 returns;
    // seed_n=10 edge case only triggers during startup or very low activity.
    const LAMBDA: f64 = 0.94;
    let seed_n = log_returns.len().min(10);
    let mut ewma_var = log_returns[..seed_n].iter().map(|r| r.powi(2)).sum::<f64>()
        / seed_n as f64;
    for r in &log_returns[seed_n..] {
        ewma_var = LAMBDA * ewma_var + (1.0 - LAMBDA) * r.powi(2);
    }
    let stddev = ewma_var.sqrt();

    // Convert log-return stddev to absolute price units
    let volatility = mean_price * stddev;

    // Apply minimum floor
    volatility.max(mean_price * MIN_VOLATILITY_BPS)
}

/// Sum the sizes of pending OPEN (non-close) orders for a given side.
fn pending_open_size(orders: &HashMap<String, model::OrderInfo>, side: &OrderSide) -> f64 {
    orders.values()
        .filter(|o| o.side == *side && !o.is_close)
        .map(|o| o.size)
        .sum()
}

/// Check if the given UTC hour is within trading hours.
/// Trading allowed: UTC 0-14 (JST 9-23). Blocked: UTC 15-23 (JST 0-8).
fn is_trading_hour(utc_hour: u32) -> bool {
    utc_hour < 15
}

const INVENTORY_SPREAD_ADJUSTMENT: f64 = 0.2;

fn calculate_spread_adjustment(position: &Position, max_position_size: f64) -> (f64, f64) {
    let net_position = position.long_size - position.short_size;
    let total_exposure = position.long_size + position.short_size;

    // Direction-based adjustment (net inventory skew)
    let inventory_ratio = if total_exposure > 0.0 {
        net_position / total_exposure.max(0.001)
    } else {
        0.0
    };

    // Gross exposure penalty: widen both spreads when total position is large
    // Normalized by max_position_size so penalty scales properly at all lot sizes
    let max_single_side = position.long_size.max(position.short_size);
    let exposure_ratio = if max_position_size > 0.0 {
        max_single_side / max_position_size
    } else {
        0.0
    };
    let exposure_penalty = (exposure_ratio * INVENTORY_SPREAD_ADJUSTMENT)
        .min(INVENTORY_SPREAD_ADJUSTMENT);

    // Direction adjustment + exposure penalty
    let buy_spread_adj = 1.0 + (inventory_ratio * INVENTORY_SPREAD_ADJUSTMENT) + exposure_penalty;
    let sell_spread_adj = 1.0 - (inventory_ratio * INVENTORY_SPREAD_ADJUSTMENT) + exposure_penalty;

    (buy_spread_adj, sell_spread_adj)
}

fn calculate_order_prices(
    mid_price: f64,
    best_pair: &(FloatingExp, FloatingExp),
    position: &Position,
    position_penalty: f64,
    min_lot: f64,
) -> (f64, f64) {
    let bid = mid_price - best_pair.0.calc() * mid_price;
    let ask = mid_price + best_pair.1.calc() * mid_price;

    // Penalty discourages adding to existing positions AND accelerates closing:
    // Long-heavy: lower buy price (harder to buy more) + lower sell price (easier to close long)
    // Short-heavy: raise sell price (harder to sell more) + raise buy price (easier to close short)
    let buy_order_price = bid - position_penalty * position.long_size / min_lot
                             + position_penalty * position.short_size / min_lot;
    let sell_order_price = ask + position_penalty * position.short_size / min_lot
                              - position_penalty * position.long_size / min_lot;

    (buy_order_price, sell_order_price)
}

fn calculate_order_sizes(
    position: &Position,
    max_position_size: f64,
    min_lot: f64,
    max_lot: f64,
    position_ratio: f64,
) -> (f64, f64) {
    let remaining_long = (max_position_size - position.long_size).max(0.0);
    let remaining_short = (max_position_size - position.short_size).max(0.0);

    let buy_size = if remaining_long < min_lot {
        0.0
    } else {
        util::round_size(
            max_lot * (1.0 - position.long_size.powf(position_ratio) / max_position_size),
        )
        .max(min_lot)
        .min(remaining_long)
    };

    let sell_size = if remaining_short < min_lot {
        0.0
    } else {
        util::round_size(
            max_lot * (1.0 - position.short_size.powf(position_ratio) / max_position_size),
        )
        .max(min_lot)
        .min(remaining_short)
    };

    (buy_size, sell_size)
}

/// Determine effective order size: close orders use min_lot when calculated size is 0,
/// open orders use the calculated size as-is.
fn effective_order_size(calculated_size: f64, is_close: bool, min_lot: f64) -> f64 {
    if is_close && calculated_size < min_lot {
        min_lot
    } else {
        calculated_size
    }
}

async fn trade(
    client: &reqwest::Client,
    config: &BotConfig,
    order_list: &Orders,
    position: &Positions,
    board_asks: &OrderBook,
    board_bids: &OrderBook,
    executions: &Executions,
    last_ws_message: &LastWsMessage,
    trade_logger: &Option<TradeLogger>,
    metrics_logger: &Option<MetricsLogger>,
    current_t_optimal_ms: &SharedU64,
    ghost_suppression: &GhostSuppression,
) -> Result<()> {
    const MAX_KEEP_BOARD_PRICE: u64 = 100_000;
    let max_position_size: f64 = config.max_position;
    let min_lot: f64 = config.min_lot;
    let max_lot: f64 = config.max_lot;
    let position_ratio: f64 = config.position_ratio;

    let mut collateral = match gmo::get_collateral::get_collateral(client).await {
        Ok(response) => response.data.actual_profit_loss,
        Err(_) => 0.0,
    };

    info!("Collateral {:?}", collateral);

    sleep(Duration::from_secs(5)).await;

    // Be(1, 1) = uniform prior (uninformative). Be(0, 1) was incorrect (P=0 prior).
    let initial_bayes_prob = BayesProb::new(BetaDistribution::new(1, 1), Duration::from_secs(300));

    let mut buy_probabilities = BTreeMap::<FloatingExp, (f64, BayesProb)>::new();
    let mut sell_probabilities = BTreeMap::<FloatingExp, (f64, BayesProb)>::new();

    // L1-L3 excluded: closest levels have highest adverse selection (-13.86 JPY/trip at L1)
    const PRICE_STEP_START: u32 = 4;
    const PRICE_STEP_END: u32 = 25;

    for i in PRICE_STEP_START..=PRICE_STEP_END {
        let key = FloatingExp { base: 10.0, exp: -5.0, rate: i as f64 };
        buy_probabilities.insert(key.clone(), (0.0, initial_bayes_prob.clone()));
        sell_probabilities.insert(key.clone(), (0.0, initial_bayes_prob.clone()));
    }

    let mut collateral_refresh_count: u64 = 0;
    let mut empty_executions_count: u64 = 0;
    let mut ws_stale_count: u64 = 0;
    let mut heartbeat_count: u64 = 0;
    // ERR-201 margin insufficient cooldown: suppress new orders until this instant
    let mut margin_cooldown_until: Option<Instant> = None;
    const MARGIN_COOLDOWN_SECS: u64 = 60;
    // Stop-loss cooldown: prevent repeated MARKET orders while get_position polls (5s)
    let mut stop_loss_cooldown_until: Option<Instant> = None;
    const STOP_LOSS_COOLDOWN_SECS: u64 = 10;
    // Ghost cooldown: suppress close orders after ghost detection (separate from SL cooldown)
    let mut ghost_cooldown_until: Option<Instant> = None;
    const WS_STALE_THRESHOLD_MS: i64 = 60_000;
    const HEARTBEAT_INTERVAL: u64 = 20; // ~5min (15s × 20 = 300s)

    loop {
        sleep(Duration::from_millis(config.order_interval_ms)).await;

        let now = Utc::now().timestamp_millis();

        // Retain the last execution_retain_ms milliseconds of executions
        executions.write().retain(|e| e.2 >= (now - config.execution_retain_ms as i64));

        let executions_snapshot = executions.read().clone();
        let last_ws_ts = *last_ws_message.read();
        let ws_age_ms = now - last_ws_ts;

        // Periodic heartbeat log
        heartbeat_count += 1;
        if heartbeat_count % HEARTBEAT_INTERVAL == 0 {
            let current_position = *position.read();
            info!(
                "[HEARTBEAT] alive - ws_last={}ms ago, position=long:{}/short:{}, pending_orders={}, exec_count={}",
                ws_age_ms,
                current_position.long_size,
                current_position.short_size,
                order_list.lock().len(),
                executions_snapshot.len(),
            );
        }

        // WebSocket health check - skip trading on stale data
        if last_ws_ts > 0 && ws_age_ms > WS_STALE_THRESHOLD_MS {
            ws_stale_count += 1;
            if ws_stale_count == 1 || ws_stale_count % 20 == 0 {
                error!(
                    "[WS_STALE] No WebSocket message for {}ms (threshold: {}ms, consecutive: {}). Skipping trade.",
                    ws_age_ms, WS_STALE_THRESHOLD_MS, ws_stale_count
                );
            }
            continue;
        }
        ws_stale_count = 0;

        // Skip trade cycle when no executions available
        if executions_snapshot.is_empty() {
            empty_executions_count += 1;
            if empty_executions_count <= 3 {
                warn!(
                    "[NO_EXECUTIONS] No executions received in last {}ms, skipping trade cycle (consecutive: {})",
                    config.execution_retain_ms, empty_executions_count
                );
            } else if empty_executions_count % 10 == 0 {
                error!(
                    "[NO_EXECUTIONS] No executions for {} consecutive cycles (~{}s). Trading is stalled.",
                    empty_executions_count,
                    empty_executions_count.saturating_mul(config.order_interval_ms) / 1000
                );
            }
            continue;
        }
        empty_executions_count = 0;

        // Circuit breaker: skip trading when recent price range exceeds threshold
        // Uses 5s window (independent of execution_retain_ms) to avoid false triggers
        const CIRCUIT_BREAKER_BPS: f64 = 0.001; // 0.1% of mid price
        const CIRCUIT_BREAKER_COOLDOWN_SECS: u64 = 30;
        const CIRCUIT_BREAKER_WINDOW_MS: i64 = 5000;
        {
            let recent_prices: Vec<u64> = executions_snapshot.iter()
                .filter(|e| e.2 >= (now - CIRCUIT_BREAKER_WINDOW_MS))
                .map(|e| e.0)
                .collect();
            if let (Some(&pmin), Some(&pmax)) = (recent_prices.iter().min(), recent_prices.iter().max()) {
                let mid_est = (pmin + pmax) as f64 / 2.0;
                if mid_est > 0.0 {
                    let range_bps = (pmax - pmin) as f64 / mid_est;
                    if range_bps > CIRCUIT_BREAKER_BPS {
                        warn!(
                            "[CIRCUIT_BREAKER] High volatility: range={} JPY, bps={:.5}, threshold={:.5}. Pausing {}s.",
                            pmax - pmin, range_bps, CIRCUIT_BREAKER_BPS, CIRCUIT_BREAKER_COOLDOWN_SECS
                        );
                        sleep(Duration::from_secs(CIRCUIT_BREAKER_COOLDOWN_SECS)).await;
                        continue;
                    }
                }
            }
        }

        let volatility = calculate_volatility(&executions_snapshot);

        let ltp = match executions_snapshot.last() {
            Some(e) => e.0,
            None => 0,
        };

        board_asks.write()
            .retain(|p, v| *v > 0.0 && *p < ltp + MAX_KEEP_BOARD_PRICE && *p >= ltp);

        board_bids.write()
            .retain(|p, v| *v > 0.0 && *p > ltp - MAX_KEEP_BOARD_PRICE && *p <= ltp);

        let best_ask = board_asks.read().iter().next()
            .map(|p| *p.0 as f64)
            .unwrap_or(0.0);

        let best_bid = board_bids.read().iter().next_back()
            .map(|p| *p.0 as f64)
            .unwrap_or(0.0);

        let mid_price = (best_ask + best_bid) / 2.0;

        // Update order prices first, then check fill probabilities against those prices
        update_order_prices(&mut buy_probabilities, mid_price, |mp, calc| mp - mp * calc);
        update_order_prices(&mut sell_probabilities, mid_price, |mp, calc| mp + mp * calc);

        // Update Bayes probabilities: each level checks if executions filled at ITS price
        update_probabilities(&mut buy_probabilities, &executions_snapshot, true);
        update_probabilities(&mut sell_probabilities, &executions_snapshot, false);

        // Find the best EV pair
        let best_pair = match maximize_expected_value(mid_price, volatility, config.alpha, &buy_probabilities, &sell_probabilities) {
            Some(p) => p,
            None => continue,
        };
        debug!("best_pair: {:?}", best_pair);

        let current_position = *position.read();
        debug!("position: {:?}", current_position);

        // Stop-loss cooldown check
        if let Some(until) = stop_loss_cooldown_until {
            if Instant::now() >= until {
                stop_loss_cooldown_until = None;
            }
        }

        // Stop-loss check: unrealized P&L exceeds threshold → MARKET close
        if config.stop_loss_jpy > 0.0 && stop_loss_cooldown_until.is_none() {
            let long_pnl = if current_position.long_size >= min_lot && current_position.long_open_price > 0.0 {
                (mid_price - current_position.long_open_price) * current_position.long_size
            } else {
                0.0
            };
            let short_pnl = if current_position.short_size >= min_lot && current_position.short_open_price > 0.0 {
                (current_position.short_open_price - mid_price) * current_position.short_size
            } else {
                0.0
            };
            let unrealized_pnl = long_pnl + short_pnl;

            if unrealized_pnl < -config.stop_loss_jpy
                && (current_position.long_size >= min_lot || current_position.short_size >= min_lot)
            {
                // Ghost SL prevention: verify position still exists before MARKET close
                // get_position polls every 5s, so cached position may be stale
                let fresh_position = gmo::get_position::get_position(client, Symbol::BTC_JPY).await;
                let has_position = match &fresh_position {
                    Ok(resp) => resp.data.as_ref()
                        .and_then(|d| d.list.as_ref())
                        .map_or(false, |list| !list.is_empty()),
                    Err(_) => true, // On API error, assume position exists (safe default)
                };
                if !has_position {
                    warn!("[STALE_SL] Position already closed (get_position confirmed empty), skipping SL. unrealized_pnl={:.3}", unrealized_pnl);
                    let ghost_until = activate_ghost_protection(position, ghost_suppression, GHOST_POSITION_COOLDOWN_SECS);
                    stop_loss_cooldown_until = Some(ghost_until);
                    ghost_cooldown_until = Some(ghost_until);
                    continue;
                }

                // Close the side with the worse P&L
                let (close_side, close_size, open_price) = if long_pnl <= short_pnl {
                    (OrderSide::SELL, current_position.long_size, current_position.long_open_price)
                } else {
                    (OrderSide::BUY, current_position.short_size, current_position.short_open_price)
                };
                info!(
                    "[STOP_LOSS] unrealized_pnl={:.3} (long={:.3} short={:.3}) threshold=-{} side={:?} size={} open_price={:.0} mid={:.0}",
                    unrealized_pnl, long_pnl, short_pnl, config.stop_loss_jpy, close_side, close_size, open_price, mid_price
                );
                let ghost_hit = send_market_close(
                    client, &close_side, close_size, trade_logger,
                    mid_price as u64, open_price, unrealized_pnl,
                ).await;
                if ghost_hit {
                    warn!("[GHOST_POSITION] Resetting position to zero, cooldown {}s", GHOST_POSITION_COOLDOWN_SECS);
                    let ghost_until = activate_ghost_protection(position, ghost_suppression, GHOST_POSITION_COOLDOWN_SECS);
                    stop_loss_cooldown_until = Some(ghost_until);
                    margin_cooldown_until = Some(ghost_until);
                    ghost_cooldown_until = Some(ghost_until);
                } else {
                    stop_loss_cooldown_until = Some(Instant::now() + Duration::from_secs(STOP_LOSS_COOLDOWN_SECS));
                }
                continue; // skip normal order cycle
            }
        }

        // Position penalty: penalize prices to discourage adding to existing positions
        let position_penalty = 50.0;
        debug!("position_penalty: {:?}", position_penalty);

        let (base_buy_price, base_sell_price) = calculate_order_prices(
            mid_price,
            &best_pair,
            &current_position,
            position_penalty,
            min_lot,
        );

        // Inventory-based spread adjustment
        let (buy_spread_adj, sell_spread_adj) = calculate_spread_adjustment(&current_position, max_position_size);
        let buy_spread = mid_price - base_buy_price;
        let sell_spread = base_sell_price - mid_price;
        let adj_buy_price = mid_price - (buy_spread * buy_spread_adj);
        let adj_sell_price = mid_price + (sell_spread * sell_spread_adj);

        // Open orders: clamp to prevent spread-crossing (SOK compliance)
        let buy_order_price = adj_buy_price.min(best_bid);
        let sell_order_price = adj_sell_price.max(best_ask);

        // Close orders: reduced spread for faster fill, NO best_bid/best_ask clamp
        // Safety: never cross mid_price (at least 1 JPY from mid)
        let close_buy_price = (mid_price - (buy_spread * config.close_spread_factor)).min(mid_price - 1.0);
        let close_sell_price = (mid_price + (sell_spread * config.close_spread_factor)).max(mid_price + 1.0);

        let (buy_size, sell_size) = calculate_order_sizes(
            &current_position,
            max_position_size,
            min_lot,
            max_lot,
            position_ratio,
        );

        // Refresh collateral periodically (every ~10 cycles)
        collateral_refresh_count += 1;
        if collateral_refresh_count % 10 == 0 {
            if let Ok(response) = gmo::get_collateral::get_collateral(client).await {
                collateral = response.data.actual_profit_loss;
            }
        }

        // Compute trade context (used for metrics, shared T_optimal, and send_order logging)
        let sigma_1s = if mid_price > 0.0 { volatility / mid_price } else { 0.0 };
        let avg_spread_pct = (best_pair.0.calc() + best_pair.1.calc()) / 2.0;
        let buy_spread_raw = best_pair.0.calc();
        let sell_spread_raw = best_pair.1.calc();
        let t_opt_ms = calculate_t_optimal(
            avg_spread_pct, sigma_1s,
            config.t_optimal_min_ms, config.t_optimal_max_ms,
        );

        // Update shared T_optimal for cancel loop (always, even without metrics logger)
        *current_t_optimal_ms.write() = t_opt_ms;

        // Log metrics
        if let Some(logger) = metrics_logger {
            let buy_prob_avg: f64 = if buy_probabilities.is_empty() {
                0.0
            } else {
                buy_probabilities.values().map(|v| v.1.calc_average()).sum::<f64>()
                    / buy_probabilities.len() as f64
            };
            let sell_prob_avg: f64 = if sell_probabilities.is_empty() {
                0.0
            } else {
                sell_probabilities.values().map(|v| v.1.calc_average()).sum::<f64>()
                    / sell_probabilities.len() as f64
            };

            let spread = best_ask - best_bid;
            let buy_spread_pct = if mid_price > 0.0 { buy_spread_raw * 100.0 } else { 0.0 };
            let sell_spread_pct = if mid_price > 0.0 { sell_spread_raw * 100.0 } else { 0.0 };

            let best_ev = expected_value(
                mid_price,
                volatility,
                config.alpha,
                &best_pair.0,
                &best_pair.1,
                buy_probabilities.get(&best_pair.0).unwrap_or(&(0.0, initial_bayes_prob.clone())),
                sell_probabilities.get(&best_pair.1).unwrap_or(&(0.0, initial_bayes_prob.clone())),
            );

            logger.log(MetricsSnapshot {
                timestamp: Utc::now().to_rfc3339(),
                mid_price,
                best_bid,
                best_ask,
                spread,
                volatility,
                best_ev,
                buy_spread_pct,
                sell_spread_pct,
                long_size: current_position.long_size,
                short_size: current_position.short_size,
                collateral,
                buy_prob_avg,
                sell_prob_avg,
                sigma_1s,
                t_optimal_ms: t_opt_ms as f64,
            });
        }

        // Close orders: allowed when opposing position exists, BUT suppressed during ghost cooldown
        // Ghost cooldown (separate from SL cooldown) prevents the ERR-422 infinite loop:
        // ghost_hit → reset → get_position overwrites → close retry
        // Normal SL cooldown (10s) does NOT suppress closes - only ghost cooldown (60s) does
        let ghost_cooldown_active = ghost_cooldown_until
            .map_or(false, |until| Instant::now() < until);
        if !ghost_cooldown_active && ghost_cooldown_until.is_some() {
            info!("[GHOST_COOLDOWN] Ghost cooldown expired, resuming close orders");
            ghost_cooldown_until = None;
        }
        let should_close_short = !ghost_cooldown_active && current_position.short_size >= min_lot;
        let should_close_long = !ghost_cooldown_active && current_position.long_size >= min_lot;

        // New orders: gated by max_position + pending order check (Bug B fix)
        // Include pending open order sizes to prevent race with get_position polling
        let orders_snapshot = order_list.lock().clone();
        let pending_buy = pending_open_size(&orders_snapshot, &OrderSide::BUY);
        let pending_sell = pending_open_size(&orders_snapshot, &OrderSide::SELL);
        let effective_long = current_position.long_size + pending_buy;
        let effective_short = current_position.short_size + pending_sell;

        // Margin cooldown: suppress new (open) orders when margin is insufficient
        let now = Instant::now();
        let margin_ok = match margin_cooldown_until {
            Some(until) if now < until => {
                debug!("[MARGIN_COOLDOWN] Suppressing new orders for {}s more",
                    (until - now).as_secs());
                false
            }
            Some(_) => {
                info!("[MARGIN_COOLDOWN] Cooldown expired, resuming new orders");
                margin_cooldown_until = None;
                true
            }
            None => true,
        };

        // Time filter: only open new positions during UTC 0-14 (JST 9-23)
        // Close orders are allowed 24h to manage existing risk
        let in_trading_hours = is_trading_hour(Utc::now().hour());

        let can_open_long = margin_ok && in_trading_hours && effective_long + buy_size <= max_position_size && buy_size >= min_lot;
        let can_open_short = margin_ok && in_trading_hours && effective_short + sell_size <= max_position_size && sell_size >= min_lot;

        // Effective order sizes: close uses min_lot, open uses calculated size
        let eff_buy_size = effective_order_size(buy_size, should_close_short, min_lot);
        let eff_sell_size = effective_order_size(sell_size, should_close_long, min_lot);

        // When both close and open are possible, close takes priority
        // (send_order receives is_close_order=should_close_*, using close_bulk_order API)
        let should_buy = should_close_short || can_open_long;
        let should_sell = should_close_long || can_open_short;

        info!(
            "[ORDER] buy={} (close_short={}, open_long={}), sell={} (close_long={}, open_short={}), pos=({}/{}), eff_pos=({:.4}/{:.4}), pending_open=({:.4}/{:.4}), margin_ok={}, size=(buy:{:.4}->{:.4}, sell:{:.4}->{:.4})",
            should_buy, should_close_short, can_open_long,
            should_sell, should_close_long, can_open_short,
            current_position.long_size, current_position.short_size,
            effective_long, effective_short,
            pending_buy, pending_sell,
            margin_ok,
            buy_size, eff_buy_size, sell_size, eff_sell_size,
        );

        // Select price based on whether the order is a close or open
        let eff_buy_price = if should_close_short { close_buy_price as u64 } else { buy_order_price as u64 };
        let eff_sell_price = if should_close_long { close_sell_price as u64 } else { sell_order_price as u64 };

        let (margin_hit, ghost_hit) = match (should_buy, should_sell) {
            (true, true) => {
                let buy_fut = send_order(
                    client, order_list, OrderSide::BUY,
                    eff_buy_price, eff_buy_size, should_close_short, config, trade_logger,
                    mid_price as u64, t_opt_ms, sigma_1s, buy_spread_raw,
                );
                let sell_fut = send_order(
                    client, order_list, OrderSide::SELL,
                    eff_sell_price, eff_sell_size, should_close_long, config, trade_logger,
                    mid_price as u64, t_opt_ms, sigma_1s, sell_spread_raw,
                );
                let (buy_res, sell_res) = tokio::join!(buy_fut, sell_fut);
                (
                    matches!(buy_res, OrderResult::MarginInsufficient)
                        || matches!(sell_res, OrderResult::MarginInsufficient),
                    matches!(buy_res, OrderResult::NoOpenPosition)
                        || matches!(sell_res, OrderResult::NoOpenPosition),
                )
            }
            (true, false) => {
                let res = send_order(
                    client, order_list, OrderSide::BUY,
                    eff_buy_price, eff_buy_size, should_close_short, config, trade_logger,
                    mid_price as u64, t_opt_ms, sigma_1s, buy_spread_raw,
                ).await;
                (
                    matches!(res, OrderResult::MarginInsufficient),
                    matches!(res, OrderResult::NoOpenPosition),
                )
            }
            (false, true) => {
                let res = send_order(
                    client, order_list, OrderSide::SELL,
                    eff_sell_price, eff_sell_size, should_close_long, config, trade_logger,
                    mid_price as u64, t_opt_ms, sigma_1s, sell_spread_raw,
                ).await;
                (
                    matches!(res, OrderResult::MarginInsufficient),
                    matches!(res, OrderResult::NoOpenPosition),
                )
            }
            (false, false) => (false, false),
        };

        // Ghost position detected: reset local position and extended cooldown
        if ghost_hit {
            warn!("[GHOST_POSITION] Close order ERR-422 detected, resetting position to zero, cooldown {}s", GHOST_POSITION_COOLDOWN_SECS);
            let ghost_until = activate_ghost_protection(position, ghost_suppression, GHOST_POSITION_COOLDOWN_SECS);
            stop_loss_cooldown_until = Some(ghost_until);
            margin_cooldown_until = Some(ghost_until);
            ghost_cooldown_until = Some(ghost_until);
        }

        // Activate margin cooldown if any order got ERR-201
        if margin_hit {
            let cooldown = Instant::now() + Duration::from_secs(MARGIN_COOLDOWN_SECS);
            warn!("[MARGIN_COOLDOWN] Margin insufficient detected, suppressing new orders for {}s", MARGIN_COOLDOWN_SECS);
            margin_cooldown_until = Some(cooldown);
        }
    }
}

async fn get_position(client: &reqwest::Client, position: &Positions, ghost_suppression: &GhostSuppression) -> Result<()> {
    loop {
        sleep(Duration::from_secs(5)).await;

        let response =
            match gmo::get_position::get_position(client, Symbol::BTC_JPY).await {
                Ok(response) => response.data.unwrap_or_default().list.unwrap_or_default(),
                Err(e) => {
                    error!("Position fetch error: {:?}", e);
                    continue;
                }
            };

        // Ghost suppression: during cooldown, only write if API returns a non-empty position
        // (non-empty proves the position is real, not stale ghost data)
        // Empty responses during suppression are skipped to prevent overwriting the reset
        // Note: minor TOCTOU race exists (trade() may set suppression between check and write)
        // but it self-corrects on the next 5s poll cycle
        let suppression_until = *ghost_suppression.read();
        if let Some(until) = suppression_until {
            let now = Instant::now();
            if now < until && response.is_empty() {
                debug!("[GHOST_SUPPRESSION] Skipping empty position update, {}s remaining",
                    (until - now).as_secs());
                continue;
            }
            // Clear expired suppression (read lock already dropped)
            if now >= until {
                *ghost_suppression.write() = None;
            }
        }

        // Track gross positions (both sides independently) with weighted average open price
        let mut long_total = 0.0;
        let mut short_total = 0.0;
        let mut long_price_sum = 0.0;
        let mut short_price_sum = 0.0;
        for x in &response {
            if x.side == "BUY" {
                long_total += x.size;
                long_price_sum += x.price * x.size;
            } else {
                short_total += x.size;
                short_price_sum += x.price * x.size;
            }
        }

        {
            let mut pos = position.write();
            pos.long_size = util::round_size(long_total);
            pos.short_size = util::round_size(short_total);
            pos.long_open_price = if long_total > 0.0 { long_price_sum / long_total } else { 0.0 };
            pos.short_open_price = if short_total > 0.0 { short_price_sum / short_total } else { 0.0 };
        }
    }
}

async fn handle_board_data(board_asks: &OrderBook, board_bids: &OrderBook, msg: &str) {
    let board: ws::Board = match serde_json::from_str(msg) {
        Ok(board) => board,
        _ => return,
    };

    let ask_pairs = board
        .asks
        .par_iter()
        .map(|x| (x.price as u64, x.size))
        .collect::<Vec<(u64, f64)>>();

    board_asks.write().extend(ask_pairs);

    let bid_pairs = board
        .bids
        .par_iter()
        .map(|x| (x.price as u64, x.size))
        .collect::<Vec<(u64, f64)>>();

    board_bids.write().extend(bid_pairs);
}

async fn handle_trade_data(executions: &Executions, msg: &str) {
    let item: ws::ExecutionItem = match serde_json::from_str(msg) {
        Ok(execution) => execution,
        _ => return,
    };

    let now = Utc::now().timestamp_millis();
    let size = if item.side == ws::Side::BUY { item.size } else { -item.size };
    executions.write().push((item.price as u64, size, now));
}

/// WebSocket接続を確立し、メッセージを処理する内部関数
async fn connect_and_process_websocket(
    board_asks: &OrderBook,
    board_bids: &OrderBook,
    executions: &Executions,
    last_ws_message: &LastWsMessage,
) -> Result<()> {
    let ws_url = Url::parse("wss://api.coin.z.com/ws/public/v1")
        .expect("Invalid WebSocket URL");
    let (socket, _) = connect_async(ws_url).await?;

    info!("Connected to websocket");

    let (mut write, mut read) = socket.split();

    let channels = vec![
        "orderbooks",
        "trades",
    ];

    for channel in &channels {
        let data = serde_json::json!({
            "command": "subscribe",
            "channel": channel,
            "symbol": "BTC_JPY"
        });

        write.send(Message::Text(data.to_string())).await?;
        info!("Subscribed to {}", channel);

        // GMO coin requires a few seconds delay due to subscription limit
        sleep(Duration::from_millis(5000)).await;
    }

    while let Some(msg) = read.next().await {
        let msg = msg?;

        let msg = match msg {
            tokio_tungstenite::tungstenite::Message::Text(s) => s,
            _ => continue,
        };

        let parsed: ws::Message = match serde_json::from_str(&msg) {
            Ok(parsed) => parsed,
            _ => continue,
        };

        // WebSocket最終受信時刻を更新
        *last_ws_message.write() = Utc::now().timestamp_millis();

        match parsed.channel {
            ws::Channel::Orderbooks => {
                handle_board_data(board_asks, board_bids, &msg).await;
            }
            ws::Channel::Trades => {
                handle_trade_data(executions, &msg).await;
            }
        }
    }
    Ok(())
}

/// WebSocket購読（自動再接続機能付き）
async fn subscribe_websocket(
    board_asks: &OrderBook,
    board_bids: &OrderBook,
    executions: &Executions,
    last_ws_message: &LastWsMessage,
) -> Result<()> {
    const MAX_RECONNECT_DELAY_SECS: u64 = 60;
    let mut reconnect_delay = Duration::from_secs(1);

    loop {
        match connect_and_process_websocket(board_asks, board_bids, executions, last_ws_message).await {
            Ok(_) => {
                warn!("WebSocket connection closed normally, reconnecting...");
                reconnect_delay = Duration::from_secs(1); // リセット
            }
            Err(e) => {
                error!("WebSocket error: {:?}, reconnecting in {:?}...", e, reconnect_delay);
            }
        }

        sleep(reconnect_delay).await;

        // 指数バックオフ（最大60秒）
        reconnect_delay = std::cmp::min(
            reconnect_delay * 2,
            Duration::from_secs(MAX_RECONNECT_DELAY_SECS)
        );
    }
}

async fn run(config: &BotConfig) {
    let trade_logger: Option<TradeLogger> = if config.trade_log_enabled {
        Some(TradeLogger::new(&config.log_dir))
    } else {
        None
    };

    let metrics_logger: Option<MetricsLogger> = if config.metrics_log_enabled {
        Some(MetricsLogger::new(&config.log_dir))
    } else {
        None
    };

    let orders = Arc::new(Mutex::new(HashMap::new()));
    let orders_ref = orders.clone();

    let position = Arc::new(RwLock::new(model::Position::new()));
    let position_ref = position.clone();

    let board_asks = Arc::new(RwLock::new(BTreeMap::new()));
    let board_asks_ref = board_asks.clone();

    let board_bids = Arc::new(RwLock::new(BTreeMap::new()));
    let board_bids_ref = board_bids.clone();

    let executions = Arc::new(RwLock::new(Vec::<(u64, f64, i64)>::new()));
    let executions_ref = executions.clone();

    let last_ws_message: LastWsMessage = Arc::new(RwLock::new(0i64));
    let last_ws_message_ws = last_ws_message.clone();
    let last_ws_message_trade = last_ws_message.clone();

    let config_ref = config.clone();
    let config_ref2 = config.clone();

    // Shared T_optimal for dynamic cancel interval (written by trade loop, read by cancel loop)
    let t_optimal_shared: SharedU64 = Arc::new(RwLock::new(config.order_cancel_ms));
    let t_optimal_cancel = t_optimal_shared.clone();
    let t_optimal_trade = t_optimal_shared;

    let trade_logger_cancel = trade_logger.clone();
    let trade_logger_trade = trade_logger.clone();

    // Shared ghost suppression: trade() sets it on ghost detection, get_position() skips writes during window
    let ghost_suppression: GhostSuppression = Arc::new(RwLock::new(None));
    let ghost_suppression_trade = ghost_suppression.clone();
    let ghost_suppression_position = ghost_suppression;

    // Share a single reqwest::Client across all tasks (connection pool reuse)
    let shared_client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .connect_timeout(std::time::Duration::from_secs(5))
        .build()
        .expect("Failed to create HTTP client");
    let client_cancel = shared_client.clone();
    let client_trade = shared_client.clone();
    let client_position = shared_client;

    tokio::select! {
        result = tokio::spawn(async move {
            if let Err(e) = cancel_child_order(&client_cancel, &config_ref, &orders, &trade_logger_cancel, &t_optimal_cancel).await {
                error!("cancel_child_order error: {:?}", e);
            }
        }) => {
            if let Err(e) = result {
                error!("cancel_child_order task panicked: {:?}", e);
            }
        }
        result = tokio::spawn(async move {
            if let Err(e) = trade(&client_trade, &config_ref2, &orders_ref, &position, &board_asks, &board_bids, &executions, &last_ws_message_trade, &trade_logger_trade, &metrics_logger, &t_optimal_trade, &ghost_suppression_trade).await {
                error!("trade error: {:?}", e);
            }
        }) => {
            if let Err(e) = result {
                error!("trade task panicked: {:?}", e);
            }
        }
        result = tokio::spawn(async move {
            if let Err(e) = get_position(&client_position, &position_ref, &ghost_suppression_position).await {
                error!("get_position error: {:?}", e);
            }
        }) => {
            if let Err(e) = result {
                error!("get_position task panicked: {:?}", e);
            }
        }
        result = tokio::spawn(async move {
            if let Err(e) = subscribe_websocket(&board_asks_ref, &board_bids_ref, &executions_ref, &last_ws_message_ws).await {
                error!("subscribe_websocket error: {:?}", e);
            }
        }) => {
            if let Err(e) = result {
                error!("subscribe_websocket task panicked: {:?}", e);
            }
        }
    }
}

fn main() {
    // トレーシング初期化 (RUST_LOG環境変数でログレベル制御)
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("trading_bot=info".parse().unwrap())
        )
        .init();

    // Note: 指定された注文がすでに変更中、取消中、取消済、全量約定、失効のいずれかの状態である場合、以下のエラーメッセージが表示されます。
    // "message_code":"ERR-5122","message_string":"The request is invalid due to the status of the specified order."
    let runtime = Builder::new_multi_thread()
        .worker_threads(4)
        .enable_all()
        .build()
        .expect("Failed to build tokio runtime");

    let config_path = std::env::var("BOT_CONFIG_PATH")
        .unwrap_or_else(|_| "src/trade-config.yaml".to_string());

    let yaml_str = fs::read_to_string(&config_path)
        .unwrap_or_else(|_| panic!("Failed to read config file: {}", config_path));
    let config: BotConfig = serde_yaml::from_str(&yaml_str)
        .expect("Failed to parse config file");

    info!("Config loaded: {:?}", config);
    runtime.block_on(run(&config));
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Position;

    #[test]
    fn rust_default_decimal_check1() {
        assert_eq!(1_000_000.0 + 0.2, 1_000_000.2);
    }

    #[test]
    fn rust_default_decimal_check2() {
        assert_eq!(0.01 + 0.3, 0.31);
    }

    #[test]
    fn rust_default_decimal_check3() {
        assert_eq!(0.000000001 + 0.231, 0.231000001);
    }

    #[test]
    fn rust_default_decimal_check4() {
        assert_eq!(0.015 / 2.0, 0.0075);
    }

    #[test]
    fn rust_default_decimal_check5() {
        assert_eq!(0.015 * 2.0, 0.03);
    }

    // ================================================================
    // Bug #1: ポジション追跡 - 両建て時にグロスで追跡すること
    // ================================================================

    #[test]
    fn test_position_tracking_both_sides() {
        // 買0.004 + 売0.004 の両建て状態をシミュレート
        // 正しい動作: gross tracking (各サイド独立集計)
        struct FakePosition {
            side: String,
            size: f64,
        }
        let response = vec![
            FakePosition { side: "BUY".to_string(), size: 0.002 },
            FakePosition { side: "BUY".to_string(), size: 0.002 },
            FakePosition { side: "SELL".to_string(), size: 0.003 },
            FakePosition { side: "SELL".to_string(), size: 0.001 },
        ];

        // Gross position tracking (same logic as fixed get_position)
        let mut long_total = 0.0;
        let mut short_total = 0.0;
        for x in &response {
            if x.side == "BUY" {
                long_total += x.size;
            } else {
                short_total += x.size;
            }
        }
        let long_size = crate::util::round_size(long_total);
        let short_size = crate::util::round_size(short_total);

        assert_eq!(long_size, 0.004, "long_size should track gross BUY positions");
        assert_eq!(short_size, 0.004, "short_size should track gross SELL positions");
    }

    #[test]
    fn test_position_tracking_net_vs_gross_regression() {
        // 旧バグのリグレッションテスト:
        // ネット計算だと両建て均等時にポジション=0と誤認する
        struct FakePosition {
            side: String,
            size: f64,
        }
        let response = vec![
            FakePosition { side: "BUY".to_string(), size: 0.004 },
            FakePosition { side: "SELL".to_string(), size: 0.004 },
        ];

        let mut long_total = 0.0;
        let mut short_total = 0.0;
        for x in &response {
            if x.side == "BUY" {
                long_total += x.size;
            } else {
                short_total += x.size;
            }
        }

        // ネット計算だとここが 0.0 になるバグがあった
        assert_ne!(long_total, 0.0, "gross tracking should NOT zero out equal positions");
        assert_eq!(crate::util::round_size(long_total), 0.004);
        assert_eq!(crate::util::round_size(short_total), 0.004);
    }

    #[test]
    fn test_position_tracking_one_side_only() {
        struct FakePosition {
            side: String,
            size: f64,
        }
        let response = vec![
            FakePosition { side: "BUY".to_string(), size: 0.001 },
            FakePosition { side: "BUY".to_string(), size: 0.001 },
        ];

        // グロス計算（正しいロジック）
        let mut long_total = 0.0;
        let mut short_total = 0.0;
        for x in &response {
            if x.side == "BUY" {
                long_total += x.size;
            } else {
                short_total += x.size;
            }
        }

        assert_eq!(crate::util::round_size(long_total), 0.002);
        assert_eq!(crate::util::round_size(short_total), 0.0);
    }

    // ================================================================
    // Bug #2: calculate_order_sizes - maxポジション時に0を返すこと
    // ================================================================

    #[test]
    fn test_order_size_at_max_position_returns_zero() {
        let pos = Position { long_size: 0.002, short_size: 0.0, ..Default::default() };
        let max_position_size = 0.002;
        let min_lot = 0.001;
        let max_lot = 0.001;
        let position_ratio = 0.9;

        let (buy_size, _sell_size) = calculate_order_sizes(
            &pos, max_position_size, min_lot, max_lot, position_ratio,
        );

        // maxポジション時、buy_sizeは0であるべき
        assert_eq!(buy_size, 0.0, "buy_size should be 0 when at max position");
    }

    #[test]
    fn test_order_size_above_max_position_returns_zero() {
        let pos = Position { long_size: 0.004, short_size: 0.004, ..Default::default() };
        let max_position_size = 0.002;
        let min_lot = 0.001;
        let max_lot = 0.001;
        let position_ratio = 0.9;

        let (buy_size, sell_size) = calculate_order_sizes(
            &pos, max_position_size, min_lot, max_lot, position_ratio,
        );

        assert_eq!(buy_size, 0.0, "buy_size should be 0 when above max position");
        assert_eq!(sell_size, 0.0, "sell_size should be 0 when above max position");
    }

    #[test]
    fn test_order_size_below_max_returns_min_lot() {
        let pos = Position { long_size: 0.0, short_size: 0.0, ..Default::default() };
        let max_position_size = 0.002;
        let min_lot = 0.001;
        let max_lot = 0.001;
        let position_ratio = 0.9;

        let (buy_size, sell_size) = calculate_order_sizes(
            &pos, max_position_size, min_lot, max_lot, position_ratio,
        );

        assert_eq!(buy_size, min_lot, "buy_size should be min_lot when no position");
        assert_eq!(sell_size, min_lot, "sell_size should be min_lot when no position");
    }

    #[test]
    fn test_order_size_caps_at_remaining() {
        // 残り0.001しかないのに0.001以上を返さないこと
        let pos = Position { long_size: 0.001, short_size: 0.0, ..Default::default() };
        let max_position_size = 0.002;
        let min_lot = 0.001;
        let max_lot = 0.001;
        let position_ratio = 0.9;

        let (buy_size, _) = calculate_order_sizes(
            &pos, max_position_size, min_lot, max_lot, position_ratio,
        );

        let remaining = max_position_size - pos.long_size;
        assert!(buy_size <= remaining,
            "buy_size {} should not exceed remaining capacity {}",
            buy_size, remaining);
    }

    // ================================================================
    // Bug #3: スプレッド調整 - 両建て均等時でもスプレッドが広がること
    // ================================================================

    #[test]
    fn test_spread_adj_neutral_position() {
        let pos = Position { long_size: 0.0, short_size: 0.0, ..Default::default() };
        let (buy_adj, sell_adj) = calculate_spread_adjustment(&pos, 0.002);
        assert_eq!(buy_adj, 1.0);
        assert_eq!(sell_adj, 1.0);
    }

    #[test]
    fn test_spread_adj_long_heavy() {
        let pos = Position { long_size: 0.002, short_size: 0.0, ..Default::default() };
        let (buy_adj, sell_adj) = calculate_spread_adjustment(&pos, 0.002);

        // ロング過多: 買スプレッド広がる(>1)
        assert!(buy_adj > 1.0, "buy spread should widen when long-heavy, got {}", buy_adj);
        // 売スプレッドは方向調整で狭まるが、exposure_penaltyで相殺される可能性あり
        assert!(sell_adj <= buy_adj, "sell adj should not exceed buy adj when long-heavy");
    }

    #[test]
    fn test_spread_adj_equal_positions_should_widen() {
        // Bug #3: 両建て均等でもスプレッドが広がるべき
        let pos = Position { long_size: 0.004, short_size: 0.004, ..Default::default() };
        let (buy_adj, sell_adj) = calculate_spread_adjustment(&pos, 0.002);

        // 両建て均等でも総エクスポージャーが大きいのでスプレッド広がるべき
        assert!(buy_adj > 1.0,
            "buy spread should widen with high total exposure, got {}",
            buy_adj);
        assert!(sell_adj > 1.0,
            "sell spread should widen with high total exposure, got {}",
            sell_adj);
    }

    #[test]
    fn test_spread_adj_half_max_meaningful_penalty() {
        // exposure_penaltyがmax_position_sizeで正規化され実効性があること
        let pos = Position { long_size: 0.001, short_size: 0.001, ..Default::default() };
        let (buy_adj, sell_adj) = calculate_spread_adjustment(&pos, 0.002);

        // 半分のポジション: 0.001/0.002 = 0.5 → penalty = 0.5 * 0.2 = 0.1
        // 両側均等なのでinventory_ratio=0, adj = 1.0 + 0 + 0.1 = 1.1
        assert!(buy_adj > 1.05,
            "half-max exposure should have meaningful penalty, got {}",
            buy_adj);
        assert!(sell_adj > 1.05,
            "half-max exposure should have meaningful penalty, got {}",
            sell_adj);
    }

    // ================================================================
    // Bug #4: position_penalty - 正しい方向で動作すること
    // ================================================================

    #[test]
    fn test_order_prices_penalty_direction_long_heavy() {
        let mid_price = 10_000_000.0;
        let best_pair = (
            FloatingExp::new(10.0, -4.0, 1.0), // buy spread = 0.01%
            FloatingExp::new(10.0, -4.0, 1.0), // sell spread = 0.01%
        );
        let min_lot = 0.001;

        // ニュートラル
        let neutral_pos = Position { long_size: 0.0, short_size: 0.0, ..Default::default() };
        let (neutral_buy, neutral_sell) = calculate_order_prices(
            mid_price, &best_pair, &neutral_pos, 50.0, min_lot,
        );

        // ロング過多
        let long_pos = Position { long_size: 0.002, short_size: 0.0, ..Default::default() };
        let (long_buy, long_sell) = calculate_order_prices(
            mid_price, &best_pair, &long_pos, 50.0, min_lot,
        );

        // ロング過多時: 買価格は下がるべき（買いを抑制）
        assert!(long_buy < neutral_buy,
            "buy price should decrease when long-heavy: {} should be < {}",
            long_buy, neutral_buy);
        // 売価格はニュートラルと同等以下（売りやすくする）
        assert!(long_sell <= neutral_sell,
            "sell price should not increase when long-heavy");
    }

    #[test]
    fn test_order_prices_penalty_direction_short_heavy() {
        let mid_price = 10_000_000.0;
        let best_pair = (
            FloatingExp::new(10.0, -4.0, 1.0),
            FloatingExp::new(10.0, -4.0, 1.0),
        );
        let min_lot = 0.001;

        // ニュートラル
        let neutral_pos = Position { long_size: 0.0, short_size: 0.0, ..Default::default() };
        let (_neutral_buy, neutral_sell) = calculate_order_prices(
            mid_price, &best_pair, &neutral_pos, 50.0, min_lot,
        );

        // ショート過多
        let short_pos = Position { long_size: 0.0, short_size: 0.002, ..Default::default() };
        let (_short_buy, short_sell) = calculate_order_prices(
            mid_price, &best_pair, &short_pos, 50.0, min_lot,
        );

        // ショート過多時: 売価格は上がるべき（売りを抑制）
        assert!(short_sell > neutral_sell,
            "sell price should increase when short-heavy: {} should be > {}",
            short_sell, neutral_sell);
    }

    // ================================================================
    // Bug #4: maxロット保持時に決済注文が出せなくなる
    // calculate_order_sizes が 0 を返すと should_buy/should_sell が
    // false になり、close注文もブロックされてしまう
    // ================================================================

    /// 決済注文に使うサイズを決定するヘルパー関数のテスト
    /// maxポジション時でも決済にはmin_lotを使うべき
    #[test]
    fn test_close_order_size_at_max_position() {
        let pos = Position { long_size: 0.01, short_size: 0.01, ..Default::default() };
        let max_position_size = 0.01;
        let min_lot = 0.001;
        let max_lot = 0.001;
        let position_ratio = 0.9;

        let (buy_size, sell_size) = calculate_order_sizes(
            &pos, max_position_size, min_lot, max_lot, position_ratio,
        );

        // 新規ポジション用サイズは0であるべき
        assert_eq!(buy_size, 0.0);
        assert_eq!(sell_size, 0.0);

        // 決済用サイズはmin_lotであるべき
        let close_buy_size = effective_order_size(buy_size, true, min_lot);
        let close_sell_size = effective_order_size(sell_size, true, min_lot);
        assert_eq!(close_buy_size, min_lot, "close buy should use min_lot even when open size is 0");
        assert_eq!(close_sell_size, min_lot, "close sell should use min_lot even when open size is 0");
    }

    #[test]
    fn test_asymmetric_max_position() {
        // Long at max, short has room
        let pos = Position { long_size: 0.01, short_size: 0.002, ..Default::default() };
        let max_position_size = 0.01;
        let min_lot = 0.001;
        let max_lot = 0.001;
        let position_ratio = 0.9;

        let (buy_size, sell_size) = calculate_order_sizes(
            &pos, max_position_size, min_lot, max_lot, position_ratio,
        );

        assert_eq!(buy_size, 0.0, "buy should be 0 at max long");
        assert!(sell_size >= min_lot, "sell should have positive size: {}", sell_size);

        // Close buy (to close short): min_lot fallback since buy_size is 0
        let eff_buy = effective_order_size(buy_size, true, min_lot);
        assert_eq!(eff_buy, min_lot, "close buy should fallback to min_lot");

        // Close sell (to close long): uses calculated size since sell_size >= min_lot
        let eff_sell = effective_order_size(sell_size, true, min_lot);
        assert_eq!(eff_sell, sell_size, "close sell should use calculated size");
    }

    #[test]
    fn test_open_order_size_uses_calculated() {
        let pos = Position { long_size: 0.002, short_size: 0.0, ..Default::default() };
        let max_position_size = 0.01;
        let min_lot = 0.001;
        let max_lot = 0.001;
        let position_ratio = 0.9;

        let (buy_size, _sell_size) = calculate_order_sizes(
            &pos, max_position_size, min_lot, max_lot, position_ratio,
        );

        // 新規注文は計算されたサイズを使う
        let open_size = effective_order_size(buy_size, false, min_lot);
        assert_eq!(open_size, buy_size, "open order should use calculated size");
    }

    // ================================================================
    // Volatility計算テスト (log-return stddev)
    // ================================================================

    #[test]
    fn test_volatility_empty_executions_returns_floor() {
        let executions: Vec<(u64, f64, i64)> = vec![];
        let vol = calculate_volatility(&executions);
        // 空のときはフロアを返す
        assert!(vol > 0.0, "empty executions should return volatility floor, got {}", vol);
    }

    #[test]
    fn test_volatility_single_execution_returns_floor() {
        let executions = vec![(6_500_000u64, 0.001, 1i64)];
        let vol = calculate_volatility(&executions);
        // 1データポイントでは標準偏差を計算できないのでフロアを返す
        assert!(vol > 0.0, "single execution should return volatility floor, got {}", vol);
    }

    #[test]
    fn test_volatility_same_price_returns_floor() {
        // 全て同じ価格 → log-return = 0 → stddev = 0 → フロアを返すべき
        let executions = vec![
            (6_500_000u64, 0.001, 1i64),
            (6_500_000, 0.001, 2),
            (6_500_000, 0.001, 3),
            (6_500_000, 0.001, 4),
            (6_500_000, 0.001, 5),
        ];
        let vol = calculate_volatility(&executions);
        assert!(vol > 0.0, "same-price executions should return volatility floor, got {}", vol);
    }

    #[test]
    fn test_volatility_varying_prices_returns_positive() {
        // 価格変動あり → 正のvolatilityを返すべき
        let executions = vec![
            (6_500_000u64, 0.001, 1i64),
            (6_501_000, 0.001, 2),
            (6_499_000, 0.001, 3),
            (6_502_000, 0.001, 4),
            (6_498_000, 0.001, 5),
        ];
        let vol = calculate_volatility(&executions);
        assert!(vol > 0.0, "varying prices should have positive volatility");
        // log-return stddevなので (max-min)/2 よりは小さいはず
        assert!(vol < 6_502_000.0, "volatility should be reasonable");
    }

    #[test]
    fn test_volatility_increases_with_larger_moves() {
        // 大きな価格変動 → より高いvolatility
        let small_moves = vec![
            (6_500_000u64, 0.001, 1i64),
            (6_500_100, 0.001, 2),
            (6_500_200, 0.001, 3),
            (6_500_100, 0.001, 4),
            (6_500_000, 0.001, 5),
        ];
        let large_moves = vec![
            (6_500_000u64, 0.001, 1i64),
            (6_510_000, 0.001, 2),
            (6_490_000, 0.001, 3),
            (6_510_000, 0.001, 4),
            (6_500_000, 0.001, 5),
        ];
        let vol_small = calculate_volatility(&small_moves);
        let vol_large = calculate_volatility(&large_moves);
        assert!(vol_large > vol_small,
            "larger moves should produce larger volatility: {} vs {}",
            vol_large, vol_small);
    }

    #[test]
    fn test_volatility_is_in_price_units() {
        // volatilityはEV計算で `expected_loss = one_sided_risk * volatility * alpha` として使われる
        // mid_price付近の値と比較して合理的な範囲であること
        let executions = vec![
            (6_500_000u64, 0.001, 1i64),
            (6_501_000, 0.001, 2),
            (6_499_000, 0.001, 3),
            (6_500_500, 0.001, 4),
            (6_499_500, 0.001, 5),
        ];
        let vol = calculate_volatility(&executions);
        // 価格が6.5M前後で±1000の動き → volatilityは数百〜数千程度が適切
        assert!(vol > 100.0, "volatility should be > 100 for ±1000 price moves, got {}", vol);
        assert!(vol < 100_000.0, "volatility should be < 100K, got {}", vol);
    }

    // ================================================================
    // max_position防御テスト - pending注文サイズを含めた判定
    // ================================================================

    #[test]
    fn test_pending_open_size_counts_open_orders_only() {
        let mut orders = HashMap::new();
        orders.insert("ord-1".to_string(), model::OrderInfo {
            price: 6_500_000, size: 0.001, side: OrderSide::BUY,
            timestamp: 0, is_close: false,
            mid_price: 6_500_000, t_optimal_ms: 3000, sigma_1s: 0.0001, spread_pct: 0.005,
        });
        orders.insert("ord-2".to_string(), model::OrderInfo {
            price: 6_500_000, size: 0.001, side: OrderSide::BUY,
            timestamp: 0, is_close: true, // close order
            mid_price: 6_500_000, t_optimal_ms: 3000, sigma_1s: 0.0001, spread_pct: 0.005,
        });
        orders.insert("ord-3".to_string(), model::OrderInfo {
            price: 6_500_000, size: 0.001, side: OrderSide::SELL,
            timestamp: 0, is_close: false,
            mid_price: 6_500_000, t_optimal_ms: 3000, sigma_1s: 0.0001, spread_pct: 0.005,
        });

        let buy_pending = pending_open_size(&orders, &OrderSide::BUY);
        let sell_pending = pending_open_size(&orders, &OrderSide::SELL);

        // Only non-close BUY order should count
        assert_eq!(buy_pending, 0.001, "only open buy orders count: {}", buy_pending);
        assert_eq!(sell_pending, 0.001, "only open sell orders count: {}", sell_pending);
    }

    #[test]
    fn test_pending_open_size_empty_orders() {
        let orders = HashMap::new();
        assert_eq!(pending_open_size(&orders, &OrderSide::BUY), 0.0);
        assert_eq!(pending_open_size(&orders, &OrderSide::SELL), 0.0);
    }

    #[test]
    fn test_effective_position_blocks_when_at_max() {
        // Scenario: local position = 0.001, pending open BUY = 0.001
        // effective_long = 0.002 >= max_position(0.002) → should NOT allow new buy
        let current_long = 0.001;
        let pending_buy = 0.001;
        let max_position = 0.002;
        let buy_size = 0.001;

        let effective_long = current_long + pending_buy;
        let can_open = effective_long + buy_size <= max_position;

        assert!(!can_open,
            "should block when effective position {} + order {} > max {}",
            effective_long, buy_size, max_position);
    }

    #[test]
    fn test_effective_position_allows_when_room() {
        // Scenario: local position = 0.0, no pending orders
        let current_long = 0.0;
        let pending_buy = 0.0;
        let max_position = 0.002;
        let buy_size = 0.001;

        let effective_long = current_long + pending_buy;
        let can_open = effective_long + buy_size <= max_position;

        assert!(can_open,
            "should allow when effective {} + order {} <= max {}",
            effective_long, buy_size, max_position);
    }

    #[test]
    fn test_effective_position_with_stale_data() {
        // Race condition scenario: position is stale (0.001), but pending open BUY exists
        // The pending order already filled → real position is 0.002
        // Without fix: 0.001 < 0.002 → allows another buy → 0.003!
        // With fix: 0.001 + 0.001 (pending) + 0.001 (new) = 0.003 > 0.002 → blocked ✓
        let current_long = 0.001; // stale: actual is 0.002
        let pending_buy = 0.001;  // this order already filled on exchange
        let max_position = 0.002;
        let buy_size = 0.001;

        let effective_long = current_long + pending_buy;
        let can_open = effective_long + buy_size <= max_position;

        assert!(!can_open,
            "with stale position and pending orders, should still block: effective={} + buy={} vs max={}",
            effective_long, buy_size, max_position);
    }

    // ================================================================
    // v0.9.5: 単一スロット動作テスト (max_position == min_lot == max_lot)
    // FIFOマッチ精度100%のための設定変更を検証
    // ================================================================

    #[test]
    fn test_single_slot_blocks_second_open() {
        // max_position = min_lot = max_lot = 0.001 → 1スロットのみ
        let pos = Position { long_size: 0.001, short_size: 0.0, ..Default::default() };
        let max_position_size = 0.001;
        let min_lot = 0.001;
        let max_lot = 0.001;
        let position_ratio = 0.9;

        let (buy_size, sell_size) = calculate_order_sizes(
            &pos, max_position_size, min_lot, max_lot, position_ratio,
        );

        // 1ポジション保持時、同方向の新規注文は0
        assert_eq!(buy_size, 0.0, "single-slot: should block second buy when holding 1 long");
        // 反対方向はまだ空き
        assert_eq!(sell_size, min_lot, "single-slot: sell should be available");
    }

    #[test]
    fn test_single_slot_close_still_works() {
        // max_position時でも決済注文は出せること
        let pos = Position { long_size: 0.001, short_size: 0.001, ..Default::default() };
        let max_position_size = 0.001;
        let min_lot = 0.001;
        let max_lot = 0.001;
        let position_ratio = 0.9;

        let (buy_size, sell_size) = calculate_order_sizes(
            &pos, max_position_size, min_lot, max_lot, position_ratio,
        );

        // 両方max → 新規注文サイズは0
        assert_eq!(buy_size, 0.0);
        assert_eq!(sell_size, 0.0);

        // 決済注文はmin_lotで出せる
        let close_buy = effective_order_size(buy_size, true, min_lot);
        let close_sell = effective_order_size(sell_size, true, min_lot);
        assert_eq!(close_buy, min_lot, "close buy should work at single-slot max");
        assert_eq!(close_sell, min_lot, "close sell should work at single-slot max");
    }

    #[test]
    fn test_single_slot_effective_position_blocks() {
        // 単一スロット: pending注文があればブロック
        let current_long = 0.0;
        let pending_buy = 0.001; // 1注文pending中
        let max_position = 0.001;
        let buy_size = 0.001;

        let effective_long = current_long + pending_buy;
        let can_open = effective_long + buy_size <= max_position;

        assert!(!can_open,
            "single-slot: pending order should block new buy: eff={} + size={} > max={}",
            effective_long, buy_size, max_position);
    }

    #[test]
    fn test_single_slot_empty_allows_one() {
        // 空ポジション: 1注文は許可
        let pos = Position { long_size: 0.0, short_size: 0.0, ..Default::default() };
        let max_position_size = 0.001;
        let min_lot = 0.001;
        let max_lot = 0.001;
        let position_ratio = 0.9;

        let (buy_size, sell_size) = calculate_order_sizes(
            &pos, max_position_size, min_lot, max_lot, position_ratio,
        );

        assert_eq!(buy_size, min_lot, "single-slot: should allow 1 buy when empty");
        assert_eq!(sell_size, min_lot, "single-slot: should allow 1 sell when empty");

        // effective positionチェックも通ること
        let can_open = 0.0 + buy_size <= max_position_size;
        assert!(can_open, "single-slot: first order should pass position check");
    }

    #[test]
    fn test_single_slot_spread_adjustment() {
        // 単一スロットでのスプレッド調整
        let pos = Position { long_size: 0.001, short_size: 0.0, ..Default::default() };
        let (buy_adj, sell_adj) = calculate_spread_adjustment(&pos, 0.001);

        // ロング保持 → 買スプレッド拡大
        assert!(buy_adj > 1.0,
            "single-slot long: buy spread should widen, got {}", buy_adj);
        // 売スプレッドは狭まるまたは同等
        assert!(sell_adj <= buy_adj,
            "single-slot long: sell adj should not exceed buy adj");
    }

    // ================================================================
    // Phase 1: ベイズ更新修正テスト
    // 各スプレッドレベルが異なる約定確率を持つべき
    // ================================================================

    #[test]
    fn test_bayesian_update_differentiates_levels() {
        // mid_price = 10,000,000 の場合:
        // level 1: buy_price = 10,000,000 - 10,000,000 * 0.00001 = 9,999,900 (狭い)
        // level 25: buy_price = 10,000,000 - 10,000,000 * 0.00025 = 9,997,500 (広い)
        //
        // 約定が 9,999,950 であった場合:
        // level 1 (buy@9,999,900): 9,999,950 <= 9,999,900? → NO (約定価格が注文価格より高い)
        // level 25 (buy@9,997,500): 9,999,950 <= 9,997,500? → NO
        //
        // 約定が 9,999,850 であった場合:
        // level 1 (buy@9,999,900): 9,999,850 <= 9,999,900? → YES (注文価格以下で約定)
        // level 25 (buy@9,997,500): 9,999,850 <= 9,997,500? → NO

        let mid_price = 10_000_000.0;
        let initial_bayes = BayesProb::new(
            BetaDistribution::new(0, 1),
            Duration::from_secs(300),
        );

        let mut buy_probs = BTreeMap::<FloatingExp, (f64, BayesProb)>::new();
        // Level 1 (tight): rate=1, calc()=0.00001
        let key1 = FloatingExp { base: 10.0, exp: -5.0, rate: 1.0 };
        // Level 25 (wide): rate=25, calc()=0.00025
        let key25 = FloatingExp { base: 10.0, exp: -5.0, rate: 25.0 };

        buy_probs.insert(key1.clone(), (0.0, initial_bayes.clone()));
        buy_probs.insert(key25.clone(), (0.0, initial_bayes.clone()));

        // Set order prices: buy_price = mid - mid * spread
        update_order_prices(&mut buy_probs, mid_price, |mp, calc| mp - mp * calc);

        // Verify prices are set correctly
        let price1 = buy_probs.get(&key1).unwrap().0;
        let price25 = buy_probs.get(&key25).unwrap().0;
        assert!((price1 - 9_999_900.0).abs() < 1.0, "level 1 price: {}", price1);
        assert!((price25 - 9_997_500.0).abs() < 1.0, "level 25 price: {}", price25);

        // Execution at 9,999,850 (below level 1's buy price, above level 25's)
        let executions: Vec<(u64, f64, i64)> = vec![(9_999_850, 0.001, 1)];

        // Update probabilities with per-level price check
        update_probabilities(&mut buy_probs, &executions, true);

        let prob1 = buy_probs.get(&key1).unwrap().1.calc_average();
        let prob25 = buy_probs.get(&key25).unwrap().1.calc_average();

        // Level 1 (tight, buy@9,999,900): execution at 9,999,850 IS below → filled → higher prob
        // Level 25 (wide, buy@9,997,500): execution at 9,999,850 NOT below → not filled → lower prob
        assert!(prob1 > prob25,
            "tight spread should have higher fill prob than wide: {} vs {}",
            prob1, prob25);
    }

    #[test]
    fn test_bayesian_update_no_executions_all_decrease() {
        let mid_price = 10_000_000.0;
        let initial_bayes = BayesProb::new(
            BetaDistribution::new(0, 1),
            Duration::from_secs(300),
        );

        let mut sell_probs = BTreeMap::<FloatingExp, (f64, BayesProb)>::new();
        let key1 = FloatingExp { base: 10.0, exp: -5.0, rate: 1.0 };
        sell_probs.insert(key1.clone(), (0.0, initial_bayes.clone()));

        update_order_prices(&mut sell_probs, mid_price, |mp, calc| mp + mp * calc);

        // No executions
        let executions: Vec<(u64, f64, i64)> = vec![];

        update_probabilities(&mut sell_probs, &executions, false);

        let prob = sell_probs.get(&key1).unwrap().1.calc_average();
        // With initial Be(0,1) and update(1, 0): Be(0, 2) → avg = 0 / (0+2) = 0.0
        assert!(prob < 0.5, "probability should decrease with no fills: {}", prob);
    }

    #[test]
    fn test_bayesian_update_sell_side_differentiates() {
        let mid_price = 10_000_000.0;
        let initial_bayes = BayesProb::new(
            BetaDistribution::new(0, 1),
            Duration::from_secs(300),
        );

        let mut sell_probs = BTreeMap::<FloatingExp, (f64, BayesProb)>::new();
        // Level 1 (tight): sell@10,000,100
        let key1 = FloatingExp { base: 10.0, exp: -5.0, rate: 1.0 };
        // Level 25 (wide): sell@10,002,500
        let key25 = FloatingExp { base: 10.0, exp: -5.0, rate: 25.0 };

        sell_probs.insert(key1.clone(), (0.0, initial_bayes.clone()));
        sell_probs.insert(key25.clone(), (0.0, initial_bayes.clone()));

        update_order_prices(&mut sell_probs, mid_price, |mp, calc| mp + mp * calc);

        // Execution at 10,000,200 (above level 1's sell price, below level 25's)
        let executions: Vec<(u64, f64, i64)> = vec![(10_000_200, 0.001, 1)];

        update_probabilities(&mut sell_probs, &executions, false);

        let prob1 = sell_probs.get(&key1).unwrap().1.calc_average();
        let prob25 = sell_probs.get(&key25).unwrap().1.calc_average();

        // Level 1 (sell@10,000,100): execution 10,000,200 >= 10,000,100 → YES → higher prob
        // Level 25 (sell@10,002,500): execution 10,000,200 >= 10,002,500 → NO → lower prob
        assert!(prob1 > prob25,
            "tight sell spread should have higher fill prob: {} vs {}",
            prob1, prob25);
    }

    // ================================================================
    // v0.9.3 Phase 0: T_optimal計算テスト
    // ================================================================

    #[test]
    fn test_calculate_t_optimal_level5_normal_vol() {
        // Level 5: spread_pct = 0.005%, sigma_1s = 0.003%
        // T = (0.005/0.003)² = 2.78s = 2780ms
        let spread_pct = 0.00005; // 0.005% as fraction
        let sigma_1s = 0.00003;   // 0.003% as fraction
        let t = calculate_t_optimal(spread_pct, sigma_1s, 2000, 30000);
        assert!(t >= 2000 && t <= 3000,
            "Level 5 normal vol should be ~2780ms, got {}ms", t);
    }

    #[test]
    fn test_calculate_t_optimal_level10_normal_vol() {
        // Level 10: spread_pct = 0.01%, sigma_1s = 0.003%
        // T = (0.01/0.003)² = 11.1s = 11111ms
        let spread_pct = 0.0001;
        let sigma_1s = 0.00003;
        let t = calculate_t_optimal(spread_pct, sigma_1s, 2000, 30000);
        assert!(t >= 10000 && t <= 12000,
            "Level 10 normal vol should be ~11111ms, got {}ms", t);
    }

    #[test]
    fn test_calculate_t_optimal_clamps_to_min() {
        // Very tight spread + high vol → T < min
        let spread_pct = 0.00001; // Level 1
        let sigma_1s = 0.0001;    // high vol
        let t = calculate_t_optimal(spread_pct, sigma_1s, 2000, 30000);
        assert_eq!(t, 2000, "should clamp to min 2000ms, got {}ms", t);
    }

    #[test]
    fn test_calculate_t_optimal_clamps_to_max() {
        // Wide spread + very low vol → T > max
        let spread_pct = 0.00025; // Level 25
        let sigma_1s = 0.000001;  // very low vol
        let t = calculate_t_optimal(spread_pct, sigma_1s, 2000, 30000);
        assert_eq!(t, 30000, "should clamp to max 30000ms, got {}ms", t);
    }

    #[test]
    fn test_calculate_t_optimal_zero_sigma_returns_max() {
        // Edge case: sigma=0 (shouldn't happen with volatility floor, but be safe)
        let spread_pct = 0.00005;
        let sigma_1s = 0.0;
        let t = calculate_t_optimal(spread_pct, sigma_1s, 2000, 30000);
        assert_eq!(t, 30000, "zero sigma should return max, got {}ms", t);
    }

    #[test]
    fn test_calculate_sigma_1s() {
        // volatility = 1000.0 (price units), mid_price = 10,000,000
        // sigma_1s = 1000 / 10,000,000 = 0.0001 = 0.01%
        // But we need to adjust for the interval: volatility is stddev over N samples in order_interval
        // sigma_1s = volatility / mid_price (as fraction)
        let volatility = 1000.0;
        let mid_price = 10_000_000.0;
        let sigma_1s: f64 = volatility / mid_price;
        assert!((sigma_1s - 0.0001).abs() < 1e-10,
            "sigma_1s should be 0.0001, got {}", sigma_1s);
    }

    // ================================================================
    // v0.9.3 Phase 1: position_penalty方向修正テスト
    // ================================================================

    #[test]
    fn test_penalty_affects_close_direction_long_held() {
        // BUG FIX: When holding long only, sell penalty should be non-zero
        let mid_price = 10_000_000.0;
        let best_pair = (
            FloatingExp::new(10.0, -5.0, 5.0),  // buy spread
            FloatingExp::new(10.0, -5.0, 5.0),  // sell spread
        );
        let position = Position { long_size: 0.001, short_size: 0.0, ..Default::default() };
        let penalty = 50.0;
        let min_lot = 0.001;

        let (_buy_price, sell_price) = calculate_order_prices(
            mid_price, &best_pair, &position, penalty, min_lot,
        );

        let base_ask = mid_price + best_pair.1.calc() * mid_price;

        // After fix: sell penalty should use long_size (the position we want to close)
        // sell_price should be LOWER than base_ask (closer to mid, easier to fill)
        // This tests the fixed direction
        assert!(sell_price != base_ask,
            "sell price should have penalty applied when long is held, sell={} base_ask={}",
            sell_price, base_ask);
    }

    #[test]
    fn test_penalty_affects_close_direction_short_held() {
        // When holding short only, buy penalty should be non-zero
        let mid_price = 10_000_000.0;
        let best_pair = (
            FloatingExp::new(10.0, -5.0, 5.0),
            FloatingExp::new(10.0, -5.0, 5.0),
        );
        let position = Position { long_size: 0.0, short_size: 0.001, ..Default::default() };
        let penalty = 50.0;
        let min_lot = 0.001;

        let (buy_price, _sell_price) = calculate_order_prices(
            mid_price, &best_pair, &position, penalty, min_lot,
        );

        let base_bid = mid_price - best_pair.0.calc() * mid_price;

        // After fix: buy penalty should use short_size (the position we want to close)
        // buy_price should be HIGHER than base_bid (closer to mid, easier to fill)
        assert!(buy_price != base_bid,
            "buy price should have penalty applied when short is held, buy={} base_bid={}",
            buy_price, base_bid);
    }

    #[test]
    fn test_penalty_zero_when_no_position() {
        // No position → no penalty on either side
        let mid_price = 10_000_000.0;
        let best_pair = (
            FloatingExp::new(10.0, -5.0, 5.0),
            FloatingExp::new(10.0, -5.0, 5.0),
        );
        let position = Position { long_size: 0.0, short_size: 0.0, ..Default::default() };
        let penalty = 50.0;
        let min_lot = 0.001;

        let (buy_price, sell_price) = calculate_order_prices(
            mid_price, &best_pair, &position, penalty, min_lot,
        );

        let base_bid = mid_price - best_pair.0.calc() * mid_price;
        let base_ask = mid_price + best_pair.1.calc() * mid_price;

        assert!((buy_price - base_bid).abs() < 1e-6,
            "no position: buy should equal base_bid, buy={} base_bid={}", buy_price, base_bid);
        assert!((sell_price - base_ask).abs() < 1e-6,
            "no position: sell should equal base_ask, sell={} base_ask={}", sell_price, base_ask);
    }

    // ================================================================
    // v0.10.0: Stop-loss P&L計算テスト
    // ================================================================

    #[test]
    fn test_stop_loss_pnl_long_position() {
        let pos = Position {
            long_size: 0.001, short_size: 0.0,
            long_open_price: 14_000_000.0, short_open_price: 0.0,
        };
        let mid_price = 13_995_000.0;
        let pnl = (mid_price - pos.long_open_price) * pos.long_size;
        // -5000 * 0.001 = -5.0 JPY
        assert!((pnl - (-5.0)).abs() < 0.01, "expected ~-5.0 JPY, got {}", pnl);
    }

    #[test]
    fn test_stop_loss_pnl_short_position() {
        let pos = Position {
            long_size: 0.0, short_size: 0.001,
            long_open_price: 0.0, short_open_price: 14_000_000.0,
        };
        let mid_price = 14_005_000.0;
        let pnl = (pos.short_open_price - mid_price) * pos.short_size;
        // -5000 * 0.001 = -5.0 JPY
        assert!((pnl - (-5.0)).abs() < 0.01, "expected ~-5.0 JPY, got {}", pnl);
    }

    #[test]
    fn test_stop_loss_both_sides_closes_worse_side() {
        // Both sides have positions: long losing more
        let long_pnl: f64 = -4.0; // long losing 4 JPY
        let short_pnl: f64 = -2.0; // short losing 2 JPY
        let total = long_pnl + short_pnl; // -6.0 JPY

        assert!(total < -5.0, "total pnl should trigger stop-loss");
        // Should close the side with worse P&L (long, since -4 < -2)
        assert!(long_pnl <= short_pnl, "long should be worse");
    }

    #[test]
    fn test_stop_loss_no_trigger_within_threshold() {
        let pos = Position {
            long_size: 0.001, short_size: 0.0,
            long_open_price: 14_000_000.0, short_open_price: 0.0,
        };
        let mid_price = 13_997_000.0; // -3000 * 0.001 = -3.0 JPY
        let pnl = (mid_price - pos.long_open_price) * pos.long_size;
        let threshold = 5.0;
        assert!(pnl >= -threshold, "pnl {} should NOT trigger stop-loss (threshold={})", pnl, threshold);
    }

    #[test]
    fn test_stop_loss_zero_open_price_skips() {
        // open_price=0 means position not yet tracked → should not compute P&L
        let pos = Position {
            long_size: 0.001, short_size: 0.0,
            long_open_price: 0.0, short_open_price: 0.0,
        };
        let min_lot = 0.001;
        let pnl = if pos.long_size >= min_lot && pos.long_open_price > 0.0 {
            (13_000_000.0 - pos.long_open_price) * pos.long_size
        } else {
            0.0
        };
        assert_eq!(pnl, 0.0, "zero open_price should yield 0 pnl");
    }

    // ================================================================
    // v0.10.0: Close spread factor pricing テスト
    // ================================================================

    #[test]
    fn test_close_pricing_more_aggressive_than_open() {
        let mid_price: f64 = 14_000_000.0;
        let buy_spread: f64 = 100.0; // 100 JPY from mid
        let sell_spread: f64 = 100.0;
        let close_spread_factor: f64 = 0.5;

        let open_buy = mid_price - buy_spread; // 13,999,900
        let close_buy = (mid_price - (buy_spread * close_spread_factor)).min(mid_price - 1.0); // 13,999,950

        let open_sell = mid_price + sell_spread; // 14,000,100
        let close_sell = (mid_price + (sell_spread * close_spread_factor)).max(mid_price + 1.0); // 14,000,050

        // Close prices should be closer to mid than open prices (more aggressive)
        assert!(close_buy > open_buy,
            "close buy should be closer to mid: close={} open={}", close_buy, open_buy);
        assert!(close_sell < open_sell,
            "close sell should be closer to mid: close={} open={}", close_sell, open_sell);
        // But still on the correct side of mid
        assert!(close_buy < mid_price, "close buy should be below mid");
        assert!(close_sell > mid_price, "close sell should be above mid");
    }

    #[test]
    fn test_close_pricing_safety_clamp() {
        // With very small spread, close price should not cross mid
        let mid_price: f64 = 14_000_000.0;
        let tiny_spread: f64 = 0.5; // 0.5 JPY from mid
        let close_spread_factor: f64 = 0.5;

        let close_buy = (mid_price - (tiny_spread * close_spread_factor)).min(mid_price - 1.0);
        let close_sell = (mid_price + (tiny_spread * close_spread_factor)).max(mid_price + 1.0);

        // Safety clamp ensures at least 1 JPY from mid
        assert!(close_buy <= mid_price - 1.0,
            "close buy should be at least 1 JPY below mid: {}", close_buy);
        assert!(close_sell >= mid_price + 1.0,
            "close sell should be at least 1 JPY above mid: {}", close_sell);
    }

    // ================================================================
    // v0.10.0: Position open_price tracking テスト
    // ================================================================

    #[test]
    fn test_position_open_price_weighted_average() {
        // Simulate two long positions at different prices
        // pos1: 0.001 BTC @ 14,000,000
        // pos2: 0.001 BTC @ 14,010,000
        // weighted avg = (14,000,000 * 0.001 + 14,010,000 * 0.001) / 0.002 = 14,005,000
        let long_total: f64 = 0.002;
        let long_price_sum: f64 = 14_000_000.0 * 0.001 + 14_010_000.0 * 0.001;
        let avg_price = long_price_sum / long_total;
        assert!((avg_price - 14_005_000.0_f64).abs() < 0.01,
            "weighted avg should be 14,005,000, got {}", avg_price);
    }

    #[test]
    fn test_position_open_price_zero_when_no_position() {
        let long_total = 0.0;
        let open_price = if long_total > 0.0 { 14_000_000.0 } else { 0.0 };
        assert_eq!(open_price, 0.0, "no position should have open_price 0");
    }

    // ================================================================
    // v0.10.1: ERR-422 ゴーストポジション修正テスト
    // ================================================================

    #[test]
    fn test_err_no_open_position_constant() {
        assert_eq!(ERR_NO_OPEN_POSITION, "ERR-422");
    }

    #[test]
    fn test_order_result_has_no_open_position_variant() {
        let result = OrderResult::NoOpenPosition;
        assert!(matches!(result, OrderResult::NoOpenPosition));
        // NoOpenPositionはMarginInsufficientではない
        assert!(!matches!(result, OrderResult::MarginInsufficient));
        assert!(!matches!(result, OrderResult::Success));
    }

    #[test]
    fn test_ghost_position_reset_logic() {
        // ゴースト検出時にpositionをゼロリセットすること
        let position = RwLock::new(Position {
            long_size: 0.001,
            short_size: 0.0,
            long_open_price: 14_000_000.0,
            short_open_price: 0.0,
        });

        // Ghost detected: ERR-422 → position reset
        {
            let mut pos = position.write();
            pos.long_size = 0.0;
            pos.short_size = 0.0;
            pos.long_open_price = 0.0;
            pos.short_open_price = 0.0;
        }

        let pos = position.read();
        assert_eq!(pos.long_size, 0.0, "ghost reset: long_size should be 0");
        assert_eq!(pos.short_size, 0.0, "ghost reset: short_size should be 0");
        assert_eq!(pos.long_open_price, 0.0, "ghost reset: long_open_price should be 0");
        assert_eq!(pos.short_open_price, 0.0, "ghost reset: short_open_price should be 0");
    }

    #[test]
    fn test_order_result_no_open_position_priority() {
        // NoOpenPositionはMarginInsufficientより優先されるべき
        // (send_orderのreturn logicを再現)
        let no_open_position = true;
        let margin_insufficient = true;
        let order_success = false;

        let result = if no_open_position {
            OrderResult::NoOpenPosition
        } else if margin_insufficient {
            OrderResult::MarginInsufficient
        } else if order_success {
            OrderResult::Success
        } else {
            OrderResult::OtherError
        };
        assert!(matches!(result, OrderResult::NoOpenPosition));
    }

    #[test]
    fn test_ghost_cooldown_extended_to_60s() {
        // ゴースト検出時のクールダウンはSTOP_LOSSの10秒ではなく60秒
        assert_eq!(GHOST_POSITION_COOLDOWN_SECS, 60);
        // STOP_LOSS_COOLDOWN_SECS=10 (trade loop内ローカル定数) より長いこと
        assert!(GHOST_POSITION_COOLDOWN_SECS > 10,
            "ghost cooldown {}s should exceed stop-loss cooldown 10s",
            GHOST_POSITION_COOLDOWN_SECS);
    }

    // ================================================================
    // v0.12.0: EWMA Volatility テスト
    // ================================================================

    #[test]
    fn test_ewma_volatility_basic() {
        let executions: Vec<(u64, f64, i64)> = vec![
            (14_000_000, 0.001, 1000),
            (14_000_100, 0.001, 2000),
            (14_000_050, 0.001, 3000),
        ];
        let vol = calculate_volatility(&executions);
        assert!(vol > 0.0, "volatility should be positive");
        assert!(vol < 1000.0, "volatility should be reasonable for small moves");
    }

    #[test]
    fn test_ewma_volatility_recency_weight() {
        // EWMA (λ=0.94) needs sufficient data to overcome seed bias.
        // Use 20+ calm points before/after the volatile shock so the
        // recency weighting dominates the initial seed.
        let base = 14_000_000u64;
        let calm_jitter = [0i64, 50, -30, 20, -10, 40, -20, 60, -50, 30,
                           10, -40, 25, -15, 35, -25, 45, -35, 55, -45];

        // Early volatile: shock at positions 0-1, then 20 calm ticks
        let mut early_volatile: Vec<(u64, f64, i64)> = Vec::new();
        let mut ts = 1000i64;
        early_volatile.push((base, 0.001, ts)); ts += 100;
        early_volatile.push((base + 10_000, 0.001, ts)); ts += 100; // big move
        early_volatile.push((base, 0.001, ts)); ts += 100; // revert
        for j in &calm_jitter {
            early_volatile.push(((base as i64 + j) as u64, 0.001, ts)); ts += 100;
        }

        // Late volatile: 20 calm ticks, then shock at the end
        let mut late_volatile: Vec<(u64, f64, i64)> = Vec::new();
        ts = 1000;
        late_volatile.push((base, 0.001, ts)); ts += 100;
        for j in &calm_jitter {
            late_volatile.push(((base as i64 + j) as u64, 0.001, ts)); ts += 100;
        }
        late_volatile.push((base + 10_000, 0.001, ts)); ts += 100; // big move
        late_volatile.push((base, 0.001, ts)); // revert

        let vol_early = calculate_volatility(&early_volatile);
        let vol_late = calculate_volatility(&late_volatile);

        // EWMA should give higher vol when recent data is volatile
        assert!(vol_late > vol_early,
            "EWMA should weight recent volatility higher: late={} early={}",
            vol_late, vol_early);
    }

    #[test]
    fn test_ewma_volatility_minimum_floor() {
        // Constant prices should still return minimum floor
        let executions: Vec<(u64, f64, i64)> = vec![
            (14_000_000, 0.001, 1000),
            (14_000_000, 0.001, 2000),
            (14_000_000, 0.001, 3000),
        ];
        let vol = calculate_volatility(&executions);
        let min_vol = 14_000_000.0 * MIN_VOLATILITY_BPS;
        assert!(vol >= min_vol,
            "volatility {} should be >= floor {}", vol, min_vol);
    }

    #[test]
    fn test_ewma_volatility_single_point() {
        let executions: Vec<(u64, f64, i64)> = vec![
            (14_000_000, 0.001, 1000),
        ];
        let vol = calculate_volatility(&executions);
        assert!(vol > 0.0);
    }

    #[test]
    fn test_ewma_volatility_empty() {
        let executions: Vec<(u64, f64, i64)> = vec![];
        let vol = calculate_volatility(&executions);
        // Empty should use default price floor
        assert!(vol > 0.0);
    }

    // ================================================================
    // v0.12.0: 時間帯フィルタ テスト
    // ================================================================

    #[test]
    fn test_trading_hours_utc_0_to_14() {
        // UTC 0-14 (JST 9-23) should be trading hours
        for hour in 0..15 {
            assert!(is_trading_hour(hour),
                "UTC {} should be in trading hours", hour);
        }
    }

    #[test]
    fn test_no_trading_utc_15_to_23() {
        // UTC 15-23 (JST 0-8) should not be trading hours
        for hour in 15..24 {
            assert!(!is_trading_hour(hour),
                "UTC {} should NOT be in trading hours", hour);
        }
    }

    #[test]
    fn test_trading_hour_boundary() {
        assert!(is_trading_hour(14), "UTC 14 = last trading hour");
        assert!(!is_trading_hour(15), "UTC 15 = first blocked hour");
        assert!(!is_trading_hour(24), "out-of-range hour should be blocked");
    }

    // ================================================================
    // v0.12.0: Ghost Position close gating テスト
    // ================================================================

    #[test]
    fn test_close_order_suppressed_during_ghost_cooldown() {
        // Ghost cooldown (60s) suppresses close orders
        let ghost_cooldown_until = Some(Instant::now() + Duration::from_secs(60));
        let ghost_cooldown_active = ghost_cooldown_until
            .map_or(false, |until| Instant::now() < until);
        assert!(ghost_cooldown_active, "ghost cooldown should be active");

        let current_position = Position {
            long_size: 0.001, short_size: 0.0,
            long_open_price: 14_000_000.0, short_open_price: 0.0,
        };
        let min_lot = 0.001;
        let should_close_long = !ghost_cooldown_active && current_position.long_size >= min_lot;
        let should_close_short = !ghost_cooldown_active && current_position.short_size >= min_lot;
        assert!(!should_close_long, "close_long should be suppressed during ghost cooldown");
        assert!(!should_close_short, "close_short should be suppressed (no position)");
    }

    #[test]
    fn test_close_order_allowed_during_sl_cooldown_without_ghost() {
        // SL cooldown (10s) should NOT suppress close orders - only ghost cooldown does
        // This tests the CRITICAL-2 fix: SL and ghost cooldowns are separate
        let _stop_loss_cooldown_until = Some(Instant::now() + Duration::from_secs(10));
        let ghost_cooldown_until: Option<Instant> = None; // no ghost cooldown
        let ghost_cooldown_active = ghost_cooldown_until
            .map_or(false, |until| Instant::now() < until);
        assert!(!ghost_cooldown_active, "ghost cooldown should NOT be active");

        let current_position = Position {
            long_size: 0.001, short_size: 0.0,
            long_open_price: 14_000_000.0, short_open_price: 0.0,
        };
        let min_lot = 0.001;
        let should_close_long = !ghost_cooldown_active && current_position.long_size >= min_lot;
        assert!(should_close_long, "close should be allowed during SL-only cooldown");
    }

    #[test]
    fn test_close_order_allowed_after_ghost_cooldown() {
        let ghost_cooldown_until: Option<Instant> = None;
        let ghost_cooldown_active = ghost_cooldown_until
            .map_or(false, |until| Instant::now() < until);
        assert!(!ghost_cooldown_active, "no cooldown should be active");

        let current_position = Position {
            long_size: 0.001, short_size: 0.0,
            long_open_price: 14_000_000.0, short_open_price: 0.0,
        };
        let min_lot = 0.001;
        let should_close_long = !ghost_cooldown_active && current_position.long_size >= min_lot;
        assert!(should_close_long, "close should be allowed when no cooldown active");
    }

    #[test]
    fn test_close_order_allowed_with_expired_cooldown() {
        // Cooldown already expired (in the past)
        let ghost_cooldown_until = Some(Instant::now() - Duration::from_secs(1));
        let ghost_cooldown_active = ghost_cooldown_until
            .map_or(false, |until| Instant::now() < until);
        assert!(!ghost_cooldown_active, "expired cooldown should not be active");

        let current_position = Position {
            long_size: 0.0, short_size: 0.001,
            long_open_price: 0.0, short_open_price: 14_000_000.0,
        };
        let min_lot = 0.001;
        let should_close_short = !ghost_cooldown_active && current_position.short_size >= min_lot;
        assert!(should_close_short, "close_short should be allowed after expired cooldown");
    }

    // ================================================================
    // v0.12.0: Ghost Suppression get_position テスト
    // ================================================================

    #[test]
    fn test_ghost_suppression_type() {
        // Verify GhostSuppression type works correctly
        let suppression: GhostSuppression = Arc::new(RwLock::new(None));

        // Initially no suppression
        assert!(suppression.read().is_none());

        // Set suppression
        *suppression.write() = Some(Instant::now() + Duration::from_secs(60));
        assert!(suppression.read().is_some());

        // Check if within suppression window
        let until = (*suppression.read()).unwrap();
        assert!(Instant::now() < until, "should be within suppression window");
    }

    #[test]
    fn test_ghost_suppression_expired() {
        let suppression: GhostSuppression = Arc::new(RwLock::new(
            Some(Instant::now() - Duration::from_secs(1))
        ));

        // Suppression window has passed
        let until = (*suppression.read()).unwrap();
        assert!(Instant::now() >= until, "suppression should have expired");
    }
}
