# close_fill_sim — Close Fill シミュレータ設計

## 概要

close注文のfill確率を確率的にモデル化し、(min_hold, close_spread_factor) のパラメータスイープを
Lookahead bias なしで実行するシミュレータ。既存 min_hold_sim.py の「mid即時fill」仮定を置き換える。

## 背景と目的

### 既存 min_hold_sim.py の問題

min_hold_sim.py は3つの非現実的な仮定を置いている:

1. **close は min_hold 時点の mid 価格で即時 fill** — 実際は `mid +/- spread * factor` の LIMIT 注文で、fill まで cancel-resubmit が複数回発生する
2. **fill 確率 = 100%** — 実際は LIMIT 注文が板に触れるかは不確定
3. **spread_captured は元 trip から流用** — min_hold 変更後の close 価格・spread 環境が反映されていない

これにより min_hold_sim の結果は楽観的であり、パラメータ変更の判断材料として信頼性が低い。

### close_fill_sim の目的

- (min_hold, close_spread_factor) の42組を独立にシミュレーションし、最適組み合わせを DSR 付きで推薦する
- 各パラメータ組で「実際の bot が何をするか」を忠実に再現する
- 結果を v0.16.0 のパラメータ決定に使う

## アーキテクチャ

### データフロー

```
入力:
  metrics.csv  --> market_timeline (3s snapshots: mid, bid, ask, sigma_1s, spread)
  trades.csv   --> trips (open_fill with level/side/price/timestamp)

処理:
  for each (min_hold, close_spread_factor) pair:
    for each trip:
      Phase 1: Hold期間 -- SLチェックのみ
      Phase 2: Close試行 -- fill確率判定 + SLチェック

出力:
  per-trip SimResult list --> DSR評価
                         --> 集計メトリクス
                         --> (min_hold, factor) グリッド表示
```

### モジュール配置

```
scripts/backtester/
  close_fill_sim.py   <-- 新規（本スペック対象）
  run_analysis.py      <-- close_fill モード追加
  data_loader.py       <-- 変更なし（Trip, MetricsRow を使用）
  market_replay.py     <-- 変更なし（build_market_timeline, get_market_state_at を使用）
  dsr.py               <-- 変更なし（evaluate_dsr を使用）
```

### スコープ制限

- open 側の EV 選択・level 選択はシミュレーション対象外
- 既存 trip の open_fill をそのまま使い、close 側のみ再シミュレーション
- min_hold_sim.py は簡易版として共存させる（差分が Lookahead bias の定量指標になる）

## シミュレーションエンジン

### Phase 1 — Hold 期間 [open_time -> open_time + min_hold_s]

各 3s ティックで SL チェックのみ実行。close 注文は出さない。

```python
for tick in ticks_during_hold:
    unrealized = (tick.mid - open_price) * size * direction
    if unrealized < -stop_loss_jpy:
        return SimResult(outcome="sl", simulated_pnl=unrealized, ...)
```

min_hold は close 注文を抑制するだけで、SL は常に有効。
min_hold=300s でも 60s 時点で unrealized < -15 なら SL 発動。

### Phase 2 — Close 試行期間 [open_time + min_hold_s -> fill or SL or データ末端]

各 3s ティックで以下を順に実行:

1. SL チェック（Phase 1 と同一）
2. close LIMIT price 計算
3. fill 確率判定
4. fill -> P&L 記録、終了

### Close 価格の計算（Rust ロジック再現）

各 3s ティックで更新:

```python
level_spread_jpy = open_fill.spread_pct * current_mid
adjusted_spread = level_spread_jpy - POSITION_PENALTY  # POSITION_PENALTY = 50.0

if opened_long:   # close = SELL limit
    close_price = max(current_mid + adjusted_spread * factor, current_mid + 1)
else:             # close = BUY limit
    close_price = min(current_mid - adjusted_spread * factor, current_mid - 1)
```

- `spread_pct` — trip の open_fill.spread_pct（実データ、e.g. 25e-5 for L25）
- `current_mid` — 各ティックの metrics.mid_price
- `factor` — sweep 対象パラメータ (close_spread_factor)
- `POSITION_PENALTY = 50.0` — Rust ハードコード値、0.001 BTC (1 lot) 時

