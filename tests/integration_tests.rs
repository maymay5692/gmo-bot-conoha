//! 統合テスト
//! ライブラリの公開APIをテストする

use trading_bot::model::{BotConfig, FloatingExp, OrderInfo, OrderSide, Position};
use trading_bot::bayes_prob::{BayesProb, BetaDistribution};
use trading_bot::time_queue::TimeQueue;
use trading_bot::util::round_size;

use std::str::FromStr;
use std::time::Duration;

// ============================================================
// Position Tests
// ============================================================

#[test]
fn test_position_new() {
    let pos = Position::new();
    assert_eq!(pos.long_size, 0.0);
    assert_eq!(pos.short_size, 0.0);
}

#[test]
fn test_position_clone() {
    let mut pos = Position::new();
    pos.long_size = 0.05;
    pos.short_size = 0.03;

    let cloned = pos.clone();
    assert_eq!(cloned.long_size, 0.05);
    assert_eq!(cloned.short_size, 0.03);
}

// ============================================================
// OrderSide Tests
// ============================================================

#[test]
fn test_order_side_display() {
    assert_eq!(format!("{}", OrderSide::BUY), "BUY");
    assert_eq!(format!("{}", OrderSide::SELL), "SELL");
    assert_eq!(format!("{}", OrderSide::Unknown), "Unknown");
}

#[test]
fn test_order_side_from_str() {
    assert_eq!(OrderSide::from_str("BUY").unwrap(), OrderSide::BUY);
    assert_eq!(OrderSide::from_str("SELL").unwrap(), OrderSide::SELL);
    assert!(OrderSide::from_str("INVALID").is_err());
}

// ============================================================
// OrderInfo Tests
// ============================================================

#[test]
fn test_order_info_creation() {
    let info = OrderInfo {
        price: 10_000_000,
        size: 0.01,
        side: OrderSide::BUY,
        timestamp: 1234567890,
    };
    assert_eq!(info.price, 10_000_000);
    assert_eq!(info.size, 0.01);
    assert_eq!(info.side, OrderSide::BUY);
    assert_eq!(info.timestamp, 1234567890);
}

// ============================================================
// FloatingExp Tests
// ============================================================

#[test]
fn test_floating_exp_calc() {
    let fe = FloatingExp::new(10.0, -2.0, 1.0);
    assert!((fe.calc() - 0.01).abs() < 1e-10);

    let fe2 = FloatingExp::new(10.0, -2.0, 5.0);
    assert!((fe2.calc() - 0.05).abs() < 1e-10);

    let fe3 = FloatingExp::new(10.0, 2.0, 3.0);
    assert!((fe3.calc() - 300.0).abs() < 1e-10);
}

#[test]
fn test_floating_exp_default() {
    let fe = FloatingExp::default();
    assert!((fe.calc() - 0.00001).abs() < 1e-15);
}

#[test]
fn test_floating_exp_ordering() {
    let fe1 = FloatingExp::new(10.0, -5.0, 1.0);
    let fe2 = FloatingExp::new(10.0, -5.0, 2.0);
    assert!(fe1 < fe2);
}

// ============================================================
// BotConfig Tests
// ============================================================

#[test]
fn test_bot_config_from_yaml() {
    let yaml = r#"
order_cancel_ms: 15000
order_interval_ms: 15000
position_ratio: 0.9
min_lot: 0.01
max_lot: 0.01
max_position: 0.02
"#;
    let config: BotConfig = serde_yaml::from_str(yaml).unwrap();
    assert_eq!(config.order_cancel_ms, 15000);
    assert_eq!(config.order_interval_ms, 15000);
    assert!((config.position_ratio - 0.9).abs() < 1e-10);
    assert!((config.min_lot - 0.01).abs() < 1e-10);
    assert!((config.max_lot - 0.01).abs() < 1e-10);
    assert!((config.max_position - 0.02).abs() < 1e-10);
}

// ============================================================
// BetaDistribution Tests
// ============================================================

