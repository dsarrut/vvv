import logging
from contextlib import ExitStack, contextmanager

import dearpygui.dearpygui as dpg

logger = logging.getLogger(__name__)

# Standard UI toolbar icon glyphs
ICON_SAVE = "\uf0c7"  # Floppy disk
ICON_SAVE_AS = "\ue001"  # Floppy disk with down arrow badge
ICON_ADD = "\uf067"  # Plus: add an item (landmark, profile, isodose level)
ICON_EXPORT = "\uf56e"  # File export: write data (stats, curves) to a file
ICON_FIT = "\uf065"  # Expand: fit a plot to its data
ICON_REFRESH = "\uf021"  # Arrows rotate: compute again (not a reload from disk)
ICON_SNAP = "\uf076"  # Magnet: snap to the image / crosshair

# Short text buttons: toggles showing their current mode (Lin / Log,
# Bar / Line, Ctr) and All / None selections
SMALL_BTN_W = 40


def _ensure_separator_theme():
    """Ensures clean_separator_theme exists, creating it if register_dynamic_themes has not been called."""
    if not dpg.does_item_exist("clean_separator_theme"):
        with dpg.theme(tag="clean_separator_theme"):
            with dpg.theme_component(dpg.mvTable):
                dpg.add_theme_style(dpg.mvStyleVar_CellPadding, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)


def build_horizontal_separator(width=-8, space_below=4, parent=None):
    """A reusable UI component for a clean horizontal separator with margins on both sides and below."""
    _ensure_separator_theme()
    kwargs = {
        "header_row": False,
        "policy": dpg.mvTable_SizingStretchProp,
    }
    if width is not None:
        kwargs["width"] = width
    if parent is not None:
        kwargs["parent"] = parent

    with dpg.table(**kwargs) as table:
        dpg.bind_item_theme(table, "clean_separator_theme")
        dpg.add_table_column()
        with dpg.table_row():
            dpg.add_separator()

    if space_below and space_below > 0:
        if parent is not None:
            dpg.add_spacer(height=space_below, parent=parent)
        else:
            dpg.add_spacer(height=space_below)

    return table


def build_section_title(label, color, sep_width=-8, space_below=4):
    """A reusable UI component for a section title with a horizontal separator."""
    dpg.add_text(label, color=color)
    return build_horizontal_separator(width=sep_width, space_below=space_below)


CARET_OPEN, CARET_FOLDED = "\uf0d7", "\uf0da"


def build_collapsible_title(label, color, arrow_tag, on_toggle, folded=False, sep_width=-8, space_below=4):
    """A section title that folds its panel: a caret (icon text, so the row keeps
    the height of a plain title) and the label, both clickable. The caller
    resizes the panel in on_toggle; set_title_folded updates the caret."""
    with dpg.group(horizontal=True):
        arrow = dpg.add_text(CARET_FOLDED if folded else CARET_OPEN, tag=arrow_tag, color=color)
        if dpg.does_item_exist("icon_font_tag"):
            dpg.bind_item_font(arrow, "icon_font_tag")
        title = dpg.add_text(label, color=color)
    with dpg.item_handler_registry() as handlers:
        dpg.add_item_clicked_handler(callback=lambda *_: on_toggle())
    dpg.bind_item_handler_registry(arrow, handlers)
    dpg.bind_item_handler_registry(title, handlers)
    return build_horizontal_separator(width=sep_width, space_below=space_below)


def set_title_folded(arrow_tag, folded):
    if dpg.does_item_exist(arrow_tag):
        dpg.set_value(arrow_tag, CARET_FOLDED if folded else CARET_OPEN)


DIALOG_BTN_W = 100  # footer buttons: one width (wider only if the label needs it)


def build_dialog_footer(buttons, keys_for=None):
    """Dialog footer: buttons right-aligned, all DIALOG_BTN_W wide, in the
    given order with the main action LAST (on the right): e.g.
    [("Cancel", on_cancel), ("Save", on_save)].

    keys_for: the dialog window tag; Enter then runs the last button and Esc
    the first (Cancel / Close). The key handlers go away with the window."""
    def width(label):
        size = dpg.get_text_size(label) if dpg.is_dearpygui_running() else None
        text_w = size[0] if size else 8 * len(label)
        return max(DIALOG_BTN_W, int(text_w) + 24)

    with dpg.table(
        header_row=False,
        borders_innerH=False,
        borders_innerV=False,
        borders_outerH=False,
        borders_outerV=False,
        width=-1,
    ):
        dpg.add_table_column(width_stretch=True)
        for label, _ in buttons:
            dpg.add_table_column(width_fixed=True, init_width_or_weight=width(label))
        with dpg.table_row():
            dpg.add_spacer(width=1)
            for label, cb in buttons:
                dpg.add_button(label=label, width=width(label), callback=lambda *_, cb=cb: cb())

    if keys_for:
        reg = f"{keys_for}_footer_keys"
        if dpg.does_item_exist(reg):
            dpg.delete_item(reg)

        def on_key(cb):
            def run(*_):
                if not dpg.does_item_exist(keys_for) or not dpg.is_item_shown(keys_for):
                    if dpg.does_item_exist(reg):
                        dpg.delete_item(reg)  # the dialog is gone
                    return
                cb()
            return run

        with dpg.handler_registry(tag=reg):
            dpg.add_key_press_handler(key=dpg.mvKey_Return, callback=on_key(buttons[-1][1]))
            dpg.add_key_press_handler(key=dpg.mvKey_Escape, callback=on_key(buttons[0][1]))


