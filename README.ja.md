# cq-acis

開発中の[トレラント境界・有限 UV トリム対応](docs/tolerant-trims.ja.md)には、追加範囲と残る変換制限を記載しています。

ACIS SAT/SABデータを解析し、対応する解析的B-repのサブセットを
CadQuery/OpenCascade shapeへ変換するパッケージです。

English: [README.md](README.md)

> 実験的なプロジェクトです。ACISの保存形式や出力元によってレコードが
> 異なるため、未対応エンティティはRawEntityとして保持し、正確なshapeを
> 作れない場合はエラーにします。2D トリムの近似は元の精度内で別途検証します。

## 機能

- SATコンテナ判定とASCIIレコード分割
- 旧形式1行ヘッダー／新形式3行ヘッダーの解析
- SAT 7以降の`@<length>` counted string対応
- SAB／Autodesk ShapeManager SABの限定プロファイル解析
- `$n`ポインタを検証するエンティティグラフ
- SAT保存形式105、400、600、700の型付きデコード
- body、lump、shell、face、loop、coedge、edge、vertex、point、
  straight-curve、ellipse-curve、plane-surface、cone-surface、sphere-surface、torus-surface、transformの解析
- 直線、円／楕円エッジ、平面、円筒・楕円円筒、円錐、球・トーラスの限定変換
- 非多様体ACISシェルのSolid／Compoundへの分解
- 未対応レコードのRawEntity保持
- Rustの共通モデル・参照検証・解析的形状計算とPyO3バインディング

M4 では SAT 700 の直接 `exactsur` NURBS 曲面も実験的に追加しています。
ASM 22700 / 内部 22601 の直接 NURBS、証明できる円錐の縮退辺、球面の円形穴、
二つの同軸楕円断面で囲まれた楕円円錐にも限定対応しています。
非相似の配置、他の未解釈 subtype は拒否します。
対応範囲・検証限界は [M4 の仕様](docs/m4-geometry.md)を参照してください。
0.3.0 開発版は model API 2 と core / bridge 0.2.0 を要求します。
新しい crate / Python パッケージの公開は別作業です。

## インストール

```bash
python -m pip install cq-acis
```

ソースから開発インストールする場合はRust 1.83以降とCリンカが必要です：

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

## 外部デコーダと共有するモデル

`cq_acis.model` に `AcisModel`、`AcisMetadata`、各種形状・エンティティ型を
用意しています。外部デコーダは `AcisModel(metadata=..., entities=...)` を直接
構築でき、`SatHeader`、`SatEntityGraph`、テキストの `SatRecord` は不要です。
`to_cadquery()` と新しい `convert_model()` は、共通モデルと従来の `SatModel`
の両方を受け取ります。

既存のSATモデルから共有する場合：

```python
from pathlib import Path
from cq_acis import convert_model, parse_sat_model

sat_model = parse_sat_model(Path("model.sat").read_bytes())
model = sat_model.as_acis_model()
shapes = convert_model(model)

assert model.metadata == sat_model.metadata
assert model.entities is sat_model.entities
# sat_model.graph と raw.record による既存のアクセスも維持されます。
```

外部デコーダから利用する場合の契約：

- `EntityRef` はモデル内の0始まりの連続インデックスです。`-1` はnull参照です。
  元データのIDは `RawEntity.entity_id` に保持します。構築時にインデックスと
  参照先の存在を検証しますが、形状の正しさや元形式の互換性は保証しません。
- 単位・許容誤差は `AcisMetadata` に設定します。`units_mm` は元の長さ1単位の
  ミリメートル数、`resabs` は元の長さ単位、`resnor` は無次元です。
  元データにない値は `None` のまま保持します。変換時は既存動作との互換性のため、
  単位未指定を1 mm、絶対許容誤差未指定を元の長さ単位で1e-6として扱います。
  外部デコーダは確認できた値を明示的に渡してください。
- 格納形式、保存形式バージョン、producer、dialectはメタデータに保持します。
  製品の年式とカーネルの保存形式バージョンは別の値です。
- `RawEntity.record` は省略できます。バイナリの `raw_data` と
  `SourceSpan(source_id, start_offset, end_offset)` で出典を保持できます。
  範囲は終端を含まないバイト範囲です。圧縮展開後のoffsetには展開後の領域名を付けます。
