# DSR (Deflated Sharpe Ratio) 導入 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** バックテスターの各分析モードに DSR を追加し、パラメータ比較の結果が統計的に有意か自動判定する

**Architecture:** `scripts/backtester/dsr.py` に DSR 計算ロジックを実装し、`run_analysis.py` の既存分析関数から呼び出す。scipy.stats を使用。既存モジュールへの変更は最小限（各分析関数末尾に DSR 表示を追加するのみ）。

**Tech Stack:** Python, scipy.stats (norm, skew, kurtosis), 既存 backtester モジュール

---

### Task 1: dsr.py — DSR 計算モジュール作成

**Files:**
- Create: `scripts/backtester/dsr.py`
- Create: `scripts/backtester/tests/test_dsr.py`

- [ ] **Step 1: テスト用ディレクトリ作成**

Run: `mkdir -p scripts/backtester/tests && touch scripts/backtester/tests/__init__.py`

- [ ] **Step 2: failing test を書く — expected_max_sr**

```python
# scripts/backtester/tests/test_dsr.py
"""DSR計算モジュールのテスト。"""
import math
import pytest


def test_expected_max_sr_single_trial():
    """N=1のとき、期待最大SR ≈ 0（1回しか試していない）。"""
    from backtester.dsr import expected_max_sr

    result = expected_max_sr(N=1, T=100, skew=0.0, kurt=0.0)
    # N=1: E[max] of 1 standard normal ≈ 0
    assert abs(result) < 0.1


def test_expected_max_sr_increases_with_n():
    """Nが増えるとexpected_max_srも増加する。"""
    from backtester.dsr import expected_max_sr

    sr_10 = expected_max_sr(N=10, T=100, skew=0.0, kurt=0.0)
    sr_100 = expected_max_sr(N=100, T=100, skew=0.0, kurt=0.0)
    assert sr_100 > sr_10 > 0


def test_expected_max_sr_known_value():
    """N=1000, T=1000, 正規分布のとき SR ≈ 1.4 前後。"""
    from backtester.dsr import expected_max_sr

    result = expected_max_sr(N=1000, T=1000, skew=0.0, kurt=0.0)
    # Bailey & López de Prado: N=1000 → E[max SR] ≈ 1.46
    assert 1.2 < result < 1.7
```

- [ ] **Step 3: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dsr.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 4: expected_max_sr を実装**

```python
# scripts/backtester/dsr.py
"""Deflated Sharpe Ratio (DSR) 計算モジュール。

Bailey & López de Prado (2014) に基づき、多重比較バイアスを補正した
Sharpe Ratio の統計的有意性を判定する。

参照: "The Deflated Sharpe Ratio: Correcting for Selection Bias,
       Backtest Overfitting, and Non-Normality"
"""
from __future__ import annotations

import math

from scipy.stats import norm


def expected_max_sr(
    N: int,
    T: int,
    skew: float = 0.0,
    kurt: float = 0.0,
) -> float:
    """N回の独立試行で偶然出る最大 Sharpe Ratio の期待値。

    Args:
        N:    試行回数（比較パラメータ数）
        T:    サンプル数（trip数）
        skew: P&L分布の歪度
        kurt: P&L分布の超過尖度

    Returns:
        E[max(SR)] — N回試行時に偶然期待される最大SR
    """
    if N <= 0:
        return 0.0
    if N == 1:
        return 0.0

    # SR の標準誤差 (non-normal 補正付き)
    sr_std = math.sqrt(
        (1.0 + 0.25 * kurt - skew * skew) / T
    ) if T > 0 else 1.0

    # E[max] of N i.i.d. standard normals (Euler-Mascheroni approximation)
    euler_mascheroni = 0.5772156649
    z_n = norm.ppf(1.0 - 1.0 / N)
    e_max_z = z_n + euler_mascheroni / z_n if z_n > 0 else 0.0

    return sr_std * e_max_z
```

