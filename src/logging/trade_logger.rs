use std::fs;
use std::io;
use std::path::PathBuf;

use chrono::{NaiveDate, Utc};
use tokio::sync::mpsc;
use tracing::{error, info, warn};

const CHANNEL_BUFFER_SIZE: usize = 1000;

#[derive(Debug, Clone)]
pub enum TradeEvent {
    OrderSent {
        timestamp: String,
        order_id: String,
        side: String,
        price: u64,
        size: f64,
        is_close: bool,
        mid_price: u64,
        t_optimal_ms: u64,
        sigma_1s: f64,
        spread_pct: f64,
        level: u32,
        p_fill: f64,
        best_ev: f64,
        single_leg_ev: f64,
    },
    OrderCancelled {
        timestamp: String,
        order_id: String,
        order_age_ms: u64,
        level: u32,
        side: String,
        is_close: bool,
    },
    OrderFilled {
        timestamp: String,
        order_id: String,
        side: String,
        price: u64,
        size: f64,
        order_age_ms: u64,
        is_close: bool,
        mid_price: u64,
        t_optimal_ms: u64,
        sigma_1s: f64,
        spread_pct: f64,
        level: u32,
        p_fill: f64,
        best_ev: f64,
        single_leg_ev: f64,
    },
    OrderFailed {
        timestamp: String,
        side: String,
        price: u64,
        size: f64,
        error: String,
        mid_price: u64,
        t_optimal_ms: u64,
        sigma_1s: f64,
        spread_pct: f64,
    },
    StopLossTriggered {
        timestamp: String,
        side: String,
        size: f64,
        unrealized_pnl: f64,
        mid_price: u64,
        open_price: f64,
    },
}

