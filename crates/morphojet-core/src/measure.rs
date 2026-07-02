use crate::image_table::ImageTableRow;
use anyhow::{bail, Context, Result};
use image::{DynamicImage, GenericImageView};
use rayon::prelude::*;
use std::collections::{BTreeMap, HashMap};

#[derive(Debug, Clone)]
pub struct MeasureResult {
    pub image: ImageMeasurement,
    pub objects: Vec<ObjectMeasurement>,
}

#[derive(Debug, Clone)]
pub struct ImageMeasurement {
    pub image_number: u32,
    pub channel: Option<String>,
    pub object_set: Option<String>,
    pub image_path: String,
    pub mask_path: String,
    pub width: u32,
    pub height: u32,
    pub object_count: usize,
    pub metadata: BTreeMap<String, String>,
}

#[derive(Debug, Clone)]
pub struct ObjectMeasurement {
    pub image_number: u32,
    pub object_number: u32,
    pub channel: Option<String>,
    pub object_set: Option<String>,
    pub area: u64,
    pub centroid_x: f64,
    pub centroid_y: f64,
    pub bbox_min_x: u32,
    pub bbox_min_y: u32,
    pub bbox_max_x: u32,
    pub bbox_max_y: u32,
    pub intensity_min: f64,
    pub intensity_max: f64,
    pub intensity_mean: f64,
    pub intensity_median: f64,
    pub intensity_integrated: f64,
    pub perimeter: u64,
    pub eccentricity: f64,
    pub major_axis_length: f64,
    pub minor_axis_length: f64,
    pub solidity: f64,
}

#[derive(Debug)]
struct ObjectAccumulator {
    label: u32,
    area: u64,
    sum_x: f64,
    sum_y: f64,
    sum_x2: f64,
    sum_y2: f64,
    sum_xy: f64,
    bbox_min_x: u32,
    bbox_min_y: u32,
    bbox_max_x: u32,
    bbox_max_y: u32,
    intensity_min: f64,
    intensity_max: f64,
    intensity_sum: f64,
    intensity_values: Vec<f64>,
    perimeter: u64,
    points: Vec<Point>,
}

impl ObjectAccumulator {
    fn new(label: u32, x: u32, y: u32, intensity: f64) -> Self {
        Self {
            label,
            area: 0,
            sum_x: 0.0,
            sum_y: 0.0,
            sum_x2: 0.0,
            sum_y2: 0.0,
            sum_xy: 0.0,
            bbox_min_x: x,
            bbox_min_y: y,
            bbox_max_x: x,
            bbox_max_y: y,
            intensity_min: intensity,
            intensity_max: intensity,
            intensity_sum: 0.0,
            intensity_values: Vec::new(),
            perimeter: 0,
            points: Vec::new(),
        }
    }

    fn add_pixel(&mut self, x: u32, y: u32, intensity: f64, boundary_edges: u64) {
        let xf = x as f64;
        let yf = y as f64;
        self.area += 1;
        self.sum_x += xf;
        self.sum_y += yf;
        self.sum_x2 += xf * xf;
        self.sum_y2 += yf * yf;
        self.sum_xy += xf * yf;
        self.bbox_min_x = self.bbox_min_x.min(x);
        self.bbox_min_y = self.bbox_min_y.min(y);
        self.bbox_max_x = self.bbox_max_x.max(x);
        self.bbox_max_y = self.bbox_max_y.max(y);
        self.intensity_min = self.intensity_min.min(intensity);
        self.intensity_max = self.intensity_max.max(intensity);
        self.intensity_sum += intensity;
        self.intensity_values.push(intensity);
        self.perimeter += boundary_edges;
        self.points.extend(pixel_corners(xf, yf));
    }

