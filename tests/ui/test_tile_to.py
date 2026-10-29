"""TileTo: a window placed in a cell of a grid on its head, by an action
and by dropping it on the layout picker.

Two heads: HEADLESS-2 is head 1 at 0,0 with the toolbar, HEADLESS-1 the
second at 1280,0.
"""

import os
import subprocess
import time

import pytest

from lib.compositor import CompositorManager
from lib.input_driver import InputDriver, _find_test_pointer
from lib.ipc_client import FluxlandIPC

SETTLE = 0.5
THUMB = 120  # snapLayoutPickerSize

INIT = [
    "session.output.HEADLESS-1.mode: 1024x768",
    "session.output.HEADLESS-1.position: 1280,0",
    "session.output.HEADLESS-2.position: 0,0",
    "session.screen0.toolbar.onhead: 1",
    "session.screen0.toolbar.placement: BottomCenter",
    "session.screen0.opaqueMove: true",
    "session.screen0.edgeSnapThreshold: 0",
    "session.screen0.workspacewarping: false",
    "session.screen0.enableWindowSnapping: true",
    "session.screen0.snapLayoutPicker: true",
    f"session.screen0.snapLayoutPickerSize: {THUMB}",
    "session.screen0.snapLayouts: 0,0,50,100 50,0,50,100",
]

KEYS = "OnTitlebar Move1 :StartMoving\n"


@pytest.fixture(scope="module")
def comp():
    mgr = CompositorManager()
    mgr.start(config_set="default", headless=True, outputs=2,
              init_extra=INIT)
    with open(os.path.join(mgr.config_dir, "keys"), "w") as f:
        f.write(KEYS)
    client = FluxlandIPC(socket_path=mgr.socket_path)
    client.command("Reconfigure")
    client.close()
    time.sleep(SETTLE)
    yield mgr
    mgr.stop()


@pytest.fixture
def ipc(comp):
    client = FluxlandIPC(socket_path=comp.socket_path)
    yield client
    try:
        client.command("CloseAllWindows")
        time.sleep(0.3)
    except Exception:
        pass
    client.close()


def open_on_head1(ipc, title):
    ipc.command(f"Exec foot --app-id {title}")
    deadline = time.monotonic() + 4
    win = None
    while time.monotonic() < deadline:
        win = ipc.get_window_by_app_id(title)
        if win and win["width"] > 0:
            break
        time.sleep(0.1)
    else:
        raise TimeoutError(title)
    ipc.command("SetHead 1", window=win["id"])
    time.sleep(SETTLE)
    ipc.command("MoveTo 100 100", window=win["id"])
    time.sleep(SETTLE)
    return ipc.get_window_by_app_id(title)


def usable(ipc, name):
    return {o["name"]: o for o in ipc.get_outputs()}[name]["usable"]


def cell(area, x0, x1, y0=0, y1=1000):
    """The frame of a cell in permille of an area, by the same rounding."""
    left = area["x"] + area["width"] * x0 // 1000
    right = area["x"] + area["width"] * x1 // 1000
    top = area["y"] + area["height"] * y0 // 1000
    bottom = area["y"] + area["height"] * y1 // 1000
    return left, top, right - left, bottom - top


STEP = 40  # a terminal's size comes in character cells


class Box(tuple):
    """A frame; equal to another within what a terminal's cells allow:
    the top left exactly, the size within a cell."""

    def __eq__(self, other):
        return (abs(self[0] - other[0]) <= 2 and abs(self[1] - other[1]) <= 2
                and abs(self[2] - other[2]) <= STEP
                and abs(self[3] - other[3]) <= STEP)

    def __ne__(self, other):
        return not self == other

    __hash__ = None


def frame_tuple(win):
    f = win["frame"]
    return Box((f["x"], f["y"], f["width"], f["height"]))


def test_middle_third_and_back(ipc):
    area = usable(ipc, "HEADLESS-2")
    win = open_on_head1(ipc, "Third")
    before = frame_tuple(win)

    ipc.command("TileTo 3 1 2 1", window=win["id"])
    time.sleep(SETTLE)
    assert frame_tuple(ipc.get_window_by_app_id("Third")) == cell(
        area, 333, 666)

    # The same cell again puts it back
    ipc.command("TileTo 3 1 2 1", window=win["id"])
    time.sleep(SETTLE)
    after = frame_tuple(ipc.get_window_by_app_id("Third"))
    assert after[:2] == tuple(before[:2])


def test_top_row_spans_columns(ipc):
    area = usable(ipc, "HEADLESS-2")
    win = open_on_head1(ipc, "TopRow")
    ipc.command("TileTo 2 2 1 1 2 1", window=win["id"])
    time.sleep(SETTLE)
    assert frame_tuple(ipc.get_window_by_app_id("TopRow")) == cell(
        area, 0, 1000, 0, 500)


