use crate::api::gmo::api;
use crate::model::OrderSide;
use reqwest::StatusCode;
use serde::{Deserialize, Serialize};

const PATH: &str = "/v1/closeBulkOrder";

#[derive(Deserialize, Debug)]
pub struct CloseBulkOrderResponse {
    pub data: String,
}

#[derive(Serialize, Debug)]
pub struct CloseBulkOrderParameter {
    pub symbol: api::Symbol,
    pub side: OrderSide,
    #[serde(rename = "executionType")]
    pub execution_type: api::ChildOrderType,
    pub price: Option<String>,
    pub size: String,
}

pub async fn close_bulk_order(
    client: &reqwest::Client,
    parameter: &CloseBulkOrderParameter,
) -> Result<(StatusCode, CloseBulkOrderResponse), api::ApiResponseError> {
    api::post::<CloseBulkOrderParameter, CloseBulkOrderResponse>(client, PATH, parameter).await
}