### Fill 確率モデル（Brownian micro-fill）

3s ティック間隔内の sub-second fill を確率的に捕捉する。

```python
DT = 3.0  # ティック間隔（秒）

if opened_long:  # close = SELL limit, fill条件: best_bid >= close_price
    if best_bid >= close_price:
        p_fill = 1.0
    else:
        distance = close_price - best_bid
        sigma_jpy = sigma_1s * current_mid
        p_fill = 2 * norm.cdf(-distance / (sigma_jpy * sqrt(DT)))
else:            # close = BUY limit, fill条件: best_ask <= close_price
    if best_ask <= close_price:
        p_fill = 1.0
    else:
        distance = best_ask - close_price
        sigma_jpy = sigma_1s * current_mid
        p_fill = 2 * norm.cdf(-distance / (sigma_jpy * sqrt(DT)))
```

根拠 — Brownian motion の first passage time: 価格が距離 d を時間 dt 内に横断する確率は
`2 * Phi(-d / (sigma * sqrt(dt)))` で近似できる（対称ランダムウォーク仮定）。

エッジケース:
- `sigma_1s == 0` — p_fill = 0.0（ボラゼロ = 価格不動）
- `distance <= 0` — p_fill = 1.0（既に板が close price を超えている）
- metrics データが open_time + min_hold 以前に終了 — trip を "timeout" として最終 mid で評価

### 期待値モード（推奨、決定論的）

各 trip の simulated P&L を決定論的に計算。乱数を使わないため完全に再現可能。

```python
p_survive = 1.0
expected_pnl = 0.0

for tick in close_phase_ticks:
    # 1. SL チェック（決定論的）
    unrealized = (tick.mid - open_price) * size * direction
    if unrealized < -stop_loss_jpy:
        expected_pnl += p_survive * unrealized
        p_survive = 0.0
        break

    # 2. fill 確率
    close_price = calc_close_price(tick, open_fill, factor)
    p_fill = calc_fill_prob(tick, close_price, direction)

    # 3. fill 時の P&L（limit price で fill）
    fill_pnl = (close_price - open_price) * size * direction
    expected_pnl += p_survive * p_fill * fill_pnl

    # 4. 残存確率を更新
    p_survive *= (1 - p_fill)

# データ末端到達
if p_survive > 0:
    terminal_pnl = (last_mid - open_price) * size * direction
    expected_pnl += p_survive * terminal_pnl
```

`p_survive` — 各ティック時点で「まだ fill も SL もしていない」確率。
ティックごとに `P(fill at k) = p_survive * p_fill` を P&L に加算し、残存確率を減衰させる。

### P&L 計算

| イベント | fill 価格 | P&L 計算 |
|----------|-----------|----------|
| Close fill | close_price (limit) | (close_price - open_price) * 0.001 * direction |
| SL | mid (market close) | unrealized at that tick |
| タイムアウト | last_mid | unrealized at last tick |

- `open_price` = `open_fill.price`（実際の約定価格、mid ではない）
- `direction` = +1 (long=BUY open), -1 (short=SELL open)
- `size` = 0.001 BTC（config の min_lot = max_lot = 0.001 から固定）
- 手数料 = 0（GMO レバレッジは Maker/Taker 無料）

## パラメータスイープ

### デフォルト値

| パラメータ | デフォルト | 備考 |
|-----------|-----------|------|
| min_hold_s | [60, 90, 120, 180, 240, 300] | 180 が現行値 |
| close_spread_factor | [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7] | 0.4 が現行値 |
| stop_loss_jpy | 15.0 | 現行値固定 |
| position_penalty | 50.0 | Rust ハードコード値 |

合計 42 組。CLI で個別指定も可能。

### DSR 適用

42 組の多重検定に対し DSR (Deflated Sharpe Ratio) で補正:

- 各組の per-trip P&L リストから Sharpe ratio を計算
- `evaluate_dsr(pnl_list, N=42)` で統計的有意性を判定
- significant (DSR >= 0.95) なセルのみ推薦対象

