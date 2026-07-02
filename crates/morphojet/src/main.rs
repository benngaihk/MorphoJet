use anyhow::{bail, Result};
use clap::{Parser, Subcommand};
use morphojet_core::{
    measure_rows_with_options, read_image_table, validate_image_table,
    write_measurement_csvs_atomic, MeasureOptions,
};
use serde::Serialize;
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
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

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Measure(args) => run_measure(args),
        Command::Doctor => run_doctor(),
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

fn run_measure(args: MeasureArgs) -> Result<()> {
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

    ensure_output_targets(&args)?;
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
                &args,
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

fn write_summary_json(path: &Path, summary: &MeasureSummary) -> Result<()> {
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
    let mut payload = serde_json::to_vec_pretty(summary)?;
    payload.push(b'\n');
    std::fs::write(&tmp, payload)?;
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

    let image_csv = args.out.join("Image.csv");
    let objects_csv = args.out.join("Objects.csv");
    if let Some(summary_json) = &args.summary_json {
        if summary_json == &image_csv || summary_json == &objects_csv {
            bail!(
                "--summary-json must not point at Image.csv or Objects.csv: {}",
                summary_json.display()
            );
        }
    }
    if !args.overwrite {
        let mut protected = vec![image_csv, objects_csv];
        if let Some(summary_json) = &args.summary_json {
            protected.push(summary_json.clone());
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
