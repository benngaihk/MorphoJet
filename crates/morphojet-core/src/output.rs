use crate::measure::{ImageMeasurement, MeasureResult, ObjectMeasurement};
use anyhow::{Context, Result};
use csv::Writer;
use std::collections::BTreeSet;
use std::path::Path;

const IMAGE_COLUMNS: &[&str] = &[
    "ImageNumber",
    "Channel",
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

fn write_image_record(
    writer: &mut Writer<std::fs::File>,
    image: &ImageMeasurement,
    metadata_columns: &[String],
) -> Result<()> {
    let mut record = vec![
        image.image_number.to_string(),
        image.channel.clone().unwrap_or_default(),
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
        object.area.to_string(),
        format_float(object.centroid_x),
        format_float(object.centroid_y),
        object.bbox_min_x.to_string(),
        object.bbox_min_y.to_string(),
        object.bbox_max_x.to_string(),
        object.bbox_max_y.to_string(),
        format_float(object.intensity_min),
        format_float(object.intensity_max),
        format_float(object.intensity_mean),
        format_float(object.intensity_median),
        format_float(object.intensity_integrated),
        object.perimeter.to_string(),
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
