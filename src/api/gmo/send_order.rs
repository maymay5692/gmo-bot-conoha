use crate::api::gmo::api;
use crate::model::OrderSide;
use reqwest::StatusCode;
use serde::{Deserialize, Serialize};

const PATH: &str = "/v1/order";

type PostSendOrderResponse = ChildOrderResponse;

#[derive(Deserialize, Debug)]
pub struct ChildOrderResponse {
    pub data: String,
}

#[derive(Serialize, Debug)]
pub struct ChildOrderParameter {
    pub symbol: api::Symbol,
    pub side: OrderSide,

    #[serde(rename = "executionType")]
    pub execution_type: api::ChildOrderType,
    pub price: Option<String>,
    pub size: String,

    #[serde(rename = "timeInForce", skip_serializing_if = "Option::is_none")]
    pub time_in_force: Option<api::TimeInForce>,
}

pub async fn post_child_order(
    client: &reqwest::Client,
    parameter: &ChildOrderParameter,
) -> Result<(StatusCode, PostSendOrderResponse), api::ApiResponseError> {
    api::post::<ChildOrderParameter, PostSendOrderResponse>(client, PATH, parameter).await
}
