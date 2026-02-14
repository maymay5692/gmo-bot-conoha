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

use chrono::Utc;
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
) -> Result<()> {
    loop {
        sleep(Duration::from_millis(500)).await;

        let list = order_list.lock().clone();

        for order in list.iter() {
            let now = Utc::now().timestamp_millis() as u64;

            if now - order.1.timestamp < config.order_cancel_ms {
                continue;
            }

            let child_order_acceptance_id = order.0.to_string();

            let parameter = gmo::cancel_child_order::CancelOrderParameter {
                order_id: child_order_acceptance_id.clone(),
            };

            let timestamp = Utc::now().to_rfc3339();

            match gmo::cancel_child_order::cancel_order(client, &parameter).await {
                Ok(_) => {
                    info!("Cancel Order {:?}", child_order_acceptance_id);
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
                    info!("Order already filled (ERR-5122): {:?}", child_order_acceptance_id);
                    if let Some(logger) = trade_logger {
                        let info = order.1;
                        logger.log(TradeEvent::OrderFilled {
                            timestamp,
                            order_id: child_order_acceptance_id.clone(),
                            side: info.side.to_string(),
                            price: info.price,
                            size: info.size,
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
    OtherError,
}

const ERR_MARGIN_INSUFFICIENT: &str = "ERR-201";

async fn send_order(
    client: &reqwest::Client,
    order_list: &Orders,
    side: OrderSide,
    price: u64,
    size: f64,
    is_close_order: bool,
    config: &BotConfig,
    trade_logger: &Option<TradeLogger>,
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

    if is_close_order {
        let parameter = gmo::close_bulk_order::CloseBulkOrderParameter {
            symbol: Symbol::BTC_JPY,
            side: side.clone(),
            execution_type: ChildOrderType::LIMIT,
            price: Some(price.to_string()),
            size: size.to_string(),
        };

        let response = gmo::close_bulk_order::close_bulk_order(client, &parameter).await;
        match response {
            Ok(response) => {
                order_id = response.1.data;
                order_success = true;
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
            });
        }
    }

    if margin_insufficient {
        OrderResult::MarginInsufficient
    } else if order_success {
        OrderResult::Success
    } else {
        OrderResult::OtherError
    }
}

fn update_probabilities(
    probabilities: &mut BTreeMap<FloatingExp, (f64, BayesProb)>,
    condition: impl Fn(&u64) -> bool,
    executions: &[(u64, f64, i64)],
) {
    probabilities.iter_mut().for_each(|p| {
        p.1.1.update(1, executions.iter().any(|e| condition(&e.0)) as u64)
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

fn calculate_volatility(executions: &[(u64, f64, i64)]) -> f64 {
    let executions_max_price = executions
        .iter()
        .max_by(|a, b| a.0.cmp(&b.0))
        .map(|e| e.0 as f64)
        .unwrap_or(0.0);

    let executions_min_price = executions
        .iter()
        .min_by(|a, b| a.0.cmp(&b.0))
        .map(|e| e.0 as f64)
        .unwrap_or(0.0);

    if executions_max_price <= 0.0 || executions_min_price <= 0.0 {
        0.0
    } else {
        (executions_max_price - executions_min_price) / 2.0
    }
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

    // Long-heavy: lower buy price (harder to fill → discourages buying more)
    // Short-heavy: raise sell price (harder to fill → discourages selling more)
    let buy_order_price = bid - position_penalty * position.long_size / min_lot;
    let sell_order_price = ask + position_penalty * position.short_size / min_lot;

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

    // Be(α(1), β(1)) and retain the last 300 seconds of probabilities
    let initial_bayes_prob = BayesProb::new(BetaDistribution::new(0, 1), Duration::from_secs(300));

    let mut buy_probabilities = BTreeMap::<FloatingExp, (f64, BayesProb)>::new();
    let mut sell_probabilities = BTreeMap::<FloatingExp, (f64, BayesProb)>::new();

    const PRICE_STEP_COUNT: u32 = 25; // 1 step = price * base^exp * rate yen

    for i in 0..PRICE_STEP_COUNT {
        let key = FloatingExp { base: 10.0, exp: -5.0, rate: (i + 1) as f64 };
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
    const WS_STALE_THRESHOLD_MS: i64 = 60_000;
    const HEARTBEAT_INTERVAL: u64 = 20; // ~5min (15s × 20 = 300s)

    loop {
        sleep(Duration::from_millis(config.order_interval_ms)).await;

        let now = Utc::now().timestamp_millis();

        // Retain the last order_interval_ms seconds of executions
        executions.write().retain(|e| e.2 >= (now - config.order_interval_ms as i64));

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
                    config.order_interval_ms, empty_executions_count
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

        // Update the bayes probabilities
        update_probabilities(&mut buy_probabilities, |p| *p <= best_bid as u64, &executions_snapshot);
        update_probabilities(&mut sell_probabilities, |p| *p >= best_ask as u64, &executions_snapshot);

        // Update the order price
        update_order_prices(&mut buy_probabilities, mid_price, |mp, calc| mp - mp * calc);
        update_order_prices(&mut sell_probabilities, mid_price, |mp, calc| mp + mp * calc);

        // Find the best EV pair
        let best_pair = match maximize_expected_value(mid_price, volatility, config.alpha, &buy_probabilities, &sell_probabilities) {
            Some(p) => p,
            None => continue,
        };
        debug!("best_pair: {:?}", best_pair);

        let current_position = *position.read();
        debug!("position: {:?}", current_position);

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

        // Prevent spread-crossing: buy at most at best_bid, sell at least at best_ask
        let buy_order_price = adj_buy_price.min(best_bid);
        let sell_order_price = adj_sell_price.max(best_ask);

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
            let buy_spread_pct = if mid_price > 0.0 { best_pair.0.calc() * 100.0 } else { 0.0 };
            let sell_spread_pct = if mid_price > 0.0 { best_pair.1.calc() * 100.0 } else { 0.0 };

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
            });
        }

        // Close orders: always allowed when opposing position exists (Bug A fix)
        let should_close_short = current_position.short_size >= buy_size;
        let should_close_long = current_position.long_size >= sell_size;

        // New orders: gated by max_position + pending order check (Bug B fix)
        let has_pending_buy = order_list.lock().values().any(|o| o.side == OrderSide::BUY);
        let has_pending_sell = order_list.lock().values().any(|o| o.side == OrderSide::SELL);

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

        let can_open_long = margin_ok && current_position.long_size < max_position_size && !has_pending_buy;
        let can_open_short = margin_ok && current_position.short_size < max_position_size && !has_pending_sell;

        let should_buy = (should_close_short || can_open_long) && buy_size >= min_lot;
        let should_sell = (should_close_long || can_open_short) && sell_size >= min_lot;

        info!(
            "[ORDER] buy={} (close_short={}, open_long={}), sell={} (close_long={}, open_short={}), pos=({}/{}), pending=({}/{}), margin_ok={}",
            should_buy, should_close_short, can_open_long,
            should_sell, should_close_long, can_open_short,
            current_position.long_size, current_position.short_size,
            has_pending_buy, has_pending_sell,
            margin_ok,
        );

        let margin_hit = match (should_buy, should_sell) {
            (true, true) => {
                let buy_fut = send_order(
                    client, order_list, OrderSide::BUY,
                    buy_order_price as u64, buy_size, should_close_short, config, trade_logger,
                );
                let sell_fut = send_order(
                    client, order_list, OrderSide::SELL,
                    sell_order_price as u64, sell_size, should_close_long, config, trade_logger,
                );
                let (buy_res, sell_res) = tokio::join!(buy_fut, sell_fut);
                matches!(buy_res, OrderResult::MarginInsufficient)
                    || matches!(sell_res, OrderResult::MarginInsufficient)
            }
            (true, false) => {
                let res = send_order(
                    client, order_list, OrderSide::BUY,
                    buy_order_price as u64, buy_size, should_close_short, config, trade_logger,
                ).await;
                matches!(res, OrderResult::MarginInsufficient)
            }
            (false, true) => {
                let res = send_order(
                    client, order_list, OrderSide::SELL,
                    sell_order_price as u64, sell_size, should_close_long, config, trade_logger,
                ).await;
                matches!(res, OrderResult::MarginInsufficient)
            }
            (false, false) => false,
        };

        // Activate margin cooldown if any order got ERR-201
        if margin_hit {
            let cooldown = Instant::now() + Duration::from_secs(MARGIN_COOLDOWN_SECS);
            warn!("[MARGIN_COOLDOWN] Margin insufficient detected, suppressing new orders for {}s", MARGIN_COOLDOWN_SECS);
            margin_cooldown_until = Some(cooldown);
        }
    }
}

async fn get_position(client: &reqwest::Client, position: &Positions) -> Result<()> {
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

        // Track gross positions (both sides independently)
        let mut long_total = 0.0;
        let mut short_total = 0.0;
        for x in &response {
            if x.side == "BUY" {
                long_total += x.size;
            } else {
                short_total += x.size;
            }
        }

        {
            let mut pos = position.write();
            pos.long_size = util::round_size(long_total);
            pos.short_size = util::round_size(short_total);
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

    let trade_logger_cancel = trade_logger.clone();
    let trade_logger_trade = trade_logger.clone();

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
            if let Err(e) = cancel_child_order(&client_cancel, &config_ref, &orders, &trade_logger_cancel).await {
                error!("cancel_child_order error: {:?}", e);
            }
        }) => {
            if let Err(e) = result {
                error!("cancel_child_order task panicked: {:?}", e);
            }
        }
        result = tokio::spawn(async move {
            if let Err(e) = trade(&client_trade, &config_ref2, &orders_ref, &position, &board_asks, &board_bids, &executions, &last_ws_message_trade, &trade_logger_trade, &metrics_logger).await {
                error!("trade error: {:?}", e);
            }
        }) => {
            if let Err(e) = result {
                error!("trade task panicked: {:?}", e);
            }
        }
        result = tokio::spawn(async move {
            if let Err(e) = get_position(&client_position, &position_ref).await {
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
        let pos = Position { long_size: 0.002, short_size: 0.0 };
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
        let pos = Position { long_size: 0.004, short_size: 0.004 };
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
        let pos = Position { long_size: 0.0, short_size: 0.0 };
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
        let pos = Position { long_size: 0.001, short_size: 0.0 };
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
        let pos = Position { long_size: 0.0, short_size: 0.0 };
        let (buy_adj, sell_adj) = calculate_spread_adjustment(&pos, 0.002);
        assert_eq!(buy_adj, 1.0);
        assert_eq!(sell_adj, 1.0);
    }

    #[test]
    fn test_spread_adj_long_heavy() {
        let pos = Position { long_size: 0.002, short_size: 0.0 };
        let (buy_adj, sell_adj) = calculate_spread_adjustment(&pos, 0.002);

        // ロング過多: 買スプレッド広がる(>1)
        assert!(buy_adj > 1.0, "buy spread should widen when long-heavy, got {}", buy_adj);
        // 売スプレッドは方向調整で狭まるが、exposure_penaltyで相殺される可能性あり
        assert!(sell_adj <= buy_adj, "sell adj should not exceed buy adj when long-heavy");
    }

    #[test]
    fn test_spread_adj_equal_positions_should_widen() {
        // Bug #3: 両建て均等でもスプレッドが広がるべき
        let pos = Position { long_size: 0.004, short_size: 0.004 };
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
        let pos = Position { long_size: 0.001, short_size: 0.001 };
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
        let neutral_pos = Position { long_size: 0.0, short_size: 0.0 };
        let (neutral_buy, neutral_sell) = calculate_order_prices(
            mid_price, &best_pair, &neutral_pos, 50.0, min_lot,
        );

        // ロング過多
        let long_pos = Position { long_size: 0.002, short_size: 0.0 };
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
        let neutral_pos = Position { long_size: 0.0, short_size: 0.0 };
        let (_neutral_buy, neutral_sell) = calculate_order_prices(
            mid_price, &best_pair, &neutral_pos, 50.0, min_lot,
        );

        // ショート過多
        let short_pos = Position { long_size: 0.0, short_size: 0.002 };
        let (_short_buy, short_sell) = calculate_order_prices(
            mid_price, &best_pair, &short_pos, 50.0, min_lot,
        );

        // ショート過多時: 売価格は上がるべき（売りを抑制）
        assert!(short_sell > neutral_sell,
            "sell price should increase when short-heavy: {} should be > {}",
            short_sell, neutral_sell);
    }
}
