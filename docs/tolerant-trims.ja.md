# トレラント境界と有限 spline トリム

[English](tolerant-trims.md) | 日本語

0.3.3 で、観測済み ASM 22700／内部 22601 の対応を追加しました。
これらの追加機能は 0.3.2 には含まれません。0.3.3 の core・bridge・Python 拡張・変換器を
組み合わせて使用してください。

## 対応範囲

- `tedge-edge` と inline curve が null の `tcoedge-coedge` を変換経路に接続します。
  直線・楕円または明示 spline が、保存頂点にモデル本来の `resabs` 以内で一致する場合に限ります。
  辺・coedge の向き、保存パラメータ区間、ループの前後リンクを検査し、元エンティティは raw のまま残します。
- forward の明示 spline 曲面と確認済み subtype 参照の有限 U/V 範囲を保持します。
  範囲は clamped knot 定義域内の空でない部分領域に限定します。
  反転、周期 spline、未知 trailer は未対応です。NURBS 評価は元の支持曲面を評価します。
- 面の変換では有限の支持領域を保持し、解析曲線の境界箱または spline 制御点の保守的な境界箱で
  トリム全体を検査します。領域外のトリムは面を拒否し、切り落として補いません。
  保存区間・UV の丸め差は最大 `1e-10` パラメータ単位（大きな UV 座標では 64 ULP）までで、
  3D の幾何許容差とは別に扱います。
- 同じ spline 定義への参照を確認できる、forward・2 knot・次数1の `exp_par_cur` を
  保存 UV 直線として使用できます。不変のファイル内 subtype 表で支持曲面を対応付けます。
  内包する支持範囲は無限、chart shift はゼロに限定します。
  その他の pcurve プロファイルでは、従来の照合付き投影経路を使用します。

`NativeModel.linear_surface_pcurve(pcurve_ref, surface_ref)` は追加ビュー
`LinearSurfacePcurve` を返します。別プロファイルは `None`、対応プロファイル内の破損や
支持曲面の不一致は `AcisModelError` です。元の pcurve、区間、UV の2点、保存 fit tolerance、
定義の出典を保持します。model API 2 と既存エンティティの構造は変更しません。

使用する2D曲線は支持曲面上で評価し、OCCT の同一パラメータ照合によって元の3D辺と比較します。
トレラント数値や保存 fit tolerance でモデルの許容差を広げません。
inline curve や局所的な修復規則の意味は推測しません。
`tolerant_boundaries`、`saved_pcurves`、`bounded_surface_faces` に通過した検査を記録しますが、
これらは完成ソリッドを証明するものではありません。

## 検証と残る制限

円・有理1/4円の解析式、多角形の面積・法線、既知の立方体の有限 NURBS 表現を使います。
端点不一致、余分な周回、不正な範囲、端点の間で UV 領域を出るトリム、支持参照の不一致、
入力切断、chart shift を拒否することも確認します。

固定した Inventor FTC07 2021 では、トレラント coedge 195件から有効な辺を構築し、
inline curve 10件は未対応、1件は元の端点許容差を超えるため拒否します。
有限曲面8件と直線 pcurve ビュー153件を出典付きで取得します。
個別に変換できる有効面は258面中112面から192面に増えました。
曲面上の曲線との偏差が残るため、この部品全体は変換を拒否します。
有限の native 面8件も、面全体の変換にはまだ成功していません。
これはローカルでの部品要素の検証で、Inventor や現在の Model State との照合ではありません。

公開コーパスの完成ソリッドは33入力中10件を維持します。この33入力には非 IPT 文書5件を含みます。
holdout を実装調整に使用しません。再現用ツールは inventor-kit の
`scripts/validate_tolerant_trims.py` です。
OCCT の参照資料は[英語版](tolerant-trims.md)にあります。
