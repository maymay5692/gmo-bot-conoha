pub mod api;
pub mod bayes_prob;
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

use crate::api::gmo;
use crate::api::gmo::ws;
use crate::bayes_prob::{BayesProb, BetaDistribution};
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
    buy: &BTreeMap<FloatingExp, (f64, BayesProb)>,
    sell: &BTreeMap<FloatingExp, (f64, BayesProb)>,
) -> Option<(FloatingExp, FloatingExp)> {
    let mut best_pair = None;
    let mut best_expected_value = f64::NEG_INFINITY;

    // Risk aversion coefficient (0 <= alpha)
    let alpha = 0.9;

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

async fn cancel_child_order(client: &reqwest::Client, config: &BotConfig, order_list: &Orders) -> Result<()> {
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

            _ = gmo::cancel_child_order::cancel_order(client, &parameter).await;
            info!("Cancel Order {:?}", child_order_acceptance_id);
            if list.contains_key(&child_order_acceptance_id) {
                order_list.lock().remove(&child_order_acceptance_id);
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

async fn send_order(
    client: &reqwest::Client,
    order_list: &Orders,
    side: OrderSide,
    price: u64,
    size: f64,
    is_close_order: bool,
    config: &BotConfig,
) -> Result<()> {
    // バリデーション
    if let Err(reason) = validate_order_params(price, size, config) {
        warn!("Invalid Order: {} - side={:?} price={} size={}", reason, side, price, size);
        return Ok(());
    }

    let mut order_id = String::new();
    let mut order_success = false;

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
            Err(e) => {
                error!("Close Order Failed {:?}", e);
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
            Err(e) => {
                error!("Send Order Failed {:?}", e);
            }
        }
    }

    // 成功した場合のみ注文リストに追加
    if order_success && !order_id.is_empty() {
        let order_info = model::OrderInfo {
            price,
            size,
            side,
            timestamp: Utc::now().timestamp_millis() as u64,
        };

        if is_close_order {
            info!("Close Order sent: id={} {:?}", order_id, order_info);
        } else {
            info!("Send Order sent: id={} {:?}", order_id, order_info);
        }

        order_list.lock().insert(order_id, order_info);
    }

    Ok(())
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

fn calculate_order_prices(
    mid_price: f64,
    best_pair: &(FloatingExp, FloatingExp),
    position: &Position,
    position_penalty: f64,
    min_lot: f64,
) -> (f64, f64) {
    let bid = mid_price - best_pair.0.calc() * mid_price;
    let ask = mid_price + best_pair.1.calc() * mid_price;

    let buy_order_price = bid + position_penalty * position.long_size / min_lot;
    let sell_order_price = ask - position_penalty * position.short_size / min_lot;

    (buy_order_price, sell_order_price)
}

fn calculate_order_sizes(
    position: &Position,
    max_position_size: f64,
    min_lot: f64,
    max_lot: f64,
    position_ratio: f64,
) -> (f64, f64) {
    let buy_size = util::round_size(
        max_lot * (1.0 - position.long_size.powf(position_ratio) / max_position_size),
    )
    .max(min_lot);

    let sell_size = util::round_size(
        max_lot * (1.0 - position.short_size.powf(position_ratio) / max_position_size),
    )
    .max(min_lot);

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
) -> Result<()> {
    const MAX_KEEP_BOARD_PRICE: u64 = 100_000;
    let max_position_size: f64 = config.max_position;
    let min_lot: f64 = config.min_lot;
    let max_lot: f64 = config.max_lot;
    let position_ratio: f64 = config.position_ratio;

    let collateral = match gmo::get_collateral::get_collateral(client).await {
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

    loop {
        sleep(Duration::from_millis(config.order_interval_ms)).await;

        let now = Utc::now().timestamp_millis();

        // Retain the last order_interval_ms seconds of executions
        executions.write().retain(|e| e.2 >= (now - config.order_interval_ms as i64));

        let executions_snapshot = executions.read().clone();

        if executions_snapshot.is_empty() {
            continue;
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

        // Update the bayes probabilities
        update_probabilities(&mut buy_probabilities, |p| *p <= best_bid as u64, &executions_snapshot);
        update_probabilities(&mut sell_probabilities, |p| *p >= best_ask as u64, &executions_snapshot);

        // Update the order price
        update_order_prices(&mut buy_probabilities, mid_price, |mp, calc| mp - mp * calc);
        update_order_prices(&mut sell_probabilities, mid_price, |mp, calc| mp + mp * calc);

        // Find the best EV pair
        let best_pair = match maximize_expected_value(mid_price, volatility, &buy_probabilities, &sell_probabilities) {
            Some(p) => p,
            None => continue,
        };
        debug!("best_pair: {:?}", best_pair);

        let current_position = *position.read();
        debug!("position: {:?}", current_position);

        let position_penalty = 0.0;
        debug!("position_penalty: {:?}", position_penalty);

        let (buy_order_price, sell_order_price) = calculate_order_prices(
            mid_price,
            &best_pair,
            &current_position,
            position_penalty,
            min_lot,
        );

        let (buy_size, sell_size) = calculate_order_sizes(
            &current_position,
            max_position_size,
            min_lot,
            max_lot,
            position_ratio,
        );

        if current_position.long_size < max_position_size {
            let is_close_order = current_position.short_size >= buy_size;
            _ = send_order(
                client,
                order_list,
                OrderSide::BUY,
                buy_order_price as u64,
                buy_size,
                is_close_order,
                config,
            )
            .await;
        }

        if current_position.short_size < max_position_size {
            let is_close_order = current_position.long_size >= sell_size;
            _ = send_order(
                client,
                order_list,
                OrderSide::SELL,
                sell_order_price as u64,
                sell_size,
                is_close_order,
                config,
            )
            .await;
        }
    }
}

async fn get_position(client: &reqwest::Client, position: &Positions) -> Result<()> {
    loop {
        sleep(Duration::from_secs(10)).await;

        let response =
            match gmo::get_position::get_position(client, Symbol::BTC_JPY).await {
                Ok(response) => response.data.unwrap_or_default().list.unwrap_or_default(),
                Err(e) => {
                    error!("Position fetch error: {:?}", e);
                    continue;
                }
            };

        let total_position = response.iter().fold(0.0, |acc, x| {
            acc + if x.side == "BUY" { x.size } else { -x.size }
        });

        position.write().short_size = if total_position < 0.0 {
            -util::round_size(total_position)
        } else {
            0.0
        };

        position.write().long_size = if total_position > 0.0 {
            util::round_size(total_position)
        } else {
            0.0
        };
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
) -> Result<()> {
    const MAX_RECONNECT_DELAY_SECS: u64 = 60;
    let mut reconnect_delay = Duration::from_secs(1);

    loop {
        match connect_and_process_websocket(board_asks, board_bids, executions).await {
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

    let config_ref = config.clone();
    let config_ref2 = config.clone();

    tokio::select! {
        result = tokio::spawn(async move {
            if let Err(e) = cancel_child_order(&reqwest::Client::new(), &config_ref, &orders).await {
                error!("cancel_child_order error: {:?}", e);
            }
        }) => {
            if let Err(e) = result {
                error!("cancel_child_order task panicked: {:?}", e);
            }
        }
        result = tokio::spawn(async move {
            if let Err(e) = trade(&reqwest::Client::new(), &config_ref2, &orders_ref, &position, &board_asks, &board_bids, &executions).await {
                error!("trade error: {:?}", e);
            }
        }) => {
            if let Err(e) = result {
                error!("trade task panicked: {:?}", e);
            }
        }
        result = tokio::spawn(async move {
            if let Err(e) = get_position(&reqwest::Client::new(), &position_ref).await {
                error!("get_position error: {:?}", e);
            }
        }) => {
            if let Err(e) = result {
                error!("get_position task panicked: {:?}", e);
            }
        }
        result = tokio::spawn(async move {
            if let Err(e) = subscribe_websocket(&board_asks_ref, &board_bids_ref, &executions_ref).await {
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
}