extern crate hyper;

use crate::api::gmo::auth::{get_credential, CredentialError};
use hyper::header::{HeaderMap, HeaderName, CONTENT_TYPE};
use hyper::http::HeaderValue;
use reqwest::{Method, StatusCode, Url};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fmt;
use std::str::FromStr;
use serde::Deserializer;
use tracing::{debug, error};

pub const ENDPOINT: &str = "https://api.coin.z.com/private";

pub fn deserialize_number_from_string<'de, D, T>(deserializer: D) -> Result<T, D::Error>
where
    D: Deserializer<'de>,
    T: std::str::FromStr,
    T::Err: std::fmt::Display,
{
    let s = String::deserialize(deserializer)?;
    T::from_str(&s).map_err(serde::de::Error::custom)
}

#[allow(non_camel_case_types)]
#[derive(Serialize, Deserialize, Debug)]
pub enum Symbol {
    Unknown,
    BTC_JPY,
}

impl fmt::Display for Symbol {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match *self {
            Symbol::BTC_JPY => write!(f, "BTC_JPY"),
            _ => write!(f, "Unknown"),
        }
    }
}

impl FromStr for Symbol {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "BTC_JPY" => Ok(Symbol::BTC_JPY),
            _ => Err(()),
        }
    }
}

#[derive(Serialize, Deserialize, Debug)]
pub enum ChildOrderType {
    Unknown,
    LIMIT,
    MARKET,
}

impl fmt::Display for ChildOrderType {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match *self {
            ChildOrderType::LIMIT => write!(f, "LIMIT"),
            ChildOrderType::MARKET => write!(f, "MARKET"),
            _ => write!(f, "Unknown"),
        }
    }
}

#[derive(Serialize, Debug, Clone)]
pub enum TimeInForce {
    SOK,
    FAK,
    FAS,
    FOK,
}

impl FromStr for ChildOrderType {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "LIMIT" => Ok(ChildOrderType::LIMIT),
            "MARKET" => Ok(ChildOrderType::MARKET),
            _ => Err(()),
        }
    }
}

/// GMO API error message returned when status != 0
#[derive(Deserialize, Debug, Clone)]
pub struct ApiErrorMessage {
    pub message_code: String,
    pub message_string: String,
}

impl fmt::Display for ApiErrorMessage {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "[{}] {}", self.message_code, self.message_string)
    }
}

/// Common API response envelope for status checking (two-stage parsing)
#[derive(Deserialize, Debug)]
struct ApiRawResponse {
    pub status: i32,
    pub messages: Option<Vec<ApiErrorMessage>>,
    #[allow(dead_code)]
    pub responsetime: Option<String>,
}

#[derive(Debug)]
pub enum ApiResponseError {
    Credential(CredentialError),
    Reqwest(reqwest::Error),
    StatusCode(StatusCode),
    UrlParse(url::ParseError),
    Deserialize(serde_json::Error),
    ApiError(Vec<ApiErrorMessage>),
}

impl fmt::Display for ApiResponseError {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            ApiResponseError::Credential(e) => write!(f, "Credential error: {:?}", e),
            ApiResponseError::Reqwest(e) => write!(f, "Request error: {}", e),
            ApiResponseError::StatusCode(s) => write!(f, "HTTP status: {}", s),
            ApiResponseError::UrlParse(e) => write!(f, "URL parse error: {}", e),
            ApiResponseError::Deserialize(e) => write!(f, "Deserialize error: {}", e),
            ApiResponseError::ApiError(msgs) => {
                let msg_str: Vec<String> = msgs.iter().map(|m| m.to_string()).collect();
                write!(f, "API error: {}", msg_str.join(", "))
            }
        }
    }
}

impl From<CredentialError> for ApiResponseError {
    fn from(error: CredentialError) -> Self {
        ApiResponseError::Credential(error)
    }
}

