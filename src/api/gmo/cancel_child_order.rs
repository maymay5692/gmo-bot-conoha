use crate::api::gmo::api;
use reqwest::StatusCode;
use serde::{Deserialize, Serialize};

const PATH: &str = "/v1/cancelOrder";

#[derive(Deserialize, Debug)]
pub struct CancelOrderResponse {}

#[derive(Serialize, Debug)]
pub struct CancelOrderParameter {
    #[serde(rename = "orderId")]
    pub order_id: String,
}

pub async fn cancel_order(
    client: &reqwest::Client,
    parameter: &CancelOrderParameter,
) -> Result<(StatusCode, CancelOrderResponse), api::ApiResponseError> {
    api::post::<CancelOrderParameter, CancelOrderResponse>(client, PATH, parameter).await
}
