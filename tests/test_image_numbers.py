from types import SimpleNamespace

from vvv.core.controller import Controller


def _add(c, vid, name):
    c.view_states[vid] = SimpleNamespace()
    c.volumes[vid] = SimpleNamespace(name=name, _is_outdated=False)


def test_numbers_are_stable_and_not_reused():
    c = Controller()
    for vid, name in (("10", "a"), ("11", "b"), ("12", "c")):
        _add(c, vid, name)
    assert [c.image_number(v) for v in ("10", "11", "12")] == [1, 2, 3]

    del c.view_states["10"], c.volumes["10"]  # close the first image
    assert [c.image_number(v) for v in ("11", "12")] == [2, 3]  # no renumbering
    _add(c, "13", "d")
    assert c.image_number("13") == 4  # 1 is not reused

    for v in ("11", "12", "13"):
        del c.view_states[v], c.volumes[v]
    _add(c, "14", "e")
    assert c.image_number("14") == 1  # restarts once every image is closed


def test_renumber_follows_the_workspace_order():
    c = Controller()
    _add(c, "1", "open_before")
    c.image_number("1")
    for vid in ("5", "3", "4"):  # loaded in parallel: any order
        _add(c, vid, vid)
        c.image_number(vid)
    c.renumber_images(["3", "4", "5"])
    assert [c.image_number(v) for v in ("1", "3", "4", "5")] == [1, 2, 3, 4]


def test_display_name_and_plain_name():
    c = Controller()
    _add(c, "7", "(3) ct.nii.gz")  # a legacy name still carrying a prefix
    c.volumes["7"]._is_outdated = True
    assert c.get_image_name("7") == "ct.nii.gz"
    assert c.get_image_display_name("7") == ("(1) ct.nii.gz *", True)
