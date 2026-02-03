// 少数点8桁までで丸める
pub fn round_size(size: f64) -> f64 {
    let base: f64 = 10.0;
    let floating_point = 8.0;
    let pow = base.powf(floating_point);
    (size * pow).round() / pow
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn test_round_size() {
        let size = 1.23456789;
        let rounded = round_size(size);
        assert_eq!(rounded, 1.23456789);
    }

    #[test]
    fn test_round_size2() {
        let size = 0.01;
        let rounded = round_size(size);
        assert_eq!(rounded, 0.01);
    }

    #[test]
    fn test_round_size3() {
        let size = 0.123456789;
        let rounded = round_size(size);
        assert_eq!(rounded, 0.12345679);
    }
}
