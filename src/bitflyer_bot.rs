pub mod api;
pub mod bayes_prob;
pub mod model;
pub mod time_queue;
pub mod util;

use crate::api::bitflyer;
use crate::bitflyer::ws::Side;
use crate::model::BotConfig;
use crate::bayes_prob::{BayesProb, BetaDistribution};
use crate::api::bitflyer::api::ProductCode;
use crate::api::bitflyer::api::ChildOrderType;

use std::{
    collections::BTreeMap,
    collections::HashMap,
    ops::{Add, Sub},
    str::FromStr,
    sync::Arc,
    time::Duration,
    fs,
};

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

// (price, size)
type OrderBook = RwLock<BTreeMap<u64, f64>>;

// (price, size, timestamp, delay)
type Executions = RwLock<Vec<(u64, f64, i64, i64, Side)>>;

/// 注文パラメータのバリデーション
fn validate_order_params(
    price: u64,
    size: f64,
    config: &BotConfig,
) -> std::result::Result<(), &'static str> {
    if price == 0 {
        return Err("Price cannot be zero");
    }
    if size < config.min_lot {
        return Err("Size below minimum lot");
    }
    if size > config.max_lot * 10.0 {
        return Err("Size exceeds maximum allowed");
    }
    if (size * 100.0).fract() != 0.0 {
        return Err("Size precision too high");
    }
    Ok(())
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

            let parameter = bitflyer::cancel_child_order::CancelChildOrderParameter {
                product_code: ProductCode::FX_BTC_JPY,
                child_order_acceptance_id: child_order_acceptance_id.clone(),
            };

            if let Err(e) = bitflyer::cancel_child_order::cancel_child_order(client, &parameter).await {
                warn!("Failed to cancel order {}: {:?}", child_order_acceptance_id, e);
            }

            if order_list.lock().contains_key(&child_order_acceptance_id) {
                order_list.lock().remove(&child_order_acceptance_id);
            }
        }
    }
}

async fn send_order(
    client: &reqwest::Client,
    config: &BotConfig,
    order_list: &Orders,
    side: model::OrderSide,
    price: u64,
    size: f64,
) -> Result<()> {
    // 注文パラメータのバリデーション
    if let Err(e) = validate_order_params(price, size, config) {
        warn!("Invalid Order Parameter: {:?} price={} size={} reason={}", side, price, size, e);
        return Ok(());
    }

    let parameter = bitflyer::send_order::ChildOrderParameter {
        product_code: ProductCode::FX_BTC_JPY,
        child_order_type: ChildOrderType::LIMIT,
        side: side.clone(),
        price: Some(price),
        size,
        minute_to_expire: 1,
    };

    let response = bitflyer::send_order::post_child_order(client, &parameter).await;

    match response {
        Ok(response) => {
            let order_info = model::OrderInfo {
                price,
                size,
                side,
                timestamp: Utc::now().timestamp_millis() as u64,
            };

            info!("Send Order: {:?}", parameter);

            order_list
                .lock()
                .insert(response.1.child_order_acceptance_id, order_info);
        }
        Err(e) => {
            error!("Send Order Failed: {:?}", e);
        }
    }
    Ok(())
}

