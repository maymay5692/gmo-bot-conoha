use crate::api::gmo::api;
use crate::api::gmo::api::deserialize_number_from_string;
use serde::{Deserialize};

const PATH: &str = "/v1/account/margin";

#[derive(Debug, Deserialize, Clone)]
pub struct Collateral {
    pub data: CollateralDetail,
}

#[derive(Debug, Deserialize, Clone)]
pub struct CollateralDetail {
    #[serde(deserialize_with = "deserialize_number_from_string", rename = "actualProfitLoss")]
    pub actual_profit_loss: f64,

    #[serde(deserialize_with = "deserialize_number_from_string", rename = "availableAmount")]
    pub available_amount: f64,

    #[serde(deserialize_with = "deserialize_number_from_string")]
    pub margin: f64,

    #[serde(deserialize_with = "deserialize_number_from_string", rename = "profitLoss")]
    pub profit_loss: f64,

    #[serde(rename = "marginCallStatus")]
    pub margin_call_status: String,
}

pub async fn get_collateral(client: &reqwest::Client) -> Result<Collateral, api::ApiResponseError> {
    api::get::<Collateral>(client, PATH, None).await
}