def build_help_button(text, gui, text_fn=None):
    """A reusable help icon button that only appears when Beginner Mode is active.
    text_fn: makes the text from the key map (shortcut_key); it is made again
    when the keys change in Settings (then text is not used)."""
    tag = dpg.generate_uuid()
    btn = dpg.add_button(label="\uf059", width=20, tag=tag, show=getattr(gui, "is_beginner_mode", False))
    if dpg.does_item_exist("icon_font_tag"):
        dpg.bind_item_font(btn, "icon_font_tag")
    if dpg.does_item_exist("help_button_theme"):
        dpg.bind_item_theme(btn, "help_button_theme")
        
    if text_fn:
        text_tag = dpg.generate_uuid()
        build_beginner_tooltip(btn, text_fn(), gui, text_tag=text_tag)
        register_shortcut_hint(gui, text_tag, text_fn, None, kind="fn")
    else:
        build_beginner_tooltip(btn, text, gui)

    if not hasattr(gui, "beginner_tags"):
        gui.beginner_tags = []
    gui.beginner_tags.append(tag)
    return btn


def build_icon_button(
    icon=None,
    label=None,
    callback=None,
    tooltip=None,
    gui=None,
    api=None,
    width=20,
    theme="icon_button_theme",
    tag=None,
    user_data=None,
    enabled=True,
    show=True,
    shortcut=None,
    **kwargs,
):
    """Creates a standardized icon button with optional always-on tooltip (U15.1, U21);
    shortcut: a key map action whose key the tooltip shows (F2)."""
    if icon is None and label is not None:
        icon = label
    if gui is None and api is not None:
        gui = api
    btn_kwargs = {"label": icon, "width": width, "enabled": enabled, "show": show}
    if tag is not None:
        btn_kwargs["tag"] = tag
    if user_data is not None:
        btn_kwargs["user_data"] = user_data
    if callback is not None:
        btn_kwargs["callback"] = callback
    btn_kwargs.update(kwargs)

    btn = dpg.add_button(**btn_kwargs)
    if dpg.does_item_exist("icon_font_tag"):
        dpg.bind_item_font(btn, "icon_font_tag")
    if theme and dpg.does_item_exist(theme):
        dpg.bind_item_theme(btn, theme)
    if tooltip and gui:
        build_tooltip(btn, tooltip, gui, always_on=True, shortcut=shortcut)
    return btn


def build_delete_button(
    label="\uf00d",
    icon=None,
    width=20,
    user_data=None,
    callback=None,
    tooltip="Delete",
    gui=None,
    api=None,
    tag=None,
    show=True,
    enabled=True,
    **kwargs,
):
    """Creates a standardized red icon close/delete button."""
    if icon is not None:
        label = icon
    if gui is None and api is not None:
        gui = api
    return build_icon_button(
        icon=label,
        width=width,
        user_data=user_data,
        callback=callback,
        tooltip=tooltip,
        gui=gui,
        theme="delete_button_theme",
        tag=tag,
        show=show,
        enabled=enabled,
        **kwargs,
    )


REGISTERED_INPUT_FILTER_TAGS = set()

# Room kept right of the filter input (it fills the rest of the row): the two
# 24 px buttons, the "M / N" count and the item spacing (6-8 px).
_FILTER_BTN_W = 24
_FILTER_COUNT_W = 56
_FILTER_RESERVE_W = 2 * (_FILTER_BTN_W + 8) + _FILTER_COUNT_W + 8
_FILTER_COUNT_DY = 2  # (frame height - small text height) / 2 - frame padding


def name_matches(name, filter_text, invert=False):
    """Name filter rule shared by all lists: case-insensitive substring of the
    stripped filter text; invert keeps the non-matching names. An empty filter
    keeps everything, inverted or not."""
    text = (filter_text or "").strip().lower()
    if not text:
        return True
    return (text in (name or "").lower()) != bool(invert)


