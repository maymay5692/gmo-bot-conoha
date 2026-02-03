use crate::time_queue::TimeQueue;
use std::time::Duration;

// ベータ分布を用いたベイズ確率
// データは直近duration間を保持するTimeQueueを用いる
#[derive(Debug, Clone)]
pub struct BayesProb {
    pub distribution: BetaDistribution,
    time_data: TimeQueue<(u64, u64)>,
}

impl BayesProb {
    pub fn new(prior_distribution: BetaDistribution, retain_duration: Duration) -> BayesProb {
        BayesProb {
            distribution: prior_distribution,
            time_data: TimeQueue::new(retain_duration),
        }
    }

    // ベイズ更新
    // n: 試行回数, r: 成功回数
    // 1回試行して成功したかを更新する場合はupdate(1, 1 or 0)とする
    pub fn update(&mut self, n: u64, r: u64) {
        self.time_data.retain();
        self.time_data.push((n, r));

        let (b, a) = self.time_data.get_data().iter()
            .fold((0, 0), |(acc_a, acc_b), (a, b)| (acc_a + a, acc_b + b));

        self.distribution = BetaDistribution::new(a, b - a);
    }
    
    // ベータ分布の平均確率
    pub fn calc_average(&self) -> f64 {
        let denominator = self.distribution.a + self.distribution.b;
        if denominator == 0 {
            return 0.5; // Return uninformative prior expectation
        }
        let e = self.distribution.a as f64 / denominator as f64;
        e.clamp(0.0, 1.0)
    }    
}

// ベータ分布
#[derive(Debug, Clone)]
pub struct BetaDistribution {
    pub a: u64,
    pub b: u64,
}

impl BetaDistribution {
    pub fn new(a: u64, b: u64) -> BetaDistribution {
        BetaDistribution { a, b }
    }
}
