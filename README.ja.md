# cq-acis

ACIS SAT/SABデータを解析し、対応する解析的B-repのサブセットを
CadQuery/OpenCascade shapeへ変換するパッケージです。

English: [README.md](README.md)

> 実験的なプロジェクトです。ACISの保存形式や出力元によってレコードが
> 異なるため、未対応エンティティはRawEntityとして保持し、正確なshapeを
> 作れない場合は近似せずエラーにします。

## 機能

- SATコンテナ判定とASCIIレコード分割
- 旧形式1行ヘッダー／新形式3行ヘッダーの解析
- SAT 7以降の`@<length>` counted string対応
- SAB／Autodesk ShapeManager SABのプリアンブル判定
- `$n`ポインタを検証するエンティティグラフ
- SAT保存形式105、400、600、700の型付きデコード
- body、lump、shell、face、loop、coedge、edge、vertex、point、
  straight-curve、ellipse-curve、plane-surface、cone-surface、transformの解析
- 直線、円／楕円エッジ、平面、円筒、円錐の正確なCadQuery変換
- 非多様体ACISシェルのSolid／Compoundへの分解
- 未対応レコードのRawEntity保持

楕円断面の円錐、楕円筒、せん断配置、未対応の曲線・曲面は近似せず拒否します。

## インストール

```bash
python -m pip install cq-acis
```

ソースから開発インストールする場合：

```bash
python -m pip install -e .
```

## 簡単な使用例

```python
from cq_acis import BodyEntity, parse_sat_model

with open("model.sat", "rb") as source:
    model = parse_sat_model(source.read())

for body in model.bodies():
    assert isinstance(body, BodyEntity)
    print(body.index, model.resolve(body.lump))
```

CadQueryへ変換する場合：

```python
from cq_acis import import_sat_file

result = import_sat_file("model.sat")
shape = result.val()
assert shape.isValid()
print(shape.Volume())
```

## パース例と3D確認

[`examples/parse_sat.py`](examples/parse_sat.py) はSATを読み込み、body統計を表示し、
STEP、STL、SVGを書き出します。

```bash
PYTHONPATH=src python examples/parse_sat.py
PYTHONPATH=src python examples/parse_sat.py path/to/model.sat \
  --output-dir /tmp/cq-acis-output
```

生成したSTLまたはSTEPを3D CADビューアで開いてください。`ocp_vscode`を導入している
場合は`--show`も利用できます。

## 開発用コーパス

コーパスはPython wheelには含めず、パーサと変換の回帰テスト用にリポジトリで管理します。
取得元と固定コミットは[`corpus/sources.lock.json`](corpus/sources.lock.json)、
SHA-256とSATメタデータは[`corpus/manifest.jsonl`](corpus/manifest.jsonl)に記録します。

```bash
python scripts/fetch_corpus.py
python scripts/fetch_corpus.py --check
```

第三者データの再配布条件は[`corpus/README.md`](corpus/README.md)と
`corpus/licenses/`を確認してください。

## テスト

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

現在の固定コーパスは25 artifact（SAT 23、SAB 2）を含み、CadQuery回帰テストでは
23 SAT、147 bodyを変換します。

## ライセンス

プロジェクト本体は[MIT License](LICENSE)で公開します。コーパスの第三者ファイルには
`corpus/licenses/`の個別通知が適用されます。
