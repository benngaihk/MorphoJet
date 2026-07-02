use anyhow::{bail, Error, Result};
use clap::{Parser, Subcommand};
use morphojet_core::{
    measure_rows_with_options, read_image_table, validate_image_table,
    write_measurement_csvs_atomic, MeasureOptions,
};
use serde::Serialize;
use std::collections::BTreeSet;
use std::path::{Component, Path, PathBuf};
use std::process::ExitCode;
use std::time::Instant;

#[derive(Debug, Parser)]
#[command(name = "morphojet")]
#[command(about = "Fast batch measurements for existing microscopy label masks")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Measure(MeasureArgs),
    Doctor,
}

#[derive(Debug, Parser)]
struct MeasureArgs {
    #[arg(long)]
    images: PathBuf,
    #[arg(long)]
    out: PathBuf,
    #[arg(long)]
    threads: Option<usize>,
    #[arg(long)]
    cellprofiler_compatible: bool,
    #[arg(long)]
    overwrite: bool,
    #[arg(long)]
    summary_json: Option<PathBuf>,
    #[arg(long)]
    error_json: Option<PathBuf>,
}

#[derive(Debug, Serialize)]
struct MeasureSummary {
    status: &'static str,
    version: &'static str,
    commit: &'static str,
    platform_os: &'static str,
    platform_arch: &'static str,
    elapsed_seconds: f64,
    image_rows: usize,
    object_rows: usize,
    channels: Vec<String>,
    object_sets: Vec<String>,
    output_dir: String,
    image_csv: String,
    objects_csv: String,
    cellprofiler_compatible: bool,
    threads: usize,
}

#[derive(Debug, Serialize)]
struct ErrorReport {
    status: &'static str,
    version: &'static str,
    commit: &'static str,
    command: &'static str,
    error_code: String,
    message: String,
    causes: Vec<String>,
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    match cli.command {
        Command::Measure(args) => match run_measure(&args) {
            Ok(()) => ExitCode::SUCCESS,
            Err(error) => {
                if let Some(path) = args
                    .error_json
                    .as_ref()
                    .filter(|_| can_write_error_report(&args))
                {
                    let report = ErrorReport::from_error("measure", &error);
                    if let Err(report_error) = write_json_atomic(path, &report) {
                        eprintln!(
                            "MorphoJet: failed to write error JSON {}: {report_error:#}",
                            path.display()
                        );
                    }
                }
                eprintln!("Error: {error:#}");
                ExitCode::FAILURE
            }
        },
        Command::Doctor => match run_doctor() {
            Ok(()) => ExitCode::SUCCESS,
            Err(error) => {
                eprintln!("Error: {error:#}");
                ExitCode::FAILURE
            }
        },
    }
}

fn run_doctor() -> Result<()> {
    let current_exe = std::env::current_exe()?;
    println!("morphojet.version={}", env!("CARGO_PKG_VERSION"));
    println!("morphojet.commit={}", env!("MORPHOJET_BUILD_COMMIT"));
    println!("platform.os={}", std::env::consts::OS);
    println!("platform.arch={}", std::env::consts::ARCH);
    println!("parallel.default_threads={}", rayon::current_num_threads());
    println!("runtime.current_exe={}", current_exe.display());
    Ok(())
}

fn run_measure(args: &MeasureArgs) -> Result<()> {
    let started = Instant::now();
    if let Some(threads) = args.threads {
        if threads == 0 {
            bail!("--threads must be greater than 0");
        }
        rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build_global()?;
    }

    if args.cellprofiler_compatible {
        eprintln!("MorphoJet: writing CellProfiler-style measurement CSV names");
    }

    ensure_output_targets(args)?;
    std::fs::create_dir_all(&args.out)?;
    let rows = read_image_table(&args.images)?;
    validate_image_table(&rows)?;
    let results = measure_rows_with_options(
        &rows,
        MeasureOptions {
            compact_object_numbers: args.cellprofiler_compatible,
        },
    )?;
    write_measurement_csvs_atomic(&args.out, &results)?;

    let object_count: usize = results.iter().map(|result| result.objects.len()).sum();
    if let Some(summary_path) = &args.summary_json {
        write_summary_json(
            summary_path,
            &MeasureSummary::from_results(
                args,
                &results,
                object_count,
                started.elapsed().as_secs_f64(),
            ),
        )?;
    }
    eprintln!(
        "MorphoJet: measured {} image rows and {} objects",
        results.len(),
        object_count
    );
    Ok(())
}

impl MeasureSummary {
    fn from_results(
        args: &MeasureArgs,
        results: &[morphojet_core::MeasureResult],
        object_count: usize,
        elapsed_seconds: f64,
    ) -> Self {
        let channels = results
            .iter()
            .filter_map(|result| result.image.channel.clone())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>();
        let object_sets = results
            .iter()
            .filter_map(|result| result.image.object_set.clone())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>();
        Self {
            status: "PASS",
            version: env!("CARGO_PKG_VERSION"),
            commit: env!("MORPHOJET_BUILD_COMMIT"),
            platform_os: std::env::consts::OS,
            platform_arch: std::env::consts::ARCH,
            elapsed_seconds,
            image_rows: results.len(),
            object_rows: object_count,
            channels,
            object_sets,
            output_dir: args.out.display().to_string(),
            image_csv: args.out.join("Image.csv").display().to_string(),
            objects_csv: args.out.join("Objects.csv").display().to_string(),
            cellprofiler_compatible: args.cellprofiler_compatible,
            threads: rayon::current_num_threads(),
        }
    }
}

