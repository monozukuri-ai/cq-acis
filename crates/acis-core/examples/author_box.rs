//! Generate a bounded metric box SAB using only six numeric inputs.
use acis_core::{
    authoring::BoxSpec,
    encode::{HistoryMode, SabEncoder},
    sab::{parse_sab, SabLimits},
    Vec3,
};
use std::{env, fs};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().skip(1).collect();
    if args.len() != 8 {
        return Err("usage: author_box OUTPUT.sab SIZE_X_MM SIZE_Y_MM SIZE_Z_MM MIN_X_MM MIN_Y_MM MIN_Z_MM source|result".into());
    }
    let numbers: Vec<f64> = args[1..7]
        .iter()
        .map(|s| s.parse())
        .collect::<Result<_, _>>()?;
    let size = Vec3::from((numbers[0], numbers[1], numbers[2]));
    let origin = Vec3::from((numbers[3], numbers[4], numbers[5]));
    let history = match args[7].as_str() {
        "source" => HistoryMode::None,
        "result" => HistoryMode::InsertionOnlyStateOne,
        _ => return Err("history must be source or result".into()),
    };
    let generated = BoxSpec::new(size, origin).build()?;
    let bytes = SabEncoder::default().encode(&generated, history)?;
    let decoded = parse_sab(&bytes, "authored-box", &SabLimits::default())?;
    // Do not replace existing evidence accidentally.
    use std::io::Write;
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&args[0])?;
    file.write_all(&bytes)?;
    println!("{{\"bytes\":{},\"active_entities\":{},\"decoded_entities\":{},\"scale\":{},\"history\":{},\"volume_mm3\":{}}}",bytes.len(),generated.model().entities().len(),decoded.model.entities().len(),decoded.header.scale,decoded.history.is_some(),generated.validation().volume_mm3);
    Ok(())
}
