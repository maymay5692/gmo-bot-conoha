use crate::api::bitflyer::api;
use serde::Deserialize;
use std::collections::HashMap;

const PATH: &str = "/v1/me/getpositions";

type GetPositionResponse = Vec<PositionDetail>;

#[derive(Deserialize, Debug, Clone)]
pub struct PositionDetail {
    pub product_code: String,
    pub side: String,
    pub price: f64,
    pub size: f64,
    pub commission: f64,
    pub open_date: String,
    pub swap_point_accumulate: f64,
    pub require_collateral: f64,
    pub leverage: f64,
    pub pnl: f64,
    pub sfd: f64,
}

pub async fn get_position(
    client: &reqwest::Client,
    product_code: api::ProductCode,
) -> Result<GetPositionResponse, api::ApiResponseError> {
    let mut params = HashMap::new();
    params.insert("product_code".to_string(), product_code.to_string());
    api::get::<GetPositionResponse>(client, PATH, Some(&params)).await
}
