use super::*;

fn word(out: &mut Vec<u8>, value: i64, width: usize) {
    out.extend_from_slice(&value.to_le_bytes()[..width]);
}
fn name(out: &mut Vec<u8>, value: &str) {
    out.extend_from_slice(&[13, value.len() as u8]);
    out.extend_from_slice(value.as_bytes());
}
fn fixture(width: usize, flags: i64, extra: Option<(&str, Vec<u8>)>) -> Vec<u8> {
    let mut out = if width == 4 {
        b"ASM BinaryFile4".to_vec()
    } else {
        b"ASM BinaryFile8".to_vec()
    };
    for n in [23200, 0, 0, flags] {
        word(&mut out, n, width);
    }
    for text in ["test", "ASM", "date"] {
        out.extend_from_slice(&[7, text.len() as u8]);
        out.extend_from_slice(text.as_bytes());
    }
    for n in [1.0_f64, 1e-6, 1e-10] {
        out.push(6);
        out.extend_from_slice(&n.to_le_bytes());
    }
    name(&mut out, "asmheader");
    out.push(12);
    word(&mut out, -1, width);
    out.push(4);
    word(&mut out, -1, width);
    out.push(17);
    if let Some((kind, fields)) = extra {
        name(&mut out, kind);
        out.push(12);
        word(&mut out, -1, width);
        out.push(4);
        word(&mut out, -1, width);
        out.extend(fields);
        out.push(17);
    }
    name(&mut out, "End-of-ASM-data");
    out
}
fn parse(data: &[u8]) -> Result<SabDocument> {
    parse_sab(data, "test-domain", &SabLimits::default())
}

#[test]
fn four_and_eight_byte_words_preserve_source_and_signed_values() {
    for width in [4, 8] {
        let value = if width == 8 {
            i64::MIN + 7
        } else {
            i32::MIN as i64 + 7
        };
        let mut fields = vec![4];
        word(&mut fields, value, width);
        fields.push(12);
        word(&mut fields, 0, width);
        let data = fixture(width, 0, Some(("future-attribute", fields)));
        let doc = parse(&data).unwrap();
        assert_eq!(doc.header.integer_width, width as u8);
        let raw = doc.model.entities()[1].raw();
        let span = raw.source.as_ref().unwrap();
        assert_eq!(
            raw.raw_data.as_deref(),
            Some(&data[span.start_offset..span.end_offset])
        );
        assert_eq!(
            raw.values,
            vec![
                AcisValue::Integer(value.into()),
                AcisValue::Reference(EntityRef(0))
            ]
        );
        assert!(raw.record.is_none());
    }
}
#[test]
fn every_truncation_without_history_is_rejected() {
    let data = fixture(4, 0, None);
    for end in 0..data.len() {
        assert!(parse(&data[..end]).is_err(), "accepted prefix {end}");
    }
    let mut trailing = data.clone();
    trailing.push(0);
    assert!(parse(&trailing).is_err());
    let mut unknown = data;
    unknown[15..19].copy_from_slice(&23201i32.to_le_bytes());
    assert!(parse(&unknown).unwrap_err().message.contains("unsupported"));
}
#[test]
fn unknown_tags_bad_lengths_and_unbalanced_scopes_fail() {
    for fields in [
        vec![255],
        vec![16],
        vec![15],
        vec![9, 255, 255, 255, 255],
        vec![7, 2, 255, 255],
    ] {
        assert!(parse(&fixture(4, 0, Some(("future", fields)))).is_err());
    }
}
#[test]
fn references_cannot_resolve_into_opaque_history() {
    let mut ref_one = vec![12];
    word(&mut ref_one, 2, 4);
    let mut data = fixture(4, 1, Some(("future", ref_one)));
    let end = data.len() - 17;
    data.truncate(end);
    name(&mut data, "delta_state");
    data.extend_from_slice(b"opaque history");
    assert!(parse(&data).is_err());
    let mut data = fixture(4, 1, None);
    data.truncate(data.len() - 17);
    name(&mut data, "delta_state");
    data.extend_from_slice(b"opaque history");
    let doc = parse(&data).unwrap();
    assert!(doc.history.is_some());
    assert_eq!(doc.model.entities().len(), 2);
    data[27..31].copy_from_slice(&0u32.to_le_bytes());
    assert!(parse(&data).is_err());
}
#[test]
fn byte_record_token_string_and_depth_limits_are_enforced() {
    let data = fixture(4, 0, None);
    for limits in [
        SabLimits {
            max_bytes: data.len() - 1,
            ..Default::default()
        },
        SabLimits {
            max_records: 0,
            ..Default::default()
        },
        SabLimits {
            max_tokens: 1,
            ..Default::default()
        },
        SabLimits {
            max_string_bytes: 1,
            ..Default::default()
        },
    ] {
        assert!(parse_sab(&data, "test", &limits).is_err());
    }
    let deep = fixture(4, 0, Some(("future", vec![15, 15, 16, 16])));
    assert!(parse_sab(
        &deep,
        "test",
        &SabLimits {
            max_depth: 1,
            ..Default::default()
        }
    )
    .is_err());
    assert!(parse_sab(
        &data,
        "test",
        &SabLimits {
            max_records: 1,
            ..Default::default()
        }
    )
    .is_ok());
}
#[test]
fn schema_extensions_remain_raw_instead_of_being_silently_ignored() {
    let mut fields = vec![12];
    word(&mut fields, -1, 4);
    fields.push(19);
    for n in [1.0_f64, 2.0, 3.0] {
        fields.extend_from_slice(&n.to_le_bytes());
    }
    let doc = parse(&fixture(4, 0, Some(("point", fields.clone())))).unwrap();
    assert!(matches!(doc.model.entities()[1], Entity::Point(_)));
    fields.push(11);
    let doc = parse(&fixture(4, 0, Some(("point", fields)))).unwrap();
    assert!(matches!(doc.model.entities()[1], Entity::Raw(_)));
    assert!(doc
        .model
        .diagnostics()
        .iter()
        .any(|d| d.code == "sab.entity_schema_unsupported"));
}
