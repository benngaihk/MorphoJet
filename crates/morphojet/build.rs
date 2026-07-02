use std::process::Command;

fn main() {
    emit_git_rerun_paths();

    let commit = Command::new("git")
        .args(["rev-parse", "--short=12", "HEAD"])
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "unknown".to_owned());

    println!("cargo:rustc-env=MORPHOJET_BUILD_COMMIT={commit}");
}

fn emit_git_rerun_paths() {
    let git_head = "../../.git/HEAD";
    println!("cargo:rerun-if-changed={git_head}");

    let Ok(head) = std::fs::read_to_string(git_head) else {
        return;
    };
    let Some(reference) = head.trim().strip_prefix("ref: ") else {
        return;
    };

    println!("cargo:rerun-if-changed=../../.git/{reference}");
    println!("cargo:rerun-if-changed=../../.git/packed-refs");
}