    fn finish(
        mut self,
        image_number: u32,
        channel: Option<String>,
        object_set: Option<String>,
    ) -> ObjectMeasurement {
        self.intensity_values
            .sort_by(|left, right| left.total_cmp(right));
        let median = median(&self.intensity_values);
        let area = self.area as f64;
        let centroid_x = self.sum_x / area;
        let centroid_y = self.sum_y / area;
        let mean = self.intensity_sum / area;
        let (major_axis_length, minor_axis_length, eccentricity) = axis_features(
            self.sum_x2 / area - centroid_x * centroid_x,
            self.sum_y2 / area - centroid_y * centroid_y,
            self.sum_xy / area - centroid_x * centroid_y,
        );
        let solidity = solidity(area, &self.points);

        ObjectMeasurement {
            image_number,
            object_number: self.label,
            channel,
            object_set,
            area: self.area,
            centroid_x,
            centroid_y,
            bbox_min_x: self.bbox_min_x,
            bbox_min_y: self.bbox_min_y,
            bbox_max_x: self.bbox_max_x,
            bbox_max_y: self.bbox_max_y,
            intensity_min: self.intensity_min,
            intensity_max: self.intensity_max,
            intensity_mean: mean,
            intensity_median: median,
            intensity_integrated: self.intensity_sum,
            perimeter: self.perimeter,
            eccentricity,
            major_axis_length,
            minor_axis_length,
            solidity,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct Point {
    x: f64,
    y: f64,
}

pub fn measure_rows(rows: &[ImageTableRow]) -> Result<Vec<MeasureResult>> {
    rows.par_iter().map(measure_row).collect()
}

pub fn measure_row(row: &ImageTableRow) -> Result<MeasureResult> {
    let (intensity, width, height) = load_intensity(row)?;
    let (labels, mask_width, mask_height) = load_labels(row)?;
    if width != mask_width || height != mask_height {
        bail!(
            "image and mask dimensions differ for ImageNumber {}: image={}x{}, mask={}x{}",
            row.image_number,
            width,
            height,
            mask_width,
            mask_height
        );
    }

    let mut objects: HashMap<u32, ObjectAccumulator> = HashMap::new();
    for y in 0..height {
        for x in 0..width {
            let idx = (y * width + x) as usize;
            let label = labels[idx];
            if label == 0 {
                continue;
            }
            let value = intensity[idx];
            let boundary_edges = boundary_edges(&labels, width, height, x, y, label);
            objects
                .entry(label)
                .or_insert_with(|| ObjectAccumulator::new(label, x, y, value))
                .add_pixel(x, y, value, boundary_edges);
        }
    }

    let mut objects = objects
        .into_values()
        .map(|object| {
            object.finish(
                row.image_number,
                row.channel.clone(),
                row.object_set.clone(),
            )
        })
        .collect::<Vec<_>>();
    objects.sort_by_key(|object| object.object_number);

    let image = ImageMeasurement {
        image_number: row.image_number,
        channel: row.channel.clone(),
        object_set: row.object_set.clone(),
        image_path: row.image_path.display().to_string(),
        mask_path: row.mask_path.display().to_string(),
        width,
        height,
        object_count: objects.len(),
        metadata: row.metadata.clone(),
    };

    Ok(MeasureResult { image, objects })
}

fn load_intensity(row: &ImageTableRow) -> Result<(Vec<f64>, u32, u32)> {
    let image = image::open(&row.image_path)
        .with_context(|| format!("failed to open image {}", row.image_path.display()))?;
    let (width, height) = image.dimensions();
    let pixels = match image {
        DynamicImage::ImageLuma8(buffer) => {
            buffer.pixels().map(|pixel| pixel.0[0] as f64).collect()
        }
        DynamicImage::ImageLuma16(buffer) => {
            buffer.pixels().map(|pixel| pixel.0[0] as f64).collect()
        }
        other => other
            .to_luma32f()
            .pixels()
            .map(|pixel| pixel.0[0] as f64)
            .collect(),
    };
    Ok((pixels, width, height))
}

fn load_labels(row: &ImageTableRow) -> Result<(Vec<u32>, u32, u32)> {
    let image = image::open(&row.mask_path)
        .with_context(|| format!("failed to open mask {}", row.mask_path.display()))?;
    let (width, height) = image.dimensions();
    let labels = match image {
        DynamicImage::ImageLuma8(buffer) => {
            buffer.pixels().map(|pixel| pixel.0[0] as u32).collect()
        }
        DynamicImage::ImageLuma16(buffer) => {
            buffer.pixels().map(|pixel| pixel.0[0] as u32).collect()
        }
        other => other
            .to_luma16()
            .pixels()
            .map(|pixel| pixel.0[0] as u32)
            .collect(),
    };
    Ok((labels, width, height))
}

fn boundary_edges(labels: &[u32], width: u32, height: u32, x: u32, y: u32, label: u32) -> u64 {
    let mut edges = 0;
    let neighbors = [
        (x.checked_sub(1), Some(y)),
        (x.checked_add(1).filter(|nx| *nx < width), Some(y)),
        (Some(x), y.checked_sub(1)),
        (Some(x), y.checked_add(1).filter(|ny| *ny < height)),
    ];
    for (nx, ny) in neighbors {
        match (nx, ny) {
            (Some(nx), Some(ny)) => {
                let neighbor_idx = (ny * width + nx) as usize;
                if labels[neighbor_idx] != label {
                    edges += 1;
                }
            }
            _ => edges += 1,
        }
    }
    edges
}

fn median(values: &[f64]) -> f64 {
    match values.len() {
        0 => f64::NAN,
        len if len % 2 == 1 => values[len / 2],
        len => (values[len / 2 - 1] + values[len / 2]) / 2.0,
    }
}

fn axis_features(var_x: f64, var_y: f64, cov_xy: f64) -> (f64, f64, f64) {
    let trace = var_x + var_y;
    let determinant_term = ((var_x - var_y).powi(2) + 4.0 * cov_xy.powi(2)).sqrt();
    let lambda_major = ((trace + determinant_term) / 2.0).max(0.0);
    let lambda_minor = ((trace - determinant_term) / 2.0).max(0.0);
    let major_axis_length = 4.0 * lambda_major.sqrt();
    let minor_axis_length = 4.0 * lambda_minor.sqrt();
    let eccentricity = if lambda_major <= f64::EPSILON {
        0.0
    } else {
        (1.0 - lambda_minor / lambda_major).clamp(0.0, 1.0).sqrt()
    };
    (major_axis_length, minor_axis_length, eccentricity)
}

fn solidity(area: f64, points: &[Point]) -> f64 {
    let hull_area = convex_hull_area(points);
    if hull_area <= f64::EPSILON {
        1.0
    } else {
        (area / hull_area).clamp(0.0, 1.0)
    }
}

fn pixel_corners(x: f64, y: f64) -> [Point; 4] {
    [
        Point {
            x: x - 0.5,
            y: y - 0.5,
        },
        Point {
            x: x + 0.5,
            y: y - 0.5,
        },
        Point {
            x: x + 0.5,
            y: y + 0.5,
        },
        Point {
            x: x - 0.5,
            y: y + 0.5,
        },
    ]
}

fn convex_hull_area(points: &[Point]) -> f64 {
    if points.len() < 3 {
        return 0.0;
    }

    let mut points = points.to_vec();
    points.sort_by(|left, right| {
        left.x
            .total_cmp(&right.x)
            .then_with(|| left.y.total_cmp(&right.y))
    });
    points.dedup_by(|left, right| left.x == right.x && left.y == right.y);

    if points.len() < 3 {
        return 0.0;
    }

    let mut lower = Vec::new();
    for point in &points {
        while lower.len() >= 2
            && cross(lower[lower.len() - 2], lower[lower.len() - 1], *point) <= 0.0
        {
            lower.pop();
        }
        lower.push(*point);
    }

    let mut upper = Vec::new();
    for point in points.iter().rev() {
        while upper.len() >= 2
            && cross(upper[upper.len() - 2], upper[upper.len() - 1], *point) <= 0.0
        {
            upper.pop();
        }
        upper.push(*point);
    }

    lower.pop();
    upper.pop();
    let hull = lower.into_iter().chain(upper).collect::<Vec<_>>();
    polygon_area(&hull)
}

fn cross(origin: Point, a: Point, b: Point) -> f64 {
    (a.x - origin.x) * (b.y - origin.y) - (a.y - origin.y) * (b.x - origin.x)
}

fn polygon_area(points: &[Point]) -> f64 {
    if points.len() < 3 {
        return 0.0;
    }
    let mut area = 0.0;
    for idx in 0..points.len() {
        let next = (idx + 1) % points.len();
        area += points[idx].x * points[next].y - points[next].x * points[idx].y;
    }
    area.abs() / 2.0
}