def set_filter_invert_state(btn_invert_tag, invert):
    """Highlight the invert button while the inverted filter is on."""
    if not dpg.does_item_exist(btn_invert_tag):
        return
    if invert and dpg.does_item_exist("active_nav_button_theme"):
        dpg.bind_item_theme(btn_invert_tag, "active_nav_button_theme")
    else:
        dpg.bind_item_theme(btn_invert_tag, 0)


# Name sort shared by the filtered lists: 0 = insertion order, 1 = A-Z, -1 = Z-A
SORT_ICONS = {0: "\uf0dc", 1: "\uf15d", -1: "\uf15e"}


def next_sort_order(order):
    """Sort button cycle: off -> A-Z -> Z-A -> off."""
    return {0: 1, 1: -1}.get(order, 0)


def sort_by_name(items, order, name=lambda x: x.name):
    """items sorted by case-insensitive name for order 1 / -1, unchanged for 0."""
    if order not in (1, -1):
        return list(items)
    return sorted(items, key=lambda x: (name(x) or "").lower(), reverse=order == -1)


def set_sort_button(btn_sort_tag, order):
    """Show the current sort order on the sort button."""
    if dpg.does_item_exist(btn_sort_tag):
        dpg.configure_item(btn_sort_tag, label=SORT_ICONS.get(order, SORT_ICONS[0]))


def set_filter_count(count_tag, shown, total):
    """'M / N': items listed by the filter / all items."""
    if dpg.does_item_exist(count_tag):
        dpg.set_value(count_tag, f"{shown} / {total}")


def build_name_filter_bar(
    group_tag,
    input_tag,
    btn_clear_tag,
    on_filter_changed,
    on_clear_clicked,
    api=None,
    btn_invert_tag=None,
    on_invert_clicked=None,
    btn_sort_tag=None,
    on_sort_clicked=None,
    sort_tooltip="Sort alphabetically",
    count_tag=None,
    hint="Filter ...",
):
    """Name filter row shared by the ROI, landmark, profile and DVH lists: input
    (fills the row), optional sort, invert (!), clear (X) and an item count (see
    set_filter_count). Match names with name_matches."""
    if input_tag:
        REGISTERED_INPUT_FILTER_TAGS.add(input_tag)

    btn_count = 1  # btn_clear
    if btn_invert_tag and on_invert_clicked:
        btn_count += 1
    if btn_sort_tag and on_sort_clicked:
        btn_count += 1

    reserve_w = btn_count * (_FILTER_BTN_W + 8) + (_FILTER_COUNT_W + 8 if count_tag else 8)

    with dpg.group(horizontal=True, tag=group_tag):
        dpg.add_input_text(
            hint=hint,
            tag=input_tag,
            width=-reserve_w,
            callback=lambda s, a: on_filter_changed(a),
        )
        if api:
            build_beginner_tooltip(
                input_tag,
                "Type to search and filter the list by name.",
                api,
            )

        if btn_sort_tag and on_sort_clicked:
            build_icon_button(
                label=SORT_ICONS[0],
                tag=btn_sort_tag,
                width=_FILTER_BTN_W,
                callback=lambda *_: on_sort_clicked(),
                tooltip=sort_tooltip,
                gui=api,
            )

        if btn_invert_tag and on_invert_clicked:
            btn_invert = dpg.add_button(
                label="!",
                tag=btn_invert_tag,
                width=_FILTER_BTN_W,
                callback=lambda *_: on_invert_clicked(),
            )
            if dpg.does_item_exist("icon_font_tag"):
                dpg.bind_item_font(btn_invert, "icon_font_tag")
            if api:
                build_tooltip(
                    btn_invert,
                    "Invert filter: when active, excludes items containing this text.",
                    api,
                    always_on=True,
                )

        btn_clear = dpg.add_button(
            label="X",
            tag=btn_clear_tag,
            width=_FILTER_BTN_W,
            callback=lambda *_: on_clear_clicked(),
        )
        if api:
            build_tooltip(
                btn_clear,
                "Clears the name filter (and the invert).",
                api,
                always_on=True,
            )
        if count_tag:
            ui_cfg = getattr(api, "ui_cfg", None)
            color = (
                ui_cfg["colors"]["text_dim"]
                if isinstance(ui_cfg, dict)
                else (150, 150, 150)
            )
            # Small font: a spacer (no item spacing) centers it on the input row
            with dpg.group() as count_group:
                dpg.add_spacer(height=_FILTER_COUNT_DY)
                count = dpg.add_text("", tag=count_tag, color=color)
            if dpg.does_item_exist("small_font_tag"):
                dpg.bind_item_font(count, "small_font_tag")
            if not dpg.does_item_exist("filter_count_theme"):
                with dpg.theme(tag="filter_count_theme"):
                    with dpg.theme_component(dpg.mvAll):
                        dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
            dpg.bind_item_theme(count_group, "filter_count_theme")
    return group_tag


