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
    },
    OrderCancelled {
        timestamp: String,
        order_id: String,
    },
    OrderFilled {
        timestamp: String,
        order_id: String,
        side: String,
        price: u64,
        size: f64,
        order_age_ms: u64,
    },
    OrderFailed {
        timestamp: String,
        side: String,
        price: u64,
        size: f64,
        error: String,
    },
}

impl TradeEvent {
    fn to_csv_row(&self) -> Vec<String> {
        match self {
            TradeEvent::OrderSent { timestamp, order_id, side, price, size, is_close } => {
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
                ]
            }
            TradeEvent::OrderCancelled { timestamp, order_id } => {
                vec![
                    timestamp.clone(),
                    "ORDER_CANCELLED".to_string(),
                    order_id.clone(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                ]
            }
            TradeEvent::OrderFilled { timestamp, order_id, side, price, size, order_age_ms } => {
                vec![
                    timestamp.clone(),
                    "ORDER_FILLED".to_string(),
                    order_id.clone(),
                    side.clone(),
                    price.to_string(),
                    size.to_string(),
                    String::new(),
                    String::new(),
                    order_age_ms.to_string(),
                ]
            }
            TradeEvent::OrderFailed { timestamp, side, price, size, error } => {
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
                ]
            }
        }
    }
}

const CSV_HEADER: &[&str] = &[
    "timestamp", "event", "order_id", "side", "price", "size", "is_close", "error", "order_age_ms",
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
        };

        let row = event.to_csv_row();
        assert_eq!(row[0], "2024-01-15T10:30:00Z");
        assert_eq!(row[1], "ORDER_SENT");
        assert_eq!(row[2], "123456");
        assert_eq!(row[3], "BUY");
        assert_eq!(row[4], "6500000");
        assert_eq!(row[5], "0.001");
        assert_eq!(row[6], "false");
        assert_eq!(row[7], "");
    }

    #[test]
    fn test_order_cancelled_csv_row() {
        let event = TradeEvent::OrderCancelled {
            timestamp: "2024-01-15T10:30:15Z".to_string(),
            order_id: "123456".to_string(),
        };

        let row = event.to_csv_row();
        assert_eq!(row[1], "ORDER_CANCELLED");
        assert_eq!(row[2], "123456");
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
        };

        let row = event.to_csv_row();
        assert_eq!(row[1], "ORDER_FILLED");
        assert_eq!(row[3], "BUY");
        assert_eq!(row.len(), 9);
        assert_eq!(row[8], "3500");
    }

    #[test]
    fn test_order_failed_csv_row() {
        let event = TradeEvent::OrderFailed {
            timestamp: "2024-01-15T10:30:00Z".to_string(),
            side: "SELL".to_string(),
            price: 6510000,
            size: 0.001,
            error: "API timeout".to_string(),
        };

        let row = event.to_csv_row();
        assert_eq!(row[1], "ORDER_FAILED");
        assert_eq!(row[7], "API timeout");
    }

    #[test]
    fn test_csv_file_path() {
        let dir = PathBuf::from("logs/trades");
        let date = NaiveDate::from_ymd_opt(2024, 1, 15).unwrap();
        let path = csv_file_path(&dir, date);
        assert_eq!(path, PathBuf::from("logs/trades/trades-2024-01-15.csv"));
    }
}
