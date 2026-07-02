use image::{GrayImage, ImageBuffer, Luma};
use std::fs;
use std::path::Path;
use std::process::{Command, Output};

fn write_images(dir: &Path, image_size: (u32, u32), mask_size: (u32, u32)) {
    let image_path = dir.join("image.tif");
    let mask_path = dir.join("mask.tif");
    let image_pixels = vec![10; (image_size.0 * image_size.1) as usize];
    let mask_pixels = vec![1_u16; (mask_size.0 * mask_size.1) as usize];
    let image = GrayImage::from_vec(image_size.0, image_size.1, image_pixels).unwrap();
    let mask: ImageBuffer<Luma<u16>, Vec<u16>> =
        ImageBuffer::from_vec(mask_size.0, mask_size.1, mask_pixels).unwrap();
    image.save(image_path).unwrap();
    mask.save(mask_path).unwrap();
}

fn write_table(dir: &Path, body: &str) -> std::path::PathBuf {
    let table = dir.join("images.csv");
    fs::write(
        &table,
        format!("ImageNumber,ImagePath,MaskPath,Channel\n{body}"),
    )
    .unwrap();
    table
}

fn write_object_set_table(dir: &Path, body: &str) -> std::path::PathBuf {
    let table = dir.join("images.csv");
    fs::write(
        &table,
        format!("ImageNumber,ImagePath,MaskPath,Channel,ObjectSet\n{body}"),
    )
    .unwrap();
    table
}

fn run_measure(table: &Path, out: &Path, extra_args: &[&str]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_morphojet"));
    command
        .arg("measure")
        .arg("--images")
        .arg(table)
        .arg("--out")
        .arg(out)
        .arg("--cellprofiler-compatible");
    for arg in extra_args {
        command.arg(arg);
    }
    command.output().unwrap()
}

fn run_doctor() -> Output {
    Command::new(env!("CARGO_BIN_EXE_morphojet"))
        .arg("doctor")
        .output()
        .unwrap()
}

fn stderr(output: &Output) -> String {
    String::from_utf8_lossy(&output.stderr).to_string()
}

#[test]
fn measure_success_writes_expected_csvs() {
    let dir = tempfile::tempdir().unwrap();
    write_images(dir.path(), (3, 2), (3, 2));
    let table = write_table(dir.path(), "1,image.tif,mask.tif,DAPI\n");
    let out = dir.path().join("out");

    let output = run_measure(&table, &out, &["--overwrite"]);

    assert!(output.status.success(), "{}", stderr(&output));
    assert!(out.join("Image.csv").exists());
    assert!(out.join("Objects.csv").exists());
    let staging_dirs = fs::read_dir(&out)
        .unwrap()
        .filter_map(Result::ok)
        .filter(|entry| {
            entry
                .file_name()
                .to_string_lossy()
                .starts_with(".morphojet-write-")
        })
        .count();
    assert_eq!(staging_dirs, 0);
}

#[test]
fn measure_success_writes_summary_json() {
    let dir = tempfile::tempdir().unwrap();
    write_images(dir.path(), (3, 2), (3, 2));
    let table = write_object_set_table(dir.path(), "1,image.tif,mask.tif,DAPI,Nuclei\n");
    let out = dir.path().join("out");
    let summary = dir.path().join("summary.json");

    let output = run_measure(
        &table,
        &out,
        &["--overwrite", "--summary-json", summary.to_str().unwrap()],
    );

    assert!(output.status.success(), "{}", stderr(&output));
    let payload: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(summary).unwrap()).unwrap();
    assert_eq!(payload["status"], "PASS");
    assert_eq!(payload["image_rows"], 1);
    assert_eq!(payload["object_rows"], 1);
    assert_eq!(payload["channels"][0], "DAPI");
    assert_eq!(payload["object_sets"][0], "Nuclei");
    assert_eq!(payload["cellprofiler_compatible"], true);
    assert!(payload["elapsed_seconds"].as_f64().unwrap() >= 0.0);
    assert!(payload["image_csv"]
        .as_str()
        .unwrap()
        .ends_with("Image.csv"));
    assert!(payload["objects_csv"]
        .as_str()
        .unwrap()
        .ends_with("Objects.csv"));
}