- [ ] **Step 5: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dsr.py::test_expected_max_sr_single_trial backtester/tests/test_dsr.py::test_expected_max_sr_increases_with_n backtester/tests/test_dsr.py::test_expected_max_sr_known_value -v`
Expected: 3 passed

- [ ] **Step 6: failing test を書く — deflated_sharpe_ratio**

以下を `test_dsr.py` に追加:

```python
def test_dsr_high_sr_is_significant():
    """真に高いSRはDSR ≥ 0.95。"""
    from backtester.dsr import deflated_sharpe_ratio

    # SR=2.0, N=8, T=200 — 非常に高いSR → 有意
    result = deflated_sharpe_ratio(
        sr_observed=2.0, N=8, T=200, skew=0.0, kurt=0.0
    )
    assert result >= 0.95


def test_dsr_low_sr_is_not_significant():
    """偶然レベルのSRはDSR < 0.95。"""
    from backtester.dsr import deflated_sharpe_ratio

    # SR=0.3, N=100, T=50 — 低SR + 多試行 + 少サンプル → 有意でない
    result = deflated_sharpe_ratio(
        sr_observed=0.3, N=100, T=50, skew=0.0, kurt=0.0
    )
    assert result < 0.95


def test_dsr_returns_between_0_and_1():
    """DSRは0〜1の範囲。"""
    from backtester.dsr import deflated_sharpe_ratio

    result = deflated_sharpe_ratio(
        sr_observed=1.0, N=10, T=100, skew=0.0, kurt=0.0
    )
    assert 0.0 <= result <= 1.0


def test_dsr_more_trials_harder_to_pass():
    """Nが増えるとDSRは下がる（有意になりにくい）。"""
    from backtester.dsr import deflated_sharpe_ratio

    dsr_10 = deflated_sharpe_ratio(
        sr_observed=1.0, N=10, T=100, skew=0.0, kurt=0.0
    )
    dsr_100 = deflated_sharpe_ratio(
        sr_observed=1.0, N=100, T=100, skew=0.0, kurt=0.0
    )
    assert dsr_10 > dsr_100
```

- [ ] **Step 7: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dsr.py -v -k "dsr"`
Expected: FAIL with "ImportError"

- [ ] **Step 8: deflated_sharpe_ratio を実装**

以下を `dsr.py` に追加:

```python
def deflated_sharpe_ratio(
    sr_observed: float,
    N: int,
    T: int,
    skew: float = 0.0,
    kurt: float = 0.0,
) -> float:
    """Deflated Sharpe Ratio を計算。

    観測された SR が、N回試行の多重比較バイアスを考慮しても
    統計的に有意かを判定する。

    Args:
        sr_observed: 観測されたベストの Sharpe Ratio
        N:           試行回数（比較パラメータ数）
        T:           サンプル数（trip数）
        skew:        P&L分布の歪度
        kurt:        P&L分布の超過尖度

    Returns:
        DSR値 (0〜1)。0.95以上なら統計的に有意。
    """
    if T <= 1 or N <= 0:
        return 0.0

    sr_benchmark = expected_max_sr(N, T, skew, kurt)

    # SR の標準誤差 (non-normal 補正付き)
    sr_std = math.sqrt(
        (1.0 + 0.25 * kurt - skew * skew) / T
    )

    if sr_std <= 0:
        return 0.0

    # 検定統計量: (observed - benchmark) / std
    test_stat = (sr_observed - sr_benchmark) / sr_std

    # 片側検定の p-value → DSR = 1 - p = CDF(test_stat)
    return float(norm.cdf(test_stat))
```

