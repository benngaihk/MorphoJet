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
    pub perimeter: f64,
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
    pixels: Vec<(u32, u32)>,
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
            pixels: Vec::new(),
        }
    }

    fn add_pixel(&mut self, x: u32, y: u32, intensity: f64) {
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
        self.pixels.push((x, y));
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
        let solidity = skimage_solidity(
            area,
            &self.pixels,
            self.bbox_min_x,
            self.bbox_min_y,
            self.bbox_max_x,
            self.bbox_max_y,
        );
        let perimeter = skimage_perimeter_4(
            &self.pixels,
            self.bbox_min_x,
            self.bbox_min_y,
            self.bbox_max_x,
            self.bbox_max_y,
        );

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
            perimeter,
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
            objects
                .entry(label)
                .or_insert_with(|| ObjectAccumulator::new(label, x, y, value))
                .add_pixel(x, y, value);
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
        DynamicImage::ImageLuma8(buffer) => buffer
            .pixels()
            .map(|pixel| pixel.0[0] as f64 / u8::MAX as f64)
            .collect(),
        DynamicImage::ImageLuma16(buffer) => buffer
            .pixels()
            .map(|pixel| pixel.0[0] as f64 / u16::MAX as f64)
            .collect(),
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

fn median(values: &[f64]) -> f64 {
    let len = values.len();
    if len == 0 {
        return f64::NAN;
    }
    let qindex = len as f64 * 0.5;
    let lower = qindex.floor() as usize;
    let fraction = qindex - lower as f64;
    if lower < len - 1 {
        values[lower] * (1.0 - fraction) + values[lower + 1] * fraction
    } else {
        values[lower]
    }
}

fn skimage_perimeter_4(
    pixels: &[(u32, u32)],
    bbox_min_x: u32,
    bbox_min_y: u32,
    bbox_max_x: u32,
    bbox_max_y: u32,
) -> f64 {
    let width = (bbox_max_x - bbox_min_x + 1) as usize;
    let height = (bbox_max_y - bbox_min_y + 1) as usize;
    let mut image = vec![false; width * height];
    for &(x, y) in pixels {
        let local_x = (x - bbox_min_x) as usize;
        let local_y = (y - bbox_min_y) as usize;
        image[local_y * width + local_x] = true;
    }

    let mut border = vec![false; width * height];
    for y in 0..height {
        for x in 0..width {
            let idx = y * width + x;
            if !image[idx] {
                continue;
            }
            let eroded = x > 0
                && x + 1 < width
                && y > 0
                && y + 1 < height
                && image[idx - 1]
                && image[idx + 1]
                && image[idx - width]
                && image[idx + width];
            border[idx] = !eroded;
        }
    }

    let sqrt_2 = std::f64::consts::SQRT_2;
    let mut total = 0.0;
    for y in 0..height {
        for x in 0..width {
            let mut code = 0usize;
            for (dx, dy, weight) in [
                (-1isize, -1isize, 10usize),
                (0, -1, 2),
                (1, -1, 10),
                (-1, 0, 2),
                (0, 0, 1),
                (1, 0, 2),
                (-1, 1, 10),
                (0, 1, 2),
                (1, 1, 10),
            ] {
                let nx = x.checked_add_signed(dx);
                let ny = y.checked_add_signed(dy);
                if let (Some(nx), Some(ny)) = (nx, ny) {
                    if nx < width && ny < height && border[ny * width + nx] {
                        code += weight;
                    }
                }
            }
            total += match code {
                5 | 7 | 15 | 17 | 25 | 27 => 1.0,
                21 | 33 => sqrt_2,
                13 | 23 => (1.0 + sqrt_2) / 2.0,
                _ => 0.0,
            };
        }
    }
    total
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

fn skimage_solidity(
    area: f64,
    pixels: &[(u32, u32)],
    bbox_min_x: u32,
    bbox_min_y: u32,
    bbox_max_x: u32,
    bbox_max_y: u32,
) -> f64 {
    let hull_area = convex_hull_pixel_count(pixels, bbox_min_x, bbox_min_y, bbox_max_x, bbox_max_y);
    if hull_area == 0 {
        1.0
    } else {
        (area / hull_area as f64).clamp(0.0, 1.0)
    }
}

fn pixel_diamond_points(x: f64, y: f64) -> [Point; 4] {
    [
        Point { x, y: y - 0.5 },
        Point { x: x - 0.5, y },
        Point { x: x + 0.5, y },
        Point { x, y: y + 0.5 },
    ]
}

fn convex_hull(points: &[Point]) -> Vec<Point> {
    if points.len() < 3 {
        return points.to_vec();
    }

    let mut points = points.to_vec();
    points.sort_by(|left, right| {
        left.x
            .total_cmp(&right.x)
            .then_with(|| left.y.total_cmp(&right.y))
    });
    points.dedup_by(|left, right| left.x == right.x && left.y == right.y);

    if points.len() < 3 {
        return points;
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
    lower.into_iter().chain(upper).collect::<Vec<_>>()
}

fn convex_hull_pixel_count(
    pixels: &[(u32, u32)],
    bbox_min_x: u32,
    bbox_min_y: u32,
    bbox_max_x: u32,
    bbox_max_y: u32,
) -> u64 {
    if pixels.is_empty() {
        return 0;
    }
    let mut points = Vec::with_capacity(pixels.len() * 4);
    for &(x, y) in pixels {
        let local_x = (x - bbox_min_x) as f64;
        let local_y = (y - bbox_min_y) as f64;
        points.extend(pixel_diamond_points(local_x, local_y));
    }
    let hull = convex_hull(&points);
    if hull.len() < 3 {
        return pixels.len() as u64;
    }

    let width = bbox_max_x - bbox_min_x + 1;
    let height = bbox_max_y - bbox_min_y + 1;
    let mut count = 0;
    for y in 0..height {
        for x in 0..width {
            if point_in_convex_polygon(
                Point {
                    x: x as f64,
                    y: y as f64,
                },
                &hull,
            ) {
                count += 1;
            }
        }
    }
    count
}

fn point_in_convex_polygon(point: Point, polygon: &[Point]) -> bool {
    let mut has_positive = false;
    let mut has_negative = false;
    const TOLERANCE: f64 = 1e-10;
    for idx in 0..polygon.len() {
        let left = polygon[idx];
        let right = polygon[(idx + 1) % polygon.len()];
        let value = cross(left, right, point);
        if value > TOLERANCE {
            has_positive = true;
        } else if value < -TOLERANCE {
            has_negative = true;
        }
        if has_positive && has_negative {
            return false;
        }
    }
    true
}

fn cross(origin: Point, a: Point, b: Point) -> f64 {
    (a.x - origin.x) * (b.y - origin.y) - (a.y - origin.y) * (b.x - origin.x)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn close(left: f64, right: f64) {
        assert!((left - right).abs() < 1e-12, "left={left} right={right}");
    }

    #[test]
    fn median_matches_cellprofiler_quantile_interpolation() {
        close(median(&[1.0]), 1.0);
        close(median(&[1.0, 3.0]), 3.0);
        close(median(&[1.0, 3.0, 5.0]), 4.0);
        close(median(&[1.0, 3.0, 5.0, 7.0]), 5.0);
    }

    #[test]
    fn perimeter_matches_skimage_0183_small_shapes() {
        close(skimage_perimeter_4(&[(0, 0)], 0, 0, 0, 0), 0.0);
        close(
            skimage_perimeter_4(&[(0, 0), (1, 0), (0, 1), (1, 1)], 0, 0, 1, 1),
            4.0,
        );
        close(
            skimage_perimeter_4(&[(0, 0), (1, 0), (2, 0)], 0, 0, 2, 0),
            1.0,
        );
        close(
            skimage_perimeter_4(&[(0, 0), (0, 1), (1, 1)], 0, 0, 1, 1),
            2.0 + std::f64::consts::SQRT_2,
        );
    }

    #[test]
    fn solidity_matches_skimage_0183_convex_hull_image_count() {
        let u_shape = [(0, 0), (2, 0), (0, 1), (1, 1), (2, 1)];
        close(skimage_solidity(5.0, &u_shape, 0, 0, 2, 1), 5.0 / 6.0);

        let concave = [
            (0, 0),
            (1, 0),
            (2, 0),
            (0, 1),
            (2, 1),
            (0, 2),
            (1, 2),
            (2, 2),
        ];
        close(skimage_solidity(8.0, &concave, 0, 0, 2, 2), 8.0 / 9.0);
    }
}
