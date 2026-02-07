//! GMOコイン高頻度取引Bot ライブラリ
//!
//! このクレートは、GMOコインAPIを使用した高頻度取引botの
//! コア機能を提供します。

pub mod api;
pub mod bayes_prob;
pub mod logging;
pub mod model;
pub mod time_queue;
pub mod util;
