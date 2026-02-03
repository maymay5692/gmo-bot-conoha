use crate::api::gmo::api;
use crate::api::gmo::api::ApiResponseError;
use serde::Deserialize;

const PATH: &str = "/v1/wallet";

type GetBalanceResponse = Vec<BalanceDetail>;

#[derive(Deserialize, Debug, Clone)]
pub struct BalanceDetail {
    pub currency: String,
    pub amount: f64,
    pub available: f64,
}

pub async fn get_balance(
    client: &reqwest::Client,
) -> Result<GetBalanceResponse, ApiResponseError> {
    api::get::<GetBalanceResponse>(client, PATH, None).await
}
