use acis_core::*;

fn raw(index: usize) -> RawEntity {
    RawEntity::new(index, "unknown")
}

#[test]
fn reference_closure_and_reverse_references_include_typed_fields() {
    let body = BodyEntity {
        raw: RawEntity::new(0, "body"),
        pattern: NULL_REF,
        lump: EntityRef(1),
        wire: NULL_REF,
        transform: NULL_REF,
    };
    let mut child = raw(1);
    child.values = vec![
        AcisValue::Reference(EntityRef(0)),
        AcisValue::Reference(EntityRef(0)),
    ];
    let model = AcisModel::new(
        AcisMetadata::default(),
        vec![Entity::Body(body), Entity::Raw(child)],
        vec![],
    )
    .unwrap();
    assert_eq!(model.bodies().count(), 1);
    assert_eq!(model.referenced_by(EntityRef(1)).unwrap(), vec![0]);
    assert_eq!(model.referenced_by(EntityRef(0)).unwrap(), vec![1]);
    assert!(model.resolve(NULL_REF).unwrap().is_none());
    assert_eq!(model.resolve(EntityRef(1)).unwrap().unwrap().index(), 1);
}

#[test]
fn invalid_models_fail_before_exposure() {
    assert!(matches!(
        AcisModel::new(AcisMetadata::default(), vec![Entity::Raw(raw(7))], vec![]),
        Err(ModelError::InvalidIdentity { .. })
    ));
    for reference in [EntityRef(-2), EntityRef(1), EntityRef(i64::MAX)] {
        let body = BodyEntity {
            raw: RawEntity::new(0, "body"),
            pattern: NULL_REF,
            lump: reference,
            wire: NULL_REF,
            transform: NULL_REF,
        };
        assert!(matches!(
            AcisModel::new(AcisMetadata::default(), vec![Entity::Body(body)], vec![]),
            Err(ModelError::InvalidReference { .. })
        ));
    }
    assert!(resolve_index(EntityRef(0), 0).is_err());
}

#[test]
fn source_facts_and_unknown_binary_data_are_owned_without_python() {
    let huge: BigInt = BigInt::from(1_u8) << 200_usize;
    let mut entity = raw(0);
    entity.entity_id = Some(huge.clone());
    entity.raw_data = Some(vec![0, 255, 1, 0]);
    entity.values = vec![
        AcisValue::Integer(huge),
        AcisValue::Bytes(vec![255, 0]),
        AcisValue::Float(-0.0),
    ];
    entity.source = Some(SourceSpan {
        source_id: "part.ipt/segment/inflated".into(),
        start_offset: 64,
        end_offset: 68,
    });
    let metadata = AcisMetadata {
        container: Some(AcisContainer::AsmSab),
        ..Default::default()
    };
    let model = AcisModel::new(metadata, vec![Entity::Raw(entity.clone())], vec![]).unwrap();
    assert_eq!(model.entities()[0].raw(), &entity);
    assert_eq!(model.metadata().units_mm, None);
    assert!(model.entities()[0].raw().record.is_none());
}

#[test]
fn source_domain_and_diagnostic_targets_are_checked() {
    let mut entity = raw(0);
    entity.source = Some(SourceSpan {
        source_id: String::new(),
        start_offset: 0,
        end_offset: 2,
    });
    assert!(matches!(
        AcisModel::new(AcisMetadata::default(), vec![Entity::Raw(entity)], vec![]),
        Err(ModelError::InvalidSourceSpan)
    ));
    let diagnostic = AcisDiagnostic {
        code: "unsupported".into(),
        message: "Unknown entity".into(),
        entity_index: Some(2),
        source: None,
    };
    assert!(matches!(
        AcisModel::new(
            AcisMetadata::default(),
            vec![Entity::Raw(raw(0))],
            vec![diagnostic]
        ),
        Err(ModelError::InvalidDiagnosticTarget { .. })
    ));
}
