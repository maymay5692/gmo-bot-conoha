extern crate hyper;

use crate::api::bitflyer::auth::{CredentialError, get_credential};
use hyper::header::{HeaderMap, HeaderName, CONTENT_TYPE};
use hyper::http::HeaderValue;
use reqwest::{Method, StatusCode, Url};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fmt;
use std::str::FromStr;

pub const ENDPOINT: &str = "https://api.bitflyer.com";

#[allow(non_camel_case_types)]
#[derive(Serialize, Deserialize, Debug)]
pub enum ProductCode {
    Unknown,
    FX_BTC_JPY,
    BTC_JPY,
}

impl fmt::Display for ProductCode {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match *self {
            ProductCode::FX_BTC_JPY => write!(f, "FX_BTC_JPY"),
            ProductCode::BTC_JPY => write!(f, "BTC_JPY"),
            _ => write!(f, "Unknown"),
        }
    }
}

impl FromStr for ProductCode {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "FX_BTC_JPY" => Ok(ProductCode::FX_BTC_JPY),
            "BTC_JPY" => Ok(ProductCode::BTC_JPY),
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

#[derive(Debug)]
pub enum ApiResponseError {
    Credential(CredentialError),
    Reqwest(reqwest::Error),
    StatusCode(StatusCode),
    UrlParse(url::ParseError),
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

pub async fn get<T: serde::de::DeserializeOwned>(
    client: &reqwest::Client,
    path: &str,
    query: Option<&HashMap<String, String>>,
) -> Result<T, ApiResponseError> {
    let url_str = format!("{}{}", ENDPOINT, path);
    let url = match query {
        Some(q) => Url::parse_with_params(&url_str, q)?,
        None => Url::parse(&url_str)?,
    };
    let header_path = match query {
        Some(_) => url.path().to_string() + "?" + url.query().unwrap(),
        None => url.path().to_string(),
    };

    let header = make_http_header(Method::GET.as_ref(), &header_path, "");
    if header.is_err() {
        return Err(ApiResponseError::Credential(header.err().unwrap()));
    };

    let get = client.get(url).headers(header.unwrap()).send().await;

    match get {
        Ok(t) => {
            if t.status().is_success() {
                Ok(t.json().await?)
            } else {
                Err(ApiResponseError::from(t.status()))
            }
        }
        Err(e) => Err(ApiResponseError::from(e)),
    }
}

pub async fn post<T: serde::Serialize, U: serde::de::DeserializeOwned>(
    client: &reqwest::Client,
    path: &str,
    body: &T,
) -> Result<(StatusCode, U), ApiResponseError> {
    let url_str = format!("{}{}", ENDPOINT, path);
    let url = Url::parse(&url_str)?;
    let body_json = serde_json::to_string(body)
        .expect("Failed to serialize request body");
    let header = make_http_header(Method::POST.as_ref(), path, &body_json)
        .map_err(ApiResponseError::Credential)?;
    let post = client.post(url).headers(header).json(body).send().await;

    match post {
        Ok(t) => {
            if t.status().is_success() {
                Ok((t.status(), t.json().await?))
            } else {
                Err(ApiResponseError::from(t.status()))
            }
        }
        Err(e) => Err(ApiResponseError::from(e)),
    }
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
