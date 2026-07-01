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
}
