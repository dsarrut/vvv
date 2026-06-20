#!/usr/bin/env python3
import sys
import os
import numpy as np
import SimpleITK as sitk
import dearpygui.dearpygui as dpg

# Screen dimensions
WIDTH, HEIGHT = 550, 550
cx, cy = WIDTH // 2, HEIGHT // 2
focal_length = 450.0
camera_dist = 500.0

# Rotation angles
theta = 0.5  # rotation around Y
phi = 0.4    # rotation around X

drag_start_theta = 0.5
drag_start_phi = 0.4
is_dragging_canvas = False

# Slice positions (in physical mm units relative to center)
slice_pos_ax = 0.0
slice_pos_cor = 0.0
slice_pos_sag = 0.0

# Load image from file or fallback to 3D phantom
def create_3d_phantom(shape=(128, 128, 128)):
    # Generate a beautiful 3D phantom with multiple structures
    z, y, x = np.ogrid[-64:64, -64:64, -64:64]
    r = np.sqrt(x**2 + y**2 + z**2)
    vol = (r < 50).astype(np.float32) * 0.4
    vol += (r < 30).astype(np.float32) * 0.3
    # Add a block structure inside
    vol[40:80, 40:80, 40:80] += 0.2
    return np.clip(vol, 0, 1)

def to_rgba(slice_gray, border_color):
    h, w = slice_gray.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    val = (slice_gray * 255).astype(np.uint8)
    rgba[..., 0] = val
    rgba[..., 1] = val
    rgba[..., 2] = val
    rgba[..., 3] = 255
    # Draw colored borders
    rgba[0:2, :, :3] = border_color
    rgba[-2:, :, :3] = border_color
    rgba[:, 0:2, :3] = border_color
    rgba[:, -2:, :3] = border_color
    return rgba

# Initialize Slices and Dimensions
image_loaded_label = "Generated 3D Phantom"
if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
    try:
        image_path = sys.argv[1]
        image = sitk.ReadImage(image_path)
        arr = sitk.GetArrayFromImage(image).astype(np.float32)
        
        # Min-max normalize
        min_v, max_v = np.min(arr), np.max(arr)
        if max_v > min_v:
            arr = (arr - min_v) / (max_v - min_v)
        else:
            arr = np.zeros_like(arr)
            
        depth, height, width = arr.shape
        spacing = image.GetSpacing()
        sz_x = width * spacing[0]
        sz_y = height * spacing[1]
        sz_z = depth * spacing[2]
        image_loaded_label = f"Loaded: {os.path.basename(image_path)}"
    except Exception as e:
        print(f"Failed to load image with SimpleITK: {e}. Falling back to phantom.")
        arr = create_3d_phantom()
        depth, height, width = arr.shape
        sz_x, sz_y, sz_z = 200.0, 200.0, 200.0
else:
    arr = create_3d_phantom()
    depth, height, width = arr.shape
    sz_x, sz_y, sz_z = 200.0, 200.0, 200.0

# Scale the physical dimensions so the bounding box fits nicely in the viewport
max_dim = max(sz_x, sz_y, sz_z)
scale_factor = 240.0 / max_dim  # Normalize max dimension to 240 units

sz_x *= scale_factor
sz_y *= scale_factor
sz_z *= scale_factor

half_x, half_y, half_z = sz_x / 2, sz_y / 2, sz_z / 2

# Extract and convert slices initially
rgba_ax = None
rgba_cor = None
rgba_sag = None

def update_slice_textures():
    global rgba_ax, rgba_cor, rgba_sag
    
    # Map physical offset position to array indices
    z_idx = int(np.clip((slice_pos_ax + half_z) / sz_z * (depth - 1), 0, depth - 1))
    y_idx = int(np.clip((slice_pos_cor + half_y) / sz_y * (height - 1), 0, height - 1))
    x_idx = int(np.clip((slice_pos_sag + half_x) / sz_x * (width - 1), 0, width - 1))
    
    slice_ax = arr[z_idx, :, :]
    slice_cor = arr[:, y_idx, :]
    slice_sag = arr[:, :, x_idx]
    
    # Use distinctive border colors: Axial -> Blue, Coronal -> Green, Sagittal -> Red
    rgba_ax = to_rgba(slice_ax, [50, 150, 255])
    rgba_cor = to_rgba(slice_cor, [50, 255, 50])
    rgba_sag = to_rgba(slice_sag, [255, 50, 50])

# Do first texture extraction
update_slice_textures()

