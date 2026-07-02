use crate::measure::{ImageMeasurement, MeasureResult, ObjectMeasurement};
use anyhow::{Context, Result};
use csv::Writer;
use std::collections::BTreeSet;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

const IMAGE_COLUMNS: &[&str] = &[
    "ImageNumber",
    "Channel",
    "ObjectSet",
    "Count_Objects",
    "Width",
    "Height",
    "ImagePath",
    "MaskPath",
];

const OBJECT_COLUMNS: &[&str] = &[
    "ImageNumber",
    "ObjectNumber",
    "Channel",
    "ObjectSet",
    "AreaShape_Area",
    "AreaShape_Center_X",
    "AreaShape_Center_Y",
    "AreaShape_BoundingBoxMinimum_X",
    "AreaShape_BoundingBoxMinimum_Y",
    "AreaShape_BoundingBoxMaximum_X",
    "AreaShape_BoundingBoxMaximum_Y",
    "Intensity_MinIntensity",
    "Intensity_MaxIntensity",
    "Intensity_MeanIntensity",
    "Intensity_MedianIntensity",
    "Intensity_IntegratedIntensity",
    "Intensity_LowerQuartileIntensity",
    "Intensity_UpperQuartileIntensity",
    "Intensity_StdIntensity",
    "Intensity_MADIntensity",
    "Location_CenterMassIntensity_X",
    "Location_CenterMassIntensity_Y",
    "Location_CenterMassIntensity_Z",
    "Location_Center_Z",
    "Location_MaxIntensity_Z",
    "AreaShape_Perimeter",
    "AreaShape_Eccentricity",
    "AreaShape_MajorAxisLength",
    "AreaShape_MinorAxisLength",
    "AreaShape_Solidity",
];

pub fn write_image_csv(path: impl AsRef<Path>, results: &[MeasureResult]) -> Result<()> {
    let path = path.as_ref();
    let metadata_columns = image_metadata_columns(results);
    let mut writer = Writer::from_path(path)
        .with_context(|| format!("failed to create image CSV {}", path.display()))?;
    let mut header = IMAGE_COLUMNS
        .iter()
        .map(|value| value.to_string())
        .collect::<Vec<_>>();
    header.extend(metadata_columns.iter().cloned());
    writer.write_record(header)?;

    for result in results {
        write_image_record(&mut writer, &result.image, &metadata_columns)?;
    }
    writer.flush()?;
    Ok(())
}

pub fn write_measurement_csvs_atomic(
    out_dir: impl AsRef<Path>,
    results: &[MeasureResult],
) -> Result<()> {
    let out_dir = out_dir.as_ref();
    std::fs::create_dir_all(out_dir)
        .with_context(|| format!("failed to create output directory {}", out_dir.display()))?;
    let final_image = out_dir.join("Image.csv");
    let final_objects = out_dir.join("Objects.csv");
    ensure_publish_target(&final_image)?;
    ensure_publish_target(&final_objects)?;

    let staging_dir = out_dir.join(staging_dir_name());
    std::fs::create_dir(&staging_dir).with_context(|| {
        format!(
            "failed to create staging output directory {}",
            staging_dir.display()
        )
    })?;

    let result = (|| -> Result<()> {
        let staging_image = staging_dir.join("Image.csv");
        let staging_objects = staging_dir.join("Objects.csv");
        write_image_csv(&staging_image, results)?;
        write_object_csv(&staging_objects, results)?;
        std::fs::rename(&staging_image, &final_image)
            .with_context(|| "failed to publish Image.csv")?;
        std::fs::rename(&staging_objects, &final_objects)
            .with_context(|| "failed to publish Objects.csv")?;
        Ok(())
    })();

    let cleanup = std::fs::remove_dir_all(&staging_dir);
    if result.is_ok() {
        cleanup.with_context(|| {
            format!(
                "failed to remove staging output directory {}",
                staging_dir.display()
            )
        })?;
    } else {
        let _ = cleanup;
    }

    result
}

fn ensure_publish_target(path: &Path) -> Result<()> {
    if !path.exists() {
        return Ok(());
    }
    let metadata = std::fs::metadata(path)
        .with_context(|| format!("failed to inspect output target {}", path.display()))?;
    if !metadata.is_file() {
        anyhow::bail!("output target exists but is not a file: {}", path.display());
    }
    Ok(())
}

pub fn write_object_csv(path: impl AsRef<Path>, results: &[MeasureResult]) -> Result<()> {
    let path = path.as_ref();
    let mut writer = Writer::from_path(path)
        .with_context(|| format!("failed to create object CSV {}", path.display()))?;
    writer.write_record(OBJECT_COLUMNS)?;
    for result in results {
        for object in &result.objects {
            write_object_record(&mut writer, object)?;
        }
    }
    writer.flush()?;
    Ok(())
}

fn image_metadata_columns(results: &[MeasureResult]) -> Vec<String> {
    let mut columns = BTreeSet::new();
    for result in results {
        columns.extend(result.image.metadata.keys().cloned());
    }
    columns.into_iter().collect()
}

fn staging_dir_name() -> String {
    let pid = std::process::id();
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    format!(".morphojet-write-{pid}-{nanos}")
}

fn write_image_record(
    writer: &mut Writer<std::fs::File>,
    image: &ImageMeasurement,
    metadata_columns: &[String],
) -> Result<()> {
    let mut record = vec![
        image.image_number.to_string(),
        image.channel.clone().unwrap_or_default(),
        image.object_set.clone().unwrap_or_default(),
        image.object_count.to_string(),
        image.width.to_string(),
        image.height.to_string(),
        image.image_path.clone(),
        image.mask_path.clone(),
    ];
    for column in metadata_columns {
        record.push(image.metadata.get(column).cloned().unwrap_or_default());
    }
    writer.write_record(record)?;
    Ok(())
}

fn write_object_record(
    writer: &mut Writer<std::fs::File>,
    object: &ObjectMeasurement,
) -> Result<()> {
    writer.write_record([
        object.image_number.to_string(),
        object.object_number.to_string(),
        object.channel.clone().unwrap_or_default(),
        object.object_set.clone().unwrap_or_default(),
        object.area.to_string(),
        format_float(object.centroid_x),
        format_float(object.centroid_y),
        object.bbox_min_x.to_string(),
        object.bbox_min_y.to_string(),
        (object.bbox_max_x + 1).to_string(),
        (object.bbox_max_y + 1).to_string(),
        format_float(object.intensity_min),
        format_float(object.intensity_max),
        format_float(object.intensity_mean),
        format_float(object.intensity_median),
        format_float(object.intensity_integrated),
        format_float(object.intensity_lower_quartile),
        format_float(object.intensity_upper_quartile),
        format_float(object.intensity_std),
        format_float(object.intensity_mad),
        format_float(object.center_mass_intensity_x),
        format_float(object.center_mass_intensity_y),
        format_float(object.center_mass_intensity_z),
        format_float(object.location_center_z),
        format_float(object.max_intensity_z),
        format_float(object.perimeter),
        format_float(object.eccentricity),
        format_float(object.major_axis_length),
        format_float(object.minor_axis_length),
        format_float(object.solidity),
    ])?;
    Ok(())
}

fn format_float(value: f64) -> String {
    format!("{value:.10}")
}