fn maximize_expected_value(
    _best_bid: f64,
    _best_ask: f64,
    mid_price: f64,
    buy: &BTreeMap<model::FloatingExp, (f64, BayesProb)>,
    sell: &BTreeMap<model::FloatingExp, (f64, BayesProb)>,
) -> Option<(model::FloatingExp, model::FloatingExp)> {
    let mut best_pair = None;
    let mut best_expected_value = f64::NEG_INFINITY;

    for b in buy {
        let buy_probability: f64 = b.1.1.calc_average();
        let buy_price: f64 = mid_price - (mid_price * b.0.calc());

        for s in sell {
            let sell_probability: f64 = s.1.1.calc_average();
            let sell_price: f64 = mid_price + (mid_price * s.0.calc());

            // 期待収益
            let expected_profit = buy_probability * sell_probability * (sell_price - buy_price);

            let volatility = sell_price - buy_price;
            let alpha = 0.5;

            // 期待損失
            let expected_loss = (1.0
                - (buy_probability * sell_probability)
                - ((1.0 - buy_probability) * (1.0 - sell_probability)))
                * volatility * alpha;

            // 期待値 = 期待収益 - 期待損失
            let ev = expected_profit - expected_loss;

            if ev > best_expected_value {
                best_pair = Some((b.0.clone(), s.0.clone()));
                best_expected_value = ev;
            }
        }
    }
    best_pair
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

    let collateral = match bitflyer::get_collateral::get_collateral(client).await {
        Ok(response) => response.collateral,
        Err(_) => 0.0,
    };
    info!("Collateral: {:?}", collateral);

    sleep(Duration::from_millis(config.order_interval_ms)).await;

    let mut ltp = 0;

    // 事前分布をBe(0, 1)とする
    let initial_bayes_prob = BayesProb::new(
        BetaDistribution::new(0, 1),
        Duration::from_secs(300),
    );

    let mut buy_probabilities = BTreeMap::<model::FloatingExp, (f64, BayesProb)>::new();
    let mut sell_probabilities =
        BTreeMap::<model::FloatingExp, (f64, BayesProb)>::new();

    // mid_priceから何stepまでの価格を考慮するか
    // 1 step = price * base^exp * rate yen
    let price_step_count = 15;

    for i in 0..price_step_count {
        let key = model::FloatingExp {
            base: 10.0,
            exp: -5.0,
            rate: (i + 1) as f64,
        };
        buy_probabilities.insert(key.clone(), (0.0, initial_bayes_prob.clone()));
        sell_probabilities.insert(key.clone(), (0.0, initial_bayes_prob.clone()));
    }

    loop {
        sleep(Duration::from_secs(5)).await;

        let now = Utc::now().timestamp_millis();

        // 直近の約定履歴のみ残す
        executions.write().retain(|e| e.2 >= now - config.order_interval_ms as i64);

        if executions.read().is_empty() {
            continue;
        }

        // 最終約定価格を取得
        ltp = match executions.read().last() {
            Some(e) => e.0,
            None => ltp,
        };

        // 板情報のサイズが0以上かつ、ltpからMAX_KEEP_BOARD_PRICEの範囲のみを残す
        // L25のように個数で残すことも可
        board_asks
            .write()
            .retain(|p, v| *v > 0.0 && *p < ltp + MAX_KEEP_BOARD_PRICE && *p >= ltp);

        board_bids
            .write()
            .retain(|p, v| *v > 0.0 && *p > ltp - MAX_KEEP_BOARD_PRICE && *p <= ltp);

        let best_ask = board_asks
            .read()
            .iter()
            .next()
            .map(|p| *p.0 as f64)
            .unwrap_or(0.0);

        let best_bid = board_bids
            .read()
            .iter()
            .next_back()
            .map(|p| *p.0 as f64)
            .unwrap_or(0.0);

        let mid_price = (best_ask + best_bid) / 2.0;

        // 前回から約定履歴を確認し指値が約定しているかを更新する
        buy_probabilities.iter_mut().for_each(|p| {
            p.1.1.update(
                1,
                executions.read().iter().any(|e| e.0 <= p.1.0 as u64) as u64,
            )
        });

        sell_probabilities.iter_mut().for_each(|p| {
            p.1.1.update(
                1,
                executions.read().iter().any(|e| e.0 >= p.1.0 as u64) as u64,
            )
        });

        // 約定確率確認のための指値の更新
        buy_probabilities
            .iter_mut()
            .for_each(|p| p.1.0 = mid_price - (mid_price * p.0.calc()));

        sell_probabilities
            .iter_mut()
            .for_each(|p| p.1.0 = mid_price + (mid_price * p.0.calc()));

        let best_pair = match maximize_expected_value(
            best_bid,
            best_ask,
            mid_price,
            &buy_probabilities,
            &sell_probabilities,
        ) {
            Some(p) => p,
            None => continue,
        };

        let position = *position.read();

        // // 期待収益が最大となる指値価格を計算
        let bid = mid_price - (mid_price * best_pair.0.calc());
        let ask = mid_price + (mid_price * best_pair.1.calc());

        // ポジションがある場合はポジションサイズに応じてペナルティを課すことでΔ0に近づける
        let position_penalty = ((ask - bid) * 0.25).min(500.0);

        if position.long_size < max_position_size {
            let size = util::round_size(
                max_lot * (1.0 - position.long_size.powf(position_ratio) / max_position_size),
            )
            .max(min_lot);
            if let Err(e) = send_order(
                client,
                config,
                order_list,
                model::OrderSide::BUY,
                bid
                    .sub(position_penalty * position.long_size / min_lot)
                    .add(position_penalty * position.short_size / min_lot)
                    .min(best_bid) as u64,
                size,
            )
            .await {
                error!("Failed to send buy order: {:?}", e);
            }
        }

        if position.short_size < max_position_size {
            let size = util::round_size(
                max_lot * (1.0 - position.short_size.powf(position_ratio) / max_position_size),
            )
            .max(min_lot);
            if let Err(e) = send_order(
                client,
                config,
                order_list,
                model::OrderSide::SELL,
                ask
                    .add(position_penalty * position.short_size / min_lot)
                    .sub(position_penalty * position.long_size / min_lot)
                    .max(best_ask) as u64,
                size,
            )
            .await {
                error!("Failed to send sell order: {:?}", e);
            }
        }
    }
}

async fn get_position(client: &reqwest::Client, position: &Positions) -> Result<()> {
    loop {
        sleep(Duration::from_secs(5)).await;

        let response =
            match bitflyer::get_position::get_position(client, ProductCode::FX_BTC_JPY).await {
                Ok(response) => response,
                Err(e) => {
                    error!("Failed to get position: {:?}", e);
                    continue;
                }
            };

        let total_position = response.iter().fold(0.0, |acc, x| {
            acc + if x.side == "BUY" { x.size } else { -x.size }
        });

        // Single atomic update for position
        let new_position = model::Position {
            short_size: if total_position < 0.0 {
                -util::round_size(total_position)
            } else {
                0.0
            },
            long_size: if total_position > 0.0 {
                util::round_size(total_position)
            } else {
                0.0
            },
        };
        *position.write() = new_position;

        debug!("Position: {:?}", position.read());
    }
}

