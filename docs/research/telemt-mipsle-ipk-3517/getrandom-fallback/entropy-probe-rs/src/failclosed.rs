//! Research-only fail-closed probe: without entropy devices the forked crates
//! MUST return errors; any "success" without an entropy source is a security
//! bug and fails the gate. Run inside a mount namespace whose /dev is an empty
//! tmpfs (see getrandom-fallback/gate.sh).

fn main() {
    if std::path::Path::new("/dev/urandom").exists() {
        println!("RS_FAIL_CLOSED_SKIPPED_DEVICE_PRESENT");
        return;
    }
    let mut buf = [0u8; 32];
    let e4 = getrandom_4::fill(&mut buf).is_err();
    let e3 = getrandom_3::fill(&mut buf).is_err();
    let e2 = getrandom_2::getrandom(&mut buf).is_err();
    println!("RS_FAIL_CLOSED errs: 0.4.3={} 0.3.4={} 0.2.17={}", e4, e3, e2);
    if e4 && e3 && e2 {
        println!("RS_FAIL_CLOSED_OK");
    } else {
        eprintln!("RS_FAIL_CLOSED_VIOLATION");
        std::process::exit(1);
    }
}
