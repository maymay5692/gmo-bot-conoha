use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize, Deserializer};
use std::str::FromStr;
use crate::api::gmo::api::deserialize_number_from_string;

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "snake_case")]
pub enum Channel {
    Orderbooks,
    Trades,
}

impl FromStr for Channel {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "orderbooks" => Ok(Channel::Orderbooks),
            "trades" => Ok(Channel::Trades),
            _ => Err(()),
        }
    }
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
    pub symbol: String,
    pub side: Side,

    #[serde(deserialize_with = "deserialize_number_from_string")]
    pub price: f64,

    #[serde(deserialize_with = "deserialize_number_from_string")]
    pub size: f64,
    pub timestamp: Timestamp,
}

#[derive(Deserialize, Debug)]
pub struct Board {
    pub bids: Vec<BoardItem>,
    pub asks: Vec<BoardItem>,
    pub symbol: String,
    pub timestamp: Timestamp,
}

#[derive(Deserialize, Debug)]
pub struct BoardItem {
    #[serde(deserialize_with = "deserialize_number_from_string")]
    pub price: f64,

    #[serde(deserialize_with = "deserialize_number_from_string")]
    pub size: f64,
}

#[derive(Deserialize, Debug)]
pub struct Message {
    pub channel: Channel,
}

#[derive(Serialize, Deserialize, Debug, PartialEq, Eq, Clone, Copy)]
pub enum Side {
    BUY,
    SELL,
}