def test_invalid_cells_do_nothing(ipc):
    win = open_on_head1(ipc, "Invalid")
    before = frame_tuple(win)
    for bad in ("TileTo 3 1 4 1", "TileTo 0 1 1 1", "TileTo 2 2 2 2 2 1",
                "TileTo 2 2 1"):
        try:
            ipc.command(bad, window=win["id"])
        except Exception:
            pass  # refused
    time.sleep(SETTLE)
    assert frame_tuple(ipc.get_window_by_app_id("Invalid")) == before


def test_maximized_then_tiled_restores_to_the_original(ipc):
    area = usable(ipc, "HEADLESS-2")
    win = open_on_head1(ipc, "MaxTile")
    before = frame_tuple(win)
    ipc.command("Maximize", window=win["id"])
    time.sleep(SETTLE)
    ipc.command("TileTo 2 1 2 1", window=win["id"])
    time.sleep(SETTLE)
    now = ipc.get_window_by_app_id("MaxTile")
    assert now["maximized"] is False
    assert frame_tuple(now) == cell(area, 500, 1000)
    ipc.command("TileTo 2 1 2 1", window=win["id"])
    time.sleep(SETTLE)
    assert frame_tuple(ipc.get_window_by_app_id("MaxTile"))[:2] == tuple(before[:2])


def test_tile_on_the_second_head(ipc):
    area = usable(ipc, "HEADLESS-1")
    win = open_on_head1(ipc, "Head2")
    ipc.command("SetHead 2", window=win["id"])
    time.sleep(SETTLE)
    ipc.command("TileTo 3 1 3 1", window=win["id"])
    time.sleep(SETTLE)
    assert frame_tuple(ipc.get_window_by_app_id("Head2")) == cell(
        area, 666, 1000)


pointer = pytest.mark.skipif(
    not _find_test_pointer(), reason="fluxland-test-pointer is not built")


def drag_through(comp, start, waypoints):
    """Press at start, move through each waypoint, release at the last."""
    args = [_find_test_pointer(), "move", str(start[0]), str(start[1]),
            "press", "1", "sleep", "50"]
    for x, y in waypoints:
        args += ["to", str(x), str(y), "sleep", "100"]
    args += ["release", "1"]
    subprocess.run(args, check=True, capture_output=True,
                   env=comp.client_env)


def picker_cell_centre(area, index):
    """The centre of cell `index` (0 left, 1 right) of the one layout."""
    panel_w = THUMB + 20
    panel_x = area["x"] + (area["width"] - panel_w) // 2
    thumb_x = panel_x + 10
    thumb_y = area["y"] + 10 + 4 + 10  # zone threshold, gap, padding
    thumb_h = THUMB * 10 // 16
    return thumb_x + THUMB // 4 + index * THUMB // 2, thumb_y + thumb_h // 2


@pointer
def test_drop_on_a_picker_cell_tiles(comp, ipc):
    area = usable(ipc, "HEADLESS-2")
    win = open_on_head1(ipc, "PickLeft")
    f = win["frame"]
    start = (f["x"] + f["width"] // 2, f["y"] + 8)
    mid = area["x"] + area["width"] // 2
    cx, cy = picker_cell_centre(area, 0)

    drag_through(comp, start, [(mid, 100), (mid, 2), (mid, 8), (cx, cy)])
    time.sleep(SETTLE)

    now = ipc.get_window_by_app_id("PickLeft")
    assert now["maximized"] is False
    assert frame_tuple(now) == cell(area, 0, 500)

    # The right cell, from there
    f = now["frame"]
    start = (f["x"] + f["width"] // 2, f["y"] + 8)
    cx, cy = picker_cell_centre(area, 1)
    drag_through(comp, start, [(mid, 100), (mid, 2), (mid, 8), (cx, cy)])
    time.sleep(SETTLE)
    assert frame_tuple(ipc.get_window_by_app_id("PickLeft")) == cell(
        area, 500, 1000)


@pointer
def test_drop_on_the_edge_still_maximizes(comp, ipc):
    area = usable(ipc, "HEADLESS-2")
    win = open_on_head1(ipc, "EdgeMax")
    f = win["frame"]
    start = (f["x"] + f["width"] // 2, f["y"] + 8)
    mid = area["x"] + area["width"] // 2

    drag_through(comp, start, [(mid, 100), (mid, 2), (mid, 3)])
    time.sleep(SETTLE)
    assert ipc.get_window_by_app_id("EdgeMax")["maximized"] is True


@pointer
def test_leaving_the_picker_drops_normally(comp, ipc):
    area = usable(ipc, "HEADLESS-2")
    win = open_on_head1(ipc, "Away")
    f = win["frame"]
    start = (f["x"] + f["width"] // 2, f["y"] + 8)
    mid = area["x"] + area["width"] // 2
    cx, cy = picker_cell_centre(area, 0)

    # Onto a cell, then away from the panel into the middle of the head
    drag_through(comp, start, [(mid, 100), (mid, 2), (mid, 8), (cx, cy),
                               (mid, 400), (mid, 420)])
    time.sleep(SETTLE)
    now = ipc.get_window_by_app_id("Away")
    assert now["maximized"] is False
    assert frame_tuple(now) != cell(area, 0, 500)