# 3D Bounding Box Vertices
cube_vertices = np.array([
    [-half_x, -half_y, -half_z],
    [ half_x, -half_y, -half_z],
    [ half_x,  half_y, -half_z],
    [-half_x,  half_y, -half_z],
    [-half_x, -half_y,  half_z],
    [ half_x, -half_y,  half_z],
    [ half_x,  half_y,  half_z],
    [-half_x,  half_y,  half_z]
], dtype=np.float32)

cube_edges = [
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7)
]

# Output dynamic texture buffer (RGBA float32)
texture_data = np.zeros((HEIGHT, WIDTH, 4), dtype=np.float32)

def get_rotation_matrix(tx, ty):
    cx, sx = np.cos(tx), np.sin(tx)
    Rx = np.array([
        [1,   0,   0],
        [0,  cx, -sx],
        [0,  sx,  cx]
    ])
    cy, sy = np.cos(ty), np.sin(ty)
    Ry = np.array([
        [ cy,  0,  sy],
        [  0,  1,   0],
        [-sy,  0,  cy]
    ])
    return Rx @ Ry

def render_scene():
    global texture_data, theta, phi
    
    # 1. Clear color buffer and Z-buffer
    texture_data[:] = 0.12  # Dark gray background
    texture_data[..., 3] = 1.0
    z_buffer = np.full((HEIGHT, WIDTH), np.inf, dtype=np.float32)
    
    R = get_rotation_matrix(phi, theta)
    T = np.array([0, 0, camera_dist])
    
    # Define three orthogonal planes with their centers offset dynamically
    planes = [
        # 1. Axial (XY Plane at slice_pos_ax along Z)
        {"C": np.array([0, 0, slice_pos_ax]), "U": np.array([half_x, 0, 0]), "V": np.array([0, half_y, 0]), "rgba": rgba_ax},
        # 2. Coronal (XZ Plane at slice_pos_cor along Y)
        {"C": np.array([0, slice_pos_cor, 0.0]), "U": np.array([half_x, 0, 0]), "V": np.array([0, 0, half_z]), "rgba": rgba_cor},
        # 3. Sagittal (YZ Plane at slice_pos_sag along X)
        {"C": np.array([slice_pos_sag, 0.0, 0.0]), "U": np.array([0, half_y, 0]), "V": np.array([0, 0, half_z]), "rgba": rgba_sag}
    ]
    
    # Generate screen grid coordinates
    ys, xs = np.mgrid[0:HEIGHT, 0:WIDTH]
    x_s_norm = (xs - cx) / focal_length
    y_s_norm = -(ys - cy) / focal_length  # Invert Y to align with 3D coordinate system (Y-up)
    
    for plane in planes:
        A = R @ plane["C"] + T
        B = R @ plane["U"]
        D = R @ plane["V"]
        rgba = plane["rgba"]
        tex_h, tex_w, _ = rgba.shape
        
        # Cramer's rule to project screen to plane space
        a11 = x_s_norm * B[2] - B[0]
        a12 = x_s_norm * D[2] - D[0]
        a21 = y_s_norm * B[2] - B[1]
        a22 = y_s_norm * D[2] - D[1]
        
        r1 = A[0] - x_s_norm * A[2]
        r2 = A[1] - y_s_norm * A[2]
        
        det = a11 * a22 - a12 * a21
        valid_det = np.abs(det) > 1e-5
        
        u = np.zeros_like(det)
        v = np.zeros_like(det)
        
        u[valid_det] = (r1[valid_det] * a22[valid_det] - r2[valid_det] * a12[valid_det]) / det[valid_det]
        v[valid_det] = (a11[valid_det] * r2[valid_det] - a21[valid_det] * r1[valid_det]) / det[valid_det]
        
        # Calculate depth (camera Z-coordinate)
        depth = A[2] + u * B[2] + v * D[2]
        
        # Check boundary bounds and depth testing
        mask = valid_det & (u >= -1.0) & (u <= 1.0) & (v >= -1.0) & (v <= 1.0) & (depth < z_buffer)
        
        if np.any(mask):
            tex_x = ((u[mask] + 1.0) * 0.5 * (tex_w - 1)).astype(int)
            tex_y = ((v[mask] + 1.0) * 0.5 * (tex_h - 1)).astype(int)
            texture_data[mask] = rgba[tex_y, tex_x] / 255.0
            z_buffer[mask] = depth[mask]
            
    # Project bounding box wireframe
    proj_vertices = []
    for v in cube_vertices:
        v_cam = R @ v + T
        if v_cam[2] > 10:
            xs_proj = int(focal_length * v_cam[0] / v_cam[2] + cx)
            ys_proj = int(-focal_length * v_cam[1] / v_cam[2] + cy)  # Invert Y to align with texture mapping
            proj_vertices.append((xs_proj, ys_proj))
        else:
            proj_vertices.append(None)
            
    return proj_vertices