- [ ] **Step 9: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dsr.py -v`
Expected: 7 passed

- [ ] **Step 10: コミット**

```bash
git add scripts/backtester/dsr.py scripts/backtester/tests/__init__.py scripts/backtester/tests/test_dsr.py
git commit -m "feat: add DSR (Deflated Sharpe Ratio) calculation module"
```

---

### Task 2: DSR ヘルパー — trip P&L 系列から SR を計算

**Files:**
- Modify: `scripts/backtester/dsr.py`
- Modify: `scripts/backtester/tests/test_dsr.py`

- [ ] **Step 1: failing test を書く — calc_sharpe_ratio**

以下を `test_dsr.py` に追加:

```python
def test_calc_sharpe_ratio_positive():
    """正のP&Lリストから正のSRを返す。"""
    from backtester.dsr import calc_sharpe_ratio

    pnl_list = [1.0, 2.0, 1.5, 3.0, 0.5, 2.0, 1.0, 1.5]
    sr = calc_sharpe_ratio(pnl_list)
    assert sr > 0


def test_calc_sharpe_ratio_zero_variance():
    """全て同じ値 → SR = 0.0（ゼロ除算しない）。"""
    from backtester.dsr import calc_sharpe_ratio

    pnl_list = [1.0, 1.0, 1.0, 1.0]
    sr = calc_sharpe_ratio(pnl_list)
    assert sr == 0.0


def test_calc_sharpe_ratio_empty():
    """空リスト → SR = 0.0。"""
    from backtester.dsr import calc_sharpe_ratio

    sr = calc_sharpe_ratio([])
    assert sr == 0.0
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dsr.py -v -k "calc_sharpe"`
Expected: FAIL with "ImportError"

- [ ] **Step 3: calc_sharpe_ratio を実装**

以下を `dsr.py` に追加:

```python
from scipy.stats import kurtosis as sp_kurtosis
from scipy.stats import skew as sp_skew


def calc_sharpe_ratio(pnl_list: list[float]) -> float:
    """trip P&L リストから Sharpe Ratio を算出。

    年率化はせず、per-trip SR を返す。
    DSR 計算では年率化不要（比較対象も同スケールのため）。

    Args:
        pnl_list: tripごとのP&L (JPY) のリスト

    Returns:
        SR = mean / std。std=0 のとき 0.0。
    """
    if len(pnl_list) < 2:
        return 0.0

    mean = sum(pnl_list) / len(pnl_list)
    variance = sum((x - mean) ** 2 for x in pnl_list) / (len(pnl_list) - 1)
    std = math.sqrt(variance)

    if std == 0:
        return 0.0

    return mean / std


def calc_pnl_stats(pnl_list: list[float]) -> dict:
    """P&Lリストから DSR に必要な統計量を一括算出。

    Args:
        pnl_list: tripごとのP&L (JPY) のリスト

    Returns:
        {"sr": float, "T": int, "skew": float, "kurt": float}
    """
    if len(pnl_list) < 2:
        return {"sr": 0.0, "T": len(pnl_list), "skew": 0.0, "kurt": 0.0}

    return {
        "sr": calc_sharpe_ratio(pnl_list),
        "T": len(pnl_list),
        "skew": float(sp_skew(pnl_list)),
        "kurt": float(sp_kurtosis(pnl_list, fisher=True)),
    }
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dsr.py -v`
Expected: 10 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/dsr.py scripts/backtester/tests/test_dsr.py
git commit -m "feat: add calc_sharpe_ratio and calc_pnl_stats helpers"
```

---

### Task 3: DSR 表示フォーマッターと統合ヘルパー

**Files:**
- Modify: `scripts/backtester/dsr.py`
- Modify: `scripts/backtester/tests/test_dsr.py`

- [ ] **Step 1: failing test を書く — format_dsr_result, evaluate_dsr**

以下を `test_dsr.py` に追加:

