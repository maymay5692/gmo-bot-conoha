use crate::api::gmo::api;
use reqwest::StatusCode;
use serde::Serialize;

const PATH: &str = "/v1/cancelOrder";

#[derive(Serialize, Debug)]
pub struct CancelOrderParameter {
    #[serde(rename = "orderId")]
    pub order_id: String,
}

pub async fn cancel_order(
    client: &reqwest::Client,
    parameter: &CancelOrderParameter,
) -> Result<(StatusCode, ()), api::ApiResponseError> {
    api::post::<CancelOrderParameter, ()>(client, PATH, parameter).await
}
