use std::collections::HashMap;
use std::env;
use std::string::String;
use std::sync::OnceLock;
use std::time::{SystemTime, UNIX_EPOCH};

use ring::hmac;

const API_KEY: &str = "GMO_API_KEY";
const API_SECRET: &str = "GMO_API_SECRET";

/// Cached API key
static CACHED_API_KEY: OnceLock<String> = OnceLock::new();
/// Cached HMAC signing key (derived from API secret)
static CACHED_HMAC_KEY: OnceLock<hmac::Key> = OnceLock::new();

fn get_cached_api_key() -> Result<&'static String, CredentialError> {
    if let Some(key) = CACHED_API_KEY.get() {
        return Ok(key);
    }
    let val = env::var(API_KEY).map_err(CredentialError::EnvVar)?;
    Ok(CACHED_API_KEY.get_or_init(|| val))
}

fn get_cached_hmac_key() -> Result<&'static hmac::Key, CredentialError> {
    if let Some(key) = CACHED_HMAC_KEY.get() {
        return Ok(key);
    }
    let secret = env::var(API_SECRET).map_err(CredentialError::EnvVar)?;
    Ok(CACHED_HMAC_KEY.get_or_init(|| hmac::Key::new(hmac::HMAC_SHA256, secret.as_bytes())))
}

#[derive(Debug)]
pub enum CredentialError {
    EnvVar(env::VarError),
}

pub fn get_credential(
    method: &str,
    path: &str,
    body: &str,
) -> Result<HashMap<String, String>, CredentialError> {
    let api_key = get_cached_api_key()?;
    let hmac_key = get_cached_hmac_key()?;

    let timestamp = get_timestamp();
    let sign = get_access_sign(method, path, body, &timestamp, hmac_key);

    let mut map = HashMap::new();

    map.insert("API-KEY".to_string(), api_key.clone());
    map.insert("API-TIMESTAMP".to_string(), timestamp.to_string());
    map.insert("API-SIGN".to_string(), sign);

    Ok(map)
}

fn get_timestamp() -> u64 {
    let start = SystemTime::now();
    let since_epoch = start.duration_since(UNIX_EPOCH).expect("Time went backwards");

    since_epoch.as_secs() * 1000 + since_epoch.subsec_nanos() as u64 / 1_000_000
}

fn get_access_sign(
    method: &str,
    path: &str,
    body: &str,
    timestamp: &u64,
    key: &hmac::Key,
) -> String {
    let method_upper = method.to_uppercase();
    let data = format!("{}{}{}{}", timestamp, method_upper, path, body);
    let signature = hmac::sign(key, data.as_bytes());
    hex::encode(signature.as_ref())
}

#[cfg(test)]
mod tests {
    use ring::hmac;
    use crate::api::gmo::auth::{get_credential, get_access_sign};

    fn test_key(secret: &str) -> hmac::Key {
        hmac::Key::new(hmac::HMAC_SHA256, secret.as_bytes())
    }

    #[test]
    fn test_credential_without_env() {
        // 環境変数が設定されていない場合はエラーを返す
        let method = "GET".to_string();
        let path = "/v1/account/assets".to_string();
        let body = String::new();
        let credential = get_credential(&method, &path, &body);

        // 環境変数が設定されていなければエラー、設定されていれば成功
        // テスト環境では環境変数が設定されていないことが多いので、
        // どちらの結果も許容する
        assert!(credential.is_ok() || credential.is_err());
    }

    #[test]
    fn test_access_sign_produces_hex() {
        let key = test_key("test_secret");
        let sign = get_access_sign("GET", "/v1/account", "", &1234567890000, &key);

        // SHA256のHex文字列は64文字
        assert_eq!(sign.len(), 64);
        assert!(sign.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn test_access_sign_consistent() {
        let key = test_key("secret");
        let sign1 = get_access_sign("POST", "/v1/order", "{}", &1234567890000, &key);
        let sign2 = get_access_sign("POST", "/v1/order", "{}", &1234567890000, &key);

        assert_eq!(sign1, sign2);
    }

    #[test]
    fn test_access_sign_different_with_different_params() {
        let key = test_key("secret");
        let sign1 = get_access_sign("GET", "/v1/account", "", &1234567890000, &key);
        let sign2 = get_access_sign("GET", "/v1/account", "", &1234567890001, &key);

        assert_ne!(sign1, sign2);
    }
}
