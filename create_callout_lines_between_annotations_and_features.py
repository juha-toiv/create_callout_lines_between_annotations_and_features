# Copyright (c) 2022 Juha Toivola
# Licensed under the terms of the MIT License
import arcpy
from datetime import datetime
if __name__ == "__main__":
    input_anno_fc = arcpy.GetParameterAsText(0)
    input_target_fc = arcpy.GetParameterAsText(1)
    input_target_fc_textstring_field = arcpy.GetParameterAsText(2)
    output_fc = arcpy.GetParameterAsText(3)
    is_polygon_outline = arcpy.GetParameter(4)
    spatial_ref = arcpy.Describe(input_target_fc).spatialReference
    arcpy.env.outputCoordinateSystem = spatial_ref
    points_list = []
    now = datetime.now()
    now_str = now.strftime("%d%b%Y_%H%M%S")
    # copy target layer to memory
    tmp_input_target_fc = "memory/tmp_target_lyr" + now_str
    arcpy.CopyFeatures_management(input_target_fc, tmp_input_target_fc)
    # convert annotations to points and store in memory
    tmp_anno_to_pnt = "memory/tmp_convert_anno_" + now_str
    if is_polygon_outline:
        arcpy.management.FeatureToPolygon(input_anno_fc, tmp_anno_to_pnt)
    else:
        arcpy.management.FeatureToPoint(input_anno_fc, tmp_anno_to_pnt)
    # create start and end points for callout lines
    list_of_near_lyrs = []
    with arcpy.da.UpdateCursor(tmp_anno_to_pnt, ['OID@', 'TextString']) as anno_pnt_cur:
        for anno_pnt_row in anno_pnt_cur:
            anno_pnt_oid = anno_pnt_row[0]
            anno_text_string = anno_pnt_row[1]
            input_anno_pnt_id_field = arcpy.Describe(tmp_anno_to_pnt).OIDFieldName
            anno_selection_by_id = arcpy.management.SelectLayerByAttribute(tmp_anno_to_pnt, "NEW_SELECTION", input_anno_pnt_id_field + " = " + str(anno_pnt_oid))
            target_fc_query = "{} = '{}'".format(input_target_fc_textstring_field, anno_text_string)
            target_fc_sel = arcpy.management.SelectLayerByAttribute(tmp_input_target_fc, "NEW_SELECTION", target_fc_query)
            now = datetime.now()
            now_str = now.strftime("%d%b%Y_%H%M%S")
            anno_pnt_copy_near = "memory/tmp_copy_near_" + now_str
            arcpy.CopyFeatures_management(anno_selection_by_id, anno_pnt_copy_near)
            arcpy.analysis.Near(anno_pnt_copy_near, target_fc_sel, location="LOCATION")
            # if outline - create lines between nearest vertices
            if is_polygon_outline:
                with arcpy.da.UpdateCursor(anno_pnt_copy_near, ['OID@', "NEAR_X", "NEAR_Y", "NEAR_FID"]) as anno_pnt_copy_near_cur:
                    for anno_pnt_copy_near_row in anno_pnt_copy_near_cur:
                        end_x = anno_pnt_copy_near_row[1]
                        end_y = anno_pnt_copy_near_row[2]
                        near_fid = anno_pnt_copy_near_row[3]
                        input_target_fc_oid_field = arcpy.Describe(input_target_fc).OIDFieldName
                        target_near_fid_sel = arcpy.management.SelectLayerByAttribute(tmp_anno_to_pnt, "NEW_SELECTION", input_target_fc_oid_field + " = " + str(near_fid))
                        tmp_target_copy_near = "memory/tmp_target_copy_near_" + now_str
                        arcpy.CopyFeatures_management(target_near_fid_sel, tmp_target_copy_near)
                        arcpy.analysis.Near(tmp_target_copy_near, anno_pnt_copy_near, location="LOCATION")
                        with arcpy.da.UpdateCursor(tmp_target_copy_near, ['OID@', "NEAR_X", "NEAR_Y", "NEAR_FID"]) as tmp_target_copy_near_cur:
                            for tmp_target_copy_near_row in tmp_target_copy_near_cur:
                                start_x = tmp_target_copy_near_row[1]
                                start_y = tmp_target_copy_near_row[2]
                                points_list.append([[start_x, start_y], [end_x, end_y]])
                arcpy.management.Delete(anno_pnt_copy_near)
                arcpy.management.Delete(tmp_target_copy_near)
            # centroid lines from anno centroid to polygon centroid
            else:
                tmp_anno_out_fc = "memory/tmp_anno_selection_" + str(anno_pnt_oid)
                arcpy.analysis.SpatialJoin(anno_selection_by_id, target_fc_sel, tmp_anno_out_fc, "JOIN_ONE_TO_MANY", match_option="CLOSEST")
                with arcpy.da.SearchCursor(tmp_anno_out_fc, ['OID@', 'JOIN_FID', 'SHAPE@XY']) as tmp_anno_pnt_cur:
                    for tmp_anno_pnt_row in tmp_anno_pnt_cur:
                        target_feature_id = tmp_anno_pnt_row[1]
                        start_x = tmp_anno_pnt_row[2][0]
                        start_y = tmp_anno_pnt_row[2][1]
                        with arcpy.da.SearchCursor(target_fc_sel, ['OID@', 'SHAPE@XY']) as tmp_target_cur:
                            for tmp_target_row in tmp_target_cur:
                                if tmp_target_row[0] == target_feature_id:
                                    end_x = tmp_target_row[1][0]
                                    end_y = tmp_target_row[1][1]
                                    points_list.append([[start_x, start_y], [end_x, end_y]])
    # clear memory
    arcpy.management.Delete(tmp_anno_to_pnt)
    arcpy.management.Delete(tmp_input_target_fc)
    # convert start and end points from list into polyline features
    output_lines_list = []
    arcpy.AddMessage(points_list)
    for line_feature in points_list:
        output_lines_list.append(
            arcpy.Polyline(
                arcpy.Array([arcpy.Point(*coords) for coords in line_feature])))
    if is_polygon_outline:
        arcpy.CopyFeatures_management(output_lines_list, output_fc)
    else:
        now = datetime.now()
        now_str = now.strftime("%d%b%Y_%H%M%S")
        tmp_copy_out_fc = "memory/tmp_copy_" + now_str
        arcpy.CopyFeatures_management(output_lines_list, tmp_copy_out_fc)
        tmp_bound_fc = "memory/tmp_bound_" + now_str
        # trim callout lines
        arcpy.management.MinimumBoundingGeometry(input_anno_fc, tmp_bound_fc, "ENVELOPE")
        # final output
        arcpy.analysis.Erase(tmp_copy_out_fc, tmp_bound_fc, output_fc)
        # clear memory
        arcpy.management.Delete(tmp_bound_fc)
        arcpy.management.Delete(tmp_copy_out_fc)
    # add to map if map active
    try:
        aprx = arcpy.mp.ArcGISProject('CURRENT')
        active_map = aprx.activeMap.name
        aprxMap = aprx.listMaps(active_map)[0]
        aprxMap.addDataFromPath(output_polyline_feature_3d)
    except:
        pass