def on_click(sender, app_data):
    global drag_start_theta, drag_start_phi, is_dragging_canvas
    # Only initiate rotation drag if the click starts inside the 3D canvas bounds
    if dpg.is_item_hovered("canvas_drawlist"):
        is_dragging_canvas = True
        drag_start_theta = theta
        drag_start_phi = phi
    else:
        is_dragging_canvas = False

def on_drag(sender, app_data):
    global theta, phi
    if not is_dragging_canvas:
        return
    dx = app_data[1]
    dy = app_data[2]
    theta = drag_start_theta + dx * 0.005
    phi = drag_start_phi - dy * 0.005
    update_viewer()

def update_viewer():
    proj_vertices = render_scene()
    dpg.set_value("dynamic_texture_id", texture_data.ravel())
    
    dpg.delete_item("cube_wireframe", children_only=True)
    for edge in cube_edges:
        p1 = proj_vertices[edge[0]]
        p2 = proj_vertices[edge[1]]
        if p1 and p2:
            dpg.draw_line(p1, p2, color=[0, 246, 7, 255], thickness=1.5, parent="cube_wireframe")

# Slider change callbacks
def on_slider_slice_change():
    global slice_pos_ax, slice_pos_cor, slice_pos_sag
    slice_pos_ax = dpg.get_value("slider_axial")
    slice_pos_cor = dpg.get_value("slider_coronal")
    slice_pos_sag = dpg.get_value("slider_sagittal")
    update_slice_textures()
    update_viewer()

# Dear PyGui Context
dpg.create_context()
dpg.create_viewport(title="VVV 3D Perspective Intersecting Slices Viewer", width=960, height=640)

with dpg.texture_registry(show=False):
    dpg.add_dynamic_texture(width=WIDTH, height=HEIGHT, default_value=texture_data.ravel(), tag="dynamic_texture_id")

with dpg.window(label="Active Viewer (3D Orthogonal Slices)", width=930, height=600):
    dpg.add_text("Drag with Left Mouse Button inside the canvas to rotate the 3D planes.")
    
    with dpg.group(horizontal=True):
        # 3D Canvas
        with dpg.drawlist(width=WIDTH, height=HEIGHT, tag="canvas_drawlist"):
            dpg.draw_image("dynamic_texture_id", [0, 0], [WIDTH, HEIGHT], uv_min=[0, 0], uv_max=[1, 1])
            dpg.add_draw_node(tag="cube_wireframe")
            
        # Controls panel
        with dpg.group():
            dpg.add_text("Information")
            dpg.add_text(image_loaded_label, color=[0, 246, 7, 255])
            dpg.add_text(f"Dimensions: {width} x {height} x {depth}")
            
            dpg.add_separator()
            dpg.add_text("Slice Position Controls")
            
            dpg.add_slider_float(
                label="Axial (Z)", 
                tag="slider_axial", 
                default_value=0.0, 
                min_value=-half_z, 
                max_value=half_z,
                callback=on_slider_slice_change
            )
            dpg.add_slider_float(
                label="Coronal (Y)", 
                tag="slider_coronal", 
                default_value=0.0, 
                min_value=-half_y, 
                max_value=half_y,
                callback=on_slider_slice_change
            )
            dpg.add_slider_float(
                label="Sagittal (X)", 
                tag="slider_sagittal", 
                default_value=0.0, 
                min_value=-half_x, 
                max_value=half_x,
                callback=on_slider_slice_change
            )
            
            dpg.add_separator()
            dpg.add_text("Camera Settings")
            dpg.add_slider_float(
                label="Focal Length", 
                default_value=focal_length, 
                min_value=100.0, 
                max_value=1000.0, 
                callback=lambda s, a: [globals().update(focal_length=a), update_viewer()]
            )
            dpg.add_slider_float(
                label="Camera Distance", 
                default_value=camera_dist, 
                min_value=200.0, 
                max_value=1000.0, 
                callback=lambda s, a: [globals().update(camera_dist=a), update_viewer()]
            )

with dpg.handler_registry():
    dpg.add_mouse_click_handler(button=0, callback=on_click)
    dpg.add_mouse_drag_handler(button=0, callback=on_drag)

dpg.setup_dearpygui()
dpg.show_viewport()

update_viewer()

dpg.start_dearpygui()
dpg.destroy_context()
