use std::time::{Duration, Instant};

// 直近duration間のdataを保持する
#[derive(Debug, Clone)]
pub struct TimeQueue<T: Clone> {
    duration: Duration,
    data: Vec<(Instant, T)>,
}

impl<T: Clone> TimeQueue<T> {
    pub fn new(duration: Duration) -> Self {
        Self {
            duration,
            data: Vec::new(),
        }
    }

    pub fn duration(&self) -> Duration {
        self.duration
    }

    pub fn data(&self) -> &Vec<(Instant, T)> {
        &self.data
    }

    pub fn push(&mut self, item: T) {
        let now = Instant::now();
        self.data.push((now, item));
    }

    pub fn extend(&mut self, items: Vec<T>) {
        let now = Instant::now();
        self.data.extend(items.into_iter().map(|item| (now, item)));
    }

    pub fn first(&self) -> Option<T> {
        self.data.first().map(|(_, item)| item.clone())
    }

    pub fn last(&self) -> Option<T> {
        self.data.last().map(|(_, item)| item.clone())
    }

    pub fn get_data(&self) -> Vec<T> {
        self.data.iter().map(|(_, item)| item.clone()).collect()
    }

    pub fn retain(&mut self) {
        let now = Instant::now();
        self.data
            .retain(|(instant, _)| now.duration_since(*instant) <= self.duration);
    }

    pub fn len(&self) -> usize {
        self.data.len()
    }

    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }
}
