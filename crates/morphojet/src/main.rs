use anyhow::{bail, Result};
use clap::{Parser, Subcommand};
use morphojet_core::{
    measure_rows_with_options, read_image_table, validate_image_table,
    write_measurement_csvs_atomic, MeasureOptions,
};
use std::path::PathBuf;

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
    eprintln!(
        "MorphoJet: measured {} image rows and {} objects",
        results.len(),
        object_count
    );
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
    if !args.overwrite {
        let existing = [image_csv, objects_csv]
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
