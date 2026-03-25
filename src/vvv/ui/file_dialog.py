import os
import sys
import subprocess


def open_file_dialog(
    title="Open",
    multiple=False,
    is_workspace=False,
    is_directory=False,
    extensions=None,
):
    """
    Native File Dialog wrapper.
    Vendored and adapted from 'crossfiledialog' by maikelwever
    https://github.com/maikelwever/crossfiledialog
    Supports selecting single or multiple files, directories, and custom extensions.
    """

    # Determine the starting folder
    start_dir = os.getcwd()
    if not os.path.exists(start_dir):
        start_dir = os.path.expanduser("~")

    # --- FILTER LOGIC ---
    if extensions:
        clean_exts = [e.lstrip(".") for e in extensions]
        mac_exts = '{"' + '", "'.join(clean_exts) + '"}'
        space_exts = " ".join([f"*.{e}" for e in clean_exts])
        semi_exts = ";".join([f"*.{e}" for e in clean_exts])

        zenity_filter = f"--file-filter=Supported Files | {space_exts}"
        kdialog_filter = f"{space_exts} | Supported Files"
        win_filter = f"Supported Files|{semi_exts}|All Files (*.*)|*.*"

    elif is_workspace:
        mac_exts = '{"vvw", "json"}'
        zenity_filter = "--file-filter=Workspaces | *.vvw *.json"
        kdialog_filter = "*.vvw *.json | Workspaces"
        win_filter = "Workspaces|*.vvw;*.json|All Files (*.*)|*.*"

    else:
        mac_exts = '{"nii", "gz", "mhd", "mha", "nrrd", "dcm", "tif", "tiff", "png", "jpg", "jpeg"}'
        zenity_filter = "--file-filter=Medical Images | *.nii *.nii.gz *.mhd *.mha *.nrrd *.dcm *.tif *.tiff *.png *.jpg *.jpeg"
        kdialog_filter = (
            "*.nii *.nii.gz *.mhd *.mha *.nrrd *.dcm *.tif *.png *.jpg | Medical Images"
        )
        win_filter = "Medical Images|*.nii;*.nii.gz;*.mhd;*.mha;*.nrrd;*.dcm;*.tif;*.tiff;*.png;*.jpg;*.jpeg|All Files (*.*)|*.*"
    # --------------------

    if sys.platform == "darwin":  # macOS
        script = (
            f"tell application (path to frontmost application as text)\n"
            f"  activate\n"
            f"  try\n"
            f'    set defaultLoc to POSIX file "{start_dir}" as alias\n'
        )

        if is_directory:
            script += (
                f'    set theFile to choose folder with prompt "{title}" default location defaultLoc\n'
                f"    return POSIX path of theFile\n"
            )
        else:
            script += f"    set allowedExts to {mac_exts}\n"
            if multiple:
                script += (
                    f'    set theFiles to choose file with prompt "{title}" default location defaultLoc of type allowedExts with multiple selections allowed\n'
                    f"    set pathList to {{}}\n"
                    f"    repeat with aFile in theFiles\n"
                    f"      set end of pathList to POSIX path of aFile\n"
                    f"    end repeat\n"
                    f"    set AppleScript's text item delimiters to linefeed\n"
                    f"    return pathList as text\n"
                )
            else:
                script += (
                    f'    set theFile to choose file with prompt "{title}" default location defaultLoc of type allowedExts\n'
                    f"    return POSIX path of theFile\n"
                )

        script += f"  end try\n" f"end tell"

        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True
            )
            path = result.stdout.strip()
            if not path:
                return [] if multiple else None
            return path.splitlines() if multiple else path
        except Exception:
            return [] if multiple else None

    elif sys.platform == "linux":  # Linux
        if not start_dir.endswith(os.sep):
            start_dir += os.sep

        try:
            cmd = [
                "zenity",
                "--file-selection",
                f"--title={title}",
                f"--filename={start_dir}",
            ]
            if is_directory:
                cmd.append("--directory")
            else:
                cmd.append(zenity_filter)
                cmd.append("--file-filter=All Files | *")

            if multiple:
                cmd.append("--multiple")
                cmd.append("--separator=\n")

            result = subprocess.run(cmd, capture_output=True, text=True)
            path = result.stdout.strip()
            if path:
                return path.splitlines() if multiple else path
        except FileNotFoundError:
            try:
                if is_directory:
                    cmd = [
                        "kdialog",
                        "--getexistingdirectory",
                        start_dir,
                        f"--title={title}",
                    ]
                else:
                    cmd = [
                        "kdialog",
                        "--getopenfilename",
                        start_dir,
                        kdialog_filter,
                        f"--title={title}",
                    ]
                if multiple:
                    cmd.append("--multiple")
                    cmd.append("--separate-output")

                result = subprocess.run(cmd, capture_output=True, text=True)
                path = result.stdout.strip()
                if path:
                    return path.splitlines() if multiple else path
            except FileNotFoundError:
                return [] if multiple else None

    elif sys.platform == "win32":  # Windows
        if is_directory:
            script = (
                f"Add-Type -AssemblyName System.Windows.Forms;"
                f"$f = New-Object System.Windows.Forms.FolderBrowserDialog;"
                f"$f.Description = '{title}';"
                f"$f.SelectedPath = '{start_dir}';"
                f"$form = New-Object System.Windows.Forms.Form;"
                f"$form.TopMost = $true;"
                f"if ($f.ShowDialog($form) -eq 'OK') {{ $f.SelectedPath }}"
            )
        else:
            mult_str = "$true" if multiple else "$false"
            out_str = (
                "$f.FileNames -join [Environment]::NewLine"
                if multiple
                else "$f.FileName"
            )

            script = (
                f"Add-Type -AssemblyName System.Windows.Forms;"
                f"$f = New-Object System.Windows.Forms.OpenFileDialog;"
                f"$f.Title = '{title}';"
                f"$f.InitialDirectory = '{start_dir}';"
                f"$f.Filter = '{win_filter}';"
                f"$f.Multiselect = {mult_str};"
                f"$f.ShowHelp = $true;"
                f"$form = New-Object System.Windows.Forms.Form;"
                f"$form.TopMost = $true;"
                f"if ($f.ShowDialog($form) -eq 'OK') {{ {out_str} }}"
            )

        try:
            result = subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                text=True,
                creationflags=0x08000000,
            )
            path = result.stdout.strip()
            if not path:
                return [] if multiple else None
            return path.splitlines() if multiple else path
        except Exception:
            return [] if multiple else None

    return [] if multiple else None


