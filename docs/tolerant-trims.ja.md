# トレラント境界と有限 spline トリム

[English](tolerant-trims.md) | 日本語

0.3.3 では ASM 22700／内部 22601 の限定的なトレラント境界、有限 UV、forward の直線 pcurve ビューを追加しました。
spline pcurve ビューと辺ごとの許容差による変換は **0.3.4 で公開済み**です。
以下の inline／支持曲線の追加対応は **未公開の開発版**です。
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
不足した上限と未知の chart はエラーです。


## 未公開の inline／支持曲線対応

`TolerantCoedge.inline_curve` は、平面・球・トーラス上の観測済み full `par_int_cur` を返します。
元の raw coedge、値の位置、3次の保存3D fit、支持座標系、非有理3次または有理2次の UV、
knot、重み、末尾情報を保持します。未知の版・支持面・向き・閉曲線フラグ、区間の不一致、余剰値は拒否します。
平面の UV 倍率と球・トーラスの角度順序を明示的に扱います。

inline の保存3D fit と保存 UV／支持面の偏差を、その fit tolerance と元のモデル許容差以内で検証します。
別途、**変更していない共有3D辺**と支持 UV の偏差を TEDGE の上限以内で検証します。
inline の fit tolerance で共有辺の上限は広げません。
平面上の単一の有理2次小円弧では、Bernstein 係数による曲線全体の円錐曲線残差、角度の単調性、
半平面への包含、両端の一致を確認できた場合に限り、解析 pcurve で辺のパラメータに合わせます。
元の UV 制御点は保持し、検証上限と変更方法を `inline_reparameterizations` に記録します。

検証済み inline 辺または相互に参照する使用側が根拠を持つ場合、元のトレラント端点にもその局所上限を適用します。
OCCT 頂点には元の保存点の座標を使います。UV の接続には、同じ元トレラント頂点 ID と、
支持面上の点から保存点までの偏差の確認も必要です。近い別 ID の頂点をこの規則でまとめません。
通常の直線は、トレラント保存点が元の直線上にモデル精度で一致し、辺と曲線の元区間の両方に入る場合に限り、
その保存点まで区間を狭めます。TEDGE／TCOEDGE の区間には適用しません。
平面の穴の向きは OCCT `FixOrientation` だけで調整し、全ての辺の実体が維持されることを確認します。

`NativeModel.supported_curve(reference)` は、file-local な明示 spline subtype と平面を支持とする、
観測済み full `int_int_cur` の `SupportedCurve` ビューを追加します。
元の3D曲線・UV・支持定義の出典を保持します。保存3D fit を第1支持面に投影し、曲線全体の偏差を保存 fit の上限で検証します。
第2支持平面は正の重みを持つ制御点の凸包で全区間を検証します。
保存 UV はパラメータの手掛かりとして保持し、元の同一パラメータ偏差も診断に記録します。
保存 UV と投影 UV は共に支持定義域内に限定し、面への取付けも同じ支持面と有限範囲に限定します。
両支持面への距離の検証であり、厳密な交線や Inventor との同値を保証しません。
spline 端点と保存頂点の照合には元のモデル精度を維持し、意味未確定の TVERTEX 数値は許容差に使いません。

`supported_curve_checks`、`inline_pcurves`、`associated_pcurves`、`tolerant_line_trims`、
`tolerant_pcurve_joins`、`plane_wire_orientations`、`spline_endpoint_failures` に各検証と変更を分けて記録します。
固定 FTC07 2021 回帰では inline 10件とトレラント coedge の辺変換206件が通過します。
有効な個別面は245面から254/258面に増え、有限 UV 面は5/8面です。
2面の保存 pcurve は TEDGE の上限を超えます。別の2面は同じ spline 端点を共有し、
保存頂点との差が 0.00652608345231 mm と元の精度 0.00001 mm を超えるため拒否します。
FTC07 全体の変換は引き続き未対応です。

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
