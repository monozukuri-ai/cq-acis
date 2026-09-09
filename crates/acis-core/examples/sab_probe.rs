use acis_core::sab::{parse_sab, SabLimits};
fn main() {
    for path in std::env::args().skip(1) {
        let bytes = std::fs::read(&path).unwrap();
        match parse_sab(&bytes, &path, &SabLimits::default()) {
            Ok(doc) => {
                println!(
                    "{path}: {} records, {} bodies, version {}",
                    doc.model.len(),
                    doc.model.bodies().count(),
                    doc.header.save_version
                );
                for d in doc.model.diagnostics() {
                    println!("{} {}", d.code, d.message);
                }
            }
            Err(e) => println!("{path}: {e}"),
        }
    }
}
