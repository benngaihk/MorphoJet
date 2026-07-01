use anyhow::Result;
use clap::{Parser, Subcommand};
use morphojet_core::{measure_rows, read_image_table, write_image_csv, write_object_csv};
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
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Measure(args) => run_measure(args),
    }
}

fn run_measure(args: MeasureArgs) -> Result<()> {
    if let Some(threads) = args.threads {
        rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build_global()?;
    }

    if args.cellprofiler_compatible {
        eprintln!("MorphoJet: writing CellProfiler-style measurement CSV names");
    }

    std::fs::create_dir_all(&args.out)?;
    let rows = read_image_table(&args.images)?;
    let results = measure_rows(&rows)?;
    write_image_csv(args.out.join("Image.csv"), &results)?;
    write_object_csv(args.out.join("Objects.csv"), &results)?;

    let object_count: usize = results.iter().map(|result| result.objects.len()).sum();
    eprintln!(
        "MorphoJet: measured {} image rows and {} objects",
        results.len(),
        object_count
    );
    Ok(())
}