def build_batch_action_toolbar(
    tag_prefix,
    on_color_changed=None,
    on_reset_colors=None,
    on_toggle_visible=None,
    on_toggle_names=None,
    on_snap_clicked=None,
    on_delete_clicked=None,
    gui=None,
    api=None,
):
    """Row of batch buttons acting on the listed items of a table (landmarks):
    color, reset colors, show / hide, names, snap, delete (last). Only the
    actions given a callback are built."""
    g_obj = gui or api
    buttons = [
        # (callback, icon, tag suffix, tooltip)
        (on_reset_colors, "\uf043", "reset_colors", "Reset colors to default initial sequence"),
        (on_toggle_visible, "\uf06e", "toggle_visible", "Toggle show/hide listed/filtered items"),
        (on_toggle_names, "\uf02b", "toggle_names", "Toggle name labels for listed/filtered items"),
        (on_snap_clicked, "\uf076", "snap", "Snap all items to nearest voxel grid center"),
    ]
    with dpg.group(horizontal=True, tag=f"{tag_prefix}_batch_toolbar"):
        if on_color_changed:
            dpg.add_color_edit(
                default_value=[255, 255, 255, 255],
                no_inputs=True,
                no_label=True,
                no_alpha=True,
                width=20,
                height=20,
                tag=f"{tag_prefix}_batch_color",
                callback=lambda s, a: on_color_changed(a),
            )
        for cb, icon, suffix, tooltip in buttons:
            if cb:
                build_icon_button(
                    icon=icon,
                    tag=f"{tag_prefix}_batch_{suffix}",
                    callback=lambda *_, cb=cb: cb(),
                    tooltip=tooltip,
                    gui=g_obj,
                )
        if on_delete_clicked:
            build_delete_button(
                label="\uf00d",
                width=20,
                tag=f"{tag_prefix}_batch_delete",
                callback=lambda *_: on_delete_clicked(),
                tooltip="Delete listed/filtered items",
                gui=g_obj,
            )


def get_tooltip_delay(gui, always_on=True):
    """Returns the delay in seconds for tooltips based on beginner mode and settings."""
    target_gui = getattr(gui, "_gui", gui) if hasattr(gui, "_gui") else gui
    is_beg = getattr(target_gui, "is_beginner_mode", False)
    controller = getattr(target_gui, "controller", None)
    cfg = {}
    if controller and hasattr(controller, "settings"):
        cfg = controller.settings.data.get("interaction", {})
    if is_beg:
        return float(cfg.get("tooltip_delay_beginner", 0.1))
    return float(cfg.get("tooltip_delay", 0.6)) if always_on else float(cfg.get("tooltip_delay_beginner", 0.1))


def set_item_show(item, show, gui=None):
    """Sets item visibility and synchronizes any attached tooltip visibility."""
    if dpg.does_item_exist(item):
        dpg.configure_item(item, show=show)
    target_gui = getattr(gui, "_gui", gui) if hasattr(gui, "_gui") else gui
    if target_gui and hasattr(target_gui, "tooltip_parent_map"):
        for tt_tag, p in getattr(target_gui, "tooltip_parent_map", {}).items():
            if p == item and dpg.does_item_exist(tt_tag):
                is_beg = getattr(target_gui, "is_beginner_mode", False)
                is_icon = tt_tag in getattr(target_gui, "icon_tooltip_tags", [])
                tt_show = show if is_icon else (is_beg and show)
                dpg.configure_item(tt_tag, show=tt_show)


# --- Shortcut keys in tooltips and menus (F2) ---
# Virtual actions: a modifier with the key of another action
_SHIFTED_ACTIONS = {"sync_all_wl": "sync_all", "hard_reset": "reset_view"}
_KEY_NAMES = {517: "Page Up", 518: "Page Down", "Up": "↑", "Down": "↓", "Left": "←", "Right": "→"}


def _real_gui(gui):
    return getattr(gui, "_gui", gui) if gui is not None else None