```python
def test_evaluate_dsr_returns_all_fields():
    """evaluate_dsrが必要な全フィールドを返す。"""
    from backtester.dsr import evaluate_dsr

    pnl_list = [1.0, -0.5, 2.0, -1.0, 0.5, 1.5, -0.3, 0.8]
    result = evaluate_dsr(pnl_list, N=8)
    assert "dsr" in result
    assert "sr_best" in result
    assert "N" in result
    assert "T" in result
    assert "significant" in result
    assert "message" in result


def test_evaluate_dsr_message_significant():
    """有意なとき、メッセージに '有意' が含まれる。"""
    from backtester.dsr import evaluate_dsr

    # 非常に高いSRを作る
    pnl_list = [10.0] * 50 + [9.5] * 50
    result = evaluate_dsr(pnl_list, N=2)
    assert result["significant"] is True
    assert "有意" in result["message"]


def test_evaluate_dsr_message_not_significant():
    """有意でないとき、メッセージに '偶然' が含まれる。"""
    from backtester.dsr import evaluate_dsr

    # ランダムに近いP&L
    pnl_list = [0.1, -0.1, 0.05, -0.05, 0.02, -0.02]
    result = evaluate_dsr(pnl_list, N=100)
    assert result["significant"] is False
    assert "偶然" in result["message"]


def test_format_dsr_line():
    """format_dsr_lineが1行の文字列を返す。"""
    from backtester.dsr import format_dsr_line

    line = format_dsr_line(dsr=0.87, N=8, T=127, sr_best=0.42, significant=False)
    assert "DSR" in line
    assert "0.87" in line
    assert "N=8" in line
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dsr.py -v -k "evaluate or format"`
Expected: FAIL with "ImportError"

- [ ] **Step 3: evaluate_dsr と format_dsr_line を実装**

以下を `dsr.py` に追加:

```python
_DSR_THRESHOLD = 0.95


def evaluate_dsr(
    pnl_list: list[float],
    N: int,
    threshold: float = _DSR_THRESHOLD,
) -> dict:
    """P&Lリストと試行回数NからDSR評価を一括実行。

    Args:
        pnl_list: tripごとのP&L (JPY) のリスト
        N:        試行回数（比較パラメータ数）
        threshold: 有意判定閾値（デフォルト0.95）

    Returns:
        {
            "dsr": float,
            "sr_best": float,
            "N": int,
            "T": int,
            "skew": float,
            "kurt": float,
            "significant": bool,
            "message": str,
        }
    """
    stats = calc_pnl_stats(pnl_list)
    dsr = deflated_sharpe_ratio(
        sr_observed=stats["sr"],
        N=N,
        T=stats["T"],
        skew=stats["skew"],
        kurt=stats["kurt"],
    )
    significant = dsr >= threshold

    if significant:
        message = f"統計的に有意な改善 (DSR={dsr:.2f} >= {threshold})"
    else:
        message = f"閾値{threshold}未満: この改善は偶然の可能性あり (DSR={dsr:.2f})"

    return {
        "dsr": dsr,
        "sr_best": stats["sr"],
        "N": N,
        "T": stats["T"],
        "skew": stats["skew"],
        "kurt": stats["kurt"],
        "significant": significant,
        "message": message,
    }


def format_dsr_line(
    dsr: float,
    N: int,
    T: int,
    sr_best: float,
    significant: bool,
) -> str:
    """DSR結果を1行のフォーマット文字列で返す。

    表示例:
      DSR: 0.87 (N=8, T=127, SR_best=0.42) — 閾値0.95未満: この改善は偶然の可能性あり
    """
    mark = "\u2713" if significant else "\u26a0"
    if significant:
        detail = "統計的に有意な改善"
    else:
        detail = "閾値0.95未満: この改善は偶然の可能性あり"
    return f"DSR: {dsr:.2f} (N={N}, T={T}, SR_best={sr_best:.2f}) \u2014 {mark} {detail}"
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest backtester/tests/test_dsr.py -v`
Expected: 14 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/dsr.py scripts/backtester/tests/test_dsr.py
git commit -m "feat: add evaluate_dsr and format_dsr_line helpers"
```

---

### Task 4: run_analysis.py に DSR 表示を統合

**Files:**
- Modify: `scripts/backtester/run_analysis.py:171-213` (analysis_ev_sim)
- Modify: `scripts/backtester/run_analysis.py:134-168` (analysis_time_filter)

- [ ] **Step 1: run_analysis.py に dsr import を追加**

`run_analysis.py` の既存 import ブロック（L40 付近）の後に追加:

```python
from backtester.dsr import evaluate_dsr, format_dsr_line  # noqa: E402
```

- [ ] **Step 2: analysis_ev_sim に DSR を追加**

`analysis_ev_sim()` 関数末尾（alpha感度分析テーブル表示の後、L213 付近）に追加:

```python
    # --- DSR 判定 ---
    # alpha感度分析: N=len(alphas), P&Lデータはtripsから取得
    matched = [t for t in trips if t.close_fill is not None]
    if matched:
        pnl_list = [t.pnl_jpy for t in matched]
        dsr_result = evaluate_dsr(pnl_list, N=len(alphas))
        print(f"\n  {format_dsr_line(**{k: dsr_result[k] for k in ('dsr', 'N', 'T', 'sr_best', 'significant')})}")
