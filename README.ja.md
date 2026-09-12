# cq-acis

ACIS SAT/SAB データを解析し、対応する B-rep 形状を
CadQuery/OpenCascade の shape に変換するパッケージです。

English: [README.md](README.md)

> 実験的なプロジェクトです。対応する形状は保存形式のバージョンと出力元に依存します。
> 未対応エンティティは raw レコードとして保持し、元データの精度内で形状を構築できない
> 場合は変換エラーにします。投影した 2D トリムは、変更していない元の 3D 曲線と照合します。

## 機能

- 旧形式・新形式の SAT ヘッダー、counted string、エンティティ参照の解析
- SAT 保存形式 105、400、600、700 と、一部の SAB／Autodesk ShapeManager バイナリへの対応
- 直線、円、楕円、平面、円筒、円錐、球、トーラスの限定変換と、
  明示 NURBS・一部のトレラント境界への実験的対応
- トポロジー、メタデータ、診断、未対応レコードの元データの取得
- 外部デコーダを CadQuery 変換に接続する共有モデル API

対応条件は[形状の対応範囲と制限](docs/geometry-support.md)と
[SAB／ASM の対応範囲](docs/sab-support.md)を参照してください。

## インストール

**Python 3.11 以降**が必要です。依存パッケージとして CadQuery 2.8 以降もインストールします。

```bash
python -m pip install cq-acis
```

ビルド済み wheel のインストールに Rust は不要です。ソースからインストールする場合は、
Rust 1.83 以降と C リンカを用意し、リポジトリのルートで実行します。

```bash
python -m pip install -e .
```

CadQuery の対応プラットフォームの条件も適用されます。

## 簡単な使用例

SAT を解析し、トポロジーの参照をたどります。

```python
from pathlib import Path
from cq_acis import parse_sat_model

model = parse_sat_model(Path("model.sat").read_bytes())
for body in model.bodies():
    lump = model.resolve(body.lump)
    print(body.index, lump.index if lump else None)
```

SAT ファイルを CadQuery の `Workplane` として読み込みます。

```python
from cq_acis import import_sat_file

result = import_sat_file("model.sat")
shape = result.val()
assert shape.isValid()
print(shape.Volume())
```

SAB／ASM バイナリを読み込む場合：

```python
from pathlib import Path
from cq_acis import parse_sab_model, to_cadquery

model = parse_sab_model(Path("model.sab").read_bytes(), source_id="model.sab")
print(model.diagnostics)
result = to_cadquery(model)
```

解析に成功しても、すべての形状を変換できるとは限りません。
[使用方法とエラーの扱い](docs/usage.md)を参照してください。

## ドキュメント

- [ドキュメント一覧](docs/README.md)
- [使用方法・エクスポート・3D 確認](docs/usage.md)
- [共有モデル API](docs/model-api.ja.md)
- [形状の対応範囲と制限](docs/geometry-support.md)
- [SAB／ASM の対応範囲と履歴の制限](docs/sab-support.md)
- [トレラント境界と有限 UV トリム](docs/tolerant-trims.ja.md)
- Rust API: [acis-core](crates/acis-core/README.md)、
  [acis-py-bridge](crates/acis-py-bridge/README.md)

公開 API と対応形式の範囲は、開発に伴い変更される可能性があります。

## ライセンス

プロジェクト本体は [MIT License](LICENSE) で公開します。
依存コードの帰属情報は[第三者通知](THIRD_PARTY_NOTICES.md)を参照してください。
リポジトリの[テスト用コーパス](corpus/README.md)は Python 配布物に含めず、
[個別のライセンス通知](corpus/licenses/)を適用します。
