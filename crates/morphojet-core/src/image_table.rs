use anyhow::{anyhow, bail, Context, Result};
use csv::StringRecord;
use std::collections::{BTreeMap, HashSet};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ImageTableRow {
    pub image_number: u32,
    pub image_path: PathBuf,
    pub mask_path: PathBuf,
    pub channel: Option<String>,
    pub object_set: Option<String>,
    pub metadata: BTreeMap<String, String>,
}

pub fn read_image_table(path: impl AsRef<Path>) -> Result<Vec<ImageTableRow>> {
    let path = path.as_ref();
    let base_dir = path.parent().unwrap_or_else(|| Path::new("."));
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to open image table {}", path.display()))?;
    let headers = reader
        .headers()
        .context("failed to read image table headers")?
        .clone();

    let image_number_idx = required_header(&headers, &["ImageNumber"])?;
    let image_path_idx = required_header(&headers, &["ImagePath", "PathName_Image"])?;
    let mask_path_idx = required_header(&headers, &["MaskPath", "PathName_Mask"])?;
    let channel_idx = optional_header(&headers, &["Channel", "ChannelName"]);
    let object_set_idx = optional_header(&headers, &["ObjectSet", "ObjectsName", "ObjectName"]);

    let mut rows = Vec::new();
    for (row_index, record) in reader.records().enumerate() {
        let record = record.with_context(|| format!("failed to read CSV row {}", row_index + 2))?;
        let image_number = get(&record, image_number_idx, "ImageNumber")?
            .parse::<u32>()
            .with_context(|| format!("invalid ImageNumber at CSV row {}", row_index + 2))?;
        let image_path = resolve_path(base_dir, get(&record, image_path_idx, "ImagePath")?);
        let mask_path = resolve_path(base_dir, get(&record, mask_path_idx, "MaskPath")?);
        let channel = channel_idx
            .and_then(|idx| record.get(idx))
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned);
        let object_set = object_set_idx
            .and_then(|idx| record.get(idx))
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned);

        let mut metadata = BTreeMap::new();
        for (idx, header) in headers.iter().enumerate() {
            if idx == image_number_idx || idx == image_path_idx || idx == mask_path_idx {
                continue;
            }
            if Some(idx) == channel_idx {
                continue;
            }
            if Some(idx) == object_set_idx {
                continue;
            }
            let value = record.get(idx).unwrap_or("").trim();
            if !value.is_empty() {
                metadata.insert(header.to_owned(), value.to_owned());
            }
        }

        rows.push(ImageTableRow {
            image_number,
            image_path,
            mask_path,
            channel,
            object_set,
            metadata,
        });
    }

    Ok(rows)
}

pub fn validate_image_table(rows: &[ImageTableRow]) -> Result<()> {
    if rows.is_empty() {
        bail!("image table contains no rows");
    }

    let mut identities = HashSet::new();
    for row in rows {
        let identity = (
            row.image_number,
            row.channel.clone().unwrap_or_default(),
            row.object_set.clone().unwrap_or_default(),
        );
        if !identities.insert(identity) {
            bail!(
                "duplicate image row identity: ImageNumber={} Channel={} ObjectSet={}",
                row.image_number,
                row.channel.as_deref().unwrap_or(""),
                row.object_set.as_deref().unwrap_or("")
            );
        }

        ensure_readable_file(&row.image_path, "image", row.image_number)?;
        ensure_readable_file(&row.mask_path, "mask", row.image_number)?;
    }

    Ok(())
}

fn ensure_readable_file(path: &Path, kind: &str, image_number: u32) -> Result<()> {
    let metadata = std::fs::metadata(path).with_context(|| {
        format!(
            "{} path for ImageNumber {} is not readable: {}",
            kind,
            image_number,
            path.display()
        )
    })?;
    if !metadata.is_file() {
        bail!(
            "{} path for ImageNumber {} is not a file: {}",
            kind,
            image_number,
            path.display()
        );
    }
    Ok(())
}

fn required_header(headers: &StringRecord, names: &[&str]) -> Result<usize> {
    optional_header(headers, names).ok_or_else(|| {
        anyhow!(
            "missing required column; expected one of {}",
            names.join(", ")
        )
    })
}

fn optional_header(headers: &StringRecord, names: &[&str]) -> Option<usize> {
    headers.iter().position(|header| names.contains(&header))
}

fn get<'a>(record: &'a StringRecord, idx: usize, name: &str) -> Result<&'a str> {
    let value = record
        .get(idx)
        .ok_or_else(|| anyhow!("missing value for column {name}"))?
        .trim();
    if value.is_empty() {
        return Err(anyhow!("empty value for column {name}"));
    }
    Ok(value)
}

fn resolve_path(base_dir: &Path, value: &str) -> PathBuf {
    let path = PathBuf::from(value);
    if path.is_absolute() {
        path
    } else {
        base_dir.join(path)
    }
}
