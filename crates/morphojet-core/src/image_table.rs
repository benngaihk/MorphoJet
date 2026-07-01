use anyhow::{anyhow, Context, Result};
use csv::StringRecord;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ImageTableRow {
    pub image_number: u32,
    pub image_path: PathBuf,
    pub mask_path: PathBuf,
    pub channel: Option<String>,
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

        let mut metadata = BTreeMap::new();
        for (idx, header) in headers.iter().enumerate() {
            if idx == image_number_idx || idx == image_path_idx || idx == mask_path_idx {
                continue;
            }
            if Some(idx) == channel_idx {
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
            metadata,
        });
    }

    Ok(rows)
}

fn required_header(headers: &StringRecord, names: &[&str]) -> Result<usize> {
    optional_header(headers, names)
        .ok_or_else(|| anyhow!("missing required column; expected one of {}", names.join(", ")))
}

fn optional_header(headers: &StringRecord, names: &[&str]) -> Option<usize> {
    headers
        .iter()
        .position(|header| names.iter().any(|name| header == *name))
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
