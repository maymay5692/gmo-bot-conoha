use std::str::FromStr;
use std::fmt;
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Copy, Default)]
pub struct Position {
    pub long_size: f64,
    pub short_size: f64,
    pub long_open_price: f64,
    pub short_open_price: f64,
}

impl Position {
    pub fn new() -> Self {
        Self::default()
    }
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub enum OrderSide {
    Unknown,
    BUY,
    SELL,
}

impl fmt::Display for OrderSide {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match *self {
            OrderSide::BUY => write!(f, "BUY"),
            OrderSide::SELL => write!(f, "SELL"),
            _ => write!(f, "Unknown"),
        }
    }
}

impl FromStr for OrderSide {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "BUY" => Ok(OrderSide::BUY),
            "SELL" => Ok(OrderSide::SELL),
            _ => Err(()),
        }
    }
}

#[derive(Debug, Clone)]
pub struct OrderInfo {
    pub price: u64,
    pub size: f64,
    pub side: OrderSide,
    pub timestamp: u64,
    pub is_close: bool,
    pub mid_price: u64,
    pub t_optimal_ms: u64,
    pub sigma_1s: f64,
    pub spread_pct: f64,
    pub level: u32,
    pub p_fill: f64,
    pub best_ev: f64,
    pub single_leg_ev: f64,
}

#[derive(Debug, Clone)]
pub struct OrderOutcome {
    pub side: OrderSide,
    pub filled: bool,
    pub is_close: bool,
    pub level: u32,
}

// ハッシュキーとして登録可能な浮動小数点指数
#[derive(Debug, Clone, PartialEq)]
pub struct FloatingExp {
    pub base: f64,
    pub exp: f64,
    pub rate: f64,
}

impl FloatingExp {
    pub fn new(base: f64, exp: f64, rate: f64) -> Self {
        Self { base, exp, rate }
    }

    pub fn calc(&self) -> f64 {
        self.base.powf(self.exp) * self.rate
    }
}

impl Default for FloatingExp {
    fn default() -> Self {
        Self {
            base: 10.0,
            exp: -5.0,
            rate: 1.0,
        }
    }
}

impl Eq for FloatingExp {}

impl PartialOrd for FloatingExp {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for FloatingExp {
    fn cmp(&self, other: &FloatingExp) -> std::cmp::Ordering {
        // Use total_cmp for consistent NaN handling (available in Rust 1.62+)
        self.rate.total_cmp(&other.rate)
    }
}

fn default_log_dir() -> String {
    "logs".to_string()
}

fn default_true() -> bool {
    true
}

fn default_alpha() -> f64 {
    0.5
}

fn default_execution_retain_ms() -> u64 {
    5000
}

fn default_t_optimal_min_ms() -> u64 {
    2000
}

fn default_t_optimal_max_ms() -> u64 {
    30000
}

fn default_close_spread_factor() -> f64 {
    0.5
}

fn default_stop_loss_jpy() -> f64 {
    5.0
}

#[derive(Deserialize, Debug, Clone)]
pub struct BotConfig {
    pub order_cancel_ms: u64,
    pub order_interval_ms: u64,
    pub position_ratio: f64,
    pub min_lot: f64,
    pub max_lot: f64,
    pub max_position: f64,
    #[serde(default = "default_log_dir")]
    pub log_dir: String,
    #[serde(default = "default_true")]
    pub trade_log_enabled: bool,
    #[serde(default = "default_true")]
    pub metrics_log_enabled: bool,
    #[serde(default = "default_alpha")]
    pub alpha: f64,
    #[serde(default = "default_execution_retain_ms")]
    pub execution_retain_ms: u64,
    #[serde(default = "default_t_optimal_min_ms")]
    pub t_optimal_min_ms: u64,
    #[serde(default = "default_t_optimal_max_ms")]
    pub t_optimal_max_ms: u64,
    #[serde(default = "default_close_spread_factor")]
    pub close_spread_factor: f64,
    #[serde(default = "default_stop_loss_jpy")]
    pub stop_loss_jpy: f64,
}

#[cfg(test)]
mod tests {
    use crate::model::FloatingExp;

    #[test]
    fn floating_exp1() {
        let t = FloatingExp::new(10.0, -2.0, 1.0);
        assert_eq!(t.calc(), 0.01);
    }

    #[test]
    fn floating_exp2() {
        let t = FloatingExp::new(10.0, -2.0, 5.0);
        assert_eq!(t.calc(), 0.05);
    }

    #[test]
    fn floating_exp3() {
        let t = FloatingExp::new(10.0, 2.0, 3.0);
        assert_eq!(t.calc(), 300.0);
    }
}