def shortcut_key(gui, action):
    """The key of a shortcut action as shown to the user ('K', 'Shift+S',
    'Cmd+O' / 'Ctrl+O', 'Page Up'), from the current key map; '' if none."""
    g = _real_gui(gui)
    try:
        keys = g.controller.settings.data["shortcuts"]
    except (AttributeError, KeyError, TypeError):
        return ""
    base = _SHIFTED_ACTIONS.get(action, action)
    val = keys.get(base)
    if val in (None, ""):
        return ""
    name = _KEY_NAMES.get(val, str(val))
    if action in _SHIFTED_ACTIONS:
        return f"Shift+{name}"
    if action == "open_file":
        import sys

        return f"{'Cmd' if sys.platform == 'darwin' else 'Ctrl'}+{name}"
    return name


def _with_shortcut(gui, text, action):
    key = shortcut_key(gui, action)
    return f"{text} ({key})" if key else text


def register_shortcut_hint(gui, item, text, action, kind="text"):
    """Keep `item` showing the key of `action` when it changes in Settings:
    kind 'text' (a text item: `text (key)`), 'menu' (a menu item's shortcut)
    or 'fn' (a text item set to text(), a function of the key map)."""
    g = _real_gui(gui)
    if g is None:
        return
    if not isinstance(getattr(g, "shortcut_hints", None), list):
        g.shortcut_hints = []
    # Rebuilt panels (the image list) register again: drop the deleted items
    g.shortcut_hints = [h for h in g.shortcut_hints if dpg.does_item_exist(h[0])]
    g.shortcut_hints.append((item, text, action, kind))


def refresh_shortcut_hints(gui):
    """Show the current keys in the registered tooltips and menus."""
    g = _real_gui(gui)
    hints = getattr(g, "shortcut_hints", None) or []
    for item, text, action, kind in hints:
        if not dpg.does_item_exist(item):
            continue
        if kind == "menu":
            dpg.configure_item(item, shortcut=shortcut_key(g, action))
        elif kind == "fn":
            dpg.set_value(item, text())
        else:
            dpg.set_value(item, _with_shortcut(g, text, action))


def add_menu_shortcut(gui, item, action):
    """Show the key of `action` in a menu item (kept up to date)."""
    if dpg.does_item_exist(item):
        dpg.configure_item(item, shortcut=shortcut_key(gui, action))
    register_shortcut_hint(gui, item, None, action, kind="menu")


def build_tooltip(parent, text, gui, tag=None, text_tag=None, always_on=True, shortcut=None):
    """A reusable tooltip attached to an existing widget.

    If always_on=True (icon buttons, toolbars):
        Visible in both normal and beginner modes with an activation delay:
        - tooltip_delay (default 0.6s) in normal mode
        - tooltip_delay_beginner (default 0.1s) in beginner mode
        Registered in gui.icon_tooltip_tags so toggling beginner mode updates delay.
    If always_on=False (educational tooltips on text/sliders):
        Visible only when Beginner Mode is active (show=is_beginner, delay=0.1s).
        Registered in gui.beginner_tags so toggling beginner mode toggles visibility.
    shortcut: a key map action (e.g. "add_profile"): its key is added, as
    "text (P)", and kept up to date when it is changed in Settings.
    """
    base_text = text
    if shortcut:
        text = _with_shortcut(gui, text, shortcut)
    target_gui = getattr(gui, "_gui", gui) if hasattr(gui, "_gui") else gui
    is_beg = getattr(target_gui, "is_beginner_mode", False)
    delay = get_tooltip_delay(target_gui, always_on=always_on)
    parent_shown = True
    if dpg.does_item_exist(parent):
        parent_shown = bool(dpg.get_item_configuration(parent).get("show", True))
    show_initial = parent_shown if always_on else (is_beg and parent_shown)

    tt_kwargs = {"parent": parent, "show": show_initial, "delay": delay}
    if tag:
        tt_kwargs["tag"] = tag
    try:
        tt_tag = dpg.add_tooltip(**tt_kwargs)
    except (Exception, SystemError):
        return None

    if not hasattr(target_gui, "tooltip_parent_map") or not isinstance(
        target_gui.tooltip_parent_map, dict
    ):
        target_gui.tooltip_parent_map = {}
    target_gui.tooltip_parent_map[tt_tag] = parent

    colors = (
        getattr(target_gui, "ui_cfg", {}).get("colors", {})
        if hasattr(target_gui, "ui_cfg")
        else {}
    )
    dim_col = (
        colors.get("text_dim", [150, 150, 150])
        if isinstance(colors, dict)
        else [150, 150, 150]
    )
    try:
        if text_tag:
            text_item = dpg.add_text(text, parent=tt_tag, color=dim_col, tag=text_tag)
        else:
            text_item = dpg.add_text(text, parent=tt_tag, color=dim_col)
        if shortcut:
            register_shortcut_hint(target_gui, text_item, base_text, shortcut)
    except (Exception, SystemError):
        logger.debug("build_tooltip: ignored error", exc_info=True)

    if always_on:
        if not hasattr(target_gui, "icon_tooltip_tags") or not isinstance(
            target_gui.icon_tooltip_tags, list
        ):
            target_gui.icon_tooltip_tags = []
        target_gui.icon_tooltip_tags.append(tt_tag)
    else:
        if hasattr(target_gui, "beginner_tags") and isinstance(
            target_gui.beginner_tags, list
        ):
            target_gui.beginner_tags.append(tt_tag)
    return tt_tag


