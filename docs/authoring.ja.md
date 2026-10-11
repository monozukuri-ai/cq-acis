# 実験段階のanalytic authoring

開発checkoutに`from_cadquery`を追加しました。単一の閉じたCadQuery solidから
共有ACISモデルとASM 23200 SAB候補を生成します。Inventor API・nativeファイル・
templateは生成の入力にしません。未リリース・native未適格で、IPT出力は含みません。

```python
import cadquery as cq
from cq_acis import from_cadquery, parse_sab_model, to_cadquery

solid = cq.Workplane("XY").circle(7).extrude(19).val()
authored = from_cadquery(solid)
assert not authored.native_qualified
rebuilt = to_cadquery(parse_sab_model(authored.to_sab())).val()
assert rebuilt.isValid()
```

対応候補は平面・円筒と、直線・円・楕円による境界です。共有edge/vertex、穴の内側loop、
full circle、seam両枝、面の向き、edge parameterを保持します。OCCTの配置はadaptorで
1回だけ適用し、メッシュ化やSTEP exportは行いません。WorkplaneはSolidを1個だけ
含む必要があります。Compoundからのsolid選択は呼出側で明示します。

入力はmm、SAB座標は1単位10 mmです。直線parameterはmm、楕円parameterはradianを
保持します。入力toleranceは1e-5 mm以下、各topology表4096件、coedge8192件、
座標は±1,000,000 mmに制限します。一般3D spline、他の曲面、退化edge、複数shell、
未接続loop、partner不足、不正frameを拒否します。Rustの検査は所有参照と境界の整合を
確認しますが、一般的な自己交差検査kernelの代替にはなりません。

Rustの`FaceSpec` loopは面の向きを適用する前の支持曲面に従います。生成ACISでは
面の向きに合わせ、裏向き面の巡回順と各edge-useの向きを両方反転します。
共有edgeのpartnerは逆方向に巡回します。OCCT再構築はwireの向きを修復する場合が
あるため、再構築成功だけではこの規則の正しさを確認できません。

`authored.pcurves`は元のUV直線・楕円・B-spline定義をseamの両枝も含めて保持し、
`authored.charts`は元のframe・UV範囲・円筒chartの向き補正を保持します。
現候補ではこれらのpcurveをSABへ明示出力せず、native kernelによる導出を検証します。
この経路は未適格です。ローカルの往復成功をInventorでの受入と解釈しないでください。

`to_sab(history=True)`はstate-one挿入履歴候補を付けますが、Inventor文書graphの
初期化は含みません。既存RustのBoxSpec/default encoderは別の限定profileとして維持します。

## 意味付きの形状仕様

0.3.10リリース候補の `authored.to_spec()` は共有頂点・辺・支持面・face loopを
mm単位の独立したJSON互換値として返します。文書writerへの入力用で、IPTやSABのbyte列は含みません。
返された値を変更しても元の形状には反映しません。共有model APIのversionは2を維持します。
