use crate::api::bitflyer::api;
use serde::Deserialize;

const PATH: &str = "/v1/me/getcollateral";

#[derive(Deserialize, Debug, Clone)]
pub struct Collateral {
    pub collateral: f64,
    pub require_collateral: f64,
    pub open_position_pnl: f64,
    pub keep_rate: f64,
}

pub async fn get_collateral(client: &reqwest::Client) -> Result<Collateral, api::ApiResponseError> {
    api::get::<Collateral>(client, PATH, None).await
}
