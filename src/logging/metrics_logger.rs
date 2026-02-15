use std::fs;
use std::io;
use std::path::PathBuf;

use chrono::{NaiveDate, Utc};
use tokio::sync::mpsc;
use tracing::{error, info, warn};

const CHANNEL_BUFFER_SIZE: usize = 1000;

#[derive(Debug, Clone)]
pub struct MetricsSnapshot {
    pub timestamp: String,
    pub mid_price: f64,
    pub best_bid: f64,
    pub best_ask: f64,
    pub spread: f64,
    pub volatility: f64,
    pub best_ev: f64,
    pub buy_spread_pct: f64,
    pub sell_spread_pct: f64,
    pub long_size: f64,
    pub short_size: f64,
    pub collateral: f64,
    pub buy_prob_avg: f64,
    pub sell_prob_avg: f64,
    pub sigma_1s: f64,
    pub t_optimal_ms: f64,
}

impl MetricsSnapshot {
    fn to_csv_row(&self) -> Vec<String> {
        vec![
            self.timestamp.clone(),
            self.mid_price.to_string(),
            self.best_bid.to_string(),
            self.best_ask.to_string(),
            self.spread.to_string(),
            self.volatility.to_string(),
            self.best_ev.to_string(),
            self.buy_spread_pct.to_string(),
            self.sell_spread_pct.to_string(),
            self.long_size.to_string(),
            self.short_size.to_string(),
            self.collateral.to_string(),
            self.buy_prob_avg.to_string(),
            self.sell_prob_avg.to_string(),
            self.sigma_1s.to_string(),
            self.t_optimal_ms.to_string(),
        ]
    }
}

const CSV_HEADER: &[&str] = &[
    "timestamp", "mid_price", "best_bid", "best_ask", "spread", "volatility",
    "best_ev", "buy_spread_pct", "sell_spread_pct", "long_size", "short_size",
    "collateral", "buy_prob_avg", "sell_prob_avg", "sigma_1s", "t_optimal_ms",
];

#[derive(Clone)]
pub struct MetricsLogger {
    sender: mpsc::Sender<MetricsSnapshot>,
}

impl MetricsLogger {
    pub fn new(log_dir: &str) -> Self {
        let (sender, receiver) = mpsc::channel(CHANNEL_BUFFER_SIZE);
        let metrics_dir = PathBuf::from(log_dir).join("metrics");
        tokio::spawn(writer_task(metrics_dir, receiver));
        Self { sender }
    }

    pub fn log(&self, snapshot: MetricsSnapshot) {
        if let Err(e) = self.sender.try_send(snapshot) {
            warn!("Metrics logger buffer full, dropping snapshot: {}", e);
        }
    }
}

fn csv_file_path(dir: &PathBuf, date: NaiveDate) -> PathBuf {
    dir.join(format!("metrics-{}.csv", date.format("%Y-%m-%d")))
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

fn write_csv_row(metrics_dir: &PathBuf, row: &[String]) {
    let today = Utc::now().date_naive();
    let file_path = csv_file_path(metrics_dir, today);

    if let Err(e) = ensure_csv_with_header(&file_path) {
        error!("Failed to create metrics CSV header: {}", e);
        return;
    }

    let file = match fs::OpenOptions::new().append(true).open(&file_path) {
        Ok(f) => f,
        Err(e) => {
            error!("Failed to open metrics log file: {}", e);
            return;
        }
    };

    let mut wtr = csv::WriterBuilder::new()
        .has_headers(false)
        .from_writer(file);

    if let Err(e) = wtr.write_record(row) {
        error!("Failed to write metrics snapshot: {}", e);
    }
    if let Err(e) = wtr.flush() {
        error!("Failed to flush metrics log: {}", e);
    }
}

async fn writer_task(metrics_dir: PathBuf, mut receiver: mpsc::Receiver<MetricsSnapshot>) {
    if let Err(e) = fs::create_dir_all(&metrics_dir) {
        error!("Failed to create metrics log directory: {}", e);
        return;
    }

    info!("MetricsLogger started: {}", metrics_dir.display());

    while let Some(snapshot) = receiver.recv().await {
        let row = snapshot.to_csv_row();
        let dir = metrics_dir.clone();
        if let Err(e) = tokio::task::spawn_blocking(move || {
            write_csv_row(&dir, &row);
        }).await {
            error!("Metrics log write task panicked: {}", e);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_metrics_snapshot_csv_row() {
        let snapshot = MetricsSnapshot {
            timestamp: "2024-01-15T10:30:00Z".to_string(),
            mid_price: 6505000.0,
            best_bid: 6500000.0,
            best_ask: 6510000.0,
            spread: 10000.0,
            volatility: 5000.0,
            best_ev: 0.00123,
            buy_spread_pct: 0.077,
            sell_spread_pct: 0.077,
            long_size: 0.001,
            short_size: 0.0,
            collateral: 100000.0,
            buy_prob_avg: 0.45,
            sell_prob_avg: 0.52,
            sigma_1s: 0.00077,
            t_optimal_ms: 4200.0,
        };

        let row = snapshot.to_csv_row();
        assert_eq!(row.len(), 16);
        assert_eq!(row[0], "2024-01-15T10:30:00Z");
        assert_eq!(row[1], "6505000");
        assert_eq!(row[14], "0.00077");
        assert_eq!(row[15], "4200");
    }

    #[test]
    fn test_metrics_csv_file_path() {
        let dir = PathBuf::from("logs/metrics");
        let date = NaiveDate::from_ymd_opt(2024, 1, 15).unwrap();
        let path = csv_file_path(&dir, date);
        assert_eq!(path, PathBuf::from("logs/metrics/metrics-2024-01-15.csv"));
    }
}