/// WebSocket接続とメッセージ処理（内部関数）
async fn connect_and_process_websocket(
    board_asks: &OrderBook,
    board_bids: &OrderBook,
    executions: &Executions,
) -> Result<()> {
    let url = Url::parse("wss://ws.lightstream.bitflyer.com/json-rpc")
        .expect("Invalid WebSocket URL");
    let (socket, _) = connect_async(url).await?;

    info!("Connected to bitFlyer WebSocket");

    let (mut write, mut read) = socket.split();

    let channels = vec![
        "lightning_board_FX_BTC_JPY",
        "lightning_executions_FX_BTC_JPY",
    ];

    for channel in channels {
        let data = serde_json::json!({
            "method": "subscribe",
            "params":  {"channel": channel}
        });

        write.send(Message::Text(data.to_string())).await?;
    }

    while let Some(msg) = read.next().await {
        let msg = msg?;

        let msg = match msg {
            tokio_tungstenite::tungstenite::Message::Text(s) => s,
            _ => continue,
        };

        let parsed: bitflyer::ws::Message = match serde_json::from_str(&msg) {
            Ok(parsed) => parsed,
            _ => continue,
        };

        if &parsed.method != "channelMessage" {
            continue;
        }

        let channel = bitflyer::ws::Channel::from_str(&parsed.params.channel);

        match channel {
            Ok(bitflyer::ws::Channel::lightning_board_FX_BTC_JPY) => {
                let board: bitflyer::ws::Board = match serde_json::from_value(parsed.params.message) {
                    Ok(board) => board,
                    _ => continue,
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
            Ok(bitflyer::ws::Channel::lightning_executions_FX_BTC_JPY) => {
                let all: Vec<bitflyer::ws::ExecutionItem> =
                    match serde_json::from_value(parsed.params.message) {
                        Ok(executions) => executions,
                        _ => continue,
                    };

                let now = Utc::now().timestamp_millis();

                let items = all
                    .par_iter()
                    .map(|e| {
                        (
                            e.price as u64,
                            if e.side == bitflyer::ws::Side::BUY {
                                e.size
                            } else {
                                -e.size
                            },
                            e.exec_date.get_timestamp(),
                            now - e.exec_date.get_timestamp(),
                            e.side,
                        )
                    })
                    .collect::<Vec<(u64, f64, i64, i64, bitflyer::ws::Side)>>();

                executions.write().extend(items);
            }
            _ => continue,
        }
    }

    Ok(())
}

/// WebSocket接続（指数バックオフによる自動再接続付き）
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
                reconnect_delay = Duration::from_secs(1);
            }
            Err(e) => {
                error!("WebSocket error: {:?}, reconnecting in {:?}...", e, reconnect_delay);
            }
        }

        sleep(reconnect_delay).await;
        reconnect_delay = std::cmp::min(
            reconnect_delay * 2,
            Duration::from_secs(MAX_RECONNECT_DELAY_SECS),
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

    let executions = Arc::new(RwLock::new(Vec::<(u64, f64, i64, i64, bitflyer::ws::Side)>::new()));
    let executions_ref = executions.clone();

    let config_ref = config.clone();
    let config_ref2 = config.clone();

    // Build HTTP client with timeout
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .connect_timeout(Duration::from_secs(5))
        .build()
        .expect("Failed to build HTTP client");
    let client2 = client.clone();
    let client3 = client.clone();

    tokio::select! {
        result = tokio::spawn(async move { cancel_child_order(&client, &config_ref, &orders).await }) => {
            match result {
                Ok(Ok(_)) => info!("cancel_child_order completed"),
                Ok(Err(e)) => error!("cancel_child_order error: {:?}", e),
                Err(e) => error!("cancel_child_order task panicked: {:?}", e),
            }
        }
        result = tokio::spawn(async move { trade(&client2, &config_ref2, &orders_ref, &position, &board_asks, &board_bids, &executions).await }) => {
            match result {
                Ok(Ok(_)) => info!("trade completed"),
                Ok(Err(e)) => error!("trade error: {:?}", e),
                Err(e) => error!("trade task panicked: {:?}", e),
            }
        }
        result = tokio::spawn(async move { get_position(&client3, &position_ref).await }) => {
            match result {
                Ok(Ok(_)) => info!("get_position completed"),
                Ok(Err(e)) => error!("get_position error: {:?}", e),
                Err(e) => error!("get_position task panicked: {:?}", e),
            }
        }
        result = tokio::spawn(async move { subscribe_websocket(&board_asks_ref, &board_bids_ref, &executions_ref).await }) => {
            match result {
                Ok(Ok(_)) => info!("subscribe_websocket completed"),
                Ok(Err(e)) => error!("subscribe_websocket error: {:?}", e),
                Err(e) => error!("subscribe_websocket task panicked: {:?}", e),
            }
        }
    }
}

fn main() {
    // Initialize tracing subscriber
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive(tracing::Level::INFO.into()),
        )
        .init();

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