impl From<serde_json::Error> for ApiResponseError {
    fn from(error: serde_json::Error) -> Self {
        ApiResponseError::Deserialize(error)
    }
}

impl From<StatusCode> for ApiResponseError {
    fn from(e: StatusCode) -> ApiResponseError {
        ApiResponseError::StatusCode(e)
    }
}

impl From<reqwest::Error> for ApiResponseError {
    fn from(e: reqwest::Error) -> ApiResponseError {
        ApiResponseError::Reqwest(e)
    }
}

impl From<url::ParseError> for ApiResponseError {
    fn from(e: url::ParseError) -> ApiResponseError {
        ApiResponseError::UrlParse(e)
    }
}

async fn handle_response<T: serde::de::DeserializeOwned + std::fmt::Debug>(
    response: Result<reqwest::Response, reqwest::Error>,
) -> Result<T, ApiResponseError> {
    let response = response?;
    let status = response.status();
    let response_text = response.text().await?;

    debug!("API response: {}", response_text);

    // Stage 1: HTTP status check
    if !status.is_success() {
        error!("HTTP error: {}", status);
        return Err(ApiResponseError::from(status));
    }

    // Stage 2: Parse envelope to check GMO API status
    let raw: ApiRawResponse = match serde_json::from_str(&response_text) {
        Ok(r) => r,
        Err(e) => {
            error!("Failed to parse API envelope: {}", e);
            return Err(ApiResponseError::Deserialize(e));
        }
    };

    // Stage 3: Check business-logic status
    if raw.status != 0 {
        let messages = raw.messages.unwrap_or_else(|| vec![ApiErrorMessage {
            message_code: "UNKNOWN".to_string(),
            message_string: format!("API returned status {}", raw.status),
        }]);
        error!("API error: {:?}", messages);
        return Err(ApiResponseError::ApiError(messages));
    }

    // Stage 4: Parse full response (only on success)
    match serde_json::from_str(&response_text) {
        Ok(parsed) => Ok(parsed),
        Err(e) => {
            error!("Failed to parse response data: {}", e);
            Err(ApiResponseError::Deserialize(e))
        }
    }
}

pub async fn get<T: serde::de::DeserializeOwned + std::fmt::Debug>(
    client: &reqwest::Client,
    path: &str,
    query: Option<&HashMap<String, String>>,
) -> Result<T, ApiResponseError> {
    let url_str = format!("{}{}", ENDPOINT, path);
    let url = match query {
        Some(q) => Url::parse_with_params(&url_str, q)?,
        None => Url::parse(&url_str)?,
    };
    let header = make_http_header(Method::GET.as_ref(), path, "")?;

    let get = client.get(url).headers(header).send().await;
    handle_response(get).await
}

pub async fn post<T: serde::Serialize, U: serde::de::DeserializeOwned + std::fmt::Debug>(
    client: &reqwest::Client,
    path: &str,
    body: &T,
) -> Result<(StatusCode, U), ApiResponseError> {
    let url_str = format!("{}{}", ENDPOINT, path);
    let url = Url::parse(&url_str)?;
    let body_json = serde_json::to_string(body)
        .map_err(ApiResponseError::Deserialize)?;
    let header = make_http_header(Method::POST.as_ref(), path, &body_json)?;
    let post = client.post(url).headers(header).json(body).send().await;
    let response = handle_response(post).await?;
    Ok((StatusCode::OK, response))
}

fn make_http_header(method: &str, path: &str, body: &str) -> Result<HeaderMap, CredentialError> {
    let mut header = HeaderMap::new();
    let credential = get_credential(method, path, body)?;

    let content_type = "application/json".parse()
        .expect("Invalid content type");
    header.insert(CONTENT_TYPE, content_type);

    for (k, v) in credential {
        let key = k.parse::<HeaderName>()
            .expect("Invalid header name");
        let val = v.parse::<HeaderValue>()
            .expect("Invalid header value");
        header.insert(key, val);
    }

    Ok(header)
}
