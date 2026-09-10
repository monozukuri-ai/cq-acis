use acis_core::*;
use std::f64::consts::FRAC_PI_2;
fn v(x: f64, y: f64, z: f64) -> Vec3 {
    (x, y, z).into()
}
fn close(a: Vec3, b: Vec3) {
    assert!((a - b).magnitude() < 1e-12, "{a:?} != {b:?}");
}

#[test]
fn vector_operations_and_zero_normalization() {
    assert_eq!(v(1., 0., 0.).cross(v(0., 1., 0.)), v(0., 0., 1.));
    assert_eq!(v(1., 2., 3.).dot(v(4., 5., 6.)), 32.);
    assert_eq!(v(3., 4., 0.).magnitude(), 5.);
    close(v(3., 4., 0.).normalized().unwrap(), v(0.6, 0.8, 0.));
    assert!(v(0., 0., 0.).normalized().is_err());
}

#[test]
fn ellipse_retains_signed_minor_direction() {
    let ellipse = EllipseCurveEntity {
        raw: RawEntity::new(0, "ellipse-curve"),
        pattern: NULL_REF,
        center: v(1., 2., 3.),
        normal: v(0., 0., 2.),
        major_axis: v(4., 0., 0.),
        ratio: -0.5,
        parameter_range: None,
    };
    assert_eq!(ellipse.major_radius(), 4.);
    assert_eq!(ellipse.minor_radius(), 2.);
    close(ellipse.evaluate(0.).unwrap(), v(5., 2., 3.));
    close(ellipse.evaluate(FRAC_PI_2).unwrap(), v(1., 0., 3.));
    assert!(!ellipse.is_circle(1e-12).unwrap());
    assert!(ellipse.is_circle(-1.).is_err());
}

#[test]
fn cone_and_plane_orientation_have_independent_expected_values() {
    let cone = ConeSurfaceEntity {
        raw: RawEntity::new(0, "cone-surface"),
        pattern: NULL_REF,
        center: v(0., 0., 0.),
        axis: v(0., 0., 1.),
        major_axis: v(1., 0., 0.),
        ratio: 1.,
        profile_range: None,
        sin_half_angle: 0.6,
        cos_half_angle: 0.8,
        reference_radius: 3.,
        parameter_scale: 3.,
        reversed: false,
        u_range: None,
        v_range: None,
    };
    close(cone.apex().unwrap().unwrap(), v(0., 0., -4.));
    close(cone.evaluate(0., 5.).unwrap(), v(6., 0., 4.));
    let plane = PlaneSurfaceEntity {
        raw: RawEntity::new(0, "plane-surface"),
        pattern: NULL_REF,
        origin: v(0., 0., 0.),
        normal: v(0., 0., 1.),
        u_direction: v(1., 0., 0.),
        reverse_v: true,
        u_range: None,
        v_range: None,
    };
    assert_eq!(plane.v_direction(), v(0., -1., 0.));
}

#[test]
fn transform_preserves_row_vector_order_translation_and_reflection() {
    let transform = TransformEntity {
        raw: RawEntity::new(0, "transform"),
        matrix_values: [0., 1., 0., 1., 0., 0., 0., 0., 1., 10., 20., 30.],
        scale: 2.,
        rotated: true,
        reflected: true,
        sheared: false,
    };
    assert_eq!(transform.linear_determinant(), -8.);
    close(transform.transform_vector(v(1., 2., 3.)), v(4., 2., 6.));
    close(transform.transform_point(v(1., 2., 3.)), v(14., 22., 36.));
}
