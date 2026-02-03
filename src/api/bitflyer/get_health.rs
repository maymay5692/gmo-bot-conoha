use crate::api::bitflyer::api;
use reqwest;
use serde::Deserialize;
use std::str::FromStr;

const PATH: &str = "/v1/gethealth";

#[derive(Deserialize, Debug)]
pub struct HealthStatus {
    pub status: HealthStatusEnum,
}

#[derive(Deserialize, Debug)]
pub enum HealthStatusEnum {
    Normal,
    Busy,
    VeryBusy,
    SuperBusy,
    NoOrder,
    Stop,
    Unknown,
}

impl FromStr for HealthStatusEnum {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "NORMAL" => Ok(HealthStatusEnum::Normal),
            "BUSY" => Ok(HealthStatusEnum::Busy),
            "VERY BUSY" => Ok(HealthStatusEnum::VeryBusy),
            "SUPER BUSY" => Ok(HealthStatusEnum::SuperBusy),
            "NO ORDER" => Ok(HealthStatusEnum::NoOrder),
            "STOP" => Ok(HealthStatusEnum::Stop),
            _ => Ok(HealthStatusEnum::Unknown),
        }
    }
}

pub async fn get_health(client: &reqwest::Client) -> Result<std::string::String, reqwest::Error> {
    let client = client.clone();

    match client.get(api::ENDPOINT.to_owned() + PATH).send().await {
        Ok(res) => res.text().await,
        Err(e) => Err(e),
    }
}
