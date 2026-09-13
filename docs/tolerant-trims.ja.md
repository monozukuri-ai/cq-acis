# トレラント境界と有限 spline トリム

[English](tolerant-trims.md) | 日本語

0.3.3 では ASM 22700／内部 22601 の限定的なトレラント境界、有限 UV、forward の直線 pcurve ビューを追加しました。
以下の spline pcurve ビューと辺ごとの許容差による変換は **未公開の開発版**です。
これらを使う場合は core・bridge・Python を対応するソースで揃えてください。
共有モデル API 2 と既存の直線ビューは変わりません。[共有モデル API](model-api.ja.md)も参照してください。

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
- 開いた非有理・次数 1 または 3 の `exp_par_cur` は、面と同じ明示 spline 定義を参照する場合に保存 UV spline として使えます。
  曲線の向き `C(-t)` と支持曲面の法線方向は独立して保持します。法線の反転で UV 座標は反転しません。
  clamped knot を 3D 辺の区間にアフィン変換し、UV 制御点と曲線の軌跡を保ちます。
  内包する支持範囲は無限、chart shift はゼロに限定します。
  その他の pcurve は対応する範囲で照合付き投影を使います。

## Pcurve ビューと診断

`NativeModel.linear_surface_pcurve(pcurve_ref, surface_ref)` は
`LinearSurfacePcurve` ビューを返し、別のプロファイルでは `None` を返します。
対応プロファイル内の破損や支持曲面の不一致は `AcisModelError` です。
元の pcurve、区間、UV の 2 点、保存 fit tolerance、定義の出典を保持します。

`NativeModel.spline_surface_pcurve(pcurve_ref, surface_ref)` は、次数、保存方向の knot／制御点、
clamped 多重度、曲線／支持曲面の向き、有効パラメータ区間、fit tolerance、元レコードと支持定義を持つ
`SplineSurfacePcurve` を追加します。`None` とエラーの扱いは直線ビューと同じです。
有理／周期 UV spline や未知の chart 変換は未対応です。

## 辺ごとの許容差

投影トリムと通常の辺は、元の 3D 曲線とモデル本来の許容差以内で一致する必要があります。
同一の支持定義を持つ保存 UV spline と、対応済みの null-inline `tcoedge-coedge`／`tedge-edge` の組合せでは、
`tedge.saved_scalar × 配置を含む mm 換算倍率 + 元のモデルの許容差 mm` を辺ごとの上限に使えます。
これは ASM 22700／内部 22601 のフィールドの **観測に基づく解釈**であり、ベンダー検証済みのレイアウトや汎用修復規則ではありません。

同じパラメータで独立に測定した最大偏差が有限かつ上限以内であることを確認します。
局所許容差を使える配置は相似変換に限定します。`source_edge_tolerances` に元の数値、換算倍率、
モデル許容差、適用上限、実測偏差を記録します。OCCT の辺と接続頂点の許容差をこの上限に設定しますが、
座標と 3D／UV 制御点は変更しません。`converter.tolerance`、元頂点との一致検査、有限 UV 範囲も維持します。
保存 pcurve の fit tolerance や意味未確定の頂点フィールドを追加の許容差には使いません。
不足した上限、inline coedge curve、未知の chart はエラーです。

`pcurve_checks` は通過した全ての曲面上の曲線検査と適用上限を記録します。
`pcurve_max_deviation` はその最大値で、記録された辺ごとの上限が使われた場合はモデル許容差を超えます。
`saved_pcurves`、`tolerant_boundaries`、`bounded_surface_faces` は引き続き要素単位の検査結果です。
個別面が有効でも完成ソリッドを保証しません。未対応の境界、不正な面、開いたシェルは変換エラーです。
Inventor の現在の Model State との一致を保証する機能ではありません。

偏差の計測には [OCCT の curve-on-surface checker](https://dev.opencascade.org/doc/refman/html/class_geom_lib___check_curve_on_surface.html) を使います。
Spatial の [tolerant modeling の説明](https://blog.spatial.com/3d-software-development-kits/subtleties-b-rep-translation-part-3-why-healing-matters) は
トポロジー上の接続と幾何上の軌跡に差が生じる背景を説明していますが、ここで解釈した ASM のフィールド定義を示すものではありません。

[形状の制限](geometry-support.md)、[バイナリ履歴の制限](sab-support.md)、
[エラーの扱い](usage.md#errors-and-diagnostics)も参照してください。