def build_beginner_tooltip(parent, text, gui, text_tag=None, always_on=False):
    """A reusable tooltip attached to an existing widget that only appears when Beginner Mode is active."""
    return build_tooltip(
        parent=parent, text=text, gui=gui, text_tag=text_tag, always_on=always_on
    )

# Right margin of the fields in a side panel: the same as build_horizontal_separator
FIELD_RIGHT_MARGIN = 8
# Height below a list that fills its panel (negative child window height):
# the panel bottom margin
LIST_BOTTOM_H = 8
# Label column of the 'label | field' rows (label_row, build_stepped_slider)
LABEL_COL_W = 72

# Fields followed by a beginner-only help button: tag -> (width, width in beginner mode)
_HELP_FIELDS = {}


def _item_gap(gui):
    cfg = getattr(gui, "ui_cfg", None)
    return cfg["layout"].get("sidebar_item_gap", 8) if isinstance(cfg, dict) else 8


def icons_width(n, gui):
    """Room taken by n icon buttons (20 px) and their spacing, after a field."""
    return n * (20 + _item_gap(gui))


def help_aware_width(tag, width, gui, extra=None):
    """Width of a field followed by a help button shown in beginner mode only:
    `width` normally, minus the button (`extra`, default 20 px + spacing) in
    beginner mode. Registered so apply_help_field_widths resizes it when the
    mode is toggled."""
    if extra is None:
        extra = 20 + _item_gap(gui)
    _HELP_FIELDS[tag] = (width, width - extra)
    return _HELP_FIELDS[tag][1] if getattr(gui, "is_beginner_mode", False) else width


def apply_help_field_widths(is_beginner):
    """Beginner mode toggled: resize the fields registered by help_aware_width."""
    for tag, (w, w_beg) in list(_HELP_FIELDS.items()):
        if dpg.does_item_exist(tag):
            dpg.set_item_width(tag, w_beg if is_beginner else w)
        else:
            del _HELP_FIELDS[tag]


@contextmanager
def requirement_banner(tag, need, current_tag, colors):
    """Shown above a tool whose controls are greyed out because the current
    image does not fit it: what the tool needs (one line) and what the current
    image is (current_tag, set by the tool). Items added in the with-block
    (e.g. an action button) go below."""
    with dpg.group(tag=tag):
        # wrap=0: wrap at the panel edge
        dpg.add_text(need, wrap=0, color=colors.get("outdated", [255, 180, 50, 255]))
        dpg.add_text("", tag=current_tag, color=colors.get("text_dim", [150, 150, 150, 255]))
        yield
        dpg.add_spacer(height=4)


_ENABLE_TYPES = (
    "mvButton", "mvCheckbox", "mvCombo", "mvRadioButton", "mvSelectable",
    "mvSliderFloat", "mvSliderInt", "mvDragFloat", "mvDragInt",
    "mvInputFloat", "mvInputInt", "mvInputText", "mvColorEdit",
)


def set_controls_enabled(container, enabled):
    """Enable / grey out every control inside `container` (recursively);
    the beginner help buttons stay usable."""
    if not dpg.does_item_exist(container):
        return
    for slot in (0, 1):
        for child in dpg.get_item_children(container, slot) or []:
            kind = dpg.get_item_type(child).split("::")[-1]
            if kind in _ENABLE_TYPES and not (
                kind == "mvButton" and dpg.get_item_label(child) == "\uf059"
            ):
                dpg.configure_item(child, enabled=enabled)
            set_controls_enabled(child, enabled)


@contextmanager
def click_menu(parent, mousebutton=dpg.mvMouseButton_Left):
    """Like dpg.popup, but the menu opens at the mouse from the first click
    (dpg.popup only shows the window: the first time it opened at the top left
    of the viewport). The items of the with-block are the menu content."""
    menu = dpg.add_window(popup=True, show=False, autosize=True, no_title_bar=True)

    def open_menu():
        x, y = dpg.get_mouse_pos(local=False)
        dpg.configure_item(menu, pos=[int(x), int(y)], show=True)

    with dpg.item_handler_registry() as reg:
        dpg.add_item_clicked_handler(mousebutton, callback=open_menu)
    dpg.bind_item_handler_registry(parent, reg)
    dpg.push_container_stack(menu)
    try:
        yield menu
    finally:
        dpg.pop_container_stack()


