#!/bin/bash
# Regenerates the user doc screenshots (macOS): bash scripts/doc_screenshots/run_all.sh [WxH]
# Run from the vvv root; the scenes use the local data/ folder (not in git).
# Each scene runs vvv in its own process with a temporary HOME: a copy of the
# settings (same look), the other home entries linked (for "~/..." paths in
# workspaces), so the real settings, history and recent files are not changed.
set -u
D=$(cd "$(dirname "$0")" && pwd)
O=${OUT:-user_docs/images}
U=$D/setups
Z=${1:-1280x1100}
H=$(mktemp -d)
trap 'rm -rf "$H"' EXIT
mkdir -p "$H/.config/vvv"
[ -f "$HOME/.config/vvv/.vv_settings" ] && cp "$HOME/.config/vvv/.vv_settings" "$H/.config/vvv/"
for e in "$HOME"/* ; do ln -s "$e" "$H/$(basename "$e")"; done
T=$H/tmp.png

run() { HOME=$H timeout 150 python "$D/shoot.py" "$1" --size "$Z" "${@:2}" 2>&1 | grep -E "^/|^$O|Error|Traceback|rror:" | sed "s|nav=.*||"; }

run $O/doc_02_main_layout.png --crop image_list_container:$O/doc_02_images_list.png --crop image_info_group:$O/doc_02_active_viewer.png -- data/ct.nii.gz data/spect.nii.gz
run $O/doc_03_cli_fusion.png -- "data/ct.nii.gz,data/spect.nii.gz,hot,0.6" + data/Sphere_1.nii.gz
run $O/doc_04_workspace_layout.png -- data/dose.vvw
run $O/doc_05_sync_layout.png --tab tab_sync --crop win:top_panel:$O/doc_05_sync_panel.png -- data/sync_fusion.vvw
run $O/doc_06_fusion_layout.png --tab tab_fusion --crop win:top_panel:$O/doc_06_fusion_panel.png -- data/sync_fusion.vvw
run $O/doc_07_intensity_layout.png --tab intensity_plugin --wait 12 --setup $U/ct_wl.py --crop win:top_panel:$O/doc_07_intensity_panel.png -- data/ct.nii.gz
run $O/doc_08_roi_layout.png --tab roi_plugin -- data/rois.vvw
run $O/doc_09_threshold_layout.png --tab threshold_plugin -- data/threshold.vvw
run $O/doc_10_profiles_layout.png --tab profile_plugin -- data/profiles.vvw
run $O/doc_11_landmarks_layout.png --tab landmark_plugin -- data/landmarks.vvw
run $O/doc_12_registration_layout.png --tab registration_plugin --wait 6 --setup $U/reg.py -- data/reg3.vvw
run $O/doc_13_mip_layout.png --tab mip_plugin -- data/mip.vvw
ZOOM=2.5 run $O/doc_14_dvf_layout.png --tab dvf --setup $U/fit.py -- data/dvf.vvw
run $O/doc_15_dicom_browser.png --wait 4 --setup $U/dicom.py --
run $O/doc_16_dose_layout.png --tab dose_plugin -- data/dose.vvw
run $O/doc_16_dvh_window.png --tab dose_plugin --wait 10 --setup $U/dvh.py -- data/dose.vvw
run $O/doc_17_sidecar.png --tab registration_plugin --setup $U/v3.py -- data/chris_t1.nii.gz data/chris_t2.nii.gz
run $T --tab tab_images --setup $U/v3.py --crop image_info_group:$O/doc_17_unit.png -- data/chris_t1.nii.gz data/chris_t2.nii.gz