#[test]
fn measure_failure_writes_error_json_without_summary() {
    let dir = tempfile::tempdir().unwrap();
    write_images(dir.path(), (3, 2), (3, 2));
    let table = write_table(dir.path(), "1,missing.tif,mask.tif,DAPI\n");
    let out = dir.path().join("out");
    let summary = dir.path().join("summary.json");
    let error_json = dir.path().join("error.json");

    let output = run_measure(
        &table,
        &out,
        &[
            "--overwrite",
            "--summary-json",
            summary.to_str().unwrap(),
            "--error-json",
            error_json.to_str().unwrap(),
        ],
    );

    assert!(!output.status.success());
    assert!(stderr(&output).contains("image path for ImageNumber 1 is not readable"));
    assert!(!summary.exists());
    let payload: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(error_json).unwrap()).unwrap();
    assert_eq!(payload["status"], "FAIL");
    assert_eq!(payload["command"], "measure");
    assert_eq!(payload["error_code"], "input_not_readable");
    assert!(payload["message"]
        .as_str()
        .unwrap()
        .contains("image path for ImageNumber 1 is not readable"));
    assert!(payload["version"].as_str().is_some());
    assert!(payload["commit"].as_str().is_some());
}

#[test]
fn overwrite_refusal_writes_error_code() {
    let dir = tempfile::tempdir().unwrap();
    write_images(dir.path(), (3, 2), (3, 2));
    let table = write_table(dir.path(), "1,image.tif,mask.tif,DAPI\n");
    let out = dir.path().join("out");
    let error_json = dir.path().join("error.json");

    let first = run_measure(&table, &out, &["--overwrite"]);
    assert!(first.status.success(), "{}", stderr(&first));

    let second = run_measure(
        &table,
        &out,
        &["--error-json", error_json.to_str().unwrap()],
    );

    assert!(!second.status.success());
    let payload: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(error_json).unwrap()).unwrap();
    assert_eq!(payload["error_code"], "output_exists");
}

#[test]
fn refuses_to_overwrite_existing_summary_without_flag() {
    let dir = tempfile::tempdir().unwrap();
    write_images(dir.path(), (3, 2), (3, 2));
    let table = write_table(dir.path(), "1,image.tif,mask.tif,DAPI\n");
    let out = dir.path().join("out");
    let summary = dir.path().join("summary.json");
    fs::write(&summary, "{}\n").unwrap();

    let output = run_measure(&table, &out, &["--summary-json", summary.to_str().unwrap()]);

    assert!(!output.status.success());
    assert!(stderr(&output).contains("refusing to overwrite"));
}

#[test]
fn rejects_summary_json_that_collides_with_measurement_csvs() {
    let dir = tempfile::tempdir().unwrap();
    write_images(dir.path(), (3, 2), (3, 2));
    let table = write_table(dir.path(), "1,image.tif,mask.tif,DAPI\n");
    let out = dir.path().join("out");
    let summary = out.join("Image.csv");

    let output = run_measure(
        &table,
        &out,
        &["--overwrite", "--summary-json", summary.to_str().unwrap()],
    );

    assert!(!output.status.success());
    assert!(stderr(&output).contains("--summary-json must not point at"));
}

#[test]
fn refuses_to_overwrite_existing_outputs_without_flag() {
    let dir = tempfile::tempdir().unwrap();
    write_images(dir.path(), (3, 2), (3, 2));
    let table = write_table(dir.path(), "1,image.tif,mask.tif,DAPI\n");
    let out = dir.path().join("out");

    let first = run_measure(&table, &out, &["--overwrite"]);
    assert!(first.status.success(), "{}", stderr(&first));

    let second = run_measure(&table, &out, &[]);

    assert!(!second.status.success());
    assert!(stderr(&second).contains("refusing to overwrite"));
}