impl TradeEvent {
    fn to_csv_row(&self) -> Vec<String> {
        match self {
            TradeEvent::OrderSent { timestamp, order_id, side, price, size, is_close,
                                    mid_price, t_optimal_ms, sigma_1s, spread_pct,
                                    level, p_fill, best_ev, single_leg_ev } => {
                vec![
                    timestamp.clone(),
                    "ORDER_SENT".to_string(),
                    order_id.clone(),
                    side.clone(),
                    price.to_string(),
                    size.to_string(),
                    is_close.to_string(),
                    String::new(),
                    String::new(),
                    mid_price.to_string(),
                    t_optimal_ms.to_string(),
                    sigma_1s.to_string(),
                    spread_pct.to_string(),
                    level.to_string(),
                    format!("{:.6}", p_fill),
                    format!("{:.6}", best_ev),
                    format!("{:.6}", single_leg_ev),
                ]
            }
            TradeEvent::OrderCancelled { timestamp, order_id, order_age_ms, level, side, is_close } => {
                vec![
                    timestamp.clone(),
                    "ORDER_CANCELLED".to_string(),
                    order_id.clone(),
                    side.clone(),
                    String::new(),
                    String::new(),
                    is_close.to_string(),
                    String::new(),
                    order_age_ms.to_string(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                    level.to_string(),
                    String::new(),
                    String::new(),
                    String::new(),
                ]
            }
            TradeEvent::OrderFilled { timestamp, order_id, side, price, size, order_age_ms,
                                      is_close, mid_price, t_optimal_ms, sigma_1s, spread_pct,
                                      level, p_fill, best_ev, single_leg_ev } => {
                vec![
                    timestamp.clone(),
                    "ORDER_FILLED".to_string(),
                    order_id.clone(),
                    side.clone(),
                    price.to_string(),
                    size.to_string(),
                    is_close.to_string(),
                    String::new(),
                    order_age_ms.to_string(),
                    mid_price.to_string(),
                    t_optimal_ms.to_string(),
                    sigma_1s.to_string(),
                    spread_pct.to_string(),
                    level.to_string(),
                    format!("{:.6}", p_fill),
                    format!("{:.6}", best_ev),
                    format!("{:.6}", single_leg_ev),
                ]
            }
            TradeEvent::OrderFailed { timestamp, side, price, size, error,
                                      mid_price, t_optimal_ms, sigma_1s, spread_pct } => {
                vec![
                    timestamp.clone(),
                    "ORDER_FAILED".to_string(),
                    String::new(),
                    side.clone(),
                    price.to_string(),
                    size.to_string(),
                    String::new(),
                    error.clone(),
                    String::new(),
                    mid_price.to_string(),
                    t_optimal_ms.to_string(),
                    sigma_1s.to_string(),
                    spread_pct.to_string(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                ]
            }
            TradeEvent::StopLossTriggered { timestamp, side, size, unrealized_pnl, mid_price, open_price } => {
                vec![
                    timestamp.clone(),
                    "STOP_LOSS_TRIGGERED".to_string(),
                    String::new(),
                    side.clone(),
                    format!("{:.0}", open_price),
                    size.to_string(),
                    "true".to_string(),
                    format!("unrealized_pnl={:.3}", unrealized_pnl),
                    String::new(),
                    mid_price.to_string(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                ]
            }
        }
    }
}

const CSV_HEADER: &[&str] = &[
    "timestamp", "event", "order_id", "side", "price", "size", "is_close", "error", "order_age_ms",
    "mid_price", "t_optimal_ms", "sigma_1s", "spread_pct", "level", "p_fill", "best_ev", "single_leg_ev",
];

#[derive(Clone)]
pub struct TradeLogger {
    sender: mpsc::Sender<TradeEvent>,
}

impl TradeLogger {
    pub fn new(log_dir: &str) -> Self {
        let (sender, receiver) = mpsc::channel(CHANNEL_BUFFER_SIZE);
        let trades_dir = PathBuf::from(log_dir).join("trades");
        tokio::spawn(writer_task(trades_dir, receiver));
        Self { sender }
    }

    pub fn log(&self, event: TradeEvent) {
        if let Err(e) = self.sender.try_send(event) {
            warn!("Trade logger buffer full, dropping event: {}", e);
        }
    }
}

fn csv_file_path(dir: &PathBuf, date: NaiveDate) -> PathBuf {
    dir.join(format!("trades-{}.csv", date.format("%Y-%m-%d")))
}

fn ensure_csv_with_header(path: &PathBuf) -> io::Result<()> {
    match fs::OpenOptions::new().write(true).create_new(true).open(path) {
        Ok(file) => {
            let mut wtr = csv::Writer::from_writer(file);
            wtr.write_record(CSV_HEADER)?;
            wtr.flush()?;
        }
        Err(ref e) if e.kind() == io::ErrorKind::AlreadyExists => {}
        Err(e) => return Err(e),
    }
    Ok(())
}

fn write_csv_row(trades_dir: &PathBuf, row: &[String]) {
    let today = Utc::now().date_naive();
    let file_path = csv_file_path(trades_dir, today);

    if let Err(e) = ensure_csv_with_header(&file_path) {
        error!("Failed to create CSV header: {}", e);
        return;
    }

    let file = match fs::OpenOptions::new().append(true).open(&file_path) {
        Ok(f) => f,
        Err(e) => {
            error!("Failed to open trade log file: {}", e);
            return;
        }
    };

    let mut wtr = csv::WriterBuilder::new()
        .has_headers(false)
        .from_writer(file);

    if let Err(e) = wtr.write_record(row) {
        error!("Failed to write trade event: {}", e);
    }
    if let Err(e) = wtr.flush() {
        error!("Failed to flush trade log: {}", e);
    }
}

async fn writer_task(trades_dir: PathBuf, mut receiver: mpsc::Receiver<TradeEvent>) {
    if let Err(e) = fs::create_dir_all(&trades_dir) {
        error!("Failed to create trades log directory: {}", e);
        return;
    }

    info!("TradeLogger started: {}", trades_dir.display());

    while let Some(event) = receiver.recv().await {
        let row = event.to_csv_row();
        let dir = trades_dir.clone();
        if let Err(e) = tokio::task::spawn_blocking(move || {
            write_csv_row(&dir, &row);
        }).await {
            error!("Trade log write task panicked: {}", e);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_order_sent_csv_row() {
        let event = TradeEvent::OrderSent {
            timestamp: "2024-01-15T10:30:00Z".to_string(),
            order_id: "123456".to_string(),
            side: "BUY".to_string(),
            price: 6500000,
            size: 0.001,
            is_close: false,
            mid_price: 6505000,
            t_optimal_ms: 3500,
            sigma_1s: 0.00008,
            spread_pct: 0.006,
            level: 5,
            p_fill: 0.45,
            best_ev: 1.23,
            single_leg_ev: 0.67,
        };

        let row = event.to_csv_row();
        assert_eq!(row.len(), 17);
        assert_eq!(row[0], "2024-01-15T10:30:00Z");
        assert_eq!(row[1], "ORDER_SENT");
        assert_eq!(row[2], "123456");
        assert_eq!(row[3], "BUY");
        assert_eq!(row[4], "6500000");
        assert_eq!(row[5], "0.001");
        assert_eq!(row[6], "false");
        assert_eq!(row[7], "");
        assert_eq!(row[8], "");
        assert_eq!(row[9], "6505000");
        assert_eq!(row[10], "3500");
        assert_eq!(row[11], "0.00008");
        assert_eq!(row[12], "0.006");
        assert_eq!(row[13], "5");
        assert_eq!(row[14], "0.450000");
        assert_eq!(row[15], "1.230000");
        assert_eq!(row[16], "0.670000");
    }

    #[test]
    fn test_order_cancelled_csv_row() {
        let event = TradeEvent::OrderCancelled {
            timestamp: "2024-01-15T10:30:15Z".to_string(),
            order_id: "123456".to_string(),
            order_age_ms: 5200,
            level: 8,
            side: "BUY".to_string(),
            is_close: false,
        };

        let row = event.to_csv_row();
        assert_eq!(row.len(), 17);
        assert_eq!(row[0], "2024-01-15T10:30:15Z");
        assert_eq!(row[1], "ORDER_CANCELLED");
        assert_eq!(row[2], "123456");
        assert_eq!(row[3], "BUY");       // side now populated
        assert_eq!(row[6], "false");      // is_close now populated
        assert_eq!(row[8], "5200");       // order_age_ms now populated
        assert_eq!(row[13], "8");         // level now populated
        // Other fields remain empty
        assert_eq!(row[4], "");           // price
        assert_eq!(row[5], "");           // size
        assert_eq!(row[7], "");           // error
        assert_eq!(row[9], "");           // mid_price
    }

    #[test]
    fn test_order_cancelled_close_order() {
        let event = TradeEvent::OrderCancelled {
            timestamp: "2024-01-15T10:31:00Z".to_string(),
            order_id: "789012".to_string(),
            order_age_ms: 1500,
            level: 0,
            side: "SELL".to_string(),
            is_close: true,
        };

        let row = event.to_csv_row();
        assert_eq!(row[3], "SELL");
        assert_eq!(row[6], "true");
        assert_eq!(row[8], "1500");
        assert_eq!(row[13], "0");
    }

    #[test]
    fn test_order_filled_csv_row() {
        let event = TradeEvent::OrderFilled {
            timestamp: "2024-01-15T10:30:15Z".to_string(),
            order_id: "123456".to_string(),
            side: "BUY".to_string(),
            price: 6500000,
            size: 0.001,
            order_age_ms: 3500,
            is_close: true,
            mid_price: 6502000,
            t_optimal_ms: 2000,
            sigma_1s: 0.00012,
            spread_pct: 0.008,
            level: 8,
            p_fill: 0.33,
            best_ev: 0.89,
            single_leg_ev: 0.42,
        };

        let row = event.to_csv_row();
        assert_eq!(row.len(), 17);
        assert_eq!(row[1], "ORDER_FILLED");
        assert_eq!(row[3], "BUY");
        assert_eq!(row[6], "true");
        assert_eq!(row[8], "3500");
        assert_eq!(row[9], "6502000");
        assert_eq!(row[10], "2000");
        assert_eq!(row[11], "0.00012");
        assert_eq!(row[12], "0.008");
        assert_eq!(row[13], "8");
        assert_eq!(row[14], "0.330000");
    }

    #[test]
    fn test_order_failed_csv_row() {
        let event = TradeEvent::OrderFailed {
            timestamp: "2024-01-15T10:30:00Z".to_string(),
            side: "SELL".to_string(),
            price: 6510000,
            size: 0.001,
            error: "API timeout".to_string(),
            mid_price: 6505000,
            t_optimal_ms: 5000,
            sigma_1s: 0.00006,
            spread_pct: 0.010,
        };

        let row = event.to_csv_row();
        assert_eq!(row.len(), 17);
        assert_eq!(row[1], "ORDER_FAILED");
        assert_eq!(row[7], "API timeout");
        assert_eq!(row[9], "6505000");
        assert_eq!(row[10], "5000");
        assert_eq!(row[13], "");
    }

    #[test]
    fn test_csv_header_has_17_columns() {
        assert_eq!(CSV_HEADER.len(), 17);
        assert_eq!(CSV_HEADER[9], "mid_price");
        assert_eq!(CSV_HEADER[10], "t_optimal_ms");
        assert_eq!(CSV_HEADER[11], "sigma_1s");
        assert_eq!(CSV_HEADER[12], "spread_pct");
        assert_eq!(CSV_HEADER[13], "level");
        assert_eq!(CSV_HEADER[14], "p_fill");
        assert_eq!(CSV_HEADER[15], "best_ev");
        assert_eq!(CSV_HEADER[16], "single_leg_ev");
    }

    #[test]
    fn test_csv_file_path() {
        let dir = PathBuf::from("logs/trades");
        let date = NaiveDate::from_ymd_opt(2024, 1, 15).unwrap();
        let path = csv_file_path(&dir, date);
        assert_eq!(path, PathBuf::from("logs/trades/trades-2024-01-15.csv"));
    }
}
