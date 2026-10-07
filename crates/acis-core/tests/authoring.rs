use acis_core::{
    authoring::{validate_box, BoxSpec, BOX_ENTITY_COUNT},
    encode::{EncodeError, HistoryMode, SabEncoder, SabWriteLimits, SabWriteProfile},
    sab::{parse_sab, SabLimits},
    *,
};

fn spec() -> BoxSpec {
    BoxSpec::new((20.0, 30.0, 40.0).into(), (0.0, 0.0, 0.0).into())
}
fn close(a: f64, b: f64) {
    assert!((a - b).abs() <= 1e-8_f64.max(b.abs() * 1e-12), "{a} != {b}");
}

#[test]
fn source_free_box_reader_and_independent_volume_properties() {
    // Deterministic property sweep over five size decades and translated boxes.
    let mut seed = 0x6b6f785f6d32_u64;
    for n in 0..512 {
        let mut next = || {
            seed ^= seed << 13;
            seed ^= seed >> 7;
            seed ^= seed << 17;
            (seed % 10000) as f64 / 10000.0
        };
        let scale = 10.0_f64.powi((n % 5) - 1);
        let size = Vec3::from((
            (1.0 + next() * 9.0) * scale,
            (1.0 + next() * 9.0) * scale,
            (1.0 + next() * 9.0) * scale,
        ));
        let origin = Vec3::from((
            (next() - 0.5) * 1000.0,
            (next() - 0.5) * 1000.0,
            (next() - 0.5) * 1000.0,
        ));
        let box_model = BoxSpec::new(size, origin).build().unwrap();
        for e in box_model.model().entities() {
            assert!(
                e.raw().source.is_none() && e.raw().raw_data.is_none() && e.raw().record.is_none()
            );
        }
        let bytes = SabEncoder::default()
            .encode(&box_model, HistoryMode::None)
            .unwrap();
        assert_eq!(
            bytes,
            SabEncoder::default()
                .encode(&box_model, HistoryMode::None)
                .unwrap()
        );
        let decoded = parse_sab(&bytes, "generated", &SabLimits::default()).unwrap();
        assert_eq!(decoded.model.entities().len(), BOX_ENTITY_COUNT);
        assert!(decoded.history.is_none());
        let valid = validate_box(&decoded.model).unwrap();
        for (a, b) in [
            (valid.minimum_mm, origin),
            (valid.maximum_mm, origin + size),
        ] {
            close(a.x, b.x);
            close(a.y, b.y);
            close(a.z, b.z);
        }
        close(valid.volume_mm3, size.x * size.y * size.z);
        // Independent signed tetrahedron integral, using decoded loops and
        // vertices only; does not rely on validator bounds or plane normals.
        let entities = decoded.model.entities();
        let mut volume = 0.0;
        let location = |r: EntityRef| {
            let Entity::Vertex(v) = &entities[r.0 as usize] else {
                panic!()
            };
            let Entity::Point(p) = &entities[v.point.0 as usize] else {
                panic!()
            };
            p.location - origin * 0.1
        };
        for e in entities {
            if let Entity::Loop(l) = e {
                let mut walk = Vec::new();
                let mut current = l.coedge;
                for _ in 0..4 {
                    let Entity::Coedge(c) = &entities[current.0 as usize] else {
                        panic!()
                    };
                    let Entity::Edge(edge) = &entities[c.edge.0 as usize] else {
                        panic!()
                    };
                    walk.push(location(if c.reversed {
                        edge.end_vertex
                    } else {
                        edge.start_vertex
                    }));
                    current = c.next_coedge;
                }
                for j in 1..3 {
                    volume += walk[0].dot(walk[j].cross(walk[j + 1])) / 6.0;
                }
            }
        }
        close(volume * 1000.0, size.x * size.y * size.z);
    }
}

#[test]
fn rejects_input_outside_bounded_profile() {
    for size in [
        (0.0, 1.0, 1.0),
        (-1.0, 2.0, 3.0),
        (1e-8, 1.0, 1.0),
        (f64::NAN, 1.0, 1.0),
        (f64::INFINITY, 1.0, 1.0),
        (1e9, 1.0, 1.0),
    ] {
        assert!(BoxSpec::new(size.into(), (0.0, 0.0, 0.0).into())
            .build()
            .is_err());
    }
    for origin in [
        (f64::NAN, 0.0, 0.0),
        (f64::INFINITY, 0.0, 0.0),
        (1e6, 0.0, 0.0),
    ] {
        assert!(BoxSpec::new((1.0, 2.0, 3.0).into(), origin.into())
            .build()
            .is_err());
    }
    // Smallest allowed size, and a negative maximum placement, remain valid.
    BoxSpec::new(
        (0.00032, 0.00032, 0.00032).into(),
        (-100.0, -200.0, -300.0).into(),
    )
    .build()
    .unwrap();
}

