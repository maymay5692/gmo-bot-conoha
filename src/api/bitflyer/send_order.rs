use crate::api::bitflyer::api;
use crate::model::OrderSide;
use hyper::StatusCode;
use serde::{Deserialize, Serialize};

const PATH: &str = "/v1/me/sendchildorder";

type PostSendOrderResponse = ChildOrderResponse;

#[derive(Deserialize, Debug)]
pub struct ChildOrderResponse {
    pub child_order_acceptance_id: String,
}

#[derive(Serialize, Debug)]
pub struct ChildOrderParameter {
    pub product_code: api::ProductCode,
    pub child_order_type: api::ChildOrderType,
    pub side: OrderSide,
    pub price: Option<u64>,
    pub size: f64,
    pub minute_to_expire: u32,
}

pub async fn post_child_order(
    client: &reqwest::Client,
    parameter: &ChildOrderParameter,
) -> Result<(StatusCode, PostSendOrderResponse), api::ApiResponseError> {
    api::post::<ChildOrderParameter, PostSendOrderResponse>(client, PATH, parameter).await
}