- 未対応エンティティは `RawEntity`、外部デコーダの報告は
  `AcisModel.diagnostics` の `AcisDiagnostic` として保持します。
  bodyから参照される未対応形状と、未デコードのraw bodyは変換時にエラーになります。
  その他の保持レコードや診断は完全変換の証拠にはならず、呼び出し側で確認が必要です。

既存のエンティティのimport先と `SatModel(graph, entities)` コンストラクタは維持します。
SATのフレーミングとスキーマデコードは現時点ではPythonです。
SAB／ASMバイナリ解析はRustで実装しています。InventorのCFB/RSe抽出は
別プロジェクト `inventor-kit` が担当します。[対応範囲](docs/sab-support.md)を参照してください。

## RustコアとPythonバインディング

[`crates/acis-core`](crates/acis-core) に、全14種類の型付きエンティティ、raw値、
メタデータ、診断、参照検証・解決、ベクトル演算、楕円・円錐の評価、変換行列の計算を
実装しています。PythonやCadQueryへの依存はなく、InventorデコーダからCargo依存として
利用できます。ローカル依存の設定例は [crateのREADME](crates/acis-core/README.md) にあります。

[`crates/cq-acis-py`](crates/cq-acis-py) が [PyO3](https://pyo3.rs/) による境界です。
既存のPython dataclassのコンストラクタ、import先、等値比較、`dataclasses.replace`、
既存モデル内のエンティティ同一性を維持し、数値計算と `AcisModel` の検証・参照解決を
Rustへ接続しています。ソースから実行する場合は、先にネイティブ拡張をビルドしてください。

Rustが所有するモデルとして使う場合：

```python
native = model.to_native()  # SATへの変換や再パースをせず、値をコピーします。
assert native.to_model() == model
shapes = convert_model(native)
```

`NativeModel` はCadQuery変換が利用するモデルインターフェースを実装します。
プロパティや `to_model()` は値が等しいPython dataclassを生成し、元のPythonオブジェクトの
同一性は引き継ぎません。CadQuery側では変換器の作成時に一度だけPythonモデルを生成し、
参照をたどるたびにフィールドをコピーすることを避けます。
バイト列と任意精度の整数IDもJSONを介さず保持します。
モデル参照は符号付き64 bit整数（`-1` はnull）、offsetと長さは実行環境のアドレス範囲です。
出典範囲と診断の参照先も検証し、未知のクラスや値を黙って省略せずエラーにします。
未対応の意味情報は `RawEntity` とbytesで明示的に保持してください。

配布は [maturin](https://www.maturin.rs/project_layout.html) に変更しました。
wheelのインストールにはRustは不要です。ソースビルドにはRust 1.83以降とCリンカが必要です。
拡張はCPython 3.10のstable ABIを使いますが、依存先のCadQuery 2.8以降に合わせ、
パッケージの利用には **Python 3.11以降** が必要です。CadQuery側の対応OSも確認してください。
abi3タグは全Pythonバージョン・OSでの動作確認を意味しません。

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

仮想環境を有効にして、ネイティブ拡張をビルドしてから実行します。

```bash
python -m pip install maturin
maturin develop
cargo test -p acis-core --locked
PYTHONPATH=src python -m unittest discover -s tests -v
```

現在の固定コーパスは25 artifact（SAT 23、SAB 2）を含み、CadQuery回帰テストでは
23 SAT、147 bodyを変換します。
Rustモデルとの往復比較は62,530エンティティを対象とし、SATを介さない形状構築、
出典・バイト列・整数の保持、不正参照の拒否、Python APIの互換性も検証します。

## ライセンス

プロジェクト本体は[MIT License](LICENSE)で公開します。コーパスの第三者ファイルには
`corpus/licenses/`の個別通知が適用されます。

## SAB / ASM（第3段階）

`parse_sab_model(data, source_id="model.sab")` は、対応するバイナリプロファイルを
Rustで直接解析します。[対応範囲と履歴の制限](docs/sab-support.md)を参照してください。

## Python リリース CI

`v<Cargo.toml の workspace.package.version>` の GitHub Release を公開すると、Linux・Windows・
macOS ARM64/Intel の ABI3 wheel と sdist をビルド・検証し、Trusted Publishing で
PyPI に公開します。手動実行はビルドと検証のみです。
0.3.2以降はPythonパッケージとRustの各crateで同じバージョンを使います。
PythonのバージョンはCargoの設定から自動取得し、個別の番号は設定しません。
初回の PyPI 設定と公開手順は [リリース手順](docs/releasing.md) を参照してください。
