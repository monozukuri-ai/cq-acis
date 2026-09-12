# 共有モデル API

[English](model-api.md) | 日本語

## モデルの構築

`cq_acis.model` に `AcisModel`、`AcisMetadata`、各種形状・エンティティ型を
用意しています。外部デコーダは `AcisModel(metadata=..., entities=...)` を直接
構築でき、`SatHeader`、`SatEntityGraph`、テキストの `SatRecord` は不要です。
`to_cadquery()` と `convert_model()` は、共通モデルと従来の `SatModel`
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

## ネイティブモデルと互換性

既存の公開エンティティの import 先と `SatModel(graph, entities)` は引き続き利用できます。
Python エンティティは dataclass のコンストラクタ、等値比較、`dataclasses.replace` に対応します。

```python
native = model.to_native()  # モデルの値を保持する不変のスナップショットです。
assert native.to_model() == model
shapes = convert_model(native)
```

`NativeModel` は `AcisModel` と同じ変換操作に対応します。プロパティと `to_model()` は
Python の値を返しますが、元の Python オブジェクトの同一性は引き継ぎません。
元のバイト列と任意精度の整数を保持します。モデル参照は符号付き 64 bit 整数
（`-1` は null）、offset と長さは実行環境のアドレス範囲に収まる必要があります。
不正な出典範囲や診断の参照先は拒否します。未対応のクラスや値は `RawEntity` と bytes
で表してください。

共有 dataclass の契約は `cq_acis.model.MODEL_API_VERSION == 2` で識別します。
これはパッケージのリリース番号とは別の値です。Rust 拡張では `acis-core`、
`acis-py-bridge`、Python の `cq-acis` のバージョンを揃えてください。
[bridge API](../crates/acis-py-bridge/README.md) を参照してください。

`NativeModel.tolerant_topology(reference)`、`subtype_table`、
`resolve_subtype(reference)`、`linear_surface_pcurve(pcurve_ref, surface_ref)` で
対応する raw 形状の追加ビューを取得できます。元のエンティティは raw のまま残ります。
ビューや subtype の索引だけで完全な形状対応を保証するものではありません。
[形状の対応範囲](geometry-support.md)と[トレラントトリム](tolerant-trims.ja.md)を参照してください。
