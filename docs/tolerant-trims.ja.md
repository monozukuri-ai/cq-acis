# トレラント境界と有限 spline トリム

[English](tolerant-trims.md) | 日本語

0.3.3 以降で、観測済み ASM 22700／内部 22601 の以下のプロファイルに対応します。
Rust 連携では core・bridge・Python パッケージのバージョンを揃えてください。
[共有モデル API](model-api.ja.md) を参照してください。

## 対応する境界と定義域

- `tedge-edge` と inline curve がない `tcoedge-coedge` は、直線・楕円・明示 spline が
  保存頂点と元のモデルの `resabs` 以内で一致する場合に変換できます。
  保存された向き、パラメータ区間、ループの前後リンクも一致する必要があります。
  元のエンティティは raw のまま保持します。
- forward の明示 spline 曲面と対応する subtype 参照で有限 U/V 範囲を保持します。
  範囲は clamped knot 定義域内の空でない部分領域に限定します。
  反転 chart、周期 spline、未知の末尾フィールドは未対応です。
  評価対象は変更していない元の支持曲面です。
- 面のトリム全体が有限の支持領域内に収まる必要があります。
  領域外に出るトリムは面を拒否し、切り落として補いません。
  保存 chart と区間の丸め差は最大 `1e-10` パラメータ単位
  （大きな UV 座標では 64 ULP）までで、幾何許容差とは別に扱います。
- forward・2 knot・次数 1 の `exp_par_cur` は、支持曲面と同じ明示 spline 定義を
  参照する場合に保存 UV 直線として使用できます。内包する支持範囲は無限、
  chart shift はゼロに限定します。その他の pcurve は対応する範囲で照合付き投影を使います。

## Pcurve ビューと診断

`NativeModel.linear_surface_pcurve(pcurve_ref, surface_ref)` は
`LinearSurfacePcurve` ビューを返し、別のプロファイルでは `None` を返します。
対応プロファイル内の破損や支持曲面の不一致は `AcisModelError` です。
元の pcurve、区間、UV の 2 点、保存 fit tolerance、定義の出典を保持します。

使用する 2D 曲線は支持曲面上で元の 3D 辺と一致し、偏差が元のモデルの許容差内に
収まる必要があります。トレラント数値や保存 fit tolerance で許容差を広げません。
inline coedge curve と、推測に基づく局所的な修復規則は未対応です。

変換器の `tolerant_boundaries`、`saved_pcurves`、`bounded_surface_faces` は
要素ごとの検査結果です。ビューの取得や個別面の変換に成功しても、完成ソリッドは
保証しません。他の境界・曲面・シェルが未対応または不正なら、全体の変換は失敗します。
Inventor の現在の Model State との一致を保証する機能ではありません。

[形状の制限](geometry-support.md)、[バイナリ履歴の制限](sab-support.md)、
[エラーの扱い](usage.md#errors-and-diagnostics)も参照してください。
