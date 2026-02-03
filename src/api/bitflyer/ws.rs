use chrono::{DateTime, Utc};
use serde::Deserializer;
use serde::{Deserialize, Serialize};
use std::str::FromStr;

#[allow(non_camel_case_types)]
pub enum Channel {
    lightning_board_FX_BTC_JPY,
    lightning_executions_FX_BTC_JPY,
}

impl FromStr for Channel {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "lightning_board_FX_BTC_JPY" => Ok(Channel::lightning_board_FX_BTC_JPY),
            "lightning_executions_FX_BTC_JPY" => Ok(Channel::lightning_executions_FX_BTC_JPY),
            _ => Err(()),
        }
    }
}

#[derive(Serialize, Deserialize, Debug)]
pub struct Params {
    pub channel: String,
    pub message: serde_json::Value,
}

#[derive(Debug, Clone, Copy)]
pub struct Timestamp(DateTime<Utc>);

impl<'de> Deserialize<'de> for Timestamp {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let s = String::deserialize(deserializer)?;
        let datetime = DateTime::parse_from_rfc3339(&s)
            .map_err(serde::de::Error::custom)?
            .with_timezone(&Utc);
        Ok(Timestamp(datetime))
    }
}

impl Timestamp {
    pub fn get_timestamp(&self) -> i64 {
        self.0.timestamp_millis()
    }
}

#[derive(Deserialize, Debug, Clone)]
pub struct ExecutionItem {
    pub id: i64,
    pub side: Side,
    pub price: f64,
    pub size: f64,
    pub exec_date: Timestamp,
    pub buy_child_order_acceptance_id: String,
    pub sell_child_order_acceptance_id: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct Board {
    pub mid_price: f64,
    pub bids: Vec<BoardItem>,
    pub asks: Vec<BoardItem>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct BoardItem {
    pub price: f64,
    pub size: f64,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct Message {
    pub jsonrpc: String,
    pub method: String,
    pub params: Params,
}

#[derive(Serialize, Deserialize, Debug, PartialEq, Eq, Clone, Copy)]
pub enum Side {
    BUY,
    SELL,
}

#[derive(Deserialize, Debug, Clone)]
pub struct UpdateChildOrderItem {
    pub child_order_id: String,
    pub child_order_acceptance_id: String,
    pub event_type: String,
    pub event_date: Timestamp,
    pub child_order_type: Option<String>,
    pub side: Option<Side>,
    pub price: Option<u64>,
    pub size: Option<f64>,
    pub reason: Option<String>,
    pub sfd: Option<f64>,
    pub outstanding_size: Option<f64>,
    pub expire_date: Option<Timestamp>,
}
