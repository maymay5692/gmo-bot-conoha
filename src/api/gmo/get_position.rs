use crate::api::gmo::api;
use crate::api::gmo::api::deserialize_number_from_string;
use std::collections::HashMap;
use serde::{Deserialize};

const PATH: &str = "/v1/openPositions";

#[derive(Debug, Deserialize, Clone, Default)]
pub struct Pagination {
    #[serde(rename = "currentPage")]
    pub current_page: u32,
    pub count: u32,
}

#[derive(Debug, Deserialize, Clone, Default)]
pub struct Position {
    #[serde(rename = "positionId")]
    pub position_id: u64,
    pub symbol: String,
    pub side: String,
    
    #[serde(deserialize_with = "deserialize_number_from_string")]
    pub size: f64,
    
    #[serde(deserialize_with = "deserialize_number_from_string")]
    pub price: f64,
    
    #[serde(deserialize_with = "deserialize_number_from_string")]
    pub leverage: u32,
    
    pub timestamp: String,
}

#[derive(Debug, Deserialize, Clone, Default)]
pub struct PositionData {
    pub pagination: Option<Pagination>,
    pub list: Option<Vec<Position>>,
}

#[derive(Debug, Deserialize, Clone)]
pub struct PositionResponse {
    pub status: u32,
    pub data: Option<PositionData>,
    pub responsetime: String,
}

pub async fn get_position(
    client: &reqwest::Client,
    symbol: api::Symbol,
) -> Result<PositionResponse, api::ApiResponseError> {
    let mut params = HashMap::new();
    params.insert("symbol".to_string(), symbol.to_string());
    api::get::<PositionResponse>(client, PATH, Some(&params)).await
}
