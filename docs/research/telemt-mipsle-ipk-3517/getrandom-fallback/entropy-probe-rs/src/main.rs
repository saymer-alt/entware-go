//! Research-only target-arch entropy probe (MIPS32r2 o32 softfloat, Entware ABI).
//! Verifies on the guest ABI that rand 0.10.2 ThreadRng initializes without the
//! round-2 panic and that every locked getrandom version serves distinct bytes,
//! on both the getrandom(2) path and the forced /dev/urandom fallback path.

use rand::Rng;

fn main() {
    // 1) the exact round-2 regression: ThreadRng must not panic at init
    let mut t1 = [0u8; 32];
    let mut t2 = [0u8; 32];
    rand::rng().fill_bytes(&mut t1);
    rand::rng().fill_bytes(&mut t2);
    assert!(t1 != t2, "ThreadRng produced identical consecutive buffers");
    println!("RS_THREADRNG_OK");

    // 2) each locked getrandom version must serve distinct entropy
    let mut a = [0u8; 32];
    let mut b = [0u8; 32];
    getrandom_4::fill(&mut a).expect("getrandom 0.4.3 fill failed");
    getrandom_4::fill(&mut b).expect("getrandom 0.4.3 fill failed (2)");
    assert!(a != b, "0.4.3 produced identical buffers");
    println!("RS_GETRANDOM_0_4_3_OK");

    let mut a = [0u8; 32];
    let mut b = [0u8; 32];
    getrandom_3::fill(&mut a).expect("getrandom 0.3.4 fill failed");
    getrandom_3::fill(&mut b).expect("getrandom 0.3.4 fill failed (2)");
    assert!(a != b, "0.3.4 produced identical buffers");
    println!("RS_GETRANDOM_0_3_4_OK");

    let mut a = [0u8; 32];
    let mut b = [0u8; 32];
    getrandom_2::getrandom(&mut a).expect("getrandom 0.2.17 failed");
    getrandom_2::getrandom(&mut b).expect("getrandom 0.2.17 failed (2)");
    assert!(a != b, "0.2.17 produced identical buffers");
    println!("RS_GETRANDOM_0_2_17_OK");

    println!("RS_PROBE_DONE");
}