@contextmanager
def columns_row(n, width=-FIELD_RIGHT_MARGIN, tag=None):
    """A row of n equal columns (borderless table) ending at `width` (the
    right margin by default): the items of the with-block are its cells, in
    order; give them width=-1 to fill their cell."""
    kw = {"tag": tag} if tag else {}
    with dpg.table(
        header_row=False,
        borders_innerH=False,
        borders_innerV=False,
        borders_outerH=False,
        borders_outerV=False,
        width=width,
        **kw,
    ):
        for _ in range(n):
            dpg.add_table_column(width_stretch=True)
        with dpg.table_row() as row:
            yield row


@contextmanager
def label_row(label, label_w, **text_kwargs):
    """A row 'label | field(s)' whose fields start at label_w, whatever the label
    length: items added in the with-block go in a horizontal group after the
    label. Give the last field width=-FIELD_RIGHT_MARGIN to end on the margin."""
    with dpg.group(horizontal=True, xoffset=label_w):
        dpg.add_text(label, **text_kwargs)
        with dpg.group(horizontal=True) as fields:
            yield fields


def build_stepped_slider(
    label,
    tag,
    callback,
    step_callback,
    min_val=-1e9,
    max_val=1e9,
    default_val=0.0,
    format="%.3f",
    has_checkbox=False,
    check_tag=None,
    check_cb=None,
    has_color=False,
    color_tag=None,
    color_cb=None,
    color_default=(255, 0, 0, 255),
    help_text=None,
    gui=None,
    label_width=None,
    user_data=None,
    use_slider=False,
    label_col=None,
):
    """A reusable UI component for a slider with + and - step buttons.

    label_col: the label takes a column of this width (see label_row) and the
    field + buttons end on FIELD_RIGHT_MARGIN; the checkbox / color, if any,
    go after the label."""

    # --- INTERNAL STATE (Hidden closure) ---
    # Python closures capture dictionaries by reference. This means both buttons
    # share this exact multiplier state, and it doesn't pollute the global scope!
    state = {"mult": 1.0}

    def _change_speed(sender, app_data, user_data):
        # Update the hidden multiplier when the user clicks a popup item
        state["mult"] = user_data

    def _internal_step_wrapper(sender, app_data, user_data):
        # Scale the direction by the currently selected multiplier
        external_user_data = {
            "tag": user_data["tag"],
            "dir": user_data["base_dir"] * state["mult"],
        }

        # Fire the original caller's callback with the scaled value
        if step_callback:
            step_callback(sender, app_data, external_user_data)

    # ---------------------------------------

    gap = _item_gap(gui)
    with ExitStack() as row:
        row.enter_context(dpg.group(horizontal=True, xoffset=label_col or 0))
        if label_col:
            dpg.add_text(label.strip())
            row.enter_context(dpg.group(horizontal=True))
        if has_checkbox:
            dpg.add_checkbox(tag=check_tag or 0, enabled=False, callback=check_cb)  # type: ignore

        if has_color:
            dpg.add_color_edit(
                default_value=color_default,
                tag=color_tag or 0,
                callback=color_cb,  # type: ignore
                no_inputs=True,
                no_label=True,
                no_alpha=True,
                width=20,
                height=20,
            )

        if label_col:
            pass
        elif label_width:
            lw = label_width
            if has_color:
                spacing = gui.ui_cfg["layout"].get("sidebar_item_gap", 8) if (gui and hasattr(gui, "ui_cfg")) else 8
                lw -= (20 + spacing)
            t = dpg.add_input_text(default_value=label.strip(), width=lw, readonly=True)
            if dpg.does_item_exist("sleek_readonly_theme"):
                dpg.bind_item_theme(t, "sleek_readonly_theme")
        else:
            dpg.add_text(label)

        is_beg = getattr(gui, "is_beginner_mode", False) if gui else False
        if label_col:  # the 2 step buttons, then the right margin
            field_w = -(2 * (20 + gap) + FIELD_RIGHT_MARGIN)
            if help_text and gui:  # + spacer (2 px) and help button
                field_w = help_aware_width(tag, field_w, gui, extra=2 + 20 + 2 * gap)
        else:
            field_w = -100 if (help_text and is_beg) else -60

        # 1. The Slider
        if use_slider:
            dpg.add_slider_float(
                tag=tag,
                width=field_w,
                format=format,
                min_value=min_val,
                max_value=max_val,
                default_value=default_val,
                enabled=not has_checkbox,
                callback=callback,
                user_data=user_data,
            )
        else:
            dpg.add_drag_float(
                tag=tag,
                width=field_w,
                format=format,
                speed=1.0,
                min_value=min_val,
                max_value=max_val,
                default_value=default_val,
                enabled=not has_checkbox,
                callback=callback,
                user_data=user_data,
            )

        # 2. The Minus Button
        btn_minus = f"btn_{tag}_minus"
        dpg.add_button(
            label="-",
            width=20,
            tag=btn_minus,
            user_data={"tag": tag, "base_dir": -1},
            enabled=not has_checkbox,
            callback=_internal_step_wrapper,
        )
        if dpg.does_item_exist("icon_button_theme"):
            dpg.bind_item_theme(btn_minus, "icon_button_theme")

        # Hidden Right-Click Menu for Minus
        with click_menu(btn_minus, mousebutton=dpg.mvMouseButton_Right):
            dpg.add_text("Step Speed", color=[150, 150, 150])
            dpg.add_separator()
            dpg.add_selectable(
                label="Slow (0.1x)", user_data=0.1, callback=_change_speed
            )
            dpg.add_selectable(
                label="Normal (1.0x)", user_data=1.0, callback=_change_speed
            )
            dpg.add_selectable(
                label="Fast (10.0x)", user_data=10.0, callback=_change_speed
            )
            
        # 3. The Plus Button
        btn_plus = f"btn_{tag}_plus"
        dpg.add_button(
            label="+",
            width=20,
            tag=btn_plus,
            user_data={"tag": tag, "base_dir": 1},
            enabled=not has_checkbox,
            callback=_internal_step_wrapper,
        )
        if dpg.does_item_exist("icon_button_theme"):
            dpg.bind_item_theme(btn_plus, "icon_button_theme")

        # Hidden Right-Click Menu for Plus
        with click_menu(btn_plus, mousebutton=dpg.mvMouseButton_Right):
            dpg.add_text("Step Speed", color=[150, 150, 150])
            dpg.add_separator()
            dpg.add_selectable(
                label="Slow (0.1x)", user_data=0.1, callback=_change_speed
            )
            dpg.add_selectable(
                label="Normal (1.0x)", user_data=1.0, callback=_change_speed
            )
            dpg.add_selectable(
                label="Fast (10.0x)", user_data=10.0, callback=_change_speed
            )
            
        if help_text and gui:
            sp_tag = dpg.add_spacer(width=2, show=is_beg)
            build_help_button(help_text, gui)
            if not hasattr(gui, "beginner_tags"):
                gui.beginner_tags = []
            gui.beginner_tags.append(sp_tag)