impl ErrorReport {
    fn from_error(command: &'static str, error: &Error) -> Self {
        let causes = error
            .chain()
            .skip(1)
            .map(ToString::to_string)
            .collect::<Vec<_>>();
        Self {
            status: "FAIL",
            version: env!("CARGO_PKG_VERSION"),
            commit: env!("MORPHOJET_BUILD_COMMIT"),
            command,
            error_code: classify_error(error).to_string(),
            message: error.to_string(),
            causes,
        }
    }
}

fn classify_error(error: &Error) -> &'static str {
    let text = error
        .chain()
        .map(ToString::to_string)
        .collect::<Vec<_>>()
        .join("\n")
        .to_lowercase();
    if text.contains("--threads must be greater than 0") {
        "invalid_threads"
    } else if text.contains("refusing to overwrite") {
        "output_exists"
    } else if text.contains("duplicate image table column")
        || text.contains("reserved output name")
        || text.contains("missing required column")
        || text.contains("invalid imagenumber")
        || text.contains("empty value for column")
    {
        "invalid_image_table"
    } else if text.contains("image table contains no rows") {
        "empty_image_table"
    } else if text.contains("duplicate image row identity") {
        "duplicate_image_identity"
    } else if text.contains("not readable") || text.contains("failed to open image table") {
        "input_not_readable"
    } else if text.contains("image and mask dimensions differ") {
        "dimension_mismatch"
    } else {
        "measure_failed"
    }
}

fn write_summary_json(path: &Path, summary: &MeasureSummary) -> Result<()> {
    write_json_atomic(path, summary)
}

fn write_json_atomic<T: Serialize>(path: &Path, payload: &T) -> Result<()> {
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        std::fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension(format!(
        "{}tmp",
        path.extension()
            .and_then(|value| value.to_str())
            .map(|value| format!("{value}."))
            .unwrap_or_default()
    ));
    let mut bytes = serde_json::to_vec_pretty(payload)?;
    bytes.push(b'\n');
    std::fs::write(&tmp, bytes)?;
    std::fs::rename(&tmp, path)?;
    Ok(())
}

fn ensure_output_targets(args: &MeasureArgs) -> Result<()> {
    if args.out.exists() && !args.out.is_dir() {
        bail!(
            "--out exists but is not a directory: {}",
            args.out.display()
        );
    }

    let (image_csv, objects_csv) = measurement_csv_paths(args);
    let image_csv_key = normalized_path(&image_csv)?;
    let objects_csv_key = normalized_path(&objects_csv)?;
    ensure_file_output_target(&image_csv)?;
    ensure_file_output_target(&objects_csv)?;
    let mut summary_json_key = None;
    let mut error_json_key = None;
    if let Some(summary_json) = &args.summary_json {
        let summary_key = normalized_path(summary_json)?;
        if summary_key == image_csv_key || summary_key == objects_csv_key {
            bail!(
                "--summary-json must not point at Image.csv or Objects.csv: {}",
                summary_json.display()
            );
        }
        ensure_report_target(summary_json)?;
        summary_json_key = Some(summary_key);
    }
    if let Some(error_json) = &args.error_json {
        let error_key = normalized_path(error_json)?;
        if error_key == image_csv_key || error_key == objects_csv_key {
            bail!(
                "--error-json must not point at Image.csv or Objects.csv: {}",
                error_json.display()
            );
        }
        ensure_report_target(error_json)?;
        error_json_key = Some(error_key);
    }
    if let (Some(summary_json), Some(summary_key), Some(error_key)) = (
        args.summary_json.as_ref(),
        summary_json_key.as_ref(),
        error_json_key.as_ref(),
    ) {
        if summary_key == error_key {
            bail!(
                "--summary-json and --error-json must use different paths: {}",
                summary_json.display()
            );
        }
    }
    if !args.overwrite {
        let mut protected = vec![image_csv, objects_csv];
        if let Some(summary_json) = &args.summary_json {
            protected.push(summary_json.clone());
        }
        if let Some(error_json) = &args.error_json {
            protected.push(error_json.clone());
        }
        let existing = protected
            .into_iter()
            .filter(|path| path.exists())
            .map(|path| path.display().to_string())
            .collect::<Vec<_>>();
        if !existing.is_empty() {
            bail!(
                "refusing to overwrite existing output files without --overwrite: {}",
                existing.join(", ")
            );
        }
    }
    Ok(())
}

fn measurement_csv_paths(args: &MeasureArgs) -> (PathBuf, PathBuf) {
    (args.out.join("Image.csv"), args.out.join("Objects.csv"))
}

fn ensure_file_output_target(path: &Path) -> Result<()> {
    if path.exists() && !path.is_file() {
        bail!("output target exists but is not a file: {}", path.display());
    }
    Ok(())
}

fn ensure_report_target(path: &Path) -> Result<()> {
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        if parent.exists() && !parent.is_dir() {
            bail!(
                "report parent exists but is not a directory: {}",
                parent.display()
            );
        }
    }
    if path.exists() && !path.is_file() {
        bail!("report target exists but is not a file: {}", path.display());
    }
    Ok(())
}

fn normalized_path(path: &Path) -> Result<PathBuf> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            other => normalized.push(other.as_os_str()),
        }
    }
    Ok(normalized)
}

fn can_write_error_report(args: &MeasureArgs) -> bool {
    let Some(error_json) = &args.error_json else {
        return false;
    };
    let (image_csv, objects_csv) = measurement_csv_paths(args);
    let Ok(error_key) = normalized_path(error_json) else {
        return false;
    };
    if normalized_path(&image_csv).ok().as_ref() == Some(&error_key)
        || normalized_path(&objects_csv).ok().as_ref() == Some(&error_key)
    {
        return false;
    }
    if args
        .summary_json
        .as_ref()
        .and_then(|summary_json| normalized_path(summary_json).ok())
        .as_ref()
        == Some(&error_key)
    {
        return false;
    }
    args.overwrite || !error_json.exists()
}