#[test]
fn rejects_zero_threads() {
    let dir = tempfile::tempdir().unwrap();
    let table = dir.path().join("images.csv");
    fs::write(&table, "ImageNumber,ImagePath,MaskPath,Channel\n").unwrap();
    let out = dir.path().join("out");

    let output = run_measure(&table, &out, &["--threads", "0"]);

    assert!(!output.status.success());
    assert!(stderr(&output).contains("--threads must be greater than 0"));
}

#[test]
fn rejects_empty_image_table() {
    let dir = tempfile::tempdir().unwrap();
    let table = dir.path().join("images.csv");
    fs::write(&table, "ImageNumber,ImagePath,MaskPath,Channel\n").unwrap();
    let out = dir.path().join("out");

    let output = run_measure(&table, &out, &["--overwrite"]);

    assert!(!output.status.success());
    assert!(stderr(&output).contains("image table contains no rows"));
}

#[test]
fn rejects_duplicate_image_identity() {
    let dir = tempfile::tempdir().unwrap();
    write_images(dir.path(), (3, 2), (3, 2));
    let table = write_table(
        dir.path(),
        "1,image.tif,mask.tif,DAPI\n1,image.tif,mask.tif,DAPI\n",
    );
    let out = dir.path().join("out");

    let output = run_measure(&table, &out, &["--overwrite"]);

    assert!(!output.status.success());
    assert!(stderr(&output).contains("duplicate image row identity"));
}

#[test]
fn allows_same_channel_for_distinct_object_sets() {
    let dir = tempfile::tempdir().unwrap();
    write_images(dir.path(), (3, 2), (3, 2));
    let table = write_object_set_table(
        dir.path(),
        "1,image.tif,mask.tif,DAPI,Nuclei\n1,image.tif,mask.tif,DAPI,Cells\n",
    );
    let out = dir.path().join("out");

    let output = run_measure(&table, &out, &["--overwrite"]);

    assert!(output.status.success(), "{}", stderr(&output));
    let objects = fs::read_to_string(out.join("Objects.csv")).unwrap();
    assert!(objects.contains("ObjectSet"));
    assert!(objects.contains("Nuclei"));
    assert!(objects.contains("Cells"));
}

#[test]
fn rejects_missing_image_path_before_measurement() {
    let dir = tempfile::tempdir().unwrap();
    write_images(dir.path(), (3, 2), (3, 2));
    let table = write_table(dir.path(), "1,missing.tif,mask.tif,DAPI\n");
    let out = dir.path().join("out");

    let output = run_measure(&table, &out, &["--overwrite"]);

    assert!(!output.status.success());
    assert!(stderr(&output).contains("image path for ImageNumber 1 is not readable"));
}

#[test]
fn rejects_dimension_mismatch() {
    let dir = tempfile::tempdir().unwrap();
    write_images(dir.path(), (3, 2), (4, 2));
    let table = write_table(dir.path(), "1,image.tif,mask.tif,DAPI\n");
    let out = dir.path().join("out");

    let output = run_measure(&table, &out, &["--overwrite"]);

    assert!(!output.status.success());
    assert!(stderr(&output).contains("image and mask dimensions differ"));
    assert!(!out.join("Image.csv").exists());
    assert!(!out.join("Objects.csv").exists());
}

#[test]
fn doctor_reports_build_and_runtime_context() {
    let output = run_doctor();

    assert!(output.status.success(), "{}", stderr(&output));
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("morphojet.version="));
    assert!(stdout.contains("morphojet.commit="));
    assert!(stdout.contains("platform.os="));
    assert!(stdout.contains("platform.arch="));
    assert!(stdout.contains("parallel.default_threads="));
    assert!(stdout.contains("runtime.current_exe="));
}
