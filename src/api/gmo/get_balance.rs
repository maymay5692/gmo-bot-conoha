use crate::api::gmo::api;
use crate::api::gmo::api::ApiResponseError;
use serde::Deserialize;

const PATH: &str = "/v1/wallet";

#[derive(Deserialize, Debug, Clone)]
pub struct BalanceDetail {
    pub currency: String,
    pub amount: f64,
    pub available: f64,
}

#[derive(Deserialize, Debug, Clone)]
pub struct BalanceResponse {
    pub data: Vec<BalanceDetail>,
}

pub async fn get_balance(
    client: &reqwest::Client,
) -> Result<BalanceResponse, ApiResponseError> {
    api::get::<BalanceResponse>(client, PATH, None).await
}