def build_renamable_input(tag, default_value, callback, user_data=None, width=180, tooltip=None, gui=None, on_enter=True):
    """
    Creates a renamable text input widget that triggers `callback` on enter or on focus loss (deactivation).
    Passes the current text value of the input field to `callback` as its second argument (app_data).
    """
    if tag:
        REGISTERED_INPUT_FILTER_TAGS.add(tag)
    def _wrapped_callback(sender, app_data, u):
        val = dpg.get_value(sender)
        callback(sender, val, u)

    input_id = dpg.add_input_text(
        tag=tag,
        default_value=default_value,
        width=width,
        on_enter=on_enter,
        callback=_wrapped_callback,
        user_data=user_data,
    )

    handler_tag = f"handler_deact_{tag}"
    if not dpg.does_item_exist(handler_tag):
        with dpg.item_handler_registry(tag=handler_tag):
            dpg.add_item_deactivated_after_edit_handler(
                callback=lambda s, a, u: _wrapped_callback(input_id, None, u),
                user_data=user_data
            )
    dpg.bind_item_handler_registry(input_id, handler_tag)

    if tooltip and gui:
        build_beginner_tooltip(input_id, tooltip, gui)

    return input_id


def normalize_rgba_to_int(color, default_alpha=255):
    """
    Normalizes an input RGBA/RGB color sequence to a list of integers in range [0, 255].
    Handles float components in [0.0, 1.0], int components in [0, 255], and short RGB lists.
    """
    if not color:
        return [0, 0, 0, default_alpha]

    color_list = list(color)
    is_float = any(isinstance(c, float) for c in color_list) and all(c <= 1.0 for c in color_list) and any(c > 0.0 for c in color_list)

    if is_float:
        res = [int(c * 255.0) for c in color_list[:4]]
    else:
        res = [np_clip(c) for c in color_list[:4]]

    # Ensure 4 channels (RGBA)
    if len(res) == 3:
        res.append(default_alpha)

    return [max(0, min(255, c)) for c in res]


def np_clip(val):
    try:
        return int(val)
    except Exception:
        return 0

