//! Host Rust build script: uses cc-rs 1.4.5 only to compile MIPSLE C archives.
//! It does not cross-link any MIPSLE object into the host binary.
use std::{env, path::Path};

fn main() {
    let mut build = cc::Build::new();
    build.cargo_metadata(false)
        .target("mipsel-unknown-linux-gnu")
        .archiver("mipsel-linux-gnu-ar");
    let ring_root = env::var("TELEMT_RING_SOURCE_ROOT").ok();
    if let Some(root) = ring_root {
        let source = Path::new(&root);
        let generated = env::var("TELEMT_RING_GENERATED_INCLUDE")
            .expect("TELEMT_RING_GENERATED_INCLUDE required with TELEMT_RING_SOURCE_ROOT");
        for path in [
            "crypto/mem.c",
            "crypto/limbs/limbs.c",
            "crypto/fipsmodule/aes/aes_nohw.c",
            "crypto/curve25519/curve25519.c",
        ] {
            let file = source.join(path);
            assert!(file.is_file(), "missing pinned ring source {}", file.display());
            build.file(file);
        }
        build
            .include(source.join("include"))
            .include(source.join("crypto"))
            .include(generated)
            .define("NDEBUG", None)
            .flag("-fvisibility=hidden")
            .flag("-std=c1x");
        println!("cargo:warning=ring 0.17.14 C subset through actual cc-rs");
        build.compile("ring_c_subset");
    } else {
        println!("cargo:warning=minimal native bridge.c through actual cc-rs");
        build.file("native/bridge.c").compile("cc_mipsle_probe");
    }
}
