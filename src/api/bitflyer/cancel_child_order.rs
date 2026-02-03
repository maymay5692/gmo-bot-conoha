use crate::api::bitflyer::api;
use reqwest::StatusCode;
use serde::Serialize;

const PATH: &str = "/v1/me/cancelchildorder";

#[derive(Serialize, Debug)]
pub struct CancelChildOrderParameter {
    pub product_code: api::ProductCode,
    pub child_order_acceptance_id: String,
}

pub async fn cancel_child_order(
    client: &reqwest::Client,
    parameter: &CancelChildOrderParameter,
) -> Result<(StatusCode, ()), api::ApiResponseError> {
    api::post::<CancelChildOrderParameter, ()>(client, PATH, parameter).await
}
