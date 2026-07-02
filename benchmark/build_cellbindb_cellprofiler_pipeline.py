#!/usr/bin/env python3
"""Build a CellProfiler pipeline that measures existing CellBinDB instance masks."""

from __future__ import annotations

import argparse
from pathlib import Path


PIPELINE = """CellProfiler Pipeline: http://www.cellprofiler.org
Version:5
DateRevision:400
GitHash:
ModuleCount:8
HasImagePlaneDetails:False

Images:[module_num:1|svn_version:'Unknown'|variable_revision_number:2|show_window:False|notes:['MorphoJet CellBinDB oracle: load intensity images and instance masks.']|batch_state:array([], dtype=uint8)|enabled:True|wants_pause:False]
    :
    Filter images?:Images only
    Select the rule criteria:and (extension does isimage) (directory doesnot containregexp "[\\\\\\\\/]\\\\.")

Metadata:[module_num:2|svn_version:'Unknown'|variable_revision_number:6|show_window:False|notes:['MorphoJet CellBinDB oracle: pairing is by order after filename rules.']|batch_state:array([], dtype=uint8)|enabled:True|wants_pause:False]
    Extract metadata?:No
    Metadata data type:Text
    Metadata types:{}
    Extraction method count:1
    Metadata extraction method:Extract from file/folder names
    Metadata source:File name
    Regular expression to extract from file name:^(?P<Sample>.*)$
    Regular expression to extract from folder name:(?P<Folder>.*)$
    Extract metadata from:All images
    Select the filtering criteria:and (file does contain "")
    Metadata file location:Elsewhere...|
    Match file and image metadata:[]
    Use case insensitive matching?:No
    Metadata file name:
    Does cached metadata exist?:No

NamesAndTypes:[module_num:3|svn_version:'Unknown'|variable_revision_number:8|show_window:False|notes:['Intensity image and label-mask image are paired by sorted order.']|batch_state:array([], dtype=uint8)|enabled:True|wants_pause:False]
    Assign a name to:Images matching rules
    Select the image type:Grayscale image
    Name to assign these images:Intensity
    Match metadata:[]
    Image set matching method:Order
    Set intensity range from:Image metadata
    Assignments count:2
    Single images count:0
    Maximum intensity:65535.0
    Process as 3D?:No
    Relative pixel spacing in X:1.0
    Relative pixel spacing in Y:1.0
    Relative pixel spacing in Z:1.0
    Select the rule criteria:and (file does endwith "-img.tif")
    Name to assign these images:Intensity
    Name to assign these objects:Cell
    Select the image type:Grayscale image
    Set intensity range from:Image metadata
    Maximum intensity:65535.0
    Select the rule criteria:and (file does endwith "-instancemask.tif")
    Name to assign these images:InstanceMask
    Name to assign these objects:Cell
    Select the image type:Grayscale image
    Set intensity range from:Image metadata
    Maximum intensity:65535.0

Groups:[module_num:4|svn_version:'Unknown'|variable_revision_number:2|show_window:False|notes:[]|batch_state:array([], dtype=uint8)|enabled:True|wants_pause:False]
    Do you want to group your images?:No
    grouping metadata count:1
    Metadata category:None

ConvertImageToObjects:[module_num:5|svn_version:'Unknown'|variable_revision_number:1|show_window:False|notes:['Convert CellBinDB uint16 instance labels to CellProfiler objects without relabeling.']|batch_state:array([], dtype=uint8)|enabled:True|wants_pause:False]
    Select the input image:InstanceMask
    Name the output object:Cells
    Convert to boolean image:No
    Preserve original labels:No
    Background label:0
    Connectivity:0

MeasureObjectIntensity:[module_num:6|svn_version:'Unknown'|variable_revision_number:4|show_window:False|notes:[]|batch_state:array([], dtype=uint8)|enabled:True|wants_pause:False]
    Select images to measure:Intensity
    Select objects to measure:Cells

MeasureObjectSizeShape:[module_num:7|svn_version:'Unknown'|variable_revision_number:3|show_window:False|notes:[]|batch_state:array([], dtype=uint8)|enabled:True|wants_pause:False]
    Select object sets to measure:Cells
    Calculate the Zernike features?:No
    Calculate the advanced features?:No

ExportToSpreadsheet:[module_num:8|svn_version:'Unknown'|variable_revision_number:13|show_window:False|notes:[]|batch_state:array([], dtype=uint8)|enabled:True|wants_pause:False]
    Select the column delimiter:Comma (",")
    Add image metadata columns to your object data file?:No
    Add image file and folder names to your object data file?:No
    Select the measurements to export:No
    Calculate the per-image mean values for object measurements?:No
    Calculate the per-image median values for object measurements?:No
    Calculate the per-image standard deviation values for object measurements?:No
    Output file location:Default Output Folder|
    Create a GenePattern GCT file?:No
    Select source of sample row name:Metadata
    Select the image to use as the identifier:None
    Select the metadata to use as the identifier:None
    Export all measurement types?:Yes
    Press button to select measurements:
    Representation of Nan/Inf:NaN
    Add a prefix to file names?:No
    Filename prefix:CellBinDB_
    Overwrite existing files without warning?:Yes
    Data to export:Do not use
    Combine these object measurements with those of the previous object?:No
    File name:DATA.csv
    Use the object name for the file name?:Yes
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("benchmark/results/cellbindb/cellbindb-direct-mask.cppipe"))
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(PIPELINE)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
