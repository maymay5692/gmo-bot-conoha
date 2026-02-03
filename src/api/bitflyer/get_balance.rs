use crate::api::bitflyer::api;
use serde::Deserialize;

const PATH: &str = "/v1/me/getbalance";

type GetBalanceResponse = Vec<BalanceDetail>;

#[derive(Deserialize, Debug, Clone)]
pub struct BalanceDetail {
    pub currency_code: String,
    pub amount: f64,
    pub available: f64,
}

pub async fn get_balance(
    client: &reqwest::Client,
) -> Result<GetBalanceResponse, api::ApiResponseError> {
    api::get::<GetBalanceResponse>(client, PATH, None).await
}