```

注意: `trips` は `analysis_ev_sim` の引数ではなく、呼び出し元の `main()` で保持されている。`analysis_ev_sim` のシグネチャに `trips` を追加する必要がある。

`analysis_ev_sim` の関数定義を変更:

```python
def analysis_ev_sim(trades, metrics, trips, timeline, alpha: float):
```

`main()` 内の呼び出しも修正:

```python
    if args.analysis in ("all", "ev_sim"):
        analysis_ev_sim(trades, metrics, trips, timeline, alpha=args.alpha)
```

- [ ] **Step 3: analysis_time_filter に DSR を追加**

`analysis_time_filter()` 関数末尾（フィルタ比較テーブル表示の後、L166 付近）に追加:

```python
    # --- DSR 判定 ---
    # 時間フィルタ比較: N=len(filters)
    matched = [t for t in trips if t.close_fill is not None]
    if matched:
        pnl_list = [t.pnl_jpy for t in matched]
        dsr_result = evaluate_dsr(pnl_list, N=len(filters))
        print(f"\n  {format_dsr_line(**{k: dsr_result[k] for k in ('dsr', 'N', 'T', 'sr_best', 'significant')})}")

    return result
```

- [ ] **Step 4: 動作確認**

Run: `cd scripts && python backtester/run_analysis.py --date 2026-02-27 --analysis ev_sim`
Expected: alpha感度分析テーブルの後に `DSR: X.XX (N=8, T=..., SR_best=...) — ...` が1行表示される

Run: `cd scripts && python backtester/run_analysis.py --date 2026-02-27 --analysis time_filter`
Expected: フィルタ比較テーブルの後に `DSR: X.XX (N=7, T=..., SR_best=...) — ...` が1行表示される

- [ ] **Step 5: コミット**

```bash
git add scripts/backtester/run_analysis.py
git commit -m "feat: integrate DSR display into ev_sim and time_filter analysis"
```

---

### Task 5: __init__.py 更新と全体テスト

**Files:**
- Modify: `scripts/backtester/__init__.py`

- [ ] **Step 1: __init__.py にモジュール説明を追加**

`__init__.py` の docstring に `dsr` を追加:

```python
"""GMO Bot バックテスター - 実際のCSVデータを使ったリプレイ・what-if分析。

モジュール構成:
  data_loader    - データ読み込み・パース・Trip構築
  market_replay  - 市場状態タイムライン・補間
  ev_formulas    - EV計算式群
  trip_analyzer  - トリップ分析・what-if
  decision_sim   - EVパラメータシミュレーター
  metrics_sim    - 24h Market Hoursシミュレーション (EV-to-P&L比率スケーリング)
  dsr            - Deflated Sharpe Ratio (多重比較バイアス補正)
  run_analysis   - CLI分析エントリポイント
"""
```

- [ ] **Step 2: 全テスト実行**

Run: `cd scripts && python -m pytest backtester/tests/ -v`
Expected: 14 passed

- [ ] **Step 3: コミット**

```bash
git add scripts/backtester/__init__.py
git commit -m "docs: add dsr module to backtester __init__ docstring"
```
