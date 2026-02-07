use crate::api::gmo::api;
use crate::model::OrderSide;
use reqwest::StatusCode;
use serde::{Deserialize, Serialize};

const PATH: &str = "/v1/order";

type PostSendOrderResponse = ChildOrderResponse;

#[derive(Deserialize, Debug)]
pub struct ChildOrderResponse {
    pub status: u32,
    pub data: String,
    pub responsetime: String,
}

#[derive(Serialize, Debug)]
pub struct ChildOrderParameter {
    pub symbol: api::Symbol,
    pub side: OrderSide,

    #[serde(rename = "executionType")]
    pub execution_type: api::ChildOrderType,
    pub price: Option<String>,
    pub size: String,
}

pub async fn post_child_order(
    client: &reqwest::Client,
    parameter: &ChildOrderParameter,
) -> Result<(StatusCode, PostSendOrderResponse), api::ApiResponseError> {
    api::post::<ChildOrderParameter, PostSendOrderResponse>(client, PATH, parameter).await
}