#[test]
fn test_beta_distribution_new() {
    let dist = BetaDistribution::new(5, 3);
    assert_eq!(dist.a, 5);
    assert_eq!(dist.b, 3);
}

// ============================================================
// BayesProb Tests
// ============================================================

#[test]
fn test_bayes_prob_calc_average() {
    let prior = BetaDistribution::new(1, 1);
    let prob = BayesProb::new(prior, Duration::from_secs(300));
    let avg = prob.calc_average();
    assert!((avg - 0.5).abs() < 1e-10);
}

#[test]
fn test_bayes_prob_update() {
    let prior = BetaDistribution::new(0, 1);
    let mut prob = BayesProb::new(prior, Duration::from_secs(300));

    prob.update(1, 1);
    let avg = prob.calc_average();
    assert!(avg >= 0.0 && avg <= 1.0);
}

// ============================================================
// TimeQueue Tests
// ============================================================

#[test]
fn test_time_queue_basic_operations() {
    let mut queue: TimeQueue<i32> = TimeQueue::new(Duration::from_secs(60));
    assert_eq!(queue.len(), 0);

    queue.push(42);
    assert_eq!(queue.len(), 1);
    assert_eq!(queue.first(), Some(42));
    assert_eq!(queue.last(), Some(42));

    queue.push(100);
    assert_eq!(queue.len(), 2);
    assert_eq!(queue.first(), Some(42));
    assert_eq!(queue.last(), Some(100));
}

#[test]
fn test_time_queue_get_data() {
    let mut queue: TimeQueue<i32> = TimeQueue::new(Duration::from_secs(60));
    queue.push(1);
    queue.push(2);
    queue.push(3);

    let data = queue.get_data();
    assert_eq!(data, vec![1, 2, 3]);
}

#[test]
fn test_time_queue_extend() {
    let mut queue: TimeQueue<i32> = TimeQueue::new(Duration::from_secs(60));
    queue.extend(vec![1, 2, 3, 4, 5]);
    assert_eq!(queue.len(), 5);
}

// ============================================================
// Util Tests
// ============================================================

#[test]
fn test_round_size() {
    assert_eq!(round_size(1.23456789), 1.23456789);
    assert_eq!(round_size(0.01), 0.01);
    assert_eq!(round_size(0.123456789), 0.12345679);
    assert_eq!(round_size(0.0), 0.0);
}

// ============================================================
// Trading Logic Tests
// ============================================================

#[test]
fn test_mid_price_calculation() {
    let best_ask = 10_000_100.0;
    let best_bid = 9_999_900.0;
    let mid_price = (best_ask + best_bid) / 2.0;
    assert_eq!(mid_price, 10_000_000.0);
}

#[test]
fn test_bid_ask_from_floating_exp() {
    let mid_price = 10_000_000.0;
    let fe = FloatingExp::new(10.0, -5.0, 1.0);

    let bid = mid_price - (mid_price * fe.calc());
    let ask = mid_price + (mid_price * fe.calc());

    assert!((bid - 9_999_900.0).abs() < 1e-10);
    assert!((ask - 10_000_100.0).abs() < 1e-10);
}

#[test]
fn test_volatility_calculation() {
    let executions: Vec<(u64, f64, i64)> = vec![
        (10_000_000, 0.01, 1234567890),
        (10_001_000, 0.02, 1234567891),
        (9_999_000, 0.01, 1234567892),
    ];

    let max_price = executions.iter().map(|e| e.0).max().unwrap_or(0);
    let min_price = executions.iter().map(|e| e.0).min().unwrap_or(0);
    let volatility = (max_price - min_price) as f64 / 2.0;

    assert_eq!(volatility, 1000.0);
}

#[test]
fn test_order_size_calculation() {
    let long_size: f64 = 0.0;
    let max_position_size: f64 = 0.02;
    let min_lot: f64 = 0.01;
    let max_lot: f64 = 0.01;
    let position_ratio: f64 = 0.9;

    let buy_size = round_size(
        max_lot * (1.0 - long_size.powf(position_ratio) / max_position_size)
    ).max(min_lot);

    assert_eq!(buy_size, 0.01);
}