#[test]
fn rejects_corrupt_ownership_orientation_geometry_and_ids() {
    let original = spec().build().unwrap();
    for mutation in 0..18 {
        let mut entities = original.model().entities().to_vec();
        match mutation {
            0 => {
                if let Entity::Coedge(c) = &mut entities[16] {
                    c.partner_coedge = EntityRef(16);
                }
            }
            1 => {
                if let Entity::Coedge(c) = &mut entities[16] {
                    c.reversed = !c.reversed;
                }
            }
            2 => {
                if let Entity::Coedge(c) = &mut entities[16] {
                    c.next_coedge = EntityRef(16);
                }
            }
            3 => {
                if let Entity::Coedge(c) = &mut entities[16] {
                    c.loop_ref = EntityRef(11);
                }
            }
            4 => {
                if let Entity::Face(f) = &mut entities[4] {
                    f.shell = NULL_REF;
                }
            }
            5 => {
                if let Entity::Face(f) = &mut entities[4] {
                    f.next_face = EntityRef(4);
                }
            }
            6 => {
                if let Entity::Face(f) = &mut entities[4] {
                    f.reversed = true;
                }
            }
            7 => {
                if let Entity::Face(f) = &mut entities[4] {
                    f.raw.entity_id = Some(0.into());
                }
            }
            8 => {
                if let Entity::PlaneSurface(p) = &mut entities[68] {
                    p.normal = -p.normal;
                }
            }
            9 => {
                if let Entity::PlaneSurface(p) = &mut entities[68] {
                    p.u_range = None;
                }
            }
            10 => {
                if let Entity::StraightCurve(c) = &mut entities[74] {
                    c.direction.x = f64::NAN;
                }
            }
            11 => {
                if let Entity::Edge(e) = &mut entities[40] {
                    e.end_parameter = Some(1.0);
                }
            }
            12 => {
                if let Entity::Point(p) = &mut entities[60] {
                    p.location.x += 0.1;
                }
            }
            13 => {
                if let Entity::Vertex(v) = &mut entities[52] {
                    v.point = EntityRef(61);
                }
            }
            14 => {
                if let Entity::Body(b) = &mut entities[1] {
                    b.lump = NULL_REF;
                }
            }
            15 => {
                if let Entity::Vertex(v) = &mut entities[52] {
                    v.edge = EntityRef(51);
                }
            }
            16 => {
                if let Entity::Coedge(c) = &mut entities[16] {
                    c.edge = EntityRef(60);
                }
            }
            17 => {
                if let Entity::PlaneSurface(p) = &mut entities[68] {
                    p.u_direction.x = f64::INFINITY;
                }
            }
            _ => unreachable!(),
        }
        let changed =
            AcisModel::new(original.model().metadata().clone(), entities, Vec::new()).unwrap();
        assert!(
            validate_box(&changed).is_err(),
            "mutation {mutation} accepted"
        );
    }
    let mut metadata = original.model().metadata().clone();
    metadata.units_mm = Some(1.0);
    let changed =
        AcisModel::new(metadata, original.model().entities().to_vec(), Vec::new()).unwrap();
    assert!(validate_box(&changed).is_err());
}

#[test]
fn output_budgets_fail_closed() {
    let generated = spec().build().unwrap();
    for limits in [
        SabWriteLimits {
            max_bytes: 1,
            max_entities: 86,
        },
        SabWriteLimits {
            max_bytes: 65536,
            max_entities: 85,
        },
    ] {
        assert_eq!(
            SabEncoder::new(SabWriteProfile::Asm23200MetricBox, limits)
                .encode(&generated, HistoryMode::None)
                .unwrap_err(),
            EncodeError::BudgetExceeded
        );
    }
}

#[test]
fn insertion_history_has_independently_checked_framing_and_coverage() {
    let generated = spec().build().unwrap();
    let bytes = SabEncoder::default()
        .encode(&generated, HistoryMode::InsertionOnlyStateOne)
        .unwrap();
    let parsed = parse_sab(&bytes, "generated-history", &SabLimits::default()).unwrap();
    assert_eq!(parsed.header.flags, 3);
    let span = parsed.history.unwrap();
    let suffix = &bytes[span.start_offset..];
    // Reader preserves history as opaque; independently check every typed token
    // and all insertion slots here instead of treating parse success as proof.
    let mut position = 0;
    fn name(data: &[u8], p: &mut usize) -> String {
        let mut parts = Vec::new();
        loop {
            let tag = data[*p];
            let n = data[*p + 1] as usize;
            *p += 2;
            assert!([13, 14].contains(&tag));
            parts.push(std::str::from_utf8(&data[*p..*p + n]).unwrap());
            *p += n;
            if tag == 13 {
                break;
            }
        }
        parts.join("-")
    }
    fn word(data: &[u8], p: &mut usize, tag: u8) -> i32 {
        assert_eq!(data[*p], tag);
        *p += 1;
        let v = i32::from_le_bytes(data[*p..*p + 4].try_into().unwrap());
        *p += 4;
        v
    }
    assert_eq!(name(suffix, &mut position), "Begin-of-ASM-History-Data");
    assert_eq!(name(suffix, &mut position), "history_stream");
    for v in [1, 1, 0, 19] {
        assert_eq!(word(suffix, &mut position, 4), v);
    }
    for v in [-1, 0, 0, -1] {
        assert_eq!(word(suffix, &mut position, 12), v);
    }
    assert_eq!(suffix[position], 17);
    position += 1;
    assert_eq!(name(suffix, &mut position), "delta_state");
    for v in [1, 1, 0] {
        assert_eq!(word(suffix, &mut position, 4), v);
    }
    for v in [-1, -1, 0, -1, 0] {
        assert_eq!(word(suffix, &mut position, 12), v);
    }
    assert_eq!(suffix[position], 11);
    position += 1;
    for (tag, v) in [(4, 1), (12, 0), (4, 2)] {
        assert_eq!(word(suffix, &mut position, tag), v);
    }
    for slot in 1..86 {
        for (tag, v) in [(4, 1), (12, -1), (12, slot)] {
            assert_eq!(word(suffix, &mut position, tag), v);
        }
    }
    for _ in 0..3 {
        assert_eq!(word(suffix, &mut position, 4), 0);
    }
    assert_eq!(suffix[position], 17);
    position += 1;
    assert_eq!(name(suffix, &mut position), "End-of-ASM-History-Section");
    assert_eq!(name(suffix, &mut position), "End-of-ASM-data");
    assert_eq!(position, suffix.len());
}
