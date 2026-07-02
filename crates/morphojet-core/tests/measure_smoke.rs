use image::{GrayImage, ImageBuffer, Luma};
use morphojet_core::{
    measure_rows, measure_rows_with_options, read_image_table, write_image_csv, write_object_csv,
    MeasureOptions,
};
use std::fs;

#[test]
fn measures_two_labeled_objects() {
    let dir = tempfile::tempdir().unwrap();
    let image_path = dir.path().join("image.tif");
    let mask_path = dir.path().join("mask.tif");
    let table_path = dir.path().join("images.csv");

    let image = GrayImage::from_vec(3, 2, vec![1, 2, 3, 4, 5, 6]).unwrap();
    image.save(&image_path).unwrap();

    let mask: ImageBuffer<Luma<u16>, Vec<u16>> =
        ImageBuffer::from_vec(3, 2, vec![1, 1, 0, 2, 2, 2]).unwrap();
    mask.save(&mask_path).unwrap();

    fs::write(
        &table_path,
        "ImageNumber,ImagePath,MaskPath,Channel,ObjectSet,Plate\n1,image.tif,mask.tif,DAPI,Nuclei,P001\n",
    )
    .unwrap();

    let rows = read_image_table(&table_path).unwrap();
    let results = measure_rows(&rows).unwrap();

    assert_eq!(results.len(), 1);
    assert_eq!(results[0].image.object_set.as_deref(), Some("Nuclei"));
    assert_eq!(results[0].image.object_count, 2);
    assert_eq!(results[0].objects[0].object_set.as_deref(), Some("Nuclei"));
    assert_eq!(results[0].objects[0].object_number, 1);
    assert_eq!(results[0].objects[0].area, 2);
    assert_eq!(results[0].objects[0].intensity_integrated, 3.0 / 255.0);
    assert_eq!(results[0].objects[1].object_number, 2);
    assert_eq!(results[0].objects[1].area, 3);
    assert_eq!(results[0].objects[1].intensity_integrated, 15.0 / 255.0);

    let image_csv = dir.path().join("Image.csv");
    let object_csv = dir.path().join("Objects.csv");
    write_image_csv(&image_csv, &results).unwrap();
    write_object_csv(&object_csv, &results).unwrap();

    let image_csv = fs::read_to_string(image_csv).unwrap();
    let object_csv = fs::read_to_string(object_csv).unwrap();
    assert!(image_csv.contains("Count_Objects"));
    assert!(image_csv.contains("P001"));
    assert!(object_csv.contains("AreaShape_Area"));
    assert!(object_csv.contains("Intensity_IntegratedIntensity"));
    assert!(object_csv.contains("AreaShape_Solidity"));
}

#[test]
fn compact_object_numbers_match_cellprofiler_conversion() {
    let dir = tempfile::tempdir().unwrap();
    let image_path = dir.path().join("image.tif");
    let mask_path = dir.path().join("mask.tif");
    let table_path = dir.path().join("images.csv");

    let image = GrayImage::from_vec(3, 2, vec![1, 2, 3, 4, 5, 6]).unwrap();
    image.save(&image_path).unwrap();

    let mask: ImageBuffer<Luma<u16>, Vec<u16>> =
        ImageBuffer::from_vec(3, 2, vec![0, 2, 2, 0, 5, 5]).unwrap();
    mask.save(&mask_path).unwrap();

    fs::write(
        &table_path,
        "ImageNumber,ImagePath,MaskPath,Channel\n1,image.tif,mask.tif,DAPI\n",
    )
    .unwrap();

    let rows = read_image_table(&table_path).unwrap();
    let raw_results = measure_rows(&rows).unwrap();
    let compact_results = measure_rows_with_options(
        &rows,
        MeasureOptions {
            compact_object_numbers: true,
        },
    )
    .unwrap();

    assert_eq!(raw_results[0].objects[0].object_number, 2);
    assert_eq!(raw_results[0].objects[1].object_number, 5);
    assert_eq!(compact_results[0].objects[0].object_number, 1);
    assert_eq!(compact_results[0].objects[1].object_number, 2);
    assert_eq!(compact_results[0].objects[0].area, 2);
    assert_eq!(compact_results[0].objects[1].area, 2);
}