### キャリブレーション検証

(min_hold=180, factor=0.4) = 現行設定でのシミュレーション結果を、
同日の GMO 真値 P&L と比較。乖離が大きければモデル前提を再検討。

許容基準 — シミュレーション P&L と GMO 真値の差が +/-30% 以内。

## 出力

### グリッド表示

```
P&L/trip (JPY)     factor=0.1  0.2   0.3   0.4*  0.5   0.6   0.7
min_hold= 60s      ...         ...   ...   ...   ...   ...   ...
          90s      ...         ...   ...   ...   ...   ...   ...
         120s      ...         ...   ...   ...   ...   ...   ...
         180s*     ...         ...   ...   ...   ...   ...   ...
         240s      ...         ...   ...   ...   ...   ...   ...
         300s      ...         ...   ...   ...   ...   ...   ...

* = 現行値。DSR significant に check マーク
```

同形式で win 率・SL 率・avg_hold_time グリッドも出力。

### 詳細メトリクス（各組ごと）

- trip 数, fill 数, SL 数, timeout 数
- 合計 P&L, P&L/trip, win 率
- 平均 hold_time (open -> simulated fill)
- 平均 close_delay (min_hold 経過後 -> fill)
- 平均 spread_captured
- Sharpe ratio (per-trip)
- DSR (N=42)

## 公開インターフェース

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class SimResult:
    """1 trip x 1 パラメータ組のシミュレーション結果"""
    trip_index: int
    min_hold_s: int
    factor: float
    simulated_pnl: float      # 期待値モードの加重P&L (全outcome合算)
    dominant_outcome: str      # 最大確率質量の outcome ("fill" | "sl" | "timeout")
    p_fill: float             # fill に帰属した確率質量の合計
    p_sl: float               # SL に帰属した確率質量
    p_timeout: float          # タイムアウトに帰属した確率質量 (= 最終 p_survive)
    simulated_hold_s: float   # open -> 最終イベントまでの秒数
    close_delay_s: float      # min_hold経過後 -> 最終イベント
    weighted_fill_price: float # P(fill at k) で加重した平均 fill price

def simulate_close_fill(
    trips: list[Trip],
    timeline: list[MarketState],
    min_hold_s: int,
    close_spread_factor: float,
    stop_loss_jpy: float = 15.0,
    position_penalty: float = 50.0,
) -> list[SimResult]:
    """単一パラメータ組での全trip シミュレーション"""
    ...

def run_close_fill_sweep(
    trips: list[Trip],
    timeline: list[MarketState],
    min_holds: list[int] | None = None,
    factors: list[float] | None = None,
    stop_loss_jpy: float = 15.0,
) -> dict[tuple[int, float], list[SimResult]]:
    """全パラメータ組のスイープ実行。
    デフォルト: min_holds=[60,90,120,180,240,300], factors=[0.1,0.2,...,0.7]
    戻り値: {(min_hold, factor): [SimResult, ...]}
    """
    ...

def print_sweep_grid(
    sweep_results: dict[tuple[int, float], list[SimResult]],
    metric: str = "pnl_per_trip",
) -> None:
    """グリッド形式でスイープ結果を表示"""
    ...
```

## CLI

```bash
# 基本実行
python scripts/backtester/run_analysis.py --date 2026-04-08 --analysis close_fill

# パラメータ指定
python scripts/backtester/run_analysis.py --date 2026-04-08 --analysis close_fill \
    --min-holds 60,90,120,180,240,300 \
    --factors 0.1,0.2,0.3,0.4,0.5,0.6,0.7

# 全分析に含める
python scripts/backtester/run_analysis.py --date 2026-04-08 --analysis all
```

## 既存コードとの関係

| モジュール | 変更 |
|-----------|------|
| close_fill_sim.py | 新規作成 |
| run_analysis.py | close_fill モード追加 |
| data_loader.py | 変更なし |
| market_replay.py | 変更なし |
| dsr.py | 変更なし |
| min_hold_sim.py | 変更なし（共存） |

min_hold_sim は「mid 即時 fill」簡易版として残す。
close_fill_sim との差分が Lookahead bias の定量指標になる。