def save_file_dialog(title="Save File", default_name="workspace.vvw"):
    """
    Native 'Save As' File Dialog wrapper.
    """
    start_dir = os.getcwd()
    if not os.path.exists(start_dir):
        start_dir = os.path.expanduser("~")

    # Extract the extension from the default name dynamically
    ext_parts = default_name.split(".")
    if len(ext_parts) > 1:
        ext = ext_parts[-1]
        if default_name.endswith(".nii.gz") or default_name.endswith(".tar.gz"):
            ext = ext_parts[-2] + "." + ext_parts[-1]
    else:
        ext = "*"

    filter_name = "VVV Workspace" if ext == "vvw" else "File"

    if sys.platform == "darwin":  # macOS
        script = (
            f"tell application (path to frontmost application as text)\n"
            f"  activate\n"
            f"  try\n"
            f'    set defaultLoc to POSIX file "{start_dir}" as alias\n'
            f'    set theFile to choose file name with prompt "{title}" default name "{default_name}" default location defaultLoc\n'
            f"    return POSIX path of theFile\n"
            f"  end try\n"
            f"end tell"
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True
            )
            path = result.stdout.strip()
            return path if path else None
        except Exception:
            return None

    elif sys.platform == "linux":  # Linux
        if not start_dir.endswith(os.sep):
            start_dir += os.sep

        full_default = os.path.join(start_dir, default_name)
        try:
            # Zenity
            cmd = [
                "zenity",
                "--file-selection",
                "--save",
                "--confirm-overwrite",
                f"--title={title}",
                f"--filename={full_default}",
                f"--file-filter={filter_name} | *.{ext}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            path = result.stdout.strip()
            return path if path else None
        except FileNotFoundError:
            try:
                # Kdialog
                cmd = [
                    "kdialog",
                    "--getsavefilename",
                    full_default,
                    f"*.{ext} | {filter_name}",
                    f"--title={title}",
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                path = result.stdout.strip()
                return path if path else None
            except FileNotFoundError:
                return None

    elif sys.platform == "win32":  # Windows
        script = (
            f"Add-Type -AssemblyName System.Windows.Forms;"
            f"$f = New-Object System.Windows.Forms.SaveFileDialog;"
            f"$f.Title = '{title}';"
            f"$f.InitialDirectory = '{start_dir}';"
            f"$f.FileName = '{default_name}';"
            f"$f.Filter = '{filter_name} (*.{ext})|*.{ext}|All Files (*.*)|*.*';"
            f"$form = New-Object System.Windows.Forms.Form;"
            f"$form.TopMost = $true;"
            f"if ($f.ShowDialog($form) -eq 'OK') {{ $f.FileName }}"
        )
        try:
            result = subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                text=True,
                creationflags=0x08000000,
            )
            path = result.stdout.strip()
            return path if path else None
        except Exception:
            return None

    return None
